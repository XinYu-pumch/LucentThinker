# LucentThinker — Fast, Reliable Deep Research. Free, Open Source, Local.

[中文](README.zh-CN.md)

A local personal research assistant powered by DeepSeek. It searches the web, reads sources and writes research reports with citations.

- Higher research-quality scores than GPT Deep Research and paid MiroThinker in this benchmark.
- Adjustable research depth, locally saved history.
- Bring your own API keys. Author-reported costs start around RMB 1 per run, roughly US$0.20, depending on the task and provider pricing.

## Example report

**Costco and Walmart Business Comparison**

Model: DeepSeek Flash · Generated on October 29, 2026

[Download PDF](examples/costco-vs-walmart.pdf?raw=true)

<details>
<summary>Expand the question and full answer</summary>

> ### Question
>
> I am trying to understand whether Costco or Walmart has the stronger underlying business, rather than simply which stock has performed better. Using each company's fiscal years labeled 2023, 2024 and 2025, how do their growth, margins, membership economics, inventory efficiency, cash generation and returns on invested capital compare? I am concerned that their different fiscal calendars, business mixes and accounting adjustments could make a superficial comparison misleading. Could you reconcile those differences, explain how you calculate the financial ratios, and identify which apparent improvements reflect operating progress versus one-off effects? Based on those years, which business looks more resilient in a prolonged period of weak consumer spending, and what evidence could overturn that judgment? I am not asking for a stock-price forecast.
>
> ### Answer
>
> #### Bottom line
>
> On the underlying business, **Costco is stronger — narrowly, not overwhelmingly**. It earns roughly twice Walmart’s return on invested capital, turns inventory about 40% faster, converts nearly all net income into free cash flow, carries net cash, and has a larger gross membership-fee pool with a much higher fee contribution to operating profit. Walmart is bigger, has a higher operating margin, a more grocery-heavy U.S. revenue mix, and faster-growing membership and advertising; it is the better **top-line** hedge in a deep consumer downturn.
>
> My resilience verdict is therefore split: **Costco is more resilient on profit, cash flow and balance sheet; Walmart is more resilient on revenue and traffic.** If I must choose one overall business for a prolonged weak-spending period, I give the edge to **Costco**, because its membership and balance sheet protect the bottom line. But I would not call it a clean sweep.
>
> This is a business-quality analysis, not a stock-price forecast.
>
> ---
>
> #### 1. Reconciling the calendars, business mixes and accounting
>
> ##### Fiscal calendars are offset by about six months
>
> | | Costco | Walmart |
> |---|---|---|
> | FY2023 | 53 weeks ended Sep 3, 2023 | Year ended Jan 31, 2023 |
> | FY2024 | 52 weeks ended Sep 1, 2024 | Year ended Jan 31, 2024 |
> | FY2025 | 52 weeks ended Aug 31, 2025 | Year ended Jan 31, 2025; comparable-sales calendar included a 53rd week |
>
> Costco’s FY2023 was a 53-week year; FY2024 and FY2025 were 52-week years [42][217]. Walmart’s FY2025 Q4 comparable-sales release used a 14-week period, and its supplemental calendar states that a 53rd week occurred in fiscal 2025 [25][628]. Walmart’s 10-K itself does not explicitly state the number of weeks in the financial year [763]. I therefore treat Walmart’s FY2025 reported revenue growth as calendar-benefited, but I label the 52-week adjustment as an estimate rather than a precise restatement.
>
> The practical implication is that **Costco’s FY2025 ends about seven months after Walmart’s FY2025**. The label-based comparison is not calendar-aligned. The cleanest growth measures are each company’s comparable-sales series, which adjusts for the retail calendar, rather than headline revenue growth.
>
> A rough normalization illustrates the size of the distortion:
>
> - Costco FY2024 net sales growth was **5.0%** as reported, but FY2023 had an extra week. On a simple 52-week-equivalent basis, growth was closer to **7.0%**; membership-fee growth was **5.4%** reported versus about **7.4%** adjusted [42][217]. This is an estimate, not a company disclosure.
> - Walmart FY2025 net sales growth was **5.0%** as reported [279]. If the 53rd week carried average weekly sales, 52-week growth was closer to **3.0%**. Walmart does not quantify the extra week, so this is a directional estimate based on the 14-week comparable period [25][628].
>
> These adjustments narrow the growth gap but do not reverse it.
>
> ##### The business mixes are fundamentally different
>
> Costco’s model is low gross margin, high inventory turnover and membership fees. Walmart’s is higher gross margin, broader assortment and a much larger grocery and e-commerce base.
>
> | Mix indicator | Costco FY2025 | Walmart FY2025 |
> |---|---:|---:|
> | Net sales | \$269.9B | \$674.5B |
> | Membership fees / total revenue | 1.9% | Fee-only about 0.6%; membership and other income 0.9% |
> | Foods/fresh/non-food mix | Foods and sundries ~40.6%; non-foods ~26.4%; fresh foods ~14.1%; warehouse ancillary ~19.0% | Walmart U.S.: grocery ~59.7%; general merchandise ~24.6%; health and wellness ~13.4% |
> | Fuel exposure | Gasoline about 10% of net sales | Fuel is meaningful at Sam’s Club but a smaller consolidated share |
> | E-commerce | About 7% of net sales | About 18% of net sales |
> | International | Canada plus other international ~27% of revenue | Walmart International ~18% of net sales |
> | Segment mix | Single warehouse-club segment | Walmart U.S. ~68.6% of net sales; International ~18.1%; Sam’s Club ~13.4% |
>
> Sources: Costco mix and fuel/e-commerce [11][457][460]; Walmart segment and category mix [321]; Walmart e-commerce penetration [597]; Costco segment revenue [441].
>
> This matters because **Costco’s gross margin is intentionally low**. It marks up merchandise less and earns a membership fee. Walmart’s gross margin is more than double Costco’s, but its operating expenses are also much higher. Comparing gross margins directly would make Walmart look more profitable than it is.
>
> ##### Accounting adjustments that can mislead
>
> **Costco:**
>
> - The Executive 2% reward is recorded as a **reduction of net sales**, not as SG&A. In FY2025 it reduced net sales by about **\$3.0B** [670][673]. So the headline “membership fees are 51% of operating income” is a **gross** figure. The reward is a real cost embedded in the gross-margin line.
> - Deferred membership fees were about **\$2.5–2.9B**; cash is collected upfront and revenue is recognized over the membership year [517].
> - FY2025 included a **\$142M LIFO charge**, equal to about 7 bp of gross margin [42][4].
> - FY2023 had a 53rd week; FY2024 included a **\$6.655B special dividend** and about **\$202M** of discrete tax benefits; FY2025 had about **\$100M** of discrete tax benefits [42][217].
> - Falling gasoline prices and foreign exchange reduced reported FY2025 sales by **\$2.329B** and **\$1.943B**, respectively [42].
>
> **Walmart:**
>
> - FY2023 operating expenses included **\$3.3B of opioid-related legal settlements** and **\$0.8B of business restructuring charges**—about **\$4.1B** in total. FY2024 lapped these charges, which is the main reason reported operating income jumped 32% [311].
> - “Other gains and losses” were net losses of **\$1.538B, \$3.027B and \$0.794B** in FY2023–FY2025, primarily fair-value changes on equity investments. These sit below operating income but distort net income and EPS [279][311].
> - The effective tax rate was **33.6%, 25.5% and 23.4%**; FY2023 was elevated by the Flipkart/PhonePe separation [311].
> - Walmart uses supplier-finance programs with **\$5.725B** of confirmed obligations outstanding at FY2025, which flatters reported payables and working capital [825].
> - Walmart’s own “ROI” adds back interest income, depreciation and amortization, and rent. It is a pre-tax cash return, not a NOPAT ROIC [311].
>
> ---
>
> #### 2. The numbers side by side
>
> ##### Growth and margins
>
> | Metric | Costco FY23 | Costco FY24 | Costco FY25 | Walmart FY23 | Walmart FY24 | Walmart FY25 |
> |---|---:|---:|---:|---:|---:|---:|
> | Net sales (\$B) | 237.7 | 249.6 | 269.9 | 605.9 | 642.6 | 674.5 |
> | Total revenue (\$B) | 242.3 | 254.5 | 275.2 | 611.3 | 648.1 | 681.0 |
> | Revenue growth | — | +5.0% | +8.2% | — | +6.0% | +5.1% |
> | Operating income (\$B) | 8.1 | 9.3 | 10.4 | 20.4 | 27.0 | 29.3 |
> | Operating margin | 3.35% | 3.65% | 3.77% | 3.34% | 4.17% | 4.31% |
> | Net income (\$B) | 6.3 | 7.4 | 8.1 | 11.7 | 15.5 | 19.4 |
> | Net margin | 2.60% | 2.90% | 2.94% | 1.91% | 2.39% | 2.85% |
> | Gross margin* | 10.57% | 10.92% | 11.12% | ~24.1% | ~24.4% | ~24.9% |
>
> \*Definitions differ. Costco gross margin = (net sales − merchandise costs) ÷ net sales, excluding membership fees. Walmart gross margin = (total revenue − cost of sales) ÷ total revenue. They are not directly comparable. Sources: [42][217][279][311].
>
> The important observations:
>
> - **Costco’s operating margin rose steadily**, from 3.35% to 3.77%, despite a low gross margin and rising SG&A. Membership fees supplied the difference.
> - **Walmart’s operating margin rose much more**, from 3.34% to 4.31%, but most of the FY2024 jump was the \$4.1B charge lap. FY2025’s +14 bp was more genuine but modest.
> - **Costco’s net margin was higher than Walmart’s in all three years**—2.60% vs 1.91%, 2.90% vs 2.39%, 2.94% vs 2.85%. Walmart’s higher operating margin was eaten up by net interest expense and investment losses. Costco’s net cash and interest income helped.
>
> ##### Membership economics
>
> | Metric | Costco FY23 | Costco FY24 | Costco FY25 | Walmart FY23 | Walmart FY24 | Walmart FY25 |
> |---|---:|---:|---:|---:|---:|---:|
> | Membership fee revenue (\$B) | 4.58 | 4.83 | 5.32 | Not disclosed | Not disclosed | ~3.8 fee-only (earnings call) |
> | Membership and other income (\$B) | n/a | n/a | n/a | 5.41 | 5.49 | 6.45 |
> | Fee revenue / total revenue | 1.89% | 1.90% | 1.93% | ~0.6% | ~0.6% | ~0.6% |
> | Fee revenue / operating income | 56.4% | 52.0% | 51.3% | ~13% fee-only | ~13% | ~13% |
> | Paid members (m) | 71.0 | 76.2 | 81.0 | Not disclosed | Not disclosed | Not disclosed |
> | Member growth | ~+8% | +7.3% | +6.3% | Not disclosed | Not disclosed | Not disclosed |
> | Renewal, U.S./Canada | 92.7% | 92.9% | 92.3% | Not disclosed | Not disclosed | Not disclosed |
> | Renewal, worldwide | 90.4% | 90.5% | 89.8% | Not disclosed | Not disclosed | Not disclosed |
> | Executive share of paid members | 45.4% | 46.5% | 47.8% | n/a | n/a | n/a |
> | Executive share of sales | 72.8% | 73.3% | 73.6% | n/a | n/a | n/a |
>
> Sources: Costco [42][101][217]; Walmart [321][406][410][413]. Walmart’s fee-only \$3.8B is from the FY2025 earnings call, not the 10-K; its 10-K line includes rent, recycling, gift card and other income. Sam’s Club renewal rates were described as record highs, but Walmart did not quantify them [428].
>
> ##### Inventory, cash generation and ROIC
>
> | Metric | Costco FY23 | Costco FY24 | Costco FY25 | Walmart FY23 | Walmart FY24 | Walmart FY25 |
> |---|---:|---:|---:|---:|---:|---:|
> | Inventory turnover | 12.3x | 12.6x | 13.1x | 8.2x | 8.8x | 9.2x |
> | Inventory days | 29.7 | 29.0 | 28.0 | 44.5 | 41.5 | 39.7 |
> | DPO (days) | n/a | 30.3 | 29.8 | n/a | 41.2 | 41.2 |
> | CCC (days, approximate) | n/a | ~2.7 | ~2.5 | n/a | ~5.4 | ~3.9 |
> | Operating cash flow (\$B) | 11.07 | 11.34 | 13.34 | 28.84 | 35.73 | 36.44 |
> | Capex (\$B) | 4.32 | 4.71 | 5.50 | 16.86 | 20.61 | 23.78 |
> | Free cash flow (\$B) | 6.75 | 6.63 | 7.84 | 11.98 | 15.12 | 12.66 |
> | FCF / net income | 107% | 90% | 97% | 103% | 98% | 65% |
> | Net cash/(debt) including leases (\$B) | +4.7 | +1.1 | +5.3 | −50.3 | −51.5 | −51.1 |
> | ROIC, lease-adjusted | 29.9% | 31.6% | 32.9% | 10.1% | 14.2% | 15.1% |
> | ROIC, excluding operating leases | 33.9% | 35.3% | 36.8% | 11.3% | 15.8% | 16.8% |
> | ROIC, excluding operating leases and goodwill | n/a | n/a | n/a | 12.8% | 17.7% | 18.8% |
>
> ROIC formula: NOPAT = operating income × (1 − effective tax rate); invested capital = total debt + finance leases + total equity + operating lease liabilities − cash and short-term investments; ROIC = NOPAT ÷ year-end invested capital. Costco’s current operating lease liabilities were not separately extracted, so its ROIC is slightly overstated; including them would reduce it by roughly 0.3–0.5 pp. Walmart’s FY2023 ROIC is depressed by the \$4.1B charges. Sources: [42][217][123][517][279][474][491][311].
>
> ---
>
> #### 3. Growth: Costco is accelerating, Walmart is decelerating
>
> Costco’s comparable sales, excluding gasoline and foreign exchange, accelerated from **+5% in FY2023 to +6% in FY2024 to +8% in FY2025** [42]. Reported comparable sales were +3%, +5% and +6%. FY2025 growth was driven by a **5% increase in shopping frequency**, about 1% higher average ticket, 24 net new warehouses, and 6.3% growth in paid members [42]. Lower gasoline prices and FX reduced reported sales, so the 8.1% net sales growth is not a fuel or currency illusion.
>
> Walmart’s growth moved the other way. Total revenue grew **6.0% in FY2024 and 5.1% in FY2025** [279]. Walmart U.S. comparable sales decelerated from **+7.0% to +5.5% to +4.8%** [311]. Walmart International grew 6.3% in FY2025 and Sam’s Club grew 4.7%, but Walmart U.S. is about 69% of consolidated sales [321][555]. The FY2025 revenue comparison also benefited from the 53rd comparable week.
>
> So on momentum, **Costco wins**: its comparable sales are accelerating while Walmart’s largest segment is slowing. Walmart still has the larger absolute growth and a more diversified revenue base, but its growth rate is lower and more dependent on international, Sam’s Club, e-commerce and advertising.
>
> Membership growth reinforces the difference:
>
> - Costco added paid members at a **7.3%** rate in FY2024 and **6.3%** in FY2025, ending at 81.0 million [42][217].
> - Walmart’s fee-only membership income grew **21% to about \$3.8B** in FY2025, according to the earnings call [406][410][413]. That is faster than Costco’s 10.3% fee growth, but from a smaller base and with no disclosed member count or renewal rate.
>
> ---
>
> #### 4. Margins: Walmart’s gross margin is not a superiority signal
>
> The gross-margin comparison is the most misleading part of a superficial analysis.
>
> - **Costco** earned a **10.57% → 10.92% → 11.12%** gross margin. That is intentionally low: Costco passes merchandise savings to members and earns a fee. Its SG&A was **9.08% → 9.14% → 9.25%** of net sales, leaving an operating margin of **3.35% → 3.65% → 3.77%** [42][217].
> - **Walmart** earned a **~24.1% → 24.4% → 24.9%** gross margin on a total-revenue basis, but its operating expenses were about **20.5%** of revenue. Its operating margin was **3.34% → 4.17% → 4.31%** [279][311].
>
> The operating margins converge, but the business models are completely different. Walmart’s higher gross margin covers a high-cost store and distribution network; Costco’s low gross margin covers a low-cost warehouse club and is supplemented by membership fees.
>
> Walmart’s **consolidated** operating margin is higher because **Walmart U.S. earns 5.16%**, while **Sam’s Club earns only 2.66%** and International earns 4.51% [321]. Costco’s club model earns **3.77%** [42]. On a like-for-like club basis, **Costco is more profitable than Sam’s Club**. Walmart’s consolidated margin advantage is a mix effect, not evidence that its club business is stronger.
>
> The net-margin comparison is also revealing: **Costco’s net margin was higher than Walmart’s in all three years**—2.60% vs 1.91%, 2.90% vs 2.39%, 2.94% vs 2.85% [42][279]. Walmart’s higher operating margin was consumed by net interest expense and investment losses. Costco’s net cash and interest income helped.
>
> ---
>
> #### 5. Membership economics: Costco’s is more central; Walmart’s is growing faster
>
> ##### Costco
>
> Costco’s membership is the core profit engine:
>
> - Fee revenue was **\$4.58B, \$4.83B and \$5.32B**, equal to **1.9% of revenue** but **51–56% of operating income** on a gross basis [42][217].
> - Paid members grew from **71.0 million to 81.0 million**; renewal was **90.4–90.5% worldwide** and **92.3–92.9% in the U.S./Canada** [42][101][217].
> - Executive members were **47.8% of paid members** but generated **73.6% of net sales** in FY2025 [42]. That is a high-quality, high-spend member base.
> - The September 2024 fee increase—Gold from \$60 to \$65, Executive from \$120 to \$130—accounted for about **40%** of FY2025 membership-fee growth [42][679]. The other ~60% came from member growth and upgrades.
>
> But the membership fee is not costless. The Executive 2% reward is a **contra-revenue item**, about **\$3.0B in FY2025** [670][673]. A crude net-of-reward measure is therefore about **\$2.3B, or 22% of operating income**, not 51%. This is not a GAAP subtotal—the reward also drives sales and gross profit—but it shows that the “membership is half of profit” claim overstates the pure fee cushion. The reward cap also rose to **\$1,250**, so as Executive penetration rises, the cost rises too [679].
>
> The renewal rate slipped from **92.9% to 92.3%** in the U.S./Canada and **90.5% to 89.8%** worldwide in FY2025. Management attributes this to more memberships sold online, including digital promotions, which renew at slightly lower rates [42]. That is a warning sign worth monitoring, not yet a broken moat.
>
> ##### Walmart
>
> Walmart’s membership is smaller relative to profit but growing faster:
>
> - Membership and other income was **\$5.41B, \$5.49B and \$6.45B** [321]. That line includes membership fees plus rent, recycling, gift card and other income, so it is not a clean membership metric.
> - Fee-only membership income was about **\$3.8B in FY2025, up 21%**, according to the earnings call [406][410][413]. That is about **13% of operating income**, far below Costco’s gross 51% or net ~22%.
> - Walmart+ membership income grew at a double-digit rate, and Sam’s Club membership and renewal rates reached record highs, but Walmart does not disclose paid member counts or renewal rates [423][428].
>
> The comparison: **Costco’s membership is the core profit pool; Walmart’s is a growing ecosystem attachment.** Costco has the higher renewal rate, the larger gross fee pool and the greater profit contribution. Walmart has faster growth from a smaller base and a broader ecosystem—e-commerce, advertising, delivery—that could make its membership more valuable over time. But the disclosure gap makes Walmart’s membership economics much harder to verify.
>
> ---
>
> #### 6. Inventory efficiency: Costco’s structural advantage
>
> Inventory turnover = cost of goods sold ÷ average inventory; inventory days = 365 ÷ turnover.
>
> - **Costco:** 12.3x → 12.6x → 13.1x; inventory days 29.7 → 29.0 → 28.0 [123][126][517].
> - **Walmart:** 8.2x → 8.8x → 9.2x; inventory days 44.5 → 41.5 → 39.7 [491][474].
>
> Costco turns inventory about **40% faster**. The comparison is structurally favorable to Costco: limited SKUs, palletized displays, high food turnover and a smaller general-merchandise assortment. Walmart’s broader assortment, general merchandise and e-commerce inventory are slower. Both companies improved, so this is real operating progress for both—but Walmart remains far behind.
>
> Working capital tells a more nuanced story:
>
> - Walmart’s DPO is about **41 days** versus Costco’s **30 days**. Walmart’s simplified cash conversion cycle is about **4–5 days**, versus Costco’s **2–3 days** [calculations from 491, 474, 123, 517].
> - Walmart runs a **\$17.1B working-capital deficit** (current assets less current liabilities), and it has **\$5.7B** of supplier-finance obligations [631][825]. That flatters its cash cycle and ROIC. Costco’s current ratio is about **1.03**, not negative; its float comes from deferred membership fees [517].
> - So Walmart’s cash cycle is more dependent on supplier terms and negative working capital, while Costco’s is more dependent on inventory velocity and membership float. Both are efficient, but Costco’s advantage is more structural and less reliant on financial leverage.
>
> LIFO differences and mix mean the exact gap may be overstated, but the direction is clear: **Costco is the more inventory-efficient business.**
>
> ---
>
> #### 7. Cash generation and balance sheet: Costco converts; Walmart borrows
>
> Free cash flow = operating cash flow − capital expenditures.
>
> | | Costco FY23 | Costco FY24 | Costco FY25 | Walmart FY23 | Walmart FY24 | Walmart FY25 |
> |---|---:|---:|---:|---:|---:|---:|
> | Operating cash flow (\$B) | 11.07 | 11.34 | 13.34 | 28.84 | 35.73 | 36.44 |
> | Capex (\$B) | 4.32 | 4.71 | 5.50 | 16.86 | 20.61 | 23.78 |
> | Free cash flow (\$B) | 6.75 | 6.63 | 7.84 | 11.98 | 15.12 | 12.66 |
> | FCF / net income | 107% | 90% | 97% | 103% | 98% | 65% |
> | Capex / revenue | 1.8% | 1.9% | 2.0% | 2.8% | 3.2% | 3.5% |
>
> Sources: [42][165][181][311][350].
>
> Costco converts nearly all of its net income into free cash flow. Walmart’s conversion was strong in FY2023–FY2024 but fell to **65%** in FY2025, because capex rose 15% and net income was boosted by non-cash investment-loss and tax effects. That is a red flag for the quality of Walmart’s FY2025 earnings growth.
>
> The balance sheets are starkly different:
>
> - **Costco:** cash and short-term investments of **\$15.284B**, total debt of **\$7.267B**, and long-term operating lease liabilities of **\$2.460B** at FY2025 [123][517]. Net cash is about **\$5.6B** before current operating lease liabilities, or **~\$5.3B** including an estimated ~\$250M current lease liability. Costco has been net cash in all three years.
> - **Walmart:** cash of **\$9.037B**, total debt of **\$39.067B**, finance lease liabilities of **\$6.723B**, and operating lease liabilities of **\$14.324B** at FY2025 [474]. Net debt including operating leases is about **\$51.1B**. Walmart’s net interest expense was **\$2.245B**; Costco’s interest expense was only **\$154M** and it earned interest income [42][279].
>
> Walmart generates more absolute cash, but it spends more on capex and carries far more debt. Costco’s net cash gives it more flexibility to invest in warehouses and prices during a downturn. Walmart’s FY2025 FCF covered its **\$6.69B dividend** but not its dividend plus roughly **\$7.0B of buybacks** [526][353]. Costco’s FCF covered its **\$2.18B dividend** and **\$0.9B of buybacks** and still built cash [42]. That is a meaningful difference in financial flexibility.
>
> ---
>
> #### 8. ROIC: the clearest quality gap
>
> I use a standardized NOPAT ROIC, not Walmart’s own ROI metric:
>
> **NOPAT = operating income × (1 − effective tax rate)**
>
> **Invested capital = total debt + finance leases + total equity + operating lease liabilities − cash and short-term investments**
>
> **ROIC = NOPAT ÷ year-end invested capital**
>
> | | Costco FY23 | Costco FY24 | Costco FY25 | Walmart FY23 | Walmart FY24 | Walmart FY25 |
> |---|---:|---:|---:|---:|---:|---:|
> | NOPAT (\$B) | 6.0 | 7.0 | 7.8 | 13.6 | 20.1 | 22.5 |
> | Invested capital (\$B) | 20.1 | 22.2 | 23.6 | 134.1 | 141.8 | 148.5 |
> | ROIC, lease-adjusted | 29.9% | 31.6% | 32.9% | 10.1% | 14.2% | 15.1% |
> | ROIC, excluding operating leases | 33.9% | 35.3% | 36.8% | 11.3% | 15.8% | 16.8% |
> | ROIC, excluding operating leases and goodwill | n/a | n/a | n/a | 12.8% | 17.7% | 18.8% |
>
> Sources: [42][217][123][517][279][474][491].
>
> Costco’s ROIC is roughly **double Walmart’s** under every definition. The gap is driven by:
>
> - Costco’s higher inventory turnover and membership float.
> - Costco’s lower capital intensity: capex is ~2% of sales versus Walmart’s ~3.5%.
> - Costco’s higher like-for-like club operating margin: 3.77% versus Sam’s Club’s 2.66%.
> - Walmart’s larger goodwill, lease base and store footprint.
> - Walmart’s negative working capital and supplier finance, which flatter its ROIC but are a form of financial leverage.
>
> Walmart’s own ROI of **15.5% in FY2025 and 15.0% in FY2024** is not directly comparable to Costco’s NOPAT ROIC because it adds back D&A and rent [311]. Our standardized calculation gives Walmart about **15% including leases**, consistent with its own ROI, but the composition is different. Walmart’s improvement from 10.1% to 15.1% is partly normalization from the \$4.1B FY2023 charges, not pure operating progress. Costco’s improvement from 29.9% to 32.9% is real but modest.
>
> Even with the most favorable Walmart definition—excluding operating leases and goodwill—Walmart earns about **18.8%**, still well below Costco’s ~33%. The quality gap is robust.
>
> ---
>
> #### 9. Operating progress versus one-off effects
>
> | Apparent improvement | What drove it | Verdict |
> |---|---|---|
> | **Costco FY2024 revenue +5.0%** | 53-week lap, FX and gasoline headwinds; ex-FX/gas comps +6%; member growth +7.3% | Mostly operating; the calendar understates growth (~7% on a 52-week estimate) [42][217] |
> | **Costco FY2024 gross margin +35 bp** | 16 bp from absence of prior-year charter-shipping charges; ~19 bp from other factors | About half one-off [217] |
> | **Costco FY2024 net income +17.1%** | Operating leverage, charter-charge lap, ~\$202M tax benefits; 53-week lap | Mostly operating but flattered by tax/one-offs [217] |
> | **Costco FY2025 revenue +8.1%** | Comps +6% reported, +8% ex-FX/gas; frequency +5%; 24 net new warehouses; gas/FX headwinds | Operating progress [42] |
> | **Costco FY2025 gross margin +20 bp** | +11 bp excluding gas deflation; core merchandise +19 bp; LIFO −7 bp | Core operating progress; headline flattered by gas deflation [4] |
> | **Costco FY2025 membership fees +10.3%** | ~40% price, ~60% member growth/upgrades | High quality, but the price step-up will lap in FY2026 [42] |
> | **Costco FY2025 net income +9.9%** | Operating income +11.8%; lower interest income; higher tax rate; \$100M tax benefit; FX −\$97M | Mostly operating; modest one-offs [42] |
> | **Walmart FY2024 operating income +32.2%** | Lapping \$4.1B of opioid/restructuring charges | Mostly one-off; underlying growth ~10% [279][311] |
> | **Walmart FY2024 net income +32.8%** | Same charge lap, partly offset by larger investment losses | Mostly one-off [279][311] |
> | **Walmart FY2025 operating income +8.6%** | Gross margin +20 bp, membership +21%, advertising +27%, e-commerce; opex +36 bp | Real but modest operating progress [279][311] |
> | **Walmart FY2025 net income +25.3%** | \$2.2B smaller investment loss; 2.1 pp lower tax rate; operating income +8.6% | Mostly below-the-line, not operating [279][311] |
> | **Walmart FY2025 inventory turns 9.2x vs 8.8x** | Supply-chain and inventory-management improvements | Real operating progress [491][474] |
> | **Walmart FY2025 FCF −16%** | Capex +15%, working capital; net income boosted by non-cash items | Cash conversion weakened; caution [279][311] |
>
> The pattern is clear: **Costco’s improvements are mostly operating, with some accounting and price help. Walmart’s biggest apparent improvement—FY2024’s 32% operating-income jump—is mostly a one-off charge lap. Its FY2025 25% net-income growth is mostly below-the-line investment-loss and tax effects, not operating progress.** Walmart’s real operating progress is visible but modest: inventory turns, membership/advertising growth, and gross-margin efficiency.
>
> ---
>
> #### 10. Resilience in a prolonged period of weak consumer spending
>
> Resilience is not one metric. The two companies win on different dimensions.
>
> | Dimension | Winner | Why |
> |---|---|---|
> | Revenue/traffic in a deep downturn | **Walmart** | Grocery is ~60% of Walmart U.S. sales; EDLP positioning; in 2008–09 Walmart’s U.S. comps were positive while Costco’s turned negative [321][800][792][803] |
> | Profit margin | **Walmart on operating margin; Costco on net margin** | Walmart operating margin 4.31% vs Costco 3.77%; Costco net margin 2.94% vs Walmart 2.85% [42][279] |
> | Membership economics | **Costco** | Larger gross fee pool, ~90% renewal, 51% gross/~22% net of operating income vs Walmart ~13% fee-only [42][101][217][406] |
> | Inventory efficiency | **Costco** | 13.1x vs 9.2x; 28 vs 40 days [123][517][491][474] |
> | Cash generation | **Costco** | 97% FCF/net income vs 65%; net cash vs ~\$51B net debt including leases [42][311][517][474] |
> | ROIC | **Costco** | ~33% vs ~15% lease-adjusted; ~37% vs ~19% excluding operating leases and goodwill [calculations] |
> | Growth momentum | **Costco** | Comps accelerated from +5% to +8% ex-FX/gas; Walmart U.S. decelerated from +7.0% to +4.8% [42][311] |
> | Scale and diversification | **Walmart** | \$681B revenue vs \$275B; three segments, 19 countries, larger absolute FCF [279][321] |
> | Overall business quality | **Costco, narrowly** | Quality metrics dominate; Walmart is the better top-line hedge |
>
> The 2008–09 evidence is the best real-world stress test we have. Walmart’s U.S. same-store sales were positive—**+1.7% in December 2008, +5.1% in February 2009, +5% in April 2009**—while Costco’s were negative—**−4% in December 2008, −4.1% in February 2009, −8% in April 2009, −6% in June 2009** [800][792][803][799]. Costco’s FY2009 comparable sales fell **4%**, net sales fell **1.5%**, and net income fell **15%**, while its renewal rate held at **87%** [785][813]. That shows both sides: Walmart’s top line was more defensive, but Costco’s membership base remained sticky and it stayed profitable.
>
> Today, Costco’s FY2025 comps accelerated to **+8% ex-FX/gas** even as Walmart U.S. decelerated to **+4.8%** [42][311]. That is evidence that Costco’s value proposition is attracting trade-down traffic and that it may be more resilient today than it was in 2008. But it is not proof: Costco still has a meaningful non-food/discretionary mix (~26% of sales), business members (~16% of paid members) and gasoline exposure, all of which could be cyclical in a prolonged downturn [11][42].
>
> My verdict:
>
> - **On revenue and traffic resilience: Walmart.** Its grocery mix, scale and EDLP positioning give it a higher floor in a deep consumer recession. The 2008–09 record supports this.
> - **On profit, cash-flow and balance-sheet resilience: Costco.** Its membership fees, ~90% renewal, net cash, high inventory turns, low capex and ~33% ROIC give it more protection on the bottom line.
> - **Overall: Costco, narrowly.** If the scenario is a prolonged weak-spending period, I would rather own the business whose profit and cash flow are protected by membership and a net-cash balance sheet. But I would not be surprised if Walmart’s revenue outperforms. This is a case where the “better business” and the “better recession top-line” are not the same company.
>
> ---
>
> #### 11. What evidence could overturn this judgment
>
> ##### Evidence that would weaken the Costco case
>
> - **Renewal rates fall below ~90% worldwide or ~92% in the U.S./Canada for multiple quarters**, or paid-member growth drops below ~3%.
> - **Executive penetration stalls, or the 2% reward cost grows faster than membership-fee revenue**, shrinking the net fee cushion.
> - **Core gross margin, excluding gasoline and LIFO, turns negative**, or inventory turns fall below ~12x.
> - **FCF/net income falls below ~80%**, capex rises above ~3% of sales without commensurate sales growth, or net cash turns into net debt.
> - **Comparable sales excluding FX and gasoline turn negative**, or shopping frequency/traffic declines.
> - **The fee increase causes churn**, or tariffs/FX/non-food weakness pressures margins.
> - **Costco’s ROIC falls toward Walmart’s** because of higher capex, leases or lower margins.
>
> ##### Evidence that would weaken the Walmart case
>
> - **Walmart U.S. comparable sales turn negative** or grocery market share falls.
> - **Membership income growth decelerates sharply**, or Sam’s Club renewal rates decline (if disclosed).
> - **Advertising growth stalls**, e-commerce losses widen, or inventory turns reverse.
> - **Supplier-finance obligations unwind** or suppliers tighten terms, causing a cash outflow.
> - **Capex continues to rise without operating-income growth**, or net debt/leverage rises.
> - **Gross-margin gains prove to be temporary markdown laps**, or investment losses mask operating weakness.
> - **Walmart’s ROIC gap versus Costco narrows** because membership/advertising become a larger share of profit, or because Costco’s returns fall.
>
> ##### Evidence that would overturn the overall resilience verdict
>
> - If **Costco’s renewal and member growth stay strong through a deep recession** while its comps remain positive, the “Walmart is more revenue-defensive” view would be weakened.
> - If **Walmart’s operating income and FCF hold up better than Costco’s** in a downturn, the “Costco is more resilient” view would be weakened.
> - If **Walmart discloses membership fee-only revenue, paid members and renewal rates** and they are stronger than the current partial data suggest, its membership story would become more comparable.
> - If **Costco’s Executive reward cost outgrows fees**, or its net cash position deteriorates, its membership/balance-sheet cushion would be smaller than it looks.
>
> ---
>
> #### 12. Verification gaps and how to interpret the numbers
>
> - **Walmart does not disclose membership-fee-only revenue, paid member counts or renewal rates.** The ~\$3.8B fee-only figure is from the FY2025 earnings call, not the 10-K; the 10-K’s “membership and other income” line includes rent, recycling, gift card and other income [321][406][410]. This is the biggest gap in the membership comparison.
> - **Walmart’s FY2025 53rd week is not explicitly confirmed in the 10-K.** The Q4 comparable-sales release used a 14-week period, and the supplemental calendar says a 53rd week occurred in fiscal 2025 [25][628]; the 10-K does not state the financial-year week count [763]. The ~3.0% 52-week growth estimate is therefore directional, not a precise restatement. If the reported financials do not include the extra week, Walmart’s 5.0% growth is cleaner than the estimate suggests.
> - **Costco’s current operating lease liabilities were not separately extracted.** The ROIC calculation uses long-term operating lease liabilities only, which slightly overstates Costco’s ROIC and net cash. Including current lease liabilities would reduce ROIC by roughly 0.3–0.5 pp.
> - **Costco’s Executive reward amount (~\$3.007B) comes from a secondary analysis of the 10-K**, not a directly quoted 10-K table [670][673]. The net-of-reward ratio is an analytical approximation, not a GAAP subtotal. The accrued member rewards liability figures in the sources conflict, so they are not relied on here.
> - **Costco’s FY2023 53rd-week impact was not quantified.** The 52-week revenue and membership-fee adjustments are simple per-week estimates, not company disclosures.
> - **LIFO reserves were not normalized.** Both companies use LIFO for part of inventory; inventory turnover is calculated on reported inventory. The ~13x versus ~9x gap is large enough that the direction is robust, but the exact gap may be overstated or understated.
> - **Walmart’s gross margin definition varies.** The ~24–25% figures are calculated from total revenue less cost of sales and may not match Walmart’s disclosed gross-profit rate exactly. Operating margin is the cleaner comparison.
> - **Walmart’s ~\$7.0B buyback figure is from a secondary source** [353]; the 10-K cash-flow line may differ because of settlement timing.
> - **The fiscal years are offset by about six months.** The conclusions rely on comparable-sales trends and multi-year averages, not a single-year point estimate.
> - **The 2008–09 analogy is directional, not a forecast.** Both companies’ mixes have changed: Costco is more grocery/fresh-heavy and has a higher renewal rate today; Walmart has a larger e-commerce, advertising and membership ecosystem.
> - **This is not a tax or personal-cash-flow analysis.** The figures are pre-tax operating and cash-flow metrics; no after-tax disposable cash calculation is implied.
>
> **Net judgment:** Costco is the stronger underlying business, narrowly, and the more resilient profit/cash-flow model. Walmart is the more defensive revenue stream in a deep consumer downturn and is improving its membership, advertising and e-commerce mix. The evidence supports “Costco for quality, Walmart for top-line defense”—not a one-sided victory for either.
>
> ##### References
>
> - [4](<https://www.marketscreener.com/news/costco-wholesale-annual-report-for-fiscal-year-ending-08-31-2025-form-10-k-ce7d5bd2de8af025#1#2>) Costco Wholesale : Annual Report for Fiscal Year Ending 08/31, 2025 (Form 10-K) — <https://www.marketscreener.com/news/costco-wholesale-annual-report-for-fiscal-year-ending-08-31-2025-form-10-k-ce7d5bd2de8af025#1#2>
> - [11](<https://stockanalysis.com/stocks/cost/financials/metrics/#main#1>) Costco (COST) Business Metrics & Revenue Breakdown — <https://stockanalysis.com/stocks/cost/financials/metrics/#main#1>
> - [25](<https://last10k.com/sec-filings/wmt/0000104169-25-000021.htm#1>) 10-K Annual Report Fri Mar 14 2025 - Walmart Inc. (WMT) SEC Filing 10-K Annual Report for the fiscal year ending Friday, January 31, 2025 — <https://last10k.com/sec-filings/wmt/0000104169-25-000021.htm#1>
> - [42](<https://www.sec.gov/Archives/edgar/data/909832/000090983225000101/cost-20250831.htm#ie1561bbf248347fbab0c7507ac97c984_94#2>) cost-20250831 — <https://www.sec.gov/Archives/edgar/data/909832/000090983225000101/cost-20250831.htm#ie1561bbf248347fbab0c7507ac97c984_94#2>
> - [101](<https://www.metatrader.com/es/symbols/nasdaq/cost/documents/2960359-annual-report-fy2023>) COSTCO WHOLESALE CORP annual report, FY2023 (NASDAQ:COST) | MetaTrader — <https://www.metatrader.com/es/symbols/nasdaq/cost/documents/2960359-annual-report-fy2023>
> - [123](<https://markets.ft.markitdigital.com/data/equities/tearsheet/financials?s=CTO:STU&subView=BalanceSheet#1>) Costco Wholesale Corp — <https://markets.ft.markitdigital.com/data/equities/tearsheet/financials?s=CTO:STU&subView=BalanceSheet#1>
> - [126](<https://markets.ft.markitdigital.com/data/equities/tearsheet/financials?s=COST:VIE&subview=BalanceSheet#1>) Costco Wholesale Corp - Costco Wholesale Corp — <https://markets.ft.markitdigital.com/data/equities/tearsheet/financials?s=COST:VIE&subview=BalanceSheet#1>
> - [165](<https://markets.ft.markitdigital.com/data/equities/tearsheet/financials?s=COST*:MEX&subview=CashFlow#1>) Costco Wholesale Corp - Costco Wholesale Corp — <https://markets.ft.markitdigital.com/data/equities/tearsheet/financials?s=COST*:MEX&subview=CashFlow#1>
> - [181](<https://stockanalysis.com/stocks/cost/financials/cash-flow-statement/#main#1>) Costco (COST) Cash Flow Statement - Costco Wholesale Corporation (COST) — <https://stockanalysis.com/stocks/cost/financials/cash-flow-statement/#main#1>
> - [217](<https://www.sec.gov/Archives/edgar/data/909832/000090983224000049/cost-20240901.htm#2>) cost-20240901 — <https://www.sec.gov/Archives/edgar/data/909832/000090983224000049/cost-20240901.htm#2>
> - [279](<https://content-archive.fast-edgar.com/20250314/APB2H222322292Z2222M22ZZBMKGI2S23272/R3.htm#1>) Consolidated Statements of Income - USD ($) — <https://content-archive.fast-edgar.com/20250314/APB2H222322292Z2222M22ZZBMKGI2S23272/R3.htm#1>
> - [311](<https://www.publicnow.com/view/74BDAB3E52AD027861351CBC18B7E45588B43169#2>) Walmart Inc. (via Public) / Annual Report for Fiscal Year Ending January 31, 2025 (Form 10-K) - = Average invested capital  | $  | 291,444  | $  | 277,522 — <https://www.publicnow.com/view/74BDAB3E52AD027861351CBC18B7E45588B43169#2>
> - [321](<https://content-archive.fast-edgar.com/20250314/APB2H222322292Z2222M22ZZBMKGI2S23272/R37.htm#1>) https://content-archive.fast-edgar.com/20250314/APB2H222322292Z2222M22ZZBMKGI2S23272/R37.htm#1 — <https://content-archive.fast-edgar.com/20250314/APB2H222322292Z2222M22ZZBMKGI2S23272/R37.htm#1>
> - [350](<https://markets.ft.markitdigital.com/data/equities/tearsheet/financials?s=WMT:BRN&subview=CashFlow#1>) Walmart Inc, WMT:BRN financials - Walmart Inc — <https://markets.ft.markitdigital.com/data/equities/tearsheet/financials?s=WMT:BRN&subview=CashFlow#1>
> - [353](<https://ca.finance.yahoo.com/quote/WMT.DE/cash-flow/>) Walmart Inc. (WMT.DE) Cash Flow - Yahoo Finance - Yahoo Finance — <https://ca.finance.yahoo.com/quote/WMT.DE/cash-flow/>
> - [406](<https://www.rmwcommerce.com/blog/walmart-great-fy-2025-earnings-maytag-repairman-envious-of-consistent-performance-trump-guidance-included>) Walmart Great FY 2025 Earnings: Maytag Repairman Envious of Consistent Performance - Trump Guidance Included — <https://www.rmwcommerce.com/blog/walmart-great-fy-2025-earnings-maytag-repairman-envious-of-consistent-performance-trump-guidance-included>
> - [410](<https://www.linkedin.com/posts/ecommercestrategyconsulting_walmart-great-fy-2025-earnings-maytag-repairman-activity-7298344040473784323-d_Qn#1>) Walmart Great FY 2025 Earnings: Maytag Repairman Envious of Consistent Performance - Trump Guidance Included | Rick Watson - 跳到主要内容 — <https://www.linkedin.com/posts/ecommercestrategyconsulting_walmart-great-fy-2025-earnings-maytag-repairman-activity-7298344040473784323-d_Qn#1>
> - [413](<https://m.sgpjbg.com/bgdown/640662.html>) 沃尔玛WALMART (WMT) 2025财年综合年度报告「NYSE」（英文版）-在线下载-三个皮匠报告文库 — <https://m.sgpjbg.com/bgdown/640662.html>
> - [423](<https://www.nasdaq.com/articles/walmarts-membership-fees-jump-17-can-they-boost-profits#1>) Walmart's Membership Fees Jump 17%: Can They Boost Profits? - Walmart's Membership Fees Jump 17%: Can They Boost Profits? — <https://www.nasdaq.com/articles/walmarts-membership-fees-jump-17-can-they-boost-profits#1>
> - [428](<https://www.grocerydive.com/news/walmart-sams-club-convenience-delivery-membership-growth/740671/?utm_campaign=Yahoo-Licensed-Content-rreditorial&utm_source=yahoo&utm_medium=newsfeed>) Walmart’s push for convenience pays off in membership growth — <https://www.grocerydive.com/news/walmart-sams-club-convenience-delivery-membership-growth/740671/?utm_campaign=Yahoo-Licensed-Content-rreditorial&utm_source=yahoo&utm_medium=newsfeed>
> - [441](<https://www.edgarparser.com/COST/2025/FY>) COST - COSTCO WHOLESALE CORP /NEW FY 2025 Financial Data — <https://www.edgarparser.com/COST/2025/FY>
> - [457](<https://symbology.online/companies/COST/changes/business-description#diff-06a32e23-dded-7edc-8000-c88cdeb371eb>) Costco Wholesale Corp /new Business Description synthesis. — <https://symbology.online/companies/COST/changes/business-description#diff-06a32e23-dded-7edc-8000-c88cdeb371eb>
> - [460](<https://www.gurufocus.com/term/payments-to-suppliers-for-goods-and-services/CEUX:CTOD>) Costco Wholesale (CEUX:CTOD) Payments to Suppliers for Good — <https://www.gurufocus.com/term/payments-to-suppliers-for-goods-and-services/CEUX:CTOD>
> - [474](<https://content.edgar-online.com/ExternalLink/EDGAR/0000104169-25-000021.html?hash=0a3e3b0e1843987c1ba4bcdcf691a962e2f8c760fb7312860b47a1d3d27a9858&dest=wmt-20250131_htm_i55dba7a5534b4e0a8906aac30b2ec33b_127#wmt-20250131_htm_i55dba7a5534b4e0a8906aac30b2ec33b_127#14>) Walmart Inc. (Form: 10-K, Received: 03/14/2025 16:41:32) - Finance lease right-of-use assets, net | 6,112 | 5,855 — <https://content.edgar-online.com/ExternalLink/EDGAR/0000104169-25-000021.html?hash=0a3e3b0e1843987c1ba4bcdcf691a962e2f8c760fb7312860b47a1d3d27a9858&dest=wmt-20250131_htm_i55dba7a5534b4e0a8906aac30b2ec33b_127#wmt-20250131_htm_i55dba7a5534b4e0a8906aac30b2ec33b_127#14>
> - [491](<https://content-archive.fast-edgar.com/20240315/APBZH222322292Z2222M22ZZBMKGZ2V23262/R5.htm#1>) Consolidated Balance Sheets - USD ($) — <https://content-archive.fast-edgar.com/20240315/APBZH222322292Z2222M22ZZBMKGZ2V23262/R5.htm#1>
> - [517](<https://s201.q4cdn.com/287523651/files/doc_news/Costco-Wholesale-Corporation-Reports-Fourth-Quarter-and-Fiscal-Year-2025-Operating-Results-2025.pdf#1#1#1>) Costco Wholesale Corporation Reports Fourth Quarter and Fiscal Year 2025 Operating Results — <https://s201.q4cdn.com/287523651/files/doc_news/Costco-Wholesale-Corporation-Reports-Fourth-Quarter-and-Fiscal-Year-2025-Operating-Results-2025.pdf#1#1#1>
> - [526](<https://stock.walmart.com/_assets/_2dee1a4445bc4535cc7320ff1e66b4ae/walmart/db/950/9949/annual_report/Walmart+2025+Annual+Report.pdf#13#27#13>) Net cash provided by operating activities was \\(36.4 billion,\\) 35.7 billion and \\(28.8 billion for fiscal 2025, 2024 and 2023, ... — <https://stock.walmart.com/_assets/_2dee1a4445bc4535cc7320ff1e66b4ae/walmart/db/950/9949/annual_report/Walmart+2025+Annual+Report.pdf#13#27#13>
> - [555](<https://news.futunn.com/translate-news/notice/304003439/zh-hk/0#12>) wmt-20250131 - 沃爾瑪國際部門的淨銷售額在2025財年和2024財年分別增加了72億美元或6.3%和137億美元或13.5%，與上一個財年相比 — <https://news.futunn.com/translate-news/notice/304003439/zh-hk/0#12>
> - [597](<https://corporate.walmart.com/news/2025/02/20/walmart-releases-q4-fy25-earnings>) Walmart Releases Q4 FY25 Earnings — <https://corporate.walmart.com/news/2025/02/20/walmart-releases-q4-fy25-earnings>
> - [628](<https://stock.walmart.com/_assets/_03bc6c6c19d917c293f3e6e109724517/walmart/db/938/9939/presentation/Earnings+Presentation+%28FY25+Q4%29.pdf#2#3#2>) Continued strength in Sam's Club and eCommerce, with eCommerce sales growth of \\(34\\%\\) Opened 6 new clubs in the past 12 months... — <https://stock.walmart.com/_assets/_03bc6c6c19d917c293f3e6e109724517/walmart/db/938/9939/presentation/Earnings+Presentation+%28FY25+Q4%29.pdf#2#3#2>
> - [631](<http://news.10jqka.com.cn/field/sn/20260423/57576897.shtml?_x_output_type_b6db407c4_=embedded_pdf#12#25#12>) Net sales for the Sam's Club U — <http://news.10jqka.com.cn/field/sn/20260423/57576897.shtml?_x_output_type_b6db407c4_=embedded_pdf#12#25#12>
> - [670](<https://www.insidermonkey.com/news/costco-cost-collects-more-membership-fees-how-much-does-it-give-back-1845085/#1>) Costco (COST) Collects More Membership Fees. How Much Does It Give Back? - Costco (COST) Collects More Membership Fees. How Much Does It Give Back? — <https://www.insidermonkey.com/news/costco-cost-collects-more-membership-fees-how-much-does-it-give-back-1845085/#1>
> - [673](<https://finance.yahoo.com/markets/stocks/articles/costco-cost-collects-more-membership-022301447.html#1>) Costco (COST) Collects More Membership Fees. How Much Does It Give Back? - Skip to main content — <https://finance.yahoo.com/markets/stocks/articles/costco-cost-collects-more-membership-022301447.html#1>
> - [679](<https://www.consumeraffairs.com/news/costco-to-raise-membership-fee-for-the-first-time-in-7-years-071224.html#1>) Costco to raise membership fee for the first time in 7 years - Costco to raise membership fee for the first time in 7 years — <https://www.consumeraffairs.com/news/costco-to-raise-membership-fee-for-the-first-time-in-7-years-071224.html#1>
> - [763](<https://stock.walmart.com/sec-filings/all-sec-filings/content/0000104169-25-000021/wmt-20250131.htm#2>) March 14, 2025 - 10-K: Annual report \[Section 13 and 15(d), not S-K Item 405\] | Walmart Inc. (WMT) — <https://stock.walmart.com/sec-filings/all-sec-filings/content/0000104169-25-000021/wmt-20250131.htm#2>
> - [785](<https://app.stocklight.com/stocks/us/nasdaq-cost/costco-wholesale/annual-reports/nasdaq-cost-2009-10K-091122916.pdf#5#18#5>) | Increase (decrease) in comparable warehouse sales | (4)% | 8%    | 6%    | — <https://app.stocklight.com/stocks/us/nasdaq-cost/costco-wholesale/annual-reports/nasdaq-cost-2009-10K-091122916.pdf#5#18#5>
> - [792](<https://oregonbusinessreport.com/2009/03/analyzing-shoppingtrends-costco-bjs-target-and-walmart/print/#comments_controls>) Oregon Business Report Analyzing ShoppingTrends: Costco, BJs, Target and Walmart — <https://oregonbusinessreport.com/2009/03/analyzing-shoppingtrends-costco-bjs-target-and-walmart/print/#comments_controls>
> - [799](<https://journalrecord.com/2009/07/weak-retail-sales-in-june-raise-worries/>) Weak retail sales in June raise worries | The Journal Record — <https://journalrecord.com/2009/07/weak-retail-sales-in-june-raise-worries/>
> - [800](<https://www.sandiegouniontribune.com/2009/01/09/retail-chains-weakened-by-dismal-holiday-sales/>) Retail chains weakened by dismal holiday sales — <https://www.sandiegouniontribune.com/2009/01/09/retail-chains-weakened-by-dismal-holiday-sales/>
> - [803](<https://www.cnbc.com/2009/05/07/retailers-report-smaller-sales-declines-in-april.html#1>) Retailers Report Smaller Sales Declines in April - Consumers enticed by warmer weather and glimmers of hope for the economy bought a few more items in April, helping discounter Wa... — <https://www.cnbc.com/2009/05/07/retailers-report-smaller-sales-declines-in-april.html#1>
> - [813](<https://companiesmarketcap.com/sgd/costco/sec-reports-10k/0001193125-10-230379/#4>) Costco - 10-K annual report 2010 - to be negatively impacted by general economic conditions, and those conditions may continue to have a significant adverse impact... — <https://companiesmarketcap.com/sgd/costco/sec-reports-10k/0001193125-10-230379/#4>
> - [825](<https://us.kabutan.jp/disclosures/0000104169-25-000021?lang=ja#15>) ウォルマートの年次報告 - The Company utilizes various inventory methods to account for and value its inventories depending upon the nature of the store f... — <https://us.kabutan.jp/disclosures/0000104169-25-000021?lang=ja#15>

</details>

## Interface

### Web UI

![LucentThinker Web UI](pics/interface_webui.png)

### DeepSeek Harness plugin

![LucentThinker in DeepSeek Harness](pics/Interface_DSH_plugin.png)

## Benchmark

This benchmark evaluates three research applications on five tasks spanning energy, health, software, business and trade.

- **LucentThinker**
- **MiroThinker** — deep mode in the paid commercial product
- **GPT Deep Research** — GPT-6 Pro + Deep Research

**gpt-6-astra** scores their responses against the same six-dimensional rubric.

![Research Quality Benchmark](benchmarks/2026-11-02/en/score.png)

Author-organized, non-blind evaluation, with one response per application per task.

[Report & answers](benchmarks/2026-11-02/en/README.md) · [Questions](benchmarks/2026-11-02/en/questions.md) · [Scoring](benchmarks/2026-11-02/en/methodology.md) · [Download ZIP](benchmarks/2026-11-02/lucentthinker-benchmark-en.zip)

## Install

**DSH plugin** — Open **Plugins → Add plugin**, enter `dsh-plugin-lucentthinker`, and enable it. Includes runtimes for macOS Apple Silicon and Windows x64. [Plugin guide](dsh-plugin/README.md)

**Standalone Web UI** — Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then clone the project.

```sh
git clone https://github.com/XinYu-pumch/LucentThinker.git
cd LucentThinker
```

On **macOS**, run the following command or double-click `Launch LucentThinker.command`.

```sh
./start.sh --open
```

On **Windows**, double-click `start.cmd`.

Dependencies install automatically, then the UI opens at [localhost:8765](http://127.0.0.1:8765). Close the launch terminal or press Ctrl+C to stop.

## Configure

1. In Settings, enter your DeepSeek API key under both **DeepSeek** and **Search & Fetch**.

   ![DeepSeek model provider settings](pics/setting_llm.png)

   ![DeepSeek Search & Fetch settings](pics/settings_search.png)

2. Refresh the model list and add **DeepSeek Flash**. Set its thinking level to **Max** (recommended), then select it for both the **main model** and **extraction model**.
3. Choose a research depth, enter your question, and start.

Other providers are supported, with thinking configurations for major model families. [Advanced guide in Chinese](docs/advanced.zh-CN.md)

## Acknowledgements

[LINUX DO](https://linux.do/) · [Reddit](https://www.reddit.com/)

## License

[GPL-3.0-or-later](LICENSE) · [Attribution and notices](NOTICE)
