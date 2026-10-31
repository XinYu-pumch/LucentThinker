# DSH 本地插件集成

桌面验证日期为 2026-10-31，跨平台适配日期为 2026-11-01。目标宿主为 DeepSeek Harness 0.2.1-rc.5。

## 交付结构

- `dsh-plugin/package.json`：npm 清单、DSH 版本约束、组合包与浏览器入口声明。
- `dsh-plugin/cordis.patch.yml`：只增加 `lucentthinker` 一个插件条目。
- `src/host.js`：Cordis 服务与 Remote 接口；不修改安装包或 DSH 内置模块。
- `src/client.cjs`：注册 `sidebar.panellist`、`main`、`settings.section` 三个入口。
- `src/engine.js`：进程所有权、启动去重、退出等待和失败回收。
- `app/dsh.py`：独立数据目录、本机动态端口、能力 URL、父进程管道监控、单实例数据锁。
- `scripts/build.mjs`：生成 npm 实际安装所需的代码、应用与 Python 运行环境；安装时无构建脚本。

工作台和设置内容复用现有应用的隔离 iframe。DSH 外壳与插件页面通过正式 Remote 接口获取本次引擎地址；iframe 中保留原有功能，避免 DOM、样式与全局变量进入 DSH。此版本没有把所有页面改写成 React。

## 生命周期

启用后仅注册入口及接口，首次打开工作台或设置时启动一个引擎。并发打开复用同一个启动 Promise。切换页面释放 React 定时器、iframe、SSE 与浏览器上下文，但不取消服务器上的研究。

停用由 Cordis context 归属撤回三个入口和 Remote 命名空间；宿主关闭自己创建的 stdin 管道，Python 观察 EOF 后执行 uvicorn/FastAPI 关闭流程。研究任务取消并保留已保存记录。超过 6 秒会终止本插件拥有的引擎，POSIX 使用进程组，Windows 使用子进程句柄。停用发生在启动中时同样等待退出，不允许晚到的进程重新变成就绪。

DSH 宿主被强制终止时，管道 EOF 仍会通知 Python。引擎正常结束后删除属于自身 PID 的运行状态文件，保留数据库、配置和日志；数据锁随进程释放。另一个实例无法抢占相同数据库，也不能删除第一个实例的运行状态。

## 数据与访问边界

默认数据目录为 `~/.dsh/plugin-data/lucentthinker/`，尊重 `DSH_HOME`。插件不读取独立版 `.env`，不自动复制独立版数据库或凭据；用户通过插件设置输入配置。更新和卸载都不会主动删除数据。

引擎仅监听 `127.0.0.1`，每次启动生成 256 位能力令牌，经父子私有管道传递。所有页面、静态资源和 API 路径都需准确令牌；不把令牌放进进程参数或磁盘运行状态。模型 Key 继续按原应用方式在本机受限配置文件保存。

独立版仍禁止被嵌入。插件实例只允许 `dsh-app://app` 以及宿主提供的确切 loopback Web origin 作为页面祖先；保留同源写入检查，不使用通配 CORS，不关闭 Electron 的安全设置。插件不向 DSH 对话注入研究内容或模型凭据。

## 开发与安装

当前工作目录使用 DSH 本地 `link:` 依赖，修改不需要发布 npm 或等待镜像同步。开发前先停用插件，避免重建时替换运行中的文件。

```sh
cd dsh-plugin
npm run dev:install
```

这个命令检查引擎是否仍运行，更新代码，首次时通过已安装 DSH 的 CLI 加入本地链接。默认使用 `desktop` profile；`DSH_CLI` 可指定 CLI 路径。启用插件使用 DSH 的开关；宿主模块缓存未更新时重启 DSH。

```sh
npm test
npm run pack:local
```

产物位于 `releases/dsh-plugin-lucentthinker-0.1.0.tgz`。跨平台包包含 Apple Silicon 与 Windows x64 原生 Python 3.12.9 及 `uv.lock` 锁定的运行依赖，包括 Windows 所需的 IANA 时区数据。首次启动使用内置运行环境。npm `files` 白名单排除个人数据和开发缓存。正式版本号为 `0.1.0`，npm 包名为 `dsh-plugin-lucentthinker`。

## 验证记录

- 修复了动态 Remote 服务未声明注入依赖导致的前端激活失败；在隔离 profile 重现并修复后，验证日常 DSH 正常冷启动。
- 验证 DSH 原生侧栏入口、设置分区、嵌入工作台和模型设置页面。
- 验证本地链接安装，以及独立 profile 中从 npm `.tgz` 安装；安装包中的内置 Python 可以独立启动引擎，凭据为空。
- 进程集成测试：并发启动去重、启动中停用、活动研究取消与记录保留、数据锁竞争、宿主 SIGKILL 后引擎自行退出。
- 客户端测试：动态依赖声明、三个 slot 的归属与释放、通信初始化异常不拒绝 DSH 启动。
- 安全边界测试：缺失／错误令牌拒绝、跨来源 API 拒绝、正确资源前缀、嵌入来源严格校验。
- 原应用相关回归：113 项 Python 测试及 39 项 JavaScript 测试通过。另有 6 项嵌入边界测试、7 项插件测试。

Windows x64 的自动化验证由 `.github/workflows/platforms.yml` 执行，包含源码回归、原生运行环境、实际 npm 安装、模拟研究完成与持久化、插件引擎启停与崩溃回收。安装路径含中文与空格，真实 Cordis 框架负责宿主服务的激活及撤回。双平台安装包合并后会在 Windows 和 macOS 再各执行一次安装与生命周期验证。具体成功状态以 GitHub Actions 运行结果为准。

Windows 桌面 DSH 的实际界面操作尚未验收，Intel Mac 与 Windows ARM64 暂无原生运行包。研究测试使用本地模拟模型服务。DSH 账号／模型复用、历史数据导入向导与自动更新属于后续功能。
