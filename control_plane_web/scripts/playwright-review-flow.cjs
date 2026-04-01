const fs = require('fs');
const path = require('path');
const net = require('net');
const { spawn } = require('child_process');
const { randomUUID } = require('crypto');
const { chromium } = require('playwright');

const repoRoot = path.resolve(__dirname, '..', '..');
const webRoot = path.resolve(__dirname, '..');
const runtimeDir = path.join(repoRoot, 'runtime', `playwright_e2e_${randomUUID()}`);
const backendLogPath = path.join(runtimeDir, 'backend.log');
const frontendLogPath = path.join(runtimeDir, 'frontend.log');
const screenshotPath = path.join(runtimeDir, 'playwright-review-flow.png');
const inputVideoPath = path.join(runtimeDir, 'fixture-input.mp4');

const childProcesses = [];
let shuttingDown = false;

function ensureDir(targetPath) {
  fs.mkdirSync(targetPath, { recursive: true });
}

function writeFixtureInput() {
  fs.writeFileSync(inputVideoPath, Buffer.from('fixture-video'));
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      server.close((closeError) => {
        if (closeError) {
          reject(closeError);
          return;
        }
        resolve(address.port);
      });
    });
  });
}

async function waitForHttpOk(url, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch (error) {
      void error;
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`等待服务超时: ${url}`);
}

function pipeOutput(child, logPath) {
  const stream = fs.createWriteStream(logPath, { flags: 'a' });
  if (child.stdout) {
    child.stdout.pipe(stream);
  }
  if (child.stderr) {
    child.stderr.pipe(stream);
  }
}

function normalizeEnv(env) {
  const normalized = {};
  for (const [key, value] of Object.entries(env)) {
    if (value === undefined || value === null) {
      continue;
    }
    normalized[key] = String(value);
  }
  return normalized;
}

function spawnProcess(command, args, options) {
  const child = spawn(command, args, {
    cwd: options.cwd,
    env: normalizeEnv(options.env),
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
  });
  pipeOutput(child, options.logPath);
  childProcesses.push(child);
  return child;
}

function terminateChild(child) {
  if (!child || child.exitCode !== null || child.killed) {
    return Promise.resolve();
  }
  if (process.platform === 'win32') {
    return new Promise((resolve) => {
      const killer = spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore', shell: false });
      killer.on('exit', () => resolve());
      killer.on('error', () => resolve());
    });
  }
  child.kill('SIGTERM');
  return new Promise((resolve) => {
    child.on('exit', () => resolve());
    setTimeout(() => {
      if (child.exitCode === null) {
        child.kill('SIGKILL');
      }
      resolve();
    }, 2000);
  });
}

async function cleanupChildren() {
  await Promise.allSettled(childProcesses.map((child) => terminateChild(child)));
}

async function run() {
  ensureDir(runtimeDir);
  ensureDir(path.join(runtimeDir, 'workspace'));
  ensureDir(path.join(runtimeDir, 'history'));
  ensureDir(path.join(runtimeDir, 'logs'));
  writeFixtureInput();

  const backendPort = await getFreePort();
  const frontendPort = await getFreePort();
  const apiBaseUrl = `http://127.0.0.1:${backendPort}`;
  const webBaseUrl = `http://127.0.0.1:${frontendPort}`;

  const backendEnv = {
    ...process.env,
    VIDEOLINGO_CONTROL_DB: path.join(runtimeDir, 'control_plane.db'),
    VIDEOLINGO_ACTIVE_WORKSPACE: path.join(runtimeDir, 'workspace'),
    VIDEOLINGO_HISTORY_ROOT: path.join(runtimeDir, 'history'),
    VIDEOLINGO_LOG_ROOT: path.join(runtimeDir, 'logs'),
    VIDEOLINGO_CONTROL_PLANE_WORKFLOW_MODE: 'fixture',
    VIDEOLINGO_CONTROL_PLANE_STEP_DELAY_MS: '80',
  };
  const frontendEnv = {
    ...process.env,
    VITE_API_BASE_URL: apiBaseUrl,
  };

  const backend = spawnProcess(
    'python',
    ['-m', 'uvicorn', 'control_plane.app:create_app', '--factory', '--host', '127.0.0.1', '--port', String(backendPort)],
    {
      cwd: repoRoot,
      env: backendEnv,
      logPath: backendLogPath,
    },
  );
  const frontendCommand =
    process.platform === 'win32'
      ? { command: process.env.ComSpec || 'cmd.exe', args: ['/d', '/s', '/c', 'npm run dev -- --host 127.0.0.1 --port ' + String(frontendPort)] }
      : { command: 'npm', args: ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(frontendPort)] };
  const frontend = spawnProcess(frontendCommand.command, frontendCommand.args, {
    cwd: webRoot,
    env: frontendEnv,
    logPath: frontendLogPath,
  });

  backend.on('exit', (code) => {
    if (!shuttingDown && code !== 0) {
      console.error(`后端进程提前退出，日志见: ${backendLogPath}`);
    }
  });
  frontend.on('exit', (code) => {
    if (!shuttingDown && code !== 0) {
      console.error(`前端进程提前退出，日志见: ${frontendLogPath}`);
    }
  });

  await waitForHttpOk(`${apiBaseUrl}/projects`, 30000);
  await waitForHttpOk(webBaseUrl, 30000);

  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.goto(webBaseUrl, { waitUntil: 'networkidle' });
    await page.getByRole('link', { name: '新建项目' }).click();
    await page.getByTestId('create-project-name').fill('Playwright 审阅阻塞验证');
    await page.getByTestId('create-project-source').fill(inputVideoPath);
    await page.getByTestId('create-project-submit').click();
    await page.waitForURL(/\/projects\/\d+\/overview$/);

    await page.getByTestId('overview-start-run').click();
    await page.getByTestId('workspace-project-status').waitFor({ state: 'visible' });
    await page.getByTestId('workspace-project-status').waitFor({ state: 'attached' });
    await page.waitForFunction(
      () => document.querySelector('[data-testid="workspace-project-status"]')?.textContent?.includes('待字幕审阅'),
      undefined,
      { timeout: 30000 },
    );

    await page.getByRole('link', { name: '字幕审阅' }).click();
    const subtitleInput = page.getByTestId('subtitle-review-target-1');
    await subtitleInput.fill('Playwright 已保存字幕');
    await page.getByTestId('subtitle-review-save').click();
    await page.waitForTimeout(300);
    await page.reload({ waitUntil: 'networkidle' });
    await page.getByTestId('subtitle-review-target-1').waitFor({ state: 'visible' });
    const savedValue = await page.getByTestId('subtitle-review-target-1').inputValue();
    if (savedValue !== 'Playwright 已保存字幕') {
      throw new Error(`字幕保存校验失败，当前值: ${savedValue}`);
    }

    await page.getByTestId('subtitle-review-approve').click();
    await page.waitForFunction(
      () => document.querySelector('[data-testid="workspace-project-status"]')?.textContent?.includes('已完成'),
      undefined,
      { timeout: 30000 },
    );

    await page.getByRole('link', { name: '流程' }).click();
    await page.getByTestId('workflow-node-status-c6_merge_video').waitFor({ state: 'visible' });
    await page.waitForFunction(
      () => document.querySelector('[data-testid="workflow-node-status-c6_merge_video"]')?.textContent?.includes('已完成'),
      undefined,
      { timeout: 30000 },
    );

    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`Playwright 验证通过。运行目录: ${runtimeDir}`);
    console.log(`截图: ${screenshotPath}`);
  } finally {
    await browser.close();
  }
}

run()
  .catch(async (error) => {
    console.error(error);
    console.error(`运行目录: ${runtimeDir}`);
    console.error(`后端日志: ${backendLogPath}`);
    console.error(`前端日志: ${frontendLogPath}`);
    process.exitCode = 1;
  })
  .finally(async () => {
    shuttingDown = true;
    await cleanupChildren();
  });
