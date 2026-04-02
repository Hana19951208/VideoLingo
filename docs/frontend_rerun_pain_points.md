# 前端重跑与日志可视化痛点记录

## 现状问题
- 当前前端只暴露 `b. 翻译并生成字幕` 与 `c. 配音` 两个大阶段按钮，用户无法直接触发具体子步骤。
- 后端大量步骤依赖“产物已存在则跳过”的机制，但前端没有展示哪些文件会导致跳过，也没有清理入口。
- 当前页面没有统一日志面板，失败时只能依赖 `logs/task_runner_errors.log` 或手动翻 `output/log`、`output/gpt_log`。
- 配置入口偏散且缺少摘要视图，运行前很难快速确认 `whisper.runtime`、`demucs`、`tts_method` 等关键配置。
- 阶段内部依赖关系不可见，用户不知道“只重跑翻译”会影响哪些后续文件，也不知道哪些上游产物必须保留。

## 阶段核心处理流程梳理

为了实现细粒度的子步骤控制，我们需要对现有 `b` 和 `c` 阶段的后端脚本及其输入输出进行明确映射。

### 阶段 b：翻译并生成字幕 (Subtitle Generation)
| 步骤 ID | 核心处理脚本 | 主要输入 | 主要输出 | 关键任务 |
| :--- | :--- | :--- | :--- | :--- |
| b1_asr | `core/_2_asr.py` | `input/video.mp4` | `_2_cleaned_chunks.csv` | 视频转音频、人声分离、WhisperX 词级转录并保存。 |
| b2_nlp | `core/_3_1_split_nlp.py` | `b1_asr` 产物 | `_3_1_split_by_nlp.csv` | 使用 SpaCy 根据语法/标点进行初步句子分段。 |
| b3_meaning | `core/_3_2_split_meaning.py` | `b2_nlp` 产物 | `_3_2_split_by_meaning.csv` | 使用 LLM 语义切分长句，对齐原始转录时间戳。 |
| b4_summary | `core/_4_1_summarize.py` | `b3_meaning` 产物 | `_4_1_terminology.json` | 提取视频核心关键词、生成内容摘要供翻译参考。 |
| b5_trans | `core/_4_2_translate.py` | `b3_meaning`, `b4_summary`| `_4_2_translate_lines.csv` | 执行 LLM “直译-意译-校对”翻译流水线。 |
| b6_split | `core/_5_split_sub.py` | `b5_trans` 产物 | `_5_split_sub.csv` | 针对字幕显示长度限制，对过长翻译行进行二次裁切。 |
| b7_gen_srt | `core/_6_gen_sub.py` | `b6_split` 产物 | `bilingual_subtitles.srt` | 格式化时间戳，生成标准的双语字幕 (SRT/VTT)。 |
| b8_merge_sub | `core/_7_sub_into_vid.py` | `video.mp4`, `b7_gen_srt` | `output_video_with_subs.mp4` | 使用 ffmpeg 将双语字幕“烧录”进视频原片。 |

### 阶段 c：配音 (Dubbing)
| 步骤 ID | 核心处理脚本 | 主要输入 | 主要输出 | 关键任务 |
| :--- | :--- | :--- | :--- | :--- |
| c1_task | `core/_8_1_audio_task.py` & `_8_2_dub_chunks.py` | `b6_split` 产物 | `audio_tasks.json` | 预估语速时长，拆分/合并配音片段，生成音频分包任务。 |
| c2_refer | `core/_9_refer_audio.py` | `video.mp4` | `output/audio/reference/` | 提取原视频角色的干声，作为 TTS 仿声克隆音色库。 |
| c3_select | `core/_9_1_select_reference_audio.py` | `c2_refer` 产物 | 音色文件映射 | 为每个分段音频任务匹配最合适的克隆参考音色。 |
| c4_gen_audio | `core/_10_gen_audio.py` | `c1_task`, `c3_select` | `output/audio/chunks/` | 调用 TTS 服务生成单条配音片段音频。 |
| c5_merge_audio| `core/_11_merge_audio.py` | `c4_gen_audio` 产物 | `final_audio.mp3` | 音频拼接对齐，处理语速延展适配，生成完整音轨。 |
| c6_synth | `core/_12_dub_to_vid.py` | `video.mp4`, `c5_merge_audio`| `output_video_dubbed.mp4` | 混音背景音乐，合成最终带双语字幕和配音的视频。 |

## 后端与前端责任拆分
- 后端已经具备一部分“删产物后重跑”的基础能力，因为多个步骤使用了 `check_file_exists(...)`。
- 后端缺的是统一的工作流注册、显式步骤依赖、统一清理规则，以及可被前端消费的步骤元数据。
- 前端缺的是把这些能力产品化：子步骤列表、单步执行、从某步重跑、日志查看、跳过原因可见化。
- 结论：这不是单纯的前端问题，也不是后端完全不支持，而是“后端能力零散 + 前端几乎没有暴露”。

## 本次临时补丁范围
- 仅覆盖 `b` 与 `c` 两个阶段，不重写整站工作流。
- 为 `b/c` 增加步骤注册表，显式列出步骤 id、依赖、产物文件和预览文件。
- 在前端提供：
  - `运行本步`
  - `从本步重跑`
  - `清理本步及下游`
  - `查看日志`
- 在页面上直接展示已有产物、缺失依赖、日志文件和中间产物预览。
- 在侧边栏补一个只读的关键配置摘要，先解决“运行前看不清配置”的问题。

## 后续完整重构方向
- 把工作流注册表上升为统一任务编排层，覆盖下载、字幕、配音、导出全流程。
- 增加结构化运行记录：每次运行的开始时间、结束时间、状态、失败步骤、关键配置快照。
- 增加统一日志中心，把 `task_runner`、LLM 调用日志、中间产物、错误栈整合到同一入口。
- 增加阶段依赖图和产物树，让用户能理解“某个步骤重跑会影响什么”。
- 重构配置中心，按“下载 / 字幕 / ASR / TTS / 输出”分组，而不是把所有配置混在侧栏里。
- 如果后续要支持多人协作或远程部署，再考虑把本地文件状态提升为后端 API 和任务队列。
