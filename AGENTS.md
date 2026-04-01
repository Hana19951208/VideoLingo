# VideoLingo 工作准则

这份文件只保留长期有效的项目行为准则、边界和验证约定。项目当前进度、已完成项、下一步优先级统一维护在 [docs/current-progress.md](D:/Codes/VideoLingo/docs/current-progress.md)。

## 一、基础行为
1. 所有回复、文档、代码注释必须使用简体中文。
2. 优先遵循系统与开发者指令，其次遵循本文件。
3. 复杂任务先规划再实现；遇到 bug 先定位根因，再做修复。
4. 完成前必须做新鲜验证，不能只凭推断声称“已完成”。
5. 不要擅自回退用户已有改动，尤其是文档草稿、原型目录、配置试验和运行期数据。
6. 单次任务包含较多代码改动时，完成一轮可验证的阶段性结果后要及时做一次小而聚焦的 git 提交，保持版本可追踪；提交前必须先跑与本轮改动直接相关的验证。

## 二、项目边界
1. 当前主线是“新前端控制面 + 后端控制面”重构，但阶段重点通常优先放在后端控制面接缝与真实流程打通。
2. 前端在不阻塞主流程时只做最小改动，不做大规模视觉重构。
3. 新控制面与旧 Streamlit 允许并存，不要强行一次性替换旧系统。
4. 第一阶段默认仍是“单活动项目”，不支持多项目并发执行。

## 三、前端改动原则
1. 仅做阻塞问题修复、接口接线、最小可验证页面骨架维护。
2. 不主动做大规模 UI 重构、视觉润色、组件体系重建。
3. 如果后端接口或真实流程没打通，优先修后端，不要在前端堆占位逻辑掩盖问题。
4. 关键页面应优先补稳定选择器和最小自动化覆盖，方便后续 Playwright 回归。

## 四、Playwright 验证准则
1. 涉及以下场景时，优先补一次本地 Playwright 验证，而不是只跑 Python 单元测试：
   - 新建项目
   - 启动运行
   - 字幕审阅保存
   - 配置页面保存
   - 任何跨前后端的关键流程
2. Playwright 验证必须尽量基于真实本地服务，不要只测纯静态页面。
3. 启动本地临时服务时，优先使用动态空闲端口，避免与用户本机已有服务冲突。
4. 临时运行目录统一放在 `runtime/playwright_e2e_*`。
5. 验证结束后必须停止临时前后端进程，避免污染用户环境。

## 五、YouTube 测试约定
1. 默认测试视频使用 `https://www.youtube.com/watch?v=jYUZAF3ePFE`。
2. YouTube cookies 文件默认位于项目根目录的 [www.youtube.com_cookies.txt](D:/Codes/VideoLingo/www.youtube.com_cookies.txt)。
3. 做远程视频下载验证时，优先使用这个 cookies 文件，不要假设无 cookies 也能稳定下载。
4. 如果下载失败，先输出后端真实错误，再决定是否补 `cookies-from-browser` 或其他兜底策略。

## 六、启动与验证约定
### 后端控制面
```powershell
python -m control_plane
```

### 前端工作台
```powershell
cd D:\Codes\VideoLingo\control_plane_web
npm run dev
```

### 本地 Playwright 验证
```powershell
cd D:\Codes\VideoLingo\control_plane_web
npm run test:e2e
```

## 七、仓库整洁要求
1. 忽略运行期文件和原型产物，当前约定忽略：
   - `control_plane.db`
   - `control_plane_web/*.tsbuildinfo`
   - `stitch_videolingo/`
2. 不要把本地运行目录、浏览器截图、临时日志默认提交。
3. 如果为了调试临时安装或生成新文件，结束前要确认它们是否应该进入仓库。
