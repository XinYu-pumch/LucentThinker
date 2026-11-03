"""Build the dated, offline-readable benchmark packages from checked-in inputs.

Run with Python 3.12+, matplotlib installed.
Set BENCHMARK_CJK_FONT to a Chinese font file when building outside macOS.
"""

import copy
import hashlib
import html
import json
import os
import re
import shutil
import statistics
import zipfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties


ROOT = Path(__file__).resolve().parent
RELEASE = ROOT / "2026-11-02"
SOURCE = RELEASE / "source"
SYSTEMS = {"L": "LucentThinker", "M": "MiroThinker", "G": "GPT Deep Research"}
COLORS = {"L": "#087f8c", "M": "#c56a24", "G": "#7255b5"}
DIMENSIONS = {
    "coverage": ("Requirement coverage", 20),
    "factual": ("Facts and calculations", 25),
    "evidence": ("Evidence and traceability", 20),
    "reasoning": ("Reasoning and boundaries", 20),
    "actionability": ("Decision usefulness", 10),
    "clarity": ("Organization and clarity", 5),
}
SCHEMES = {
    "Original weights": [20, 25, 20, 20, 10, 5],
    "Evidence excluded, others normalized": [25, 31.25, 0, 25, 12.5, 6.25],
    "Equal weights": [100 / 6] * 6,
    "More weight on facts and evidence": [15, 30, 30, 15, 5, 5],
    "More weight on decision usefulness": [20, 20, 15, 20, 20, 5],
}
STATUS = {
    "confirmed_error": "Confirmed error",
    "internal_inconsistency": "Internal inconsistency",
    "unsupported_or_mismatched": "Unsupported or mismatched",
    "unverified": "Unverified",
    "supported": "Supported",
    "supported_with_limits": "Supported with limits",
}


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def esc(value):
    return html.escape(str(value), quote=True)


def rounded(value):
    return str(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def total(question, system, weights=None):
    weights = weights or SCHEMES["Original weights"]
    return sum(question[system]["scores"][key] * weight / 5
               for key, weight in zip(DIMENSIONS, weights))


def means(questions, weights=None):
    return {system: statistics.mean(total(q, system, weights) for q in questions)
            for system in SYSTEMS}


def paragraphs(items):
    return "".join(f"<p>{esc(item)}</p>" for item in items)


def bullets(items):
    return "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in items) + "</ul>"


def table(headers, rows):
    return ('<div class="table-scroll"><table><thead><tr>'
            + "".join(f"<th>{esc(h)}</th>" for h in headers)
            + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
            + "</tbody></table></div>")


def prepare_english(questions):
    """Keep factual review content while removing same-topic language comparisons."""
    q4 = next(q for q in questions if q["id"] == 4)
    q4["L"]["rationales"]["factual"] = (
        "Most core three-year financial-statement figures are correct, and one-off charges are identified well. "
        "However, incorrectly adjusting Walmart’s reported growth for 53 weeks, reporting FY25 repurchases "
        "as roughly $7 billion instead of $4.494 billion, and reversing the FCF coverage conclusion are high-impact errors.")
    q = next(q for q in questions if q["id"] == 10)
    q["verdict"] = (
        "LucentThinker leads on this question. It distinguishes the EU from Europe, handles BYD’s powertrain mix, "
        "and compares Model 3 with the tariff-exempt Model Y. MiroThinker treats local Model 3 production as conditional "
        "and considers French subsidies and local-content rules. Its data and citations contain verifiable model "
        "misattribution, mismatched official webpages, and internal contradictions in tariff burdens.")
    replacements = {
        "with more direct sourcing than in the Chinese version": "with direct sourcing for key claims",
        "More cautiously treats local Model 3 production as conditional than the Chinese version": "Treats local Model 3 production as conditional",
        ", correcting a major outlook error in the Chinese version": "",
        ", placing tighter limits on attribution than the Chinese version": ", limiting what can be attributed to tariffs",
        "The text subsequently makes European Model 3 production conditional, which is more accurate than the Chinese version’s certain-substitution narrative.": "The text subsequently makes European Model 3 production conditional.",
        "M’s English version does improve the Chinese version’s Berlin Model 3 narrative, but introduces errors in attributing MG HS leadership and in the tariff burden on remaining imports. Improvement is neither uniform nor comprehensive.": "M treats Berlin Model 3 production as conditional, but makes errors in attributing MG HS leadership and in the tariff burden on remaining imports.",
        "and the EU/UK distinction is clearer than in the Chinese version": "and distinguishes the EU from the UK",
        "Improvements over the Chinese version are only partial, falling short of M’s completeness and verifiable content in the previous round.": "G falls short of M’s completeness and verifiable content in this review.",
        "G’s English version adds some genuine 2025 all-brand data": "G provides some genuine 2025 all-brand data",
        "G’s English version again refers": "G refers",
    }

    def replace(value):
        if isinstance(value, dict):
            return {key: child if key in ("quote", "file", "url") else replace(child)
                    for key, child in value.items()}
        if isinstance(value, list):
            return [replace(child) for child in value]
        if isinstance(value, str):
            for old, new in replacements.items():
                value = value.replace(old, new)
        return value

    return [replace(item) if item["id"] == 10 else item for item in questions]


METHOD_EN = """# Scoring method

Five research tasks cover energy, health, software, business and trade. The dataset contains one response per system for each task, using Q1–4 and Q10 from the question set.

| Dimension | Weight | What is assessed |
| --- | --- | --- |
| Requirement coverage | 20% | Completion of the question and its constraints |
| Facts and calculations | 25% | Correct figures, definitions, dates and arithmetic |
| Evidence and traceability | 20% | Identifiable sources that support the claims |
| Reasoning and boundaries | 20% | Sound conclusions, alternatives and uncertainty |
| Decision usefulness | 10% | Practical choices, calculations and decision criteria |
| Organization and clarity | 5% | Clear, focused presentation |

Dimensions use 0–5 in half-point steps. Total = Σ(dimension score ÷ 5 × weight). The chart averages the tasks equally, on a 0–100 scale. Scores range from missing or seriously flawed (0–1), through partial or needing substantial verification (2–3), to strong or comprehensive (4–5).

Astra reviewers assessed the complete responses, with spot checks of important claims and calculations. The evaluation was organized by LucentThinker's author and was non-blind. One response per task limits how far the findings generalize. Alternative weightings are provided in the report.

LucentThinker used deepseek-flash, MiroThinker used paid deep mode, and GPT Deep Research used the author-reported gpt6pro + deepsearch configuration. Runtime and cost were not measured. The questions use information cutoffs of 29–30 October 2026.

GPT responses contain no source URLs. Identifiable papers, authors and years receive traceability credit. Confirmed errors and unverified claims are distinguished in the detailed assessments.

[Questions](questions.md), [full scoring evidence](scores.json) and [file hashes](manifest.json) are included. Response files preserve the assessed text and line numbers. Open index.html to read the report offline.
"""

METHOD_ZH = """# 评分方法

十个研究任务覆盖能源、健康、软件、商业、职业、汽车、历史与贸易，共九个主题。其中 Q9/Q10 是同题中英提问。每系统每题各一份回答，共 30 份。

| 维度 | 权重 | 评价内容 |
| --- | --- | --- |
| 需求覆盖 | 20% | 是否完成子问并遵守情境与边界 |
| 事实与数值 | 25% | 数字、定义、日期和计算是否正确 |
| 证据与追溯 | 20% | 来源是否可定位并支持主张 |
| 推理与边界 | 20% | 结论、替代解释与不确定性处理 |
| 决策可用性 | 10% | 能否支持选择、复算和判断条件 |
| 组织表达 | 5% | 结构清楚、重点集中 |

每维 0–5 分，可用半分。总分为各维分数除以 5 后乘权重之和。简图展示各题等权平均，满分 100。0–1 分表示缺失或严重缺陷，2–3 分表示部分完成或仍需重大补核，4–5 分表示较强或全面可复核。

Astra 评审完整阅读回答，并抽核重要事实与计算。测评由 LucentThinker 作者组织，评审知道系统身份，属于非盲评。每题仅一次回答，结论的适用范围受样本限制。报告附替代权重结果。

LucentThinker 使用 deepseek-flash，MiroThinker 使用付费 deep 模式，GPT Deep Research 的配置由作者标注为 gpt6pro + deepsearch。测评未测量速度和费用。问题的信息截止日期为 2026 年 10 月 29–30 日。

GPT 回答没有来源网址，正文可辨认的论文、作者和年份仍获得相应追溯分。详细评审区分已确认错误和未核实项目。

[完整问题](questions.md)、[评分证据](scores.json)和[文件哈希](manifest.json)随报告提供。回答保留原文和行号。离线打开 index.html 即可浏览报告。
"""

TASKS = {
    1: ("Energy", "Home battery economics", "能源", "家庭电池经济性"),
    2: ("Health", "Creatine and cognition", "健康", "肌酸与认知表现"),
    3: ("Software", "B2B search architecture", "软件", "B2B 搜索架构"),
    4: ("Business", "Costco vs. Walmart", "商业", "Costco 与 Walmart"),
    5: ("Careers", "Job offers across three cities", "职业", "三城工作机会"),
    6: ("Automotive", "Replacing a car in Shanghai", "汽车", "上海换购纯电车"),
    7: ("Energy", "Perovskite commercialization", "能源", "钙钛矿商业化"),
    8: ("History", "Zheng He and maritime trade", "历史", "郑和远航与海洋贸易"),
    9: ("Trade", "EU tariffs and Chinese EVs", "贸易", "欧盟关税与中国电动车 · 中文提问"),
    10: ("Trade", "EU tariffs and Chinese EVs", "贸易", "欧盟关税与中国电动车 · 英文提问"),
}
ZH_DIMENSIONS = dict(zip(DIMENSIONS, ["需求覆盖", "事实与数值", "证据与追溯", "推理与边界", "决策可用性", "组织表达"]))
ZH_STATUS = dict(zip(STATUS, ["已确认错误", "内部矛盾", "证据缺口或错配", "未核实", "有支持", "有支持，存在限定"]))
ZH_SCHEMES = ["标准权重", "剔除证据维度，其他维度归一", "六维等权", "更重事实与证据", "更重决策可用性"]
UPDATED = "2026-11-03"


def chart(folder, questions, language):
    chinese = language == "zh"
    font = FontProperties(fname=os.environ.get("BENCHMARK_CJK_FONT", "/System/Library/Fonts/STHeiti Light.ttc"))
    if chinese and not Path(font.get_file()).exists():
        raise FileNotFoundError("Set BENCHMARK_CJK_FONT to an installed Chinese font file")
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "path", "svg.hashsalt": "lucentthinker-benchmark"})
    fig, ax = plt.subplots(figsize=(12.8, 5.1), dpi=150)
    fig.patch.set_facecolor("#f5f8fb")
    ax.set_facecolor("#f5f8fb")
    fig.subplots_adjust(left=0.245, right=0.94, top=0.72, bottom=0.22)
    values = means(questions)
    for index, system in enumerate(SYSTEMS):
        ax.barh(index, values[system], height=0.52, color=COLORS[system], zorder=3)
        ax.text(values[system] + 1.3, index, rounded(values[system]), va="center", fontsize=20, weight="bold", color=COLORS[system])
    ax.set_yticks(range(3), SYSTEMS.values(), fontsize=13)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xticks(range(0, 101, 20))
    ax.tick_params(axis="both", length=0, pad=10, labelcolor="#46566b")
    ax.grid(axis="x", color="#dae1e8", zorder=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    title = "跨领域研究质量测评" if chinese else "Research Quality Benchmark"
    subtitle = "10 项任务 · 能源、健康、软件、商业、职业、汽车、历史与贸易" if chinese else "5 tasks across energy, health, software, business and trade"
    fig.text(0.055, 0.89, title, fontsize=24, weight="bold", color="#142c42", fontproperties=font if chinese else None)
    fig.text(0.055, 0.80, subtitle, fontsize=13, color="#46566b", fontproperties=font if chinese else None)
    footer = ("平均分 / 100 · 六维加权 · 作者组织的 Astra 非盲评\n"
              "每系统每题一份回答 · 2026-11-03") if chinese else (
              "Mean score / 100 · six weighted dimensions · author-organized, non-blind Astra review\n"
              "One response per system per task · 2026-11-03")
    fig.text(0.055, 0.055, footer, fontsize=11, linespacing=1.7, color="#46566b", fontproperties=font if chinese else None)
    for extension in ("svg", "png"):
        metadata = {"Date": UPDATED} if extension == "svg" else None
        fig.savefig(folder / f"score.{extension}", dpi=150, metadata=metadata)
    plt.close(fig)


STYLE = """body{margin:0;background:#f5f8fb;color:#203346;font:16px/1.65 system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:24px}h1,h2,h3{line-height:1.25;color:#142c42}h1{font-size:30px}section,header{background:white;border:1px solid #dce4ec;border-radius:14px;padding:28px;margin:20px 0}a{color:#087786;overflow-wrap:anywhere}.chart{width:100%;height:auto;display:block}.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:760px;font-size:14px}th,td{text-align:left;border-bottom:1px solid #dce4ec;padding:12px;vertical-align:top}blockquote{border-left:4px solid #adc5d8;margin:16px 0;padding:12px 18px;background:#f5f8fb;overflow-wrap:anywhere;white-space:pre-wrap}details{border-top:1px solid #dce4ec;margin-top:16px;padding-top:16px}summary{cursor:pointer;font-weight:650}small,.muted{color:#526477}.evidence{padding:14px 0;border-bottom:1px solid #e4e9ef}nav{display:flex;flex-wrap:wrap;gap:16px}.system-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}.system-grid article{min-width:0}.system-grid h3{border-top:4px solid var(--color);padding-top:12px}.score-line{font-weight:650}.question>summary{font-size:18px}.question>summary small{display:block;font-size:14px;font-weight:400;margin:8px 0}.method-line{font-size:14px}.summary-scores{display:flex;flex-wrap:wrap;gap:18px}.summary-scores span{white-space:nowrap}@media(min-width:761px){.score-line{display:none}}@media(max-width:760px){main{padding:10px}section,header{padding:18px}.system-grid{grid-template-columns:1fr}h1{font-size:25px}}@media print{details{break-inside:auto}section{border:0}nav,button{display:none}}"""


def render_evidence(items, chinese):
    parts = []
    for item in items:
        translation = ""
        if not chinese and item.get("quote_translation"):
            translation = f'<p><em>Translation</em> {esc(item["quote_translation"])}</p>'
        status = (ZH_STATUS if chinese else STATUS).get(item["status"], item["status"])
        location = f'原文第 {item["line"]} 行' if chinese else f'Original response, line {item["line"]}'
        parts.append(f'<article class="evidence"><strong>{esc(SYSTEMS.get(item["system"], item["system"]))} · {esc(status)}</strong>'
                     f'<blockquote>{esc(item["quote"])}</blockquote>{translation}<p>{esc(item["analysis"])}</p>'
                     f'<a href="{esc(item["file"])}">{location}</a></article>')
    return "".join(parts)


def render_checks(items, chinese):
    rows = []
    for item in items:
        url = item.get("url", "")
        title = esc(item.get("source_title", "Source"))
        link = f'<a href="{esc(url)}">{title}</a>' if url.startswith(("http://", "https://", "responses/")) else title
        status = (ZH_STATUS if chinese else STATUS).get(item["status"], item["status"])
        rows.append([esc(item["claim"]), esc(status), esc(item["finding"]), link + f'<p>{esc(item.get("access_note", ""))}</p>'])
    headers = ["核查对象", "状态", "结果", "来源与访问范围"] if chinese else ["Claim", "Status", "Finding", "Source and access limits"]
    return table(headers, rows)


def comparison_notes(question, chinese):
    history_only = {"The previous L/M scores are retained in this round.", "本轮保留旧L/M分数。"}
    edits = {
        "原评审指出的": "",
        "但原有乐观NPV引证问题未被本轮消除": "但乐观NPV的引证存在问题",
        "L等待模型与M额度方案的原有缺陷仍保留，G更低分来自其自身新增的政策与交付缺陷。": "L的等待模型、M的额度方案和G的政策适用与交付内容均存在实质缺陷。",
        "L十倍capex错误仍按原评保留，本轮未因G更弱而抬高L。": "L的十倍capex错误也计入事实评分。",
        "G初评factual为1.5，抽核发现核心《明史》引句改变收益与成本关系后降为1。该调整来自新增直接反证。": "G对《明史》的核心引句改变了收益与成本关系，影响历史解释的可靠性。",
        "与前轮L/M相比": "与L/M相比",
        "前轮M": "M",
        "三方仍为": "三方排序为",
        "本轮未": "未",
        "本轮没有重新验证": "未验证",
        "本轮没有核验": "未核验",
    }
    notes = [question["three_way_verdict"], *question["decisive_differences"], *question["gpt_differences"],
             *question["caveats"], *question["gpt_caveats"]]
    rendered = []
    for note in notes:
        if note in history_only:
            continue
        for old, new in edits.items():
            note = note.replace(old, new)
        rendered.append(note)
    heading = "比较结论与限制" if chinese else "Comparative findings and limitations"
    return f'<details><summary>{heading}</summary>' + paragraphs(rendered[:1]) + bullets(rendered[1:]) + '</details>'


def paired_section(questions):
    by_id = {q["id"]: q for q in questions}
    rows = []
    for system, name in SYSTEMS.items():
        zh_score = total(by_id[9], system)
        en_score = total(by_id[10], system)
        rows.append([name, rounded(zh_score), rounded(en_score), f'{en_score - zh_score:+.1f}'])
    return ('<section><details id="paired"><summary>同题中英对照 · 欧盟关税与中国电动车</summary>'
            + table(["系统", "中文提问", "英文提问", "英文 − 中文"], rows)
            + bullets([
                "LucentThinker 的英文回答更清楚地区分欧盟与欧洲、纯电与混动，并用 Model 3 / Model Y 对照约束关税归因。",
                "MiroThinker 的英文回答对欧洲生产 Model 3 的前景更谨慎，但增加了车型归属、税率负担及引用错配问题。",
                "GPT 的两版都缺少同口径的近期纯电车型实绩。英文版补充部分真实销量，价格传导结论却伴随重复计算 VAT 等错误。",
                "LucentThinker 与 MiroThinker 的分差为中文 26.5、英文 26.0，基本接近。LucentThinker 与 GPT 的分差由 42.0 增至 46.0，MiroThinker 与 GPT 由 15.5 增至 20.0。",
            ])
            + '<p class="muted">每种语言仅一次回答，这些分差描述样本中的变化。Q9/Q10 的详细评审提供具体依据。</p></details></section>')


def report_html(folder, data, chinese):
    questions = data["questions"]
    title = "跨领域研究质量测评" if chinese else "Research Quality Benchmark"
    summary_scores = " · ".join(f'{name} {rounded(data["mean_scores"][system])}' for system, name in SYSTEMS.items())
    method_note = "满分 100 · 作者组织的 Astra 非盲评 · 每系统每题一份回答" if chinese else "Out of 100 · author-organized, non-blind Astra review · one response per system per task"
    labels = (["任务与评分", "评分标准", "逐题评审", "完整问题", "评分数据"] if chinese else
              ["Tasks and scores", "Scoring", "Assessments", "Full questions", "Score data"])
    parts = [f'<!doctype html><html lang="{"zh-CN" if chinese else "en"}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{STYLE}</style><body><main>',
             f'<header><a href="score.svg"><img class="chart" src="score.svg" alt="{esc(summary_scores)}"></a>',
             f'<p class="score-line">{esc(summary_scores)}</p>',
             f'<nav><a href="#tasks">{labels[0]}</a><a href="#method">{labels[1]}</a><a href="#assessments">{labels[2]}</a><a href="questions.md">{labels[3]}</a><a href="scores.json">{labels[4]}</a></nav></header>',
             f'<section id="tasks"><h1>{labels[0]}</h1>']
    rows = []
    for q in questions:
        domain, name = TASKS[q["id"]][2:] if chinese else TASKS[q["id"]][:2]
        rows.append([domain, f'<a href="#q{q["id"]}">{esc(name)}</a>', *[rounded(total(q, s)) for s in SYSTEMS]])
    parts += [table(["领域" if chinese else "Domain", "任务" if chinese else "Task", *SYSTEMS.values()], rows), '</section>',
              f'<section id="method"><h2>{labels[1]}</h2>']
    dimensions = [f'{ZH_DIMENSIONS[key] if chinese else label} {weight}%' for key, (label, weight) in DIMENSIONS.items()]
    parts.append(f'<p>{" · ".join(dimensions)}</p>')
    method = ("每维按 0–5 分评价，按权重换算为百分制，再对任务取平均。评审完整阅读回答并抽核关键事实与计算。" if chinese else
              "Each dimension is rated 0–5, weighted to a total out of 100, then averaged across tasks. Reviewers read each response and spot-check key claims and calculations.")
    parts += [f'<p>{method} <a href="methodology.md">{"完整方法与限制" if chinese else "Method and limitations"}</a></p>',
              f'<p class="method-line muted">{method_note}</p><details id="sensitivity"><summary>{"不同权重下的结果" if chinese else "Results under alternative weights"}</summary>']
    rows = []
    for index, (scheme, weights) in enumerate(SCHEMES.items()):
        label = ZH_SCHEMES[index] if chinese else scheme
        rows.append([label, *[rounded(value) for value in means(questions, weights).values()]])
    parts += [table(["权重" if chinese else "Weights", *SYSTEMS.values()], rows), '</details></section>']
    if chinese:
        parts.append('<section><details id="groups"><summary>按提问语言分组</summary>')
        rows = []
        for label, ids in [("英文提问 Q1–4", [1, 2, 3, 4]), ("中文提问 Q5–8", [5, 6, 7, 8])]:
            values = means([q for q in questions if q["id"] in ids])
            rows.append([label, *[rounded(value) for value in values.values()]])
        parts += [table(["问题组", *SYSTEMS.values()], rows), '<p class="muted">两组主题不同，组间分差同时受到题目内容影响。同题比较见下方 Q9/Q10。</p></details></section>', paired_section(questions)]
    parts.append(f'<section id="assessments"><h2>{labels[2]}</h2>')
    for question in questions:
        qid = question["id"]
        domain, name = TASKS[qid][2:] if chinese else TASKS[qid][:2]
        parts += [f'<details class="question" id="q{qid}"><summary>{esc(domain)} · {esc(name)}</summary>',
                  '<div class="system-grid">']
        for system, name in SYSTEMS.items():
            review = question[system]
            response = next(i["file"] for i in data["inventory"] if i["id"] == qid and i["system"] == system)
            parts += [f'<article style="--color:{COLORS[system]}"><h3>{name} · {rounded(total(question, system))}</h3>',
                      f'<a href="{response}">{"完整回答" if chinese else "Full response"}</a>',
                      f'<h4>{"有效之处" if chinese else "Strengths"}</h4>', bullets(review["strengths"]),
                      f'<h4>{"主要局限" if chinese else "Weaknesses"}</h4>', bullets(review["weaknesses"]), '</article>']
        parts += ['</div>', comparison_notes(question, chinese)]
        parts.append(f'<details><summary>{"六维评分与理由" if chinese else "Dimension ratings and reasons"}</summary>')
        rows = []
        for key, (label, _) in DIMENSIONS.items():
            label = ZH_DIMENSIONS[key] if chinese else label
            rows.append([label, *[f'<strong>{question[s]["scores"][key]}/5</strong><p>{esc(question[s]["rationales"][key])}</p>' for s in SYSTEMS]])
        parts += [table(["维度" if chinese else "Dimension", *SYSTEMS.values()], rows), '</details>',
                  f'<details><summary>{"原文证据" if chinese else "Quoted evidence"}</summary>', render_evidence(question["evidence"] + question["gpt_evidence"], chinese), '</details>',
                  f'<details><summary>{"事实与计算核查" if chinese else "Fact and calculation checks"}</summary>', render_checks(question["checks"] + question["gpt_checks"], chinese), '</details></details>']
    parts += ['</section>', f'<footer><p>{UPDATED} · <a href="README.md">{"文件与下载说明" if chinese else "Dataset guide"}</a> · <a href="scores.json">{"完整评分记录" if chinese else "Full assessment records"}</a></p></footer>',
              '</main><script>function reveal(){const target=document.getElementById(location.hash.slice(1));if(target?.tagName==="DETAILS")target.open=true}window.addEventListener("hashchange",reveal);reveal();let states=[];window.addEventListener("beforeprint",()=>{states=[...document.querySelectorAll("details")].map(x=>[x,x.open]);states.forEach(([x])=>x.open=true)});window.addEventListener("afterprint",()=>states.forEach(([x,state])=>x.open=state));</script></body></html>']
    (folder / "index.html").write_text("".join(parts))


def package_readme(folder, data, language):
    chinese = language == "zh"
    title = "跨领域研究质量测评" if chinese else "Research Quality Benchmark"
    intro = ("十项任务覆盖能源、健康、软件、商业、职业、汽车、历史与贸易，包含九个主题和一组同题中英对照。" if chinese else
             "Five tasks across energy, health, software, business and trade.")
    links = ("[完整报告](index.html) · [完整问题](questions.md) · [评分方法](methodology.md) · [评分与证据](scores.json)" if chinese else
             "[Full report](index.html) · [Questions](questions.md) · [Scoring method](methodology.md) · [Scores and evidence](scores.json)")
    note = ("离线阅读请下载上级目录对应 ZIP，解压后打开 index.html。" if chinese else
            "For offline reading, download this edition's ZIP from the parent directory, extract it and open index.html.")
    text = f"# {title}\n\n![{title}](score.png)\n\n{intro}\n\n{links}\n\n{note}\n\n"
    text += ("作者组织的 Astra 非盲评，每系统每题一份回答。\n\n" if chinese else
             "Author-organized, non-blind Astra review, one response per system per task.\n\n")
    text += f'| {"任务" if chinese else "Task"} | LucentThinker | MiroThinker | GPT Deep Research |\n| --- | --- | --- | --- |\n'
    for q in data["questions"]:
        cells = []
        for system in SYSTEMS:
            item = next(i for i in data["inventory"] if i["id"] == q["id"] and i["system"] == system)
            cells.append(f'[{rounded(total(q, system))}]({item["file"]})')
        name = TASKS[q["id"]][3 if chinese else 1]
        text += f'| {name} | ' + " | ".join(cells) + " |\n"
    text += "\n[PNG](score.png) · [SVG](score.svg) · [SHA-256](manifest.json)\n"
    (folder / "README.md").write_text(text)


def main():
    original = read_json(SOURCE / "evaluation.json")
    translations = read_json(SOURCE / "english-translations.json")["questions"]
    prompts = {int(match.group(1)): match.group(0).rstrip() + "\n" for match in re.finditer(r"^## (\d+)\..*?(?=^## \d+\.|\Z)", (SOURCE / "questions.md").read_text(), re.M | re.S)}
    for language, ids in (("en", [1, 2, 3, 4, 10]), ("zh", list(range(1, 11)))):
        folder = RELEASE / language
        folder.mkdir(parents=True, exist_ok=True)
        questions = copy.deepcopy(translations if language == "en" else original["questions"])
        if language == "en":
            questions = prepare_english(questions)
        else:
            questions[3]["L"]["rationales"]["factual"] = questions[3]["L"]["rationales"]["factual"].replace("FY25回购约70亿错为44.94亿", "FY25回购误用约70亿而核查值为44.94亿")
        inventory = [copy.deepcopy(i) for i in original["inventory"] if i["id"] in ids]
        for item in inventory:
            origin = RELEASE / "zh" / item["file"]
            assert hashlib.sha256(origin.read_bytes()).hexdigest() == item["sha256"], origin
            if language == "en":
                destination = folder / item["file"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origin, destination)
        data = {
            "date": UPDATED, "edition": language, "question_ids": ids,
            "scope": "Five tasks across energy, health, software, business and trade" if language == "en" else "跨领域十项任务，含同题中英对照",
            "rubric": {key: {"label": label if language == "en" else original["rubric"][key]["label"], "weight": weight} for key, (label, weight) in DIMENSIONS.items()},
            "methodology": "methodology.md", "mean_scores": means(questions),
            "weight_sensitivity": {label: means(questions, weights) for label, weights in SCHEMES.items()},
            "questions": questions, "inventory": inventory,
        }
        write_json(folder / "scores.json", data)
        (folder / "questions.md").write_text("\n".join(prompts[qid] for qid in ids))
        (folder / "methodology.md").write_text(METHOD_EN if language == "en" else METHOD_ZH)
        chart(folder, questions, language)
        report_html(folder, data, language == "zh")
        package_readme(folder, data, language)
        manifest = {str(file.relative_to(folder)): hashlib.sha256(file.read_bytes()).hexdigest()
                    for file in sorted(folder.rglob("*")) if file.is_file() and file.name != "manifest.json"}
        write_json(folder / "manifest.json", manifest)
        archive = RELEASE / f"lucentthinker-benchmark-{language}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for file in sorted(folder.rglob("*")):
                if file.is_file():
                    info = zipfile.ZipInfo(f"{language}/{file.relative_to(folder)}", date_time=(2026, 11, 3, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o644 << 16
                    bundle.writestr(info, file.read_bytes())
        print(language, ids, means(questions), archive.stat().st_size)


if __name__ == "__main__":
    main()
