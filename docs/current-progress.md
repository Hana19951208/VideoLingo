# 当前进度

这份文档记录项目的阶段性进展、已完成能力、当前真实状态和下一步优先级。长期行为准则见 [AGENTS.md](D:/Codes/VideoLingo/AGENTS.md)。

## 一、本轮已完成
### 1. 后端执行接缝
- 新增 [control_plane/execution.py](D:/Codes/VideoLingo/control_plane/execution.py)，引入控制面专用 `ControlPlaneRunManager`。
- `POST /projects/{id}/runs` 现在会在准备源文件后启动后台线程，按工作流真实顺序推进 `Run` 与 `NodeExecution`。
- `Project.status` / `Run.status` 已接入 `processing -> review_required -> processing -> completed|failed` 流转。
- `NodeExecution.status` 已接入 `pending|running|completed|failed|skipped`，并同步更新时间、日志摘录、错误摘要和进度。
- 控制面启动时会收敛孤儿 `processing` / `review_required` 运行，避免重启后被活动运行锁死。

### 2. 字幕审阅阻塞与节点动作
- `b5_generate_subtitles` 完成后会强制进入 `review_required`，后台线程停止，不再自动执行 `b6` 及后续音频节点。
- `approve_subtitles_and_continue` 只允许在 `review_required` 下调用，恢复后从 `b6_burn_video` 继续到结束。
- `/runs/{id}/actions` 已补齐：
  - `run_step`
  - `rerun_step`
  - `rerun_from_step`
  - `cleanup_step_and_downstream`
  - `approve_subtitles_and_continue`
- 节点重置和清理范围已统一为“整条 Run 下游”语义。

### 3. 前端最小接线
- [control_plane_web/src/app/router.tsx](D:/Codes/VideoLingo/control_plane_web/src/app/router.tsx) 已补：
  - 运行中与 `review_required` 状态的轮询刷新
  - 流程页节点动作按钮
  - 字幕审阅页保存与继续按钮稳定选择器
  - 概览页、工作区状态和创建项目表单稳定选择器
- 流程页、字幕审阅页、日志与产物页在运行中会继续轮询，便于观察阻塞切换和后续完成状态。

### 4. 测试与 E2E 基建
- 新增后端测试 [tests/test_control_plane_run_execution.py](D:/Codes/VideoLingo/tests/test_control_plane_run_execution.py)，覆盖真实执行状态、`review_required` 阻塞、恢复执行、节点动作语义和孤儿运行收敛。
- 远程 YouTube 下载策略已调整为“匿名下载优先，命中明确认证/风控提示后再回退 cookies”，并自动启用本机 `node` 作为 `yt-dlp` JavaScript runtime。
- YouTube 风控失败现在会返回清晰的 400 错误，不再以 500 模糊报错。
- 新增前端测试 [workflow-actions.test.tsx](D:/Codes/VideoLingo/control_plane_web/src/__tests__/workflow-actions.test.tsx)，覆盖：
  - 流程页动作请求
  - 字幕审阅保存与继续
  - 工作区轮询刷新到 `review_required`
  - 概览页展示真实启动失败原因
- 新增 Playwright 脚本 [playwright-review-flow.cjs](D:/Codes/VideoLingo/control_plane_web/scripts/playwright-review-flow.cjs)，使用真实本地前后端、动态端口、`runtime/playwright_e2e_*` 目录和 fixture workflow 模式完成审阅阻塞主流程验证。
- 新增真实 YouTube Playwright 脚本 [playwright-real-youtube-flow.cjs](D:/Codes/VideoLingo/control_plane_web/scripts/playwright-real-youtube-flow.cjs)，直接使用 `https://www.youtube.com/watch?v=jYUZAF3ePFE` 验证真实远程下载链路与错误展示。

## 二、当前真实状态
1. YouTube cookies 下载链路已经接到控制面，优先使用配置中的 `youtube.cookies_path`，为空时回退到仓库根目录 cookies 文件。
2. 新控制面已经不再只是“预建节点列表”，而是可以作为后端真实执行状态源。
3. 前端工作台仍保持最小骨架策略，没有做视觉重构。
4. `/runs/{id}/stream` 仍是快照式接口，本轮没有升级成持续推送。
5. 归档/恢复、历史工作区装载和更完整的产物浏览仍未闭环。

## 三、建议的下一步优先级
1. 继续补活动工作区与归档工作区的装载、恢复、索引闭环。
2. 评估是否需要把 `/runs/{id}/stream` 升级成持续推送，或者维持轮询方案。
3. 在保持最小改动前提下继续补前端日志、产物和失败恢复体验。

## 四、最近验证命令
```powershell
python -m pytest tests/test_control_plane_run_execution.py -q
python -m pytest tests/test_control_plane_source_ingest.py tests/test_control_plane_api.py tests/test_control_plane_runtime_api.py -q
cd D:\Codes\VideoLingo\control_plane_web
npm test -- src/__tests__/workflow-actions.test.tsx
npm run test:e2e
npm run test:e2e:youtube
```
