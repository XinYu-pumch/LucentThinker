# Research benchmarks

[English edition](2026-11-02/en/README.md) · [中文版](2026-11-02/zh/README.md)

The 2 November 2026 release contains two self-contained editions of the same assessment.

| Edition | Scope | Report package |
| --- | --- | --- |
| English | Q1–4 and Q10, five English prompts, 15 answers | [Download ZIP](2026-11-02/lucentthinker-benchmark-en.zip) |
| 中文 | 全部十题，30 份回答，含同题中英分析 | [下载 ZIP](2026-11-02/lucentthinker-benchmark-zh.zip) |

Each edition includes a chart in PNG and SVG, the full HTML report, prompts, unchanged response Markdown, scores and quoted evidence, the method, and SHA-256 hashes. Extract the ZIP and open `index.html` to read offline. GitHub's HTML file viewer displays source code.

## Publish the report site

This repository includes a manually triggered **Publish benchmarks** GitHub Actions workflow. After pushing the commit, choose **GitHub Actions** as the Pages source in repository Settings → Pages, then run the workflow from the Actions tab. The workflow publishes this directory.

After a successful deployment, the report landing page will be available at [the project Pages URL](https://xinyu-pumch.github.io/LucentThinker/). The English and Chinese reports will be under `/2026-11-02/en/` and `/2026-11-02/zh/`. Deployment status is shown in the workflow run. The checked-in files and offline ZIPs are usable before deployment.

## Sharing

For Reddit, attach the English PNG, describe the five-prompt result and the author-organized non-blind method, and link to the English HTML report once deployed. Include the GitHub dataset link for prompts, full answers and scoring. ZIPs are an additional offline download. Disclose that you develop LucentThinker and keep the sample size and citation caveat with the chart.

On GitHub, use the short README chart and dataset links as the entry point. Release assets can also host the two ZIPs when creating a tagged release. The chart's scores concern answer quality. The author's low-cost usage claim is separate from the evaluation.

## Rebuild

The source directory preserves the pre-publication assessment and translated review prose. The Chinese response directory holds the 30 byte-identical input answers. `build.py` verifies their recorded hashes and creates both editions and deterministic ZIPs. Its dependencies are matplotlib and beautifulsoup4. Use an isolated environment for these documentation tools.

```sh
uv run --python 3.12 --with matplotlib==3.11.2 --with beautifulsoup4==4.15.0 python benchmarks/build.py
```

On platforms without the default macOS Chinese font, set `BENCHMARK_CJK_FONT` to a Chinese font file. Chart rendering can vary with the installed font and graphics-library versions. Dimension scores, source response hashes and package manifests can be checked independently of the image renderer.

The method documents the Q4 repurchase-rationale correction. All original dimension scores are retained. Source and answer files also retain claims classified as incorrect or unverified by the review.
