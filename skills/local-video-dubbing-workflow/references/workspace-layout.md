# 工作区结构

默认工作区为 `D:\Codes\VideoDubbingWorkspace`。

- `app_template/`
  包含从当前仓库抽取的核心运行快照，不包含 Streamlit UI。
- `config/`
  `config.example.yaml` 为脱敏模板，`config.local.yaml` 为本地运行配置。
- `glossary/`
  `custom_terms.json` 为运行时权威词表。
- `runs/<run-id>/`
  单次任务目录，包含 `app/`、`logs/`、`review/`、`state.json`、`events.jsonl`。
- `current/`
  保存最近一次 run 的索引文件。
- `scripts/`
  从 skill 复制进去的便捷入口脚本。

运行快照按 run 目录复制，因此旧代码中的固定 `output/` 会自然落到当前 run 的 `app/output/`，不需要重写整条 pipeline 的输出路径。
