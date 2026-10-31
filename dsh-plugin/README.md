# LucentThinker for DeepSeek Harness

版本 **0.1.0**，兼容 DSH **0.2.1-rc.5**。

启用后，DSH 左侧显示 LucentThinker，设置中显示同名分区。研究工作台保留多模型、项目、研究过程、来源、导出和历史搜索。入口由 DSH 插件注册，研究内容在隔离页面中运行，避免污染 DSH 页面样式和全局变量。

## 安装与使用

在 DSH 的“插件 → 添加插件”中填写 `dsh-plugin-lucentthinker`，安装后启用。指定首发版本可填写 `dsh-plugin-lucentthinker@0.1.0`。本地调试可填写插件目录的绝对路径或 `.tgz` 安装包路径。开发者可使用 `link:/absolute/path/to/dsh-plugin` 安装本地链接；修改后执行 `npm run build`，然后停用并重新启用插件；宿主仍使用旧模块时重启 DSH。

普通使用不需要终端、npm、Python 或 uv。目标平台为 macOS Apple Silicon（arm64）和 Windows x64，安装包内置对应 Python 和依赖。首次打开不下载运行环境。开发构建包含当前构建平台；双平台发行包需合并两个经过验证的运行环境。Intel Mac 和 Windows ARM64 暂未提供原生包。

在“设置 → LucentThinker”配置模型供应商及 DeepSeek 网页服务。插件数据保存在 `$DSH_HOME/plugin-data/lucentthinker/`（默认 `~/.dsh/plugin-data/lucentthinker/`），独立于浏览器版和插件安装目录。首次安装是空白研究空间，不自动读取独立版的 API Key 或研究记录。

## 启停约定

- 启用：注册侧栏和设置入口；首次打开时启动插件专属引擎，使用操作系统分配的本机端口。并发打开工作台和设置页复用这个引擎，启用但从未打开时不占用 Python 进程。
- 切换 DSH 页面：研究继续，前端卸载自己的定时器和页面连接。
- 停用：撤回 DSH 入口、设置分区和 RPC，关闭引擎输入管道，等待研究取消、数据库保存及端口释放；超时会终止本插件拥有的引擎，POSIX 平台使用进程组，Windows 使用子进程句柄。
- DSH 异常退出：Python 监听父进程管道 EOF，自行结束；不依赖正常退出钩子。
- 研究中停用会中止任务，保留已保存的部分；重新启用不会自动重发研究或产生模型费用。
- 不停止独立版，不杀系统其他 Python，不修改系统代理，不写全局 Python/npm 配置。
- 卸载保留数据与诊断日志；不会自动删除研究记录。历史记录可以在独立版界面导出后保管。

## 开发与本地包

在仓库根目录准备现有项目依赖后：

```sh
cd dsh-plugin
npm run runtime:prepare
npm test
npm run test:install
npm run pack:local
```

`build` 从当前应用源码生成 `engine/` 和 `lib/`，并复制可移植 Python；不包含 `.env`、个人设置、数据库或缓存。`LUCENT_RUNTIME_SOURCE` 可指定已安装锁定依赖的可移植 Python 目录。`npm pack` 在本地生成安装包，不联系 npm 发布服务。

整体许可证为 GPL-3.0-or-later。第三方声明保留在 `NOTICE`、`licenses/` 和对应运行环境文件中。维护者使用通过全部平台验证的 `plugin-universal` 制品发布到 npm 官方仓库，命令为 `npm publish releases/dsh-plugin-lucentthinker-0.1.0.tgz --access public --registry=https://registry.npmjs.org/`。镜像同步进度由镜像服务决定。

## 界面语言

独立版和插件版首次打开默认英文，可用界面的语言按钮切换到中文。独立版在浏览器保存选择；插件把选择保存在 DSH 的稳定来源中，研究引擎重启、更换端口后仍保留。停用插件会清理语言消息监听器和状态轮询。

首次安装时主模型和摘要模型均为空，由用户添加模型后分别选择。旧版已保存的模型配置继续通过迁移加载。自定义名称、历史问答、来源原文和第三方错误详情保持原文。


## 跨平台构建与验证

GitHub Actions 的 `Platform verification` 工作流分别在 Windows x64 和 macOS arm64 构建并测试，然后合并为 `plugin-universal` 制品。最终的同一个 `.tgz` 再分别安装到两个平台的中文与空格路径下，重复运行研究及启停测试。安装流程使用包内 Python。

自动化覆盖源码回归、Windows `start.cmd` 启停、研究完成与重载、研究中停用、并发启动、宿主异常退出和文件锁释放，以及真实 Cordis 框架下的宿主入口激活、停用与再次激活。模型调用使用本地模拟接口。Windows 桌面 DSH 的实际点击与布局验收仍需另行进行。

在 Actions 页面打开成功的工作流运行，可下载 `plugin-universal`，解压后得到本地安装用 `.tgz`。GPL 许可证和第三方声明随包提供。
