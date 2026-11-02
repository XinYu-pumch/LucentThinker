# Evaluation method

## Sample and provenance

This author-organized review compares one saved answer per system and prompt. The English edition contains Q1–4 and Q10, five English prompts and 15 responses. The Chinese edition contains all ten prompts and 30 responses, including one same-topic Chinese/English pair. Grouping refers to prompt language. GPT's Q2 response is in Chinese and is preserved verbatim.

LucentThinker used deepseek-flash, MiroThinker used its paid deep mode, and GPT Deep Research used the web configuration reported by the author as gpt6pro + deepsearch. Model identity, search counts, runtime and comparable budgets cannot be independently established from the saved answers. This evaluates answer quality. Speed and cost were not measured in this benchmark.

Three Astra sub-reviewers handled Q1–4, Q5–8 and Q9–10. Reviewers knew system identities. GPT answers were initially reviewed, then calibrated against the previous LucentThinker/MiroThinker judgments and source material. The lead review checked selected high-impact calculations, source claims, quotations and line numbers. This was a non-blind LLM-assisted evaluation commissioned by LucentThinker's author, without an independent repeated rating of every answer.

LucentThinker/MiroThinker scores from 30 October 2026 were retained when GPT was added. The publication date is 2 November 2026. Question cutoffs are 29 October for Q1–8 and 30 October for Q9–10. Save dates do not change those cutoffs.

## Scoring

| Dimension | Weight |
| --- | --- |
| Requirement coverage | 20% |
| Facts and calculations | 25% |
| Evidence and traceability | 20% |
| Reasoning and boundaries | 20% |
| Decision usefulness | 10% |
| Organization and clarity | 5% |

Each dimension uses 0–5 with half-point steps. Anchors are 0 missing or severely contrary to the task, 1 serious defects, 2 partial delivery with material gaps, 3 basically usable with major verification needed, 4 strong with localized issues, and 5 comprehensive and verifiable. Total = sum(dimension score / 5 × weight). The headline is the unweighted mean across the edition's prompts, on a 0–100 scale, rounded half-up to one decimal. It is an assessment score, not a percentage of correct answers.

Factual mistakes primarily affect factual scoring and missing sources primarily affect evidence scoring. Independently missing calculations or deliverables also affect the relevant dimensions. Unverified claims remain distinguished from confirmed errors. Weight sensitivity is provided, including exclusion of evidence with the remaining dimensions renormalized.

The author confirmed that GPT's original web answers also had no citations. Identifiable author/year or book references still received appropriate traceability credit. This limitation is reflected in the scores. All systems, including LucentThinker, have substantive weaknesses documented in the question-level review. The sample does not establish general performance across tasks or repeated runs.

## Publication and audit

Saved responses are copied byte-for-byte. SHA-256 hashes, original filenames, quotations and line numbers are retained in scores.json. English review prose is translated from the existing assessment. Original quotations stay unchanged, with translations alongside Chinese quotations. Q10's language-comparison commentary is omitted from the English edition while its factual findings and scores are preserved.

One editorial correction fixes the direction of a repurchase-number error in Q4's LucentThinker factual rationale. The response used roughly $7 billion, while the cited review evidence gives $4.494 billion. The earlier rationale had these reversed. The public rationale now agrees with its evidence. All dimension scores are retained. The dated source directory preserves the pre-publication assessment.

The HTML report works offline after extracting the package. Original response Markdown and external sources are linked from it. External source availability depends on the source website. Source checks include access limitations and unverified items. No new fact-checking or scoring was performed for this language split.
