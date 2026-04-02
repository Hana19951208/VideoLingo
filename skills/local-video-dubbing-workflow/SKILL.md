---
name: local-video-dubbing-workflow
description: Run a local end-to-end video translation and dubbing workflow using a reusable external workspace, with support for YouTube download or local media input, b4 subtitle review checkpoints, run-id based resume, glossary import, and glossary-assisted ASR/translation. Use when Codex needs to bootstrap or operate the long-running local workflow for subtitle generation, dubbing, b4 review correction, or recovery after a failed run.
---

# Local Video Dubbing Workflow

## Overview

Use this skill to operate the long-running local translation and dubbing workflow through a dedicated external workspace instead of the Streamlit UI. The workflow reuses the repository's core pipeline, pauses at `b4` for review, persists run state, and allows a later agent to resume by `run-id`.

## Workflow

1. Bootstrap the external workspace if it does not exist yet.
   Run [bootstrap_workspace.py](./scripts/bootstrap_workspace.py) with an optional `--terms-source`.
   Read [workspace-layout.md](./references/workspace-layout.md) if you need the directory layout.
2. Start a new run.
   Use [run_pipeline.py](./scripts/run_pipeline.py) with either `--input-url` or `--input-file`.
   The runner stops with exit code `10` after `b4`.
3. Review `b4` outputs.
   Use [review_b4_outputs.py](./scripts/review_b4_outputs.py) with `--run-id`.
   Read [review-policy.md](./references/review-policy.md) for the correction rules.
4. Resume the run.
   Call [run_pipeline.py](./scripts/run_pipeline.py) with `--resume <run-id>`.

## Operating Rules

- Prefer the external workspace over editing the original repository outputs.
- Treat `glossary/custom_terms.json` as the runtime source of truth.
- Import `custom_terms.xlsx` through [import_terms_from_xlsx.py](./scripts/import_terms_from_xlsx.py) when new glossary content arrives.
- Expect `DEEPSEEK_API_KEY` to come from the environment. Do not write real secrets into tracked files.
- When a run stops for review or fails, inspect `state.json`, `events.jsonl`, and the run-local logs before deciding whether to resume or rerun from a step.

## Key Paths

- Skill scripts: `skills/local-video-dubbing-workflow/scripts`
- External workspace default: `D:\Codes\VideoDubbingWorkspace`
- Run state: `runs/<run-id>/state.json`
- Review outputs: `runs/<run-id>/review/`
