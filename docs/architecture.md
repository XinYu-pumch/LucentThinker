# 当前实现与上游对照（v0.5）

基线：MiroMindAI/MiroThinker `1c4253f6774bf40314271a827304b842100e054c`。固定源码在 `docs/upstream/`，初次审查快照在 `parity-audit.md`。保留用户要求的全量输入、设置页、迭代档位和 query 128 字符校验；本轮修正搜索/读取边界并实现可读时间线。

## 研究执行

主研究共享持续发展的历史：用户问题 → 主模型行动 → DeepSeek Search → 仅结果元信息与 snippet 返回 → 主模型选择 `source_id` 并提供 `info_to_extract/progress` → DeepSeek Fetch → 独立摘要请求 → 提取结果返回主模型 → 继续研究或结束。Search summary/content 只保存为后台原始响应。允许连续搜索、多个网页读取，不执行每轮强制总结。

Fetch 失败或正文为空时，才通过当前运行、当前尝试的来源绑定直接取得 Search content；没有可用 content 时再取 summary。绑定由程序记录搜索响应 ID 与结果位置，不靠模型重写 URL 后再匹配，不跨尝试或任务；每次仍先真实调用 Fetch，不以缓存绕过抓取。没有备用材料则返回失败。

每页摘要消息重新构造为 system + user：定向提示、显式提取任务、当前网页全文和来源元信息，不自动加入主研究或其他网页历史。主模型只收到 `success/url/extracted_info/error/scrape_stats/model_used/tokens_used` 等结果字段。数字、日期、单位、限定条件和来源应保留，未找到信息应明确说明，网页指令是待分析内容。

无工具正常结束、有效迭代耗尽或格式失败进入单独最终生成；最终请求不提供工具，不执行意外返回的 tool_calls，采用 Demo 用户语言 / Markdown / 来源提示，不用 boxed 或鼓励猜测的评测 fallback。主模型上下文超长直接失败；服务输出 length 标记未完成，保留已收到内容。摘要超长或失败返回结构化错误，由主模型决定下一步。

## 代码与提示词

| 文件 | 职责 |
|---|---|
| `app/agent.py` | 主模型循环、工具反馈、有效迭代/调用计数、重复和格式错误处理、最终生成、外层重试 |
| `app/extraction.py` | 完整 Fetch 正文、独立提取请求、实际统计与错误 |
| `app/context.py` | 完整历史与活动历史、深拷贝请求视图、显式 keep5 |
| `app/provider.py` | OpenAI 格式流式模型调用、重试、DeepSeek Search/Fetch、query 边界 |
| `app/settings_store.py` / `settings_api.py` | 项目内配置持久化、双角色配置、CRUD、模型列表、连接测试与密钥显隐 |
| `app/config.py` | 服务元信息、参数、快照、提示词哈希与脱敏 |
| `app/tool_schema.py` | 原生工具 schema、参数解析/别名修复、重复键 |
| `app/store.py` / `telemetry.py` | SQLite、实际请求/响应/片段、事件、用量、完整审计 |
| `app/main.py` / `app/static/` | 本机 API、SSE、GUI、设置、请求调试 |

提示词分别在 `app/prompts/main.txt`、`extraction.txt`、`final.txt`、`control.json`。快照冻结实际模板、SHA-256、schema、两模型参数、研究配置、追问范围与网页凭据来源；凭据本身不进入快照。运行期间修改设置不改变正在执行的任务。

## 三类上下文和持久记录

1. `research_messages` 保存完整主研究历史，按 attempt 区分。重复/格式/执行错误回退仅标记 rolled_back 并从活动列表移除，不删历史。
2. `model_requests` 保存每次实际发送的 messages / tools / 参数、响应、状态、错误、时间。主请求使用活动历史的深拷贝；只有显式 keep5 会把更早的工具结果替换为省略提示，保留初始问题、全部主消息和最近 5 条 tool 消息。
3. 每次摘要请求使用新消息数组，单独记录为 summary / page_extraction；无共享记忆。

`model_chunks` 保存流片段，按约 0.7 秒或 64KB 批量落盘，这些是写入批次而非输出上限。最终答案增量经 SSE 显示。请求详情按需加载，大 JSON 每次显示 30,000 字符并提供“继续显示”；只是显示分页。标题只取问题前 42 字符用于侧栏，研究问题本体完整保存和发送。

`search_responses` 保存 Search 服务原始响应与参数、运行/尝试/迭代和时间。只作传输审计与失败降级的记录/结果位置解引用，不是证据库，不自动进入主历史或跨提问记忆。降级结果另有 `content_source/degraded/fetch_error/fallback_search_response_id/fallback_query`，来源的 fetched 仅在原文独立提取成功时为真。删除会话时一并删除。

用量来自实际 response.usage；缺失则标记未知，不估算付费 tokens。正文统计基于实际 Fetch 返回内容，不承诺是网站完整原文。model_used 只在收到响应时填入。

## 迭代、重试和错误

有效主模型迭代上限支持 10 / 50 / 200 / 自定义正整数；格式错误和重复等回退不消耗有效迭代，另有 max_iterations+200 次循环尝试保护。HTTP 请求次数、搜索、提取、Fetch 和完整研究尝试分别计数。

搜索重复键仅 query；提取重复键为 source_id + info_to_extract。连续重复前四次回退，第五次允许真实执行，不靠结果缓存。普通未知工具/空搜索/可恢复执行错误沿用阈值；格式损坏前四次回退，第五次结束。原生 tool_call_id 必须配对唯一，多工具中途回退会回退整组。不修复参数别名 description/introduction，返回明确校验错误。

query 超过 128 字符，以及供应商 HTTP 400/413/422 参数错误，直接以工具反馈返回主模型改写，避免同样参数反复回滚。原始参数仍在完整历史中，没有自动缩短。

Demo 为 50/-1/0/True（最后一项来自上游缺省）。keep5_max200 为 200/5/5/False。compress 数值来自 benchmark 的额外完整重试，Gradio 无该外层循环；本项目明确作为扩展配置，最多 6 次完整尝试，不携带前次失败总结。迭代档位、keep 和完整任务重试互相独立；选择重试时 retry_with_summary=False。

主模型报告上下文超限时立即保存失败，不继续最终生成或整题重试。输出 length 不增大 max_tokens 重试；主/最终输出保留并标 incomplete，摘要输出保留为失败提取结果。网络、限流等可重试错误最多 4 次 HTTP 尝试，逐步退避；鉴权、余额等立即失败。完整任务模式仍可在普通最终生成失败时重新研究。Demo 最终生成最多三次，启用外层重试时每个完整尝试最终生成一次。

## 长度策略（用户要求的明确偏差）

- 没有输入 token 估计、上下文预算预检、工具后预算判断、按长度回退主历史、最终生成前自动删组。
- 网页全文进入摘要，没有上游 409,600 字符上限、40,960 裁尾或上下文缩短重试。
- 用户问题无 max_length；扩展追问包含本会话所有已完成问答完整文字及所有来源，无最近六条/14K/100K 等限制。严格模式仍每问独立。
- 输出采用服务公布的 max_output_tokens（实测 Flash 393,216），未知则不发送 max_tokens。没有自设 16K/8K 额度。供应商窗口仍由服务验证；不宣称无限上下文或无限输出。
- Search query 和 ori_question 的服务字符上限均为 128。schema/解析器验证 query、search_intent；供应商发送入口再验证 query、ori_question，不截断。
- Search count 不设应用上限。resolve_search_context 优先采用合法 search_intent；未提供时只在完整原始问题不超过 128 字符时使用原文，否则使用已校验的 query。超长显式意图反馈模型重写，绝不自动截断。原问题始终完整保存于主历史。

## 仍与上游不同

1. 原生 OpenAI tools/tool_call_id 替代 XML/MCP 文本协议。逻辑消息流已模拟及真实验证，不宣称逐 token 等价。上游一次迭代多结果可合并成一条 user 消息；这里每个调用对应一条 tool 消息，keep5 按实际 tool 消息计数。
2. DeepSeek 替代研究模型、搜索与抓取供应商。排序、内容与站点支持由 DeepSeek 决定，无 Jina 自定义 headers 或 Python 抓取兜底；未复刻工具全集和视觉。
3. 独立提取使用 system + user 两条而非拼成单条 user。所有页面均为新请求上下文。
4. 上述长度控制偏差来自用户后续明确要求，覆盖之前复刻预算、裁尾策略的目标。
5. GUI 新增迭代档位、多个模型配置、显式追问与 benchmark 重试。官方默认 Demo 新提问不共享研究过程，本项目严格模式保持这一点。
6. 最终生成前保留有效工具回复，再追加最终提示，避免直接 pop 破坏原生消息配对。引用始终以登记 source_id 的 URL 为准，不按模型参考文献重编号；未知编号/链接冲突分别提示，不代替事实核查。
7. 全量日志、流片段保存、来源编号表属于本地可观察性功能，不是独立可检索证据池。不存在每轮自动总结或网页摘要间共享记忆。


## v0.4 展示与收尾核对

`app/static/trace.js` 将真实事件投影为按 attempt / iteration 分组的时间线；搜索结果按需展开为卡片，阅读任务显示 URL、info_to_extract、正文获取与摘要请求状态、结构化结果中的 extracted_info。raw JSON 和 Search 原始响应只在开发视图按需加载。事件 ID 去重，历史回放不把旧失败事件覆盖成最终状态。展示公开 content，不构造或要求暴露私有推理。

主模型提示词明确 Search snippet 是发现线索，关键政策数字需读取原始来源；结束前检查比较范围、计算公式、税费口径、缺失事实和来源等级。最终生成附上当前活动历史的原文提取/摘要降级/失败/搜索次数，提示披露缺口。v0.5 使用单独的 finish_research 动作显式结束，普通无工具文本只作为进展并提示模型继续提交动作；没有新增强制每轮总结、额外审核模型或固定 Fetch 配额。这是提示词质量要求和透明记录，不是确定性的事实正确性保证。

与上游新增的明确差异：本地下载仓库的抓取工具采用 Jina → Python 直接抓取 → 摘要；这里采用 DeepSeek Fetch →（失败才按来源绑定取 Search content，缺失时取 summary）→ 独立摘要。两条路径都不把未提取全文交给主模型，不把降级结果计为原文阅读成功。用户指定的 no-local-length-cap 仍优先于上游 409600/40960/8192 限制。


## v0.5 确定性边界

Search 固定 need_content=true；主模型仍只收到元信息和 snippet。备用选择限定当前 run、attempt 和程序保存的 source_id → search_response_id/result_index 绑定：先找最近可用 content（优先于更新但只有 summary 的记录），然后找最近可用 summary。content 必须为非空字符串；不截断。实际来源写入 content_source 与模型输入元信息，GUI 分别标注。

所有参数使用严格 JSON（拒绝重复键/NaN/Infinity）与手工 schema 校验，不再修复或猜测参数别名。可配对的非法动作产生 tool 错误，保持 assistant/tool 协议配对。finish_research 必须独占一次响应，程序接受后记录完成状态和缺口，追加确认 tool 消息，再进行无工具最终写作。此工具消息正常参与 keep5 计数。显式结束与严格协议是用户授权的上游偏差，不代表增加了事实审核模型或证据库。

全量模式最终输入为当前有效主历史加最终写作要求/证据状态；回退记录只保留审计，完整 Fetch、Search content/summary 及独立提取请求不直接进入主历史。


## v0.6 参数传递审查

- 阅读入口不再接收模型 URL。模型只选 source_id；搜索登记时程序保存响应行和结果位置。Fetch 使用该位置中的原始 URL，备用材料也从相同绑定读取，没有 URL 修复、去片段重试或模糊匹配。多个分片保持各自的来源身份。
- 搜索上下文由程序按128字符协议选择：显式 search_intent、可容纳的原始问题、或本次 query。可选 search_intent 明确代表模型生成的新搜索意图。query/count 是模型决策，need_content 与接口路径由程序固定，凭据和配置不会由模型提供。
- info_to_extract 是模型生成的语义任务。正文、来源元数据、绑定 ID 和摘要消息隔离由程序组装。Fetch 返回的 content 不保证覆盖附件，提取失败不等于原文不存在。
- 工具调用 ID 来自模型服务，是原生协议配对字段；程序检查非空唯一并原样应答，不能把它当作来源身份。来源编号非法时反馈，不发送网络请求。
- 最终模型只写数字引用标记。程序按登记表生成引用标题/URL；未知编号不猜测。已有引用冲突检查继续保留，编号合法仍不代表事实受到支持。
- 公开 content 通过 note_delta 按请求 ID 展示，note 定稿覆盖同一卡片。progress 是每个搜索/阅读动作必需的公开目的，不是每轮证据总结。
- 来源选择协议、必填公开说明和自动参考列表是本应用明确的上游偏差；工具驱动循环不改成固定搜索/阅读交替。旧运行记录不迁移或回写。
