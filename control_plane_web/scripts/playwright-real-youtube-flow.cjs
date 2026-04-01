const fs = require('fs');
const path = require('path');
const net = require('net');
const { spawn } = require('child_process');
const { randomUUID } = require('crypto');
const { chromium } = require('playwright');

const repoRoot = path.resolve(__dirname, '..', '..');
const webRoot = path.resolve(__dirname, '..');
const repoPython = path.join(repoRoot, '.venv', 'Scripts', 'python.exe');
const runtimeDir = path.join(repoRoot, 'runtime', `playwright_e2e_${randomUUID()}`);
const backendLogPath = path.join(runtimeDir, 'backend.log');
const frontendLogPath = path.join(runtimeDir, 'frontend.log');
const screenshotPath = path.join(runtimeDir, 'playwright-real-youtube.png');
const youtubeUrl = 'https://www.youtube.com/watch?v=jYUZAF3ePFE';

const childProcesses = [];
let shuttingDown = false;

function ensureDir(targetPath) {
  fs.mkdirSync(targetPath, { recursive: true });
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

function pipeOutput(child, logPath) {
  const stream = fs.createWriteStream(logPath, { flags: 'a' });
  if (child.stdout) {
    child.stdout.pipe(stream);
  }
  if (child.stderr) {
    child.stderr.pipe(stream);
  }
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

function getBackendPythonCommand() {
  return fs.existsSync(repoPython) ? repoPython : 'python';
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

async function waitForProjectStatus(page, expectedStatuses, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const statusText = await page.getByTestId('overview-project-status').textContent();
    if (statusText && expectedStatuses.some((expected) => statusText.includes(expected))) {
      return statusText;
    }
    const startError = page.getByTestId('overview-start-run-error');
    if (await startError.count()) {
      const errorText = await startError.textContent();
      if (errorText) {
        throw new Error(`启动运行失败: ${errorText}`);
      }
    }
    await page.waitForTimeout(1000);
  }
  throw new Error(`等待项目状态超时，期望状态: ${expectedStatuses.join(', ')}`);
}

async function waitForDownloadedVideo(outputDir, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (fs.existsSync(outputDir)) {
      const files = fs.readdirSync(outputDir);
      const videoFile = files.find((file) => ['.mp4', '.webm', '.mkv', '.mov'].includes(path.extname(file).toLowerCase()));
      if (videoFile) {
        return path.join(outputDir, videoFile);
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`等待下载产物超时: ${outputDir}`);
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
    VIDEOLINGO_CONFIG_PATH: path.join(repoRoot, 'config.yaml'),
    PYTHONIOENCODING: 'utf-8',
  };
  const frontendEnv = {
    ...process.env,
    VITE_API_BASE_URL: apiBaseUrl,
  };

  const backend = spawnProcess(
    getBackendPythonCommand(),
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
    await page.getByTestId('create-project-name').fill('Playwright 真实 YouTube 验证');
    await page.getByTestId('create-project-source').fill(youtubeUrl);
    await page.getByTestId('create-project-submit').click();
    await page.waitForURL(/\/projects\/\d+\/overview$/);

    await page.getByTestId('overview-start-run').click();
    const statusText = await waitForProjectStatus(page, ['处理中', '待字幕审阅', '失败'], 90000);
    const downloadedVideo = await waitForDownloadedVideo(path.join(runtimeDir, 'workspace', 'output'), 90000);

    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`真实 YouTube Playwright 验证完成。运行目录: ${runtimeDir}`);
    console.log(`项目状态: ${statusText}`);
    console.log(`下载产物: ${downloadedVideo}`);
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
