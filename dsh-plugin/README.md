# LucentThinker for DeepSeek Harness

A research workspace inside **DeepSeek Harness (DSH)**. LucentThinker lets a research model search for sources, request focused webpage extraction from a separate model, and develop reports with traceable references. Organize conversations into projects, review research steps and sources, search saved history, and export reports.

Version **0.1.1** · Compatible with **DSH 0.2.1-rc.5** · **GPL-3.0-or-later**

[简体中文](#简体中文)

## Install in DSH

1. Open **Plugins → Add plugin** in DSH.
2. Enter `dsh-plugin-lucentthinker`, or pin this release with `dsh-plugin-lucentthinker@0.1.1`.
3. Install and enable the plugin.
4. Open **LucentThinker** from the sidebar. Its configuration section is available under **Settings → LucentThinker**.

### Supported platforms

| Operating system | Processor |
| --- | --- |
| macOS | Apple Silicon, arm64 |
| Windows | Intel or AMD, x64 |

Both platforms use **the same npm package**. It contains the Python runtime and dependencies for both systems. At startup, LucentThinker selects the bundled runtime for your computer.

## Configure your models

Add your model providers and credentials in **Settings → LucentThinker**, then select the **main research model** and **page extraction model** in the workspace. Both model selections start empty on a fresh installation. Configure your DeepSeek Search and Fetch credential for the webpage tools.

The interface starts in English. Use the language button to switch to Chinese. The plugin remembers your language choice across engine restarts. Saved configuration from earlier installations is loaded when you reinstall.

## Enable, disable, and uninstall

Enabling the plugin registers its sidebar and settings entries. The research engine starts when you first open the workspace or plugin settings. Multiple views share one engine, and research continues while you navigate to other DSH pages.

Disabling the plugin cancels active research, saves the available records, closes the engine, and releases its local port and data lock. If DSH exits unexpectedly, the engine detects the closed host connection and shuts down.

To uninstall, open **Plugins → Installed plugins → LucentThinker**, then choose **Uninstall LucentThinker**. Research history, model configuration, and diagnostic logs are retained for reinstallation.

### Data location

Plugin data is stored in `$DSH_HOME/plugin-data/lucentthinker/`. With the default DSH home, this is `~/.dsh/plugin-data/lucentthinker/` on macOS and `%USERPROFILE%\.dsh\plugin-data\lucentthinker\` on Windows.

The plugin maintains its own settings and research database. A fresh plugin installation begins with an empty research space. The standalone app uses its own data directory.

## Development and local installation

Clone the source repository and prepare its project dependencies. From the repository root, run the following commands on a supported platform.

```sh
cd dsh-plugin
npm run runtime:prepare
npm test
npm run test:install
npm run pack:local
```

The build creates `lib/`, copies the application into `engine/`, and packages a portable Python runtime with the locked dependencies. `LUCENT_RUNTIME_SOURCE` can point to a prepared runtime directory.

DSH also accepts an absolute plugin directory or `.tgz` path for local installation. Developers can use `link:/absolute/path/to/dsh-plugin`. After rebuilding, disable and enable the plugin to load the changes. Restart DSH if its host module cache still contains the previous build.

Native builds prepare the current platform. The **Platform verification** GitHub Actions workflow builds and tests Windows x64 and macOS arm64, combines them into the **plugin-universal** artifact, then installs and tests that same package on both platforms. Download the artifact from a successful workflow run and extract its `.tgz` file for local installation.

Automated verification covers research completion and persistence, cancellation during shutdown, concurrent startup, host crashes, file locks, Unicode installation paths, and activation and disposal through the real Cordis framework. Research tests use local mock model services. Windows desktop DSH interface validation is still pending.

Maintainers publish the verified universal package to the official npm registry.

```sh
npm publish ./releases/dsh-plugin-lucentthinker-0.1.1.tgz --access public --registry=https://registry.npmjs.org/
```

[Source repository](https://github.com/XinYu-pumch/LucentThinker) · [Build and verification runs](https://github.com/XinYu-pumch/LucentThinker/actions/workflows/platforms.yml) · [Report an issue](https://github.com/XinYu-pumch/LucentThinker/issues)

## License

LucentThinker is licensed under **GPL-3.0-or-later**. The package includes `LICENSE`, `NOTICE`, third-party licenses, and runtime license information. [License](https://github.com/XinYu-pumch/LucentThinker/blob/main/LICENSE) · [Third-party notices](https://github.com/XinYu-pumch/LucentThinker/blob/main/NOTICE)

## 简体中文

LucentThinker 是嵌入 DeepSeek Harness 的深度研究工作台，支持多轮搜索、独立网页提取、来源追溯、项目管理、历史搜索和报告导出。

### 安装与配置

1. 在 DSH 的 **插件 → 添加插件** 中填写 `dsh-plugin-lucentthinker`，或指定 `dsh-plugin-lucentthinker@0.1.1`。
2. 安装并启用后，从侧栏打开 **LucentThinker**。
3. 在 **设置 → LucentThinker** 中添加模型供应商和凭据，并配置 DeepSeek 网页服务。
4. 在工作台分别选择主研究模型和网页提取模型。首次打开默认英文，点击语言按钮可切换为中文。

**Windows x64 与 Mac Apple Silicon 使用同一个 npm 包**，包内同时提供两个平台的 Python 和依赖，启动时自动选择对应环境。

### 停用与卸载

停用插件会取消进行中的研究、保留已保存内容，并关闭研究引擎、释放端口和文件锁。

卸载路径为 **插件 → 已安装插件 → LucentThinker → 卸载 LucentThinker**。模型配置、研究记录和日志会保留，重装后可以继续使用。

默认数据位置为 macOS 的 `~/.dsh/plugin-data/lucentthinker/`，以及 Windows 的 `%USERPROFILE%\.dsh\plugin-data\lucentthinker\`。自定义 `DSH_HOME` 时，数据位于该目录下的 `plugin-data/lucentthinker/`。

Windows 已通过云端自动化验证，桌面 DSH 的实际点击与布局验收仍待完成。中国大陆镜像的同步进度由镜像服务决定。许可证为 **GPL-3.0-or-later**。
