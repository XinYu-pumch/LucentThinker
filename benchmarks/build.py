"""Build the dated, offline-readable benchmark packages from checked-in inputs.

Run with Python 3.12+, matplotlib and beautifulsoup4 installed.
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
from bs4 import BeautifulSoup


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


METHOD_EN = """# Evaluation method

## Sample and provenance

This author-organized review compares one saved answer per system and prompt. The English edition contains Q1–4 and Q10, five English prompts and 15 responses. The Chinese edition contains all ten prompts and 30 responses, including one same-topic Chinese/English pair. Grouping refers to prompt language. GPT's Q2 response is in Chinese and is preserved verbatim.

LucentThinker used deepseek-flash, MiroThinker used its paid deep mode, and GPT Deep Research used the web configuration reported by the author as gpt6pro + deepsearch. Model identity, search counts, runtime and comparable budgets cannot be independently established from the saved answers. This evaluates answer quality. Speed and cost were not measured in this benchmark.

Three Astra sub-reviewers handled Q1–4, Q5–8 and Q9–10. Reviewers knew system identities. GPT answers were initially reviewed, then calibrated against the previous LucentThinker/MiroThinker judgments and source material. The lead review checked selected high-impact calculations, source claims, quotations and line numbers. This was a non-blind LLM-assisted evaluation commissioned by LucentThinker's author, without an independent repeated rating of every answer.

LucentThinker/MiroThinker scores from 30 October 2026 were retained when GPT was added. The publication date is 2 November 2026. Question cutoffs are 29 October for Q1–8 and 30 October for Q9–10. Save dates do not change those cutoffs.

## Scoring

| Dimension | Weight |
| --- | --- |
| Requirement coverage | 20% |
| Facts and calculations | 25% |
| Evidence and traceability | 20% |
| Reasoning and boundaries | 20% |
| Decision usefulness | 10% |
| Organization and clarity | 5% |

Each dimension uses 0–5 with half-point steps. Anchors are 0 missing or severely contrary to the task, 1 serious defects, 2 partial delivery with material gaps, 3 basically usable with major verification needed, 4 strong with localized issues, and 5 comprehensive and verifiable. Total = sum(dimension score / 5 × weight). The headline is the unweighted mean across the edition's prompts, on a 0–100 scale, rounded half-up to one decimal. It is an assessment score, not a percentage of correct answers.

Factual mistakes primarily affect factual scoring and missing sources primarily affect evidence scoring. Independently missing calculations or deliverables also affect the relevant dimensions. Unverified claims remain distinguished from confirmed errors. Weight sensitivity is provided, including exclusion of evidence with the remaining dimensions renormalized.

The author confirmed that GPT's original web answers also had no citations. Identifiable author/year or book references still received appropriate traceability credit. This limitation is reflected in the scores. All systems, including LucentThinker, have substantive weaknesses documented in the question-level review. The sample does not establish general performance across tasks or repeated runs.

## Publication and audit

Saved responses are copied byte-for-byte. SHA-256 hashes, original filenames, quotations and line numbers are retained in scores.json. English review prose is translated from the existing assessment. Original quotations stay unchanged, with translations alongside Chinese quotations. Q10's language-comparison commentary is omitted from the English edition while its factual findings and scores are preserved.

One editorial correction fixes the direction of a repurchase-number error in Q4's LucentThinker factual rationale. The response used roughly $7 billion, while the cited review evidence gives $4.494 billion. The earlier rationale had these reversed. The public rationale now agrees with its evidence. All dimension scores are retained. The dated source directory preserves the pre-publication assessment.

The HTML report works offline after extracting the package. Original response Markdown and external sources are linked from it. External source availability depends on the source website. Source checks include access limitations and unverified items. No new fact-checking or scoring was performed for this language split.
"""

METHOD_ZH = """# 测评与出版说明

本版保留全部 10 个提问、30 份回答以及原报告的分组和同题中英分析。首页图表是十题等权平均，Q9/Q10 为同一主题的中英提问，因此十题涉及九个主题。英文版范围为 Q1–4、Q10。分组依据为提问语言，GPT 的 Q2 回答为中文，原文完整保留。

本测评由 LucentThinker 作者组织，使用 Astra 子评审，评审知道系统身份，属于非盲评。每系统每题仅一份保存的回答。L/M 沿用 2026-10-30 最终评分，G 在此基础上新增初评与校准，未对全部回答进行独立重复打分。完整方法、六维准则、逐题依据、核查限制和权重敏感性见 index.html 及 review-rubric.txt。

六维权重为需求覆盖 20%、事实与数值 25%、证据与追溯 20%、推理与边界 20%、决策可用性 10%、组织表达 5%。每维 0–5 分，可使用半分。总分为各维分数除以 5 后乘权重之和。首页使用题目等权平均和四舍五入至一位小数。该分数是评审分，样本规模和单次运行限制应随图表一起展示。

L 使用 deepseek-flash，M 使用付费 deep 模式，G 的 gpt6pro + deepsearch 标识由作者提供。缺少可比的运行日志、检索次数、耗时和预算。此测评未测量速度与费用。作者确认 GPT 网页版原回答也没有引用，正文可辨认的作者、论文和书目仍按追溯程度评分。所有系统的实质性问题均保留在报告中。

回答文件按字节复制，scores.json 保留 SHA-256、原文件名、短引与行号。英文版翻译评审文字并附中文短引的英译，原始回答与引用保持原样。英文版移除同题语言效果分析，纳入 Q10 的事实评审。

出版时修正一处文字颠倒。Q4 的 LucentThinker 事实评分理由原将 Walmart FY25 回购金额的错误方向写反，现根据同一评审中的证据改为回答使用约 70 亿美元，而核查值为 44.94 亿美元。维度评分全部沿用。source 目录保留出版前评审记录。

解压后可离线打开 index.html，外部核查来源依赖网站可访问性。原始评审中未核实的项目继续标注为未核实。本次拆分未新增事实核查或重新评分。发布日期为 2026-11-02。
"""


def chart(folder, questions, language):
    chinese = language == "zh"
    font = FontProperties(fname=os.environ.get("BENCHMARK_CJK_FONT", "/System/Library/Fonts/STHeiti Light.ttc"))
    if chinese and not Path(font.get_file()).exists():
        raise FileNotFoundError("Set BENCHMARK_CJK_FONT to an installed Chinese font file")
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "path", "svg.hashsalt": "lucentthinker-2026-11-02"})
    fig, ax = plt.subplots(figsize=(12.8, 5.6), dpi=150)
    fig.patch.set_facecolor("#f5f8fb")
    ax.set_facecolor("#f5f8fb")
    fig.subplots_adjust(left=0.245, right=0.94, top=0.72, bottom=0.27)
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
    title = "研究质量测评 · 10 个提问" if chinese else "Research quality on 5 English prompts"
    subtitle = "三系统 · 十题等权平均 · 满分 100" if chinese else "Three systems · mean weighted assessment score · out of 100"
    fig.text(0.055, 0.89, title, fontsize=23, weight="bold", color="#142c42", fontproperties=font if chinese else None)
    fig.text(0.055, 0.81, subtitle, fontsize=13, color="#46566b", fontproperties=font if chinese else None)
    footer = ("作者组织的非盲评 · Astra 评审 · 每系统每题一份回答 · 六维加权\n"
              "Q1–10，含一组同题中英提问；GPT Q2 回答为中文。\n"
              "2026-11-02 · GPT 原网页版无引用，已计入证据维度。") if chinese else (
              "Author-organized, non-blind Astra review · one answer per system/prompt · six dimensions\n"
              "Q1–4 + Q10 · grouping by prompt language · GPT Q2 answered in Chinese\n"
              "2026-11-02 · GPT web originals had no citations · reflected in evidence scoring")
    fig.text(0.055, 0.06, footer, fontsize=10.5, linespacing=1.7, color="#46566b", fontproperties=font if chinese else None)
    for extension in ("svg", "png"):
        fig.savefig(folder / f"score.{extension}", dpi=150, metadata={"Date": "2026-11-02"} if extension == "svg" else None)
    plt.close(fig)


STYLE = """body{margin:0;background:#f5f8fb;color:#203346;font:16px/1.65 system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:24px}h1,h2,h3{line-height:1.25;color:#142c42}h1{font-size:32px}section,header{background:white;border:1px solid #dce4ec;border-radius:14px;padding:28px;margin:20px 0}a{color:#087786;overflow-wrap:anywhere}.chart{width:100%;height:auto;display:block}.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;border-bottom:1px solid #dce4ec;padding:12px;vertical-align:top}blockquote{border-left:4px solid #adc5d8;margin:16px 0;padding:12px 18px;background:#f5f8fb;overflow-wrap:anywhere;white-space:pre-wrap}details{border-top:1px solid #dce4ec;margin-top:20px;padding-top:16px}summary{cursor:pointer;font-weight:700}small,.muted{color:#526477}.evidence{padding:14px 0;border-bottom:1px solid #e4e9ef}.notice{border-left:4px solid #c56a24;padding-left:16px}nav{display:flex;flex-wrap:wrap;gap:16px}.system-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}.system-grid article{min-width:0}.system-grid h3{border-top:4px solid var(--color);padding-top:12px}@media(max-width:760px){main{padding:10px}section,header{padding:18px}.system-grid{grid-template-columns:1fr}h1{font-size:25px}}@media print{details{break-inside:auto}section{border:0}nav,button{display:none}}"""


def render_evidence(items):
    parts = []
    for item in items:
        translation = f'<p><em>English translation</em> {esc(item["quote_translation"])}</p>' if item.get("quote_translation") else ""
        parts.append(f'<article class="evidence"><strong>{esc(SYSTEMS.get(item["system"], item["system"]))} · {esc(STATUS.get(item["status"], item["status"]))}</strong>'
                     f'<blockquote>{esc(item["quote"])}</blockquote>{translation}<p>{esc(item["analysis"])}</p>'
                     f'<a href="{esc(item["file"])}">Original response, line {item["line"]}</a></article>')
    return "".join(parts)


def render_checks(items):
    rows = []
    for item in items:
        url = item.get("url", "")
        title = esc(item.get("source_title", "Source"))
        link = f'<a href="{esc(url)}">{title}</a>' if url.startswith(("http://", "https://", "responses/")) else title
        rows.append([esc(item["claim"]), esc(STATUS.get(item["status"], item["status"])), esc(item["finding"]), link + f'<p>{esc(item.get("access_note", "Internal calculation or method check"))}</p>'])
    return table(["Claim", "Status", "Finding", "Source and access limits"], rows)


def english_html(folder, data):
    questions = data["questions"]
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             f'<title>LucentThinker research benchmark · English prompts</title><style>{STYLE}</style><body><main>',
             '<header><a href="score.svg"><img class="chart" src="score.svg" alt="Mean scores out of 100. LucentThinker 76.7, MiroThinker 49.1, GPT Deep Research 38.4."></a><p>Mean scores out of 100 · <strong>LucentThinker 76.7 · MiroThinker 49.1 · GPT Deep Research 38.4</strong></p>',
             '<h1>English-prompt research benchmark</h1><p>15 saved answers · Q1–4 and Q10 · published 2 November 2026</p>',
             '<nav><a href="#method">Method</a><a href="#scores">Scores</a><a href="#sensitivity">Weight sensitivity</a><a href="questions.md">Full prompts</a><a href="scores.json">Scores and evidence JSON</a></nav></header>',
             '<section><h2>Results in this sample</h2><p>LucentThinker received the highest weighted score on each of these five English prompts. Its reports more often deliver concrete calculations, usable decision criteria and traceable sources. All three systems have material errors or omissions, recorded below.</p>',
             '<p class="notice">This is an author-organized, non-blind Astra review of one saved answer per system and prompt. GPT’s Q2 answer is in Chinese. The author confirmed that GPT’s web originals also had no citations. Scores describe this sample and the stated rubric.</p></section>',
             '<section id="method"><h2>Evaluation method</h2>',
             '<p>LucentThinker used deepseek-flash, MiroThinker used paid deep mode, and GPT Deep Research used the author-reported web configuration gpt6pro + deepsearch. Runtime, search counts and comparable budgets are unavailable. Speed and cost were not measured.</p>',
             '<p>Astra sub-reviewers evaluated the saved responses, with lead-review spot checks of high-impact claims, arithmetic and quote locations. LucentThinker/MiroThinker scores from 30 October were retained when GPT was added. The original reviewers knew system identities. The English publication translates their review and retains all dimension scores.</p>',
             table(["Dimension", "Weight"], [[label, f"{weight}%"] for label, weight in DIMENSIONS.values()]),
             '<p>Dimensions use 0–5 in half-point steps. Total = Σ(score ÷ 5 × weight). Anchors range from missing or severely contrary (0), serious defects (1), partial delivery with material gaps (2), basically usable with major verification needed (3), strong with localized issues (4), to comprehensive and verifiable (5). The headline averages prompts equally. Unverified findings retain that status.</p>',
             '<p>Q1–4 use a 29 October 2026 cutoff and Q10 uses 30 October. The English scope is selected by prompt language. Identifiable author/year or book references in GPT answers still receive traceability credit. <a href="methodology.md">Full method, limitations and publication corrections</a></p></section>',
             '<section id="scores"><h2>Question-level scores</h2>',
             table(["Prompt", *SYSTEMS.values()], [[f'<a href="#q{q["id"]}">Q{q["id"]} · {esc(q["title"])}</a>', *[rounded(total(q, system)) for system in SYSTEMS]] for q in questions]), '</section>',
             '<section id="sensitivity"><h2>Weight sensitivity</h2><p>Mean scores for the same five prompts under alternative weights. The system ordering is retained when evidence is excluded.</p>',
             table(["Weights", *SYSTEMS.values()], [[esc(label), *[rounded(value) for value in means(questions, weights).values()]] for label, weights in SCHEMES.items()]),
             '<p>These are alternative weighted summaries of the same ratings. In Q4, GPT identifies Walmart’s prior-year one-off charges more accurately than MiroThinker. After excluding evidence, Q4 totals are 38.1 for GPT and 40.0 for MiroThinker, so their relative quality on specific points requires reading the findings.</p></section>']
    for question in questions:
        qid = question["id"]
        parts += [f'<section id="q{qid}"><h2>Q{qid} · {esc(question["title"])}</h2>',
                  f'<p>{esc(question["three_way_verdict"])}</p>', '<div class="system-grid">']
        for system, name in SYSTEMS.items():
            review = question[system]
            response = next(i["file"] for i in data["inventory"] if i["id"] == qid and i["system"] == system)
            confidence = {"中": "medium", "高": "high", "低": "low"}.get(review.get("confidence"), review.get("confidence", "unspecified"))
            parts += [f'<article style="--color:{COLORS[system]}"><h3>{name} · {rounded(total(question, system))}</h3>',
                      f'<p><a href="{response}">Read original response</a> · review confidence {esc(confidence)}</p>',
                      '<h4>Strengths</h4>', bullets(review["strengths"]), '<h4>Weaknesses</h4>', bullets(review["weaknesses"]), '</article>']
        parts += ['</div><h3>Dimension ratings and reasons</h3>',
                  table(["Dimension", *SYSTEMS.values()], [[esc(label), *[f'<strong>{question[s]["scores"][key]}/5</strong><p>{esc(question[s]["rationales"][key])}</p>' for s in SYSTEMS]] for key, (label, _) in DIMENSIONS.items()]),
                  '<h3>Decisive differences</h3>', bullets(question["decisive_differences"] + question["gpt_differences"]),
                  '<h3>Assessment limits</h3>', bullets(question["caveats"] + question["gpt_caveats"]),
                  '<details><summary>Original LucentThinker / MiroThinker comparison</summary>', paragraphs([question["verdict"]]), '</details>',
                  '<details open><summary>Quoted evidence and exact source locations</summary>', render_evidence(question["evidence"] + question["gpt_evidence"]), '</details>',
                  '<details><summary>External spot checks and internal calculations</summary>', render_checks(question["checks"] + question["gpt_checks"]), '</details></section>']
    parts += ['<footer><p>Response files are byte-identical to the assessed Markdown. SHA-256 hashes and all quote locations are in <a href="scores.json">scores.json</a>. <a href="README.md">Package guide</a></p></footer>',
              '</main><script>let states=[];window.addEventListener("beforeprint",()=>{states=[...document.querySelectorAll("details")].map(x=>[x,x.open]);states.forEach(([x])=>x.open=true)});window.addEventListener("afterprint",()=>states.forEach(([x,state])=>x.open=state));</script></body></html>']
    (folder / "index.html").write_text("".join(parts))


def chinese_html(folder):
    soup = BeautifulSoup((SOURCE / "chinese-report.html").read_text(), "html.parser")
    for question in read_json(folder / "scores.json")["questions"]:
        local_checks = {item["claim"]: item for item in question["checks"] + question["gpt_checks"]
                        if not item.get("url", "").startswith(("http://", "https://"))}
        for row in soup.select(f'#q{question["id"]} table.checks tbody tr'):
            cells = row.find_all("td", recursive=False)
            item = local_checks.get(cells[0].get_text())
            if item:
                url = item.get("url", "")
                locator = soup.new_tag("a", href=url) if url.startswith("responses/") else soup.new_tag("span")
                locator.string = item.get("source_title", "内部核查")
                cells[-1].insert(0, locator)
    chart_section = BeautifulSoup('<section class="section" id="benchmark"><a href="score.svg"><img src="score.svg" alt="十题平均分，满分100。LucentThinker 75.9，MiroThinker 47.2，GPT Deep Research 33.5。" style="width:100%;height:auto;display:block"></a><p>满分 100 · <strong>LucentThinker 75.9 · MiroThinker 47.2 · GPT Deep Research 33.5</strong></p><p class="small muted">本图采用全部十题的默认权重平均，Q9/Q10 为同一主题的中英提问。下方分组表及权重切换保留原报告口径。首页图表固定采用默认权重。</p></section>', "html.parser")
    soup.main.insert(0, chart_section.section)
    nav_link = soup.new_tag("a", href="#benchmark")
    nav_link.string = "00 · 评分简图"
    soup.nav.insert(0, nav_link)
    old = "FY25回购约70亿错为44.94亿"
    for node in soup.find_all(string=lambda s: s and old in s):
        node.replace_with(node.replace(old, "FY25回购误用约70亿而核查值为44.94亿"))
    note = soup.new_tag("p", attrs={"class": "small muted"})
    note.string = "出版说明：Q4 的 L 事实理由中回购错误方向已依据同一评审的证据修正，评分全部沿用。评审由 LucentThinker 作者组织，属于非盲评。详见方法与出版说明。"
    soup.select_one("#method").append(note)
    (folder / "index.html").write_text(str(soup))


def package_readme(folder, data, language):
    chinese = language == "zh"
    title = "三系统研究质量测评" if chinese else "Research quality benchmark"
    intro = "全部十题，30 份回答，包含同题中英对照。" if chinese else "Five English prompts (Q1–4 and Q10), 15 saved responses."
    links = ("[完整 HTML 报告](index.html) · [测评问题](questions.md) · [方法与限制](methodology.md) · [评分及证据](scores.json)" if chinese else
             "[Full HTML report](index.html) · [Prompts](questions.md) · [Method and limitations](methodology.md) · [Scores and evidence](scores.json)")
    note = ("GitHub 文件页显示 HTML 源码。下载本目录对应 ZIP 并解压，打开 index.html 即可浏览完整报告。Pages 部署说明见上级 benchmark 入口。" if chinese else
            "GitHub's file viewer shows HTML source. Download and extract this edition's ZIP, then open index.html for the complete report. See the benchmark landing page for Pages deployment instructions.")
    text = f"# {title}\n\n![{title}](score.png)\n\n{intro}\n\n{links}\n\n{note}\n\n"
    text += ("作者组织的非盲 Astra 评审，每系统每题一份回答。GPT 网页原回答也没有引用，Q2 回答为中文。分数仅描述本组样本。\n\n" if chinese else
             "Author-organized, non-blind Astra review, one answer per system and prompt. GPT's web originals had no citations, and its Q2 answer is in Chinese. Scores describe this sample.\n\n")
    text += "| Prompt | LucentThinker | MiroThinker | GPT Deep Research |\n| --- | --- | --- | --- |\n"
    for q in data["questions"]:
        cells = []
        for system in SYSTEMS:
            item = next(i for i in data["inventory"] if i["id"] == q["id"] and i["system"] == system)
            cells.append(f'[{rounded(total(q, system))}]({item["file"]})')
        text += f'| Q{q["id"]} · {q["title"]} | ' + " | ".join(cells) + " |\n"
    text += "\n[PNG](score.png) · [SVG](score.svg) · [SHA-256 manifest](manifest.json)\n"
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
            "date": "2026-11-02", "edition": language, "question_ids": ids,
            "scope": "Five English prompts" if language == "en" else "全部十题，含同题中英提问",
            "rubric": {key: {"label": label if language == "en" else original["rubric"][key]["label"], "weight": weight} for key, (label, weight) in DIMENSIONS.items()},
            "methodology": "methodology.md", "mean_scores": means(questions),
            "weight_sensitivity": {label: means(questions, weights) for label, weights in SCHEMES.items()},
            "questions": questions, "inventory": inventory,
        }
        write_json(folder / "scores.json", data)
        (folder / "questions.md").write_text("\n".join(prompts[qid] for qid in ids))
        (folder / "methodology.md").write_text(METHOD_EN if language == "en" else METHOD_ZH)
        chart(folder, questions, language)
        if language == "en":
            english_html(folder, data)
        else:
            for name in ("calibration.json", "review-rubric.txt"):
                shutil.copyfile(SOURCE / name, folder / name)
            chinese_html(folder)
        package_readme(folder, data, language)
        manifest = {str(file.relative_to(folder)): hashlib.sha256(file.read_bytes()).hexdigest()
                    for file in sorted(folder.rglob("*")) if file.is_file() and file.name != "manifest.json"}
        write_json(folder / "manifest.json", manifest)
        archive = RELEASE / f"lucentthinker-benchmark-{language}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for file in sorted(folder.rglob("*")):
                if file.is_file():
                    info = zipfile.ZipInfo(f"{language}/{file.relative_to(folder)}", date_time=(2026, 11, 2, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o644 << 16
                    bundle.writestr(info, file.read_bytes())
        print(language, ids, means(questions), archive.stat().st_size)


if __name__ == "__main__":
    main()
