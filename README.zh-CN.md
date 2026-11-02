# LucentThinker

[English](README.md)

**快速调研，来源可查，低成本运行。**

基于 DeepSeek 服务的本地个人研究助手。LucentThinker 自主搜索网页、阅读来源、核对发现，并生成带引用的研究报告。

- **快速上手**，通过 DSH 插件或一条命令启动 Web UI，按需选择研究深度。
- **可追溯**，回答附来源链接，研究历史保存在本地。
- **低成本**，使用自己的 API Key。作者使用经验中单次调研成本低至约 1 元人民币，美元预算可粗略参考 0.20 美元。实际费用取决于研究深度和服务定价。

## Benchmark

![三系统十题研究质量评分](benchmarks/2026-11-02/zh/score.png)

本组十题的平均分为 **LucentThinker 75.9/100**、**付费 MiroThinker deep 模式 47.2**、**GPT Deep Research 33.5**。完整报告分别分析中英文问题，并保留同题中英对照。

测评由作者组织，采用 Astra 非盲评，每系统每题一份回答。十题含一组同题中英提问。GPT 网页版原回答也没有引用，Q2 回答为中文。报告保留三者的问题和评分限制，本次未测量运行速度和费用。

[完整报告与回答](benchmarks/2026-11-02/zh/README.md) · [测评问题](benchmarks/2026-11-02/zh/questions.md) · [评分方法](benchmarks/2026-11-02/zh/methodology.md) · [离线报告 ZIP](benchmarks/2026-11-02/lucentthinker-benchmark-zh.zip)

## 安装

### DSH 插件

在 DSH 的 **插件 → 添加插件** 中填写 `dsh-plugin-lucentthinker` 并启用。插件包含 macOS Apple Silicon 和 Windows x64 所需的 Python 运行时。[插件说明](dsh-plugin/README.md)

### 独立 Web UI

先安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，然后克隆项目。

```sh
git clone https://github.com/XinYu-pumch/LucentThinker.git
cd LucentThinker
```

**macOS** 需要系统默认提供的 zsh。运行 `./start.sh --open`，后续也可双击 `Launch LucentThinker.command`。`./start.sh` 仅启动服务。

**Windows** 双击 `start.cmd`，自动安装依赖并打开 Web UI。

启动脚本自动安装项目 Python 环境与依赖。页面地址为 [localhost:8765](http://127.0.0.1:8765)。关闭启动终端或按 Ctrl+C 可退出服务。

## 配置

建议主模型、摘要模型和网页服务均使用 DeepSeek。

1. 打开设置，在内置 **DeepSeek** 供应商中填写 API Key。
2. 在 **Search & Fetch** 中同样填写 Key。
3. 刷新并添加 DeepSeek 模型，将它同时选为**主模型**和**摘要模型**。

选择研究深度，输入问题即可开始。也支持其他供应商，内置主流模型的思考配置。[进阶使用说明](docs/advanced.zh-CN.md)

## 开源许可

[GPL-3.0-or-later](LICENSE)。署名与第三方声明见 [NOTICE](NOTICE)。
