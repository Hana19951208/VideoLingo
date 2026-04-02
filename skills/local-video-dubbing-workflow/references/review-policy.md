# b4 审校策略

默认在 `b4` 之后停下，由 agent 读取：

- `output/log/translation_results_for_subtitles.xlsx`
- `output/log/translation_results_remerged.xlsx`
- `glossary/custom_terms.json`

优先处理：

- 专有名词、品牌名、模型名、产品名
- 音似误识别，如 `haiku -> heyku`、`claude -> cloud`
- 会影响后续烧录字幕和配音的一致性问题

自动修正规则仅覆盖高置信短术语：

- 源文本很短
- 与词表中的标准术语近似匹配
- 最佳匹配显著优于次优匹配

命中后：

- 同步修正 split 与 remerged 两份产物
- 将原错误形式作为 alias 写回 `custom_terms.json`
- 生成 `review/b4_corrections.json` 与 `review/glossary_updates.json`

较长句子中的上下文级错译先标记为候选，后续可以扩展更强的 agent 审校逻辑。
