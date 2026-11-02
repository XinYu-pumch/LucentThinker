# LucentThinker

[中文](README.zh-CN.md)

**Fast, source-backed research at low cost.**

A local personal research assistant powered by DeepSeek. LucentThinker searches the web, reads sources, checks findings and writes research reports with citations.

- **Fast setup** with a bundled DSH plugin or one-command Web UI launcher, plus configurable research depth.
- **Traceable answers** with linked sources and saved research history.
- **Low running costs** with your own API keys. The author reports research runs costing as little as RMB 1, with a rough US-dollar budget of $0.20. Actual costs depend on research depth and provider pricing.

## Benchmark

![Research quality scores on five English prompts](benchmarks/2026-11-02/en/score.png)

In this five-prompt English sample, LucentThinker scored **76.7/100**, versus **49.1** for paid MiroThinker deep mode and **38.4** for GPT Deep Research.

Author-organized, non-blind Astra review, one saved answer per system and prompt. GPT's web originals had no citations, and its Q2 response was in Chinese. The linked report includes all systems' errors and scoring limitations. Speed and cost were not measured in this benchmark.

[Report & answers](benchmarks/2026-11-02/en/README.md) · [Prompts](benchmarks/2026-11-02/en/questions.md) · [Scoring method](benchmarks/2026-11-02/en/methodology.md) · [Offline report ZIP](benchmarks/2026-11-02/lucentthinker-benchmark-en.zip)

## Install

### DSH plugin

In DSH, open **Plugins → Add plugin**, enter `dsh-plugin-lucentthinker`, and enable it. The plugin bundles its Python runtime for macOS Apple Silicon and Windows x64. [Plugin guide](dsh-plugin/README.md)

### Standalone Web UI

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then clone the project.

```sh
git clone https://github.com/XinYu-pumch/LucentThinker.git
cd LucentThinker
```

**macOS** requires zsh, included by default. Run `./start.sh --open`, or double-click `Launch LucentThinker.command` for subsequent launches. `./start.sh` starts the service alone.

**Windows** users can double-click `start.cmd` to install dependencies and open the Web UI.

The launcher installs the project Python environment and dependencies automatically. The UI runs at [localhost:8765](http://127.0.0.1:8765). Close the launch terminal or press Ctrl+C to stop it.

## Configure

For the simplest setup, use DeepSeek for both models and web access.

1. Open Settings and enter your DeepSeek API key under the built-in **DeepSeek** provider.
2. Enter the key under **Search & Fetch** as well.
3. Refresh the model list, add a DeepSeek model, then select it as both the **main model** and **summarization model**.

Choose your research depth, enter a question, and start. Other providers are supported, with built-in thinking configurations for major model families. [Advanced guide in Chinese](docs/advanced.zh-CN.md)

## License

[GPL-3.0-or-later](LICENSE). Attribution and third-party notices are in [NOTICE](NOTICE).
