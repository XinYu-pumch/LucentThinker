# Research Quality Benchmark

Research tasks across energy, health, software, business, careers, automotive, history and trade.

| Edition | Dataset | Download |
| --- | --- | --- |
| [English](2026-11-02/en/README.md) | 5 tasks, 15 responses | [ZIP](2026-11-02/lucentthinker-benchmark-en.zip) |
| [中文](2026-11-02/zh/README.md) | 10 tasks, 30 responses | [ZIP](2026-11-02/lucentthinker-benchmark-zh.zip) |

Each edition includes the HTML report, PNG/SVG chart, questions, complete responses, scoring evidence and file hashes. Extract the ZIP and open `index.html` to read offline. The Chinese edition also includes the same-topic language comparison.

Author-organized, non-blind Astra evaluation. One response per system per task. Updated 3 November 2026.

<details>
<summary>Publishing and rebuilding</summary>

For GitHub Pages, choose **GitHub Actions** in Settings → Pages, then run the **Publish benchmarks** workflow. After successful deployment, the [report site](https://xinyu-pumch.github.io/LucentThinker/) links to both editions. GitHub's file viewer displays HTML source.

For sharing, use the relevant chart and report link, with the GitHub dataset for questions, answers and evidence. The ZIPs can also be attached to a GitHub Release.

To rebuild the reports from the source records and response files, run the following command from the repository root.

```sh
uv run --python 3.12 --with matplotlib==3.11.2 python benchmarks/build.py
```

Set `BENCHMARK_CJK_FONT` to a Chinese font file on platforms without the default macOS font. Rendering depends on the font and graphics-library versions. The builder verifies response hashes and generates both ZIPs.

</details>
