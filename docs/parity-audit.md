# 实施前差异审查（2026-10-20）

> 本文件是早期实施前快照。用户后续要求取消本地长度控制并新增设置与档位；当前 v0.3 行为以 architecture.md 和 README.md 为准。上游的裁尾与预算策略在这里仅作为历史对照。

对照固定提交 `1c4253f6774bf40314271a827304b842100e054c`，不是 main 最新版本。原始文件及 SHA-256 清单保存在 `docs/upstream/<commit>/`。

| 项目 | 当前代码已验证的行为 | 指定上游行为 / 实施目标 |
|---|---|---|
| 研究循环 | agent.py 原生工具循环，可连续搜索，但 5/12/24 次上限 | Demo Gradio 覆盖为 50；keep5 配置 200。明确区分有效迭代、模型请求、搜索、提取和摘要请求 |
| 网页阅读 | fetch(url) 把前 24,000 字符交给主模型 | scrape_and_extract_info(url, info_to_extract)：抓取后独立摘要请求，主模型仅接收提取结果 |
| 双模型配置 | 共用一组硬编码域名和模型配置 | 主模型、摘要模型分别配置地址、模型、凭据及适用参数；工具继续使用 DeepSeek |
| 上下文 | 原地截短第 6 条之前的工具正文，不保存完整消息 | 深拷贝发送视图；Demo 全部保留；keep5 保留首任务、全部主消息、最近 5 条工具结果，旧结果替换省略文本 |
| 最终回答 | 第一次不调用工具即直接交付 | 无工具结束研究后仍执行独立最终生成；Demo Markdown 提示词覆盖评测 boxed/猜测提示 |
| 长度限制 | 总字符 240,000 后收尾 | 上游按末次输入/输出 token + 1.5 倍新工具结果/最终提示估计 + 输出预留 + 1000 判断，必要时回退末次交互后收尾 |
| 重复与错误 | 重复请求读缓存；参数错直接反馈 | 上游重复 query 或 URL+提取目标回滚最多 4 次，第 5 次允许重做；空搜索/未知工具等同类回滚；提取失败结果传回模型 |
| 新提问 | 自动附带最近 6 个已完成回合 | 严格模式每题独立；原追问保留为显式扩展模式，记录所传背景 |
| 可观察性 | 只有事件、最终答案及聚合计数 | 保存不可变配置、完整研究记录、每个实际请求副本、独立提取请求和返回结果，GUI 调试详情可检查 |

## 已核实的配置语义

- `demo.yaml`：max_turns=20，但 Gradio main.py:99 覆盖为 **50**；keep=-1；compress=0。demo/default 均未定义 retry_with_summary，answer_generator.py 读取默认 **True**。compress=0，所以不会启动失败摘要压缩。
- keep5 配置：200 / 5 / 5 / False。keep=5 作用于请求副本中的工具结果消息，不是循环轮数。原始 OpenAI/XML 模式把一次迭代的多个工具返回合并为一条 user 消息；原生 function calling 则每个 call 对应一条 tool 消息，此处明确按实际 tool 消息计数。
- `context_compress_limit` 在 orchestrator/answer_generator 中仅作是否启用的判断；数值由 `benchmarks/common_benchmark.py:296-425` 用作额外完整任务重试次数（5 意味着最多 6 次尝试）。**Gradio 的 execute_task_pipeline 入口本身没有该外层循环。**
- 本项目 Demo 使用一次研究；keep5 预设接入上述 benchmark 的重试调度语义，同时保留 Demo 最终回答格式。它是对 GUI 的明确扩展，不宣称官方 Gradio 会自动执行 6 次研究。retry_with_summary=False 时重试从原始任务开始，不带失败摘要，更不是每轮总结。
- 无工具正常结束、最大迭代和上下文限制均进入结束决策；keep5 非末次尝试碰到迭代/上下文上限时跳过最终答案、重新尝试；末次才做最终生成。Demo 最终生成最多 3 次，keep5 每尝试最多 1 次。
- 定向提取正文上游先保留 409,600 字符，服务报告上下文过长时按 40,960 字符递增裁尾、最多 4 次尝试。Demo 的 20,000 字符后处理只适用于 scrape/scrape_website，**不适用于 scrape_and_extract_info**。

## 供应商替换的预定差异

DeepSeek 原生 tools/tool_call_id 取代文本 XML；保留行动→工具→反馈语义，参数修复与回滚会另测。DeepSeek Fetch 无 Jina 自定义 headers / Python 直接抓取兜底；不引入 Serper/Jina，不保证 PDF 或登录网页能力。模型私有 reasoning_content 按 DeepSeek 协议回传，不作为必需 GUI 分析内容。完整记录将保留回滚尝试；上游可直接 pop 的活动历史与持久记录分离。

## 实施状态

以上差异表保留为实施前审查快照。核心流程、双模型独立提取、两套上下文预设、完整日志和请求审计、GUI 及验证现已实现。最终行为与保留偏差见 `architecture.md`，当前确定性测试和真实服务证据见 `verification.md`。
