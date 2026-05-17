"""
AlphaRadar — Beginner's Guide & How-To
=======================================
Complete strategy explainer + step-by-step usage instructions.
Shown as the FIRST tab in app.py.
"""
import streamlit as st

try:
    st.set_page_config(page_title="Guide — AlphaRadar", page_icon="📖", layout="wide")
except Exception:
    pass

st.markdown("""
<style>
.stApp { background:#ffffff; }
.main .block-container { padding:0.5rem 1.2rem 2rem; max-width:100%; }
.guide-hero {
    background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);
    border-radius:12px; padding:28px 32px; margin-bottom:24px;
}
.guide-hero h1 { color:#fff; font-size:1.6rem; font-weight:800; margin:0 0 6px; }
.guide-hero p  { color:rgba(255,255,255,0.65); font-size:0.9rem; margin:0; }
.stage-card {
    border-radius:10px; padding:14px 18px; margin:6px 0;
    border-left:4px solid #ccc;
}
.s2a  { border-color:#059669; background:#f0fdf4; }
.s2b  { border-color:#10b981; background:#ecfdf5; }
.s1b  { border-color:#3b82f6; background:#eff6ff; }
.s1a  { border-color:#94a3b8; background:#f8fafc; }
.s3   { border-color:#d97706; background:#fffbeb; }
.s4   { border-color:#dc2626; background:#fef2f2; }
.stage-name { font-size:1rem; font-weight:700; }
.stage-sub  { font-size:0.8rem; color:#64748b; margin-top:2px; }
.step-box   { background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:16px 20px; margin:8px 0; }
.step-num   { display:inline-block; width:26px; height:26px; border-radius:50%; background:#2563eb; color:#fff; font-size:12px; font-weight:700; text-align:center; line-height:26px; margin-right:10px; }
.warn-box   { background:#fef2f2; border:1px solid #fecaca; border-radius:8px; padding:12px 16px; font-size:13px; color:#991b1b; margin:8px 0; }
.ok-box     { background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:12px 16px; font-size:13px; color:#166534; margin:8px 0; }
.info-box   { background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; padding:12px 16px; font-size:13px; color:#1e40af; margin:8px 0; }
.tab-badge  { display:inline-block; font-size:11px; font-weight:600; padding:3px 10px; border-radius:12px; margin-right:6px; }
.badge-p1   { background:#fef2f2; color:#991b1b; }
.badge-p2   { background:#fffbeb; color:#92400e; }
.badge-p3   { background:#eff6ff; color:#1e40af; }
.badge-p4   { background:#f8fafc; color:#475569; }
table.guide { width:100%; border-collapse:collapse; font-size:13px; margin:8px 0; }
table.guide th { background:#f1f5f9; padding:8px 12px; text-align:left; font-weight:600; color:#374151; }
table.guide td { padding:8px 12px; border-bottom:1px solid #f1f5f9; color:#374151; vertical-align:top; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="guide-hero">
  <h1>📖 AlphaRadar — Complete Beginner's Guide</h1>
  <p>What is this tool · How it works · Step-by-step usage · Strategy explained · Glossary</p>
</div>
""", unsafe_allow_html=True)

gtab1, gtab2, gtab3, gtab4, gtab5 = st.tabs([
    "🗺 What Is AlphaRadar",
    "📐 Stages & Scores Explained",
    "🔄 Daily Workflow",
    "📟 Telegram Alerts",
    "⚙️ Technical Setup",
])

# ═══════════════════════════════════════════════
# TAB 1: WHAT IS ALPHARADAR
# ═══════════════════════════════════════════════
with gtab1:
    st.markdown("### What problem does AlphaRadar solve?")
    st.markdown("""
AlphaRadar answers one question every day: **"Which NSE stocks are worth buying right now, and which should I avoid?"**

It combines 3 legendary trading frameworks into a single score for every NSE stock:
- **Stan Weinstein's Stage Analysis** — Is the stock in an uptrend, base, or decline?
- **William O'Neil's Relative Strength** — Is this stock outperforming the market?
- **Mark Minervini's SEPA** — Does it pass all the trend template criteria?

Instead of checking charts manually for 750 stocks, AlphaRadar does this automatically every evening.
""")

    st.divider()
    st.markdown("### The 5 Tabs — When to Use Each")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
<div class="step-box">
<span class="tab-badge badge-p1">Priority 1</span><strong>📡 Market Pulse</strong><br>
<span style="font-size:13px;color:#475569">Open this FIRST every day. It tells you whether the market environment is healthy enough to buy stocks at all. If the market is in bear mode, skip the other tabs and protect capital.</span><br>
<em style="font-size:12px;color:#64748b">Frequency: Daily, 2 minutes</em>
</div>
<div class="step-box">
<span class="tab-badge badge-p1">Priority 2</span><strong>◎ Nifty Total Market</strong><br>
<span style="font-size:13px;color:#475569">Full scoring for all 750+ NSE stocks. This is where you see today's new buy signals, stage changes, and the complete filtered table. Source of your Telegram alerts.</span><br>
<em style="font-size:12px;color:#64748b">Frequency: Daily, 5 minutes</em>
</div>
""", unsafe_allow_html=True)

    with col2:
        st.markdown("""
<div class="step-box">
<span class="tab-badge badge-p2">Priority 3</span><strong>🏆 N500 Ranker</strong><br>
<span style="font-size:13px;color:#475569">A shortlisting tool. Filter by index (Nifty 50 / Midcap / Smallcap), grade, sector, and get a clean ranked table. Use to generate your daily shortlist before scanning charts.</span><br>
<em style="font-size:12px;color:#64748b">Frequency: Daily, 5 minutes</em>
</div>
<div class="step-box">
<span class="tab-badge badge-p3">Priority 4</span><strong>🎯 Manas Arora Scanner</strong><br>
<span style="font-size:13px;color:#475569">Live Breeze scan for VCP/SVRO entry patterns. Use AFTER shortlisting from NTM/Ranker. Requires fresh session token daily. Not useful if market is weak.</span><br>
<em style="font-size:12px;color:#64748b">Frequency: Daily (pre-market), 10 minutes</em>
</div>
<div class="step-box">
<span class="tab-badge badge-p4">Portfolio</span><strong>📊 N250F Momentum</strong><br>
<span style="font-size:13px;color:#475569">A separate fortnightly rebalancing strategy. Check only every 2 weeks on rebalance day. Not a daily tab. Completely independent of the other 4 tabs.</span><br>
<em style="font-size:12px;color:#64748b">Frequency: Fortnightly</em>
</div>
""", unsafe_allow_html=True)

    st.divider()
    st.markdown("### Where does the data come from?")
    st.markdown("""
<table class="guide">
<tr><th>Component</th><th>Data Source</th><th>Update Frequency</th><th>Limitation</th></tr>
<tr><td>All scores (Stage, RS, VP)</td><td>yfinance EOD</td><td>Daily ~4:45 PM via GitHub Actions</td><td>Based on previous day's close. Not intraday.</td></tr>
<tr><td>Live CMP overlay</td><td>Breeze API</td><td>On-demand (click Refresh)</td><td>Requires fresh session token each day</td></tr>
<tr><td>N250F backtest</td><td>yfinance historical</td><td>Static (baked into code)</td><td>Survivorship bias risk (delisted stocks excluded)</td></tr>
<tr><td>Market breadth</td><td>yfinance EOD</td><td>Daily ~4:45 PM</td><td>Same as scores — previous close</td></tr>
</table>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════
# TAB 2: STAGES & SCORES
# ═══════════════════════════════════════════════
with gtab2:
    st.markdown("### Weinstein Stage Analysis — The Core Framework")
    st.markdown("Every stock is always in one of 6 stages based on its 30-week moving average:")

    stages = [
        ("s2a", "Stage 2A — Early Uptrend ✅ BUY ZONE",
         "Price just broke above the 30-week MA. MA is rising. This is the ideal entry point — the base has formed and the uptrend is just beginning. Score capped at 100."),
        ("s2b", "Stage 2B — Extended Uptrend ⚠️ HOLD / WAIT",
         "Price is well above the 30-week MA (>20% extended). Still an uptrend but risk of buying is higher. Better to wait for a pullback to the MA. Score capped at 90."),
        ("s1b", "Stage 1B — Late Basing 👀 WATCHLIST",
         "Stock is basing (trading sideways). MA is starting to flatten/turn up. May break into Stage 2 soon. Add to watchlist. NOT a buy yet — wait for the breakout above 30W MA."),
        ("s1a", "Stage 1A — Early Basing 💤 WAIT",
         "Stock is still in early base. MA is flat or slightly declining. No action. Monitor every few weeks."),
        ("s3", "Stage 3 — Distribution 🚩 EXIT",
         "Stock is topping out. Price is rolling over the 30-week MA. If you hold, start reducing. Do NOT buy."),
        ("s4", "Stage 4 — Downtrend ❌ AVOID / SELL",
         "Price is below a declining 30-week MA. Score is hard-capped at 20. Do NOT buy regardless of how 'cheap' it looks. Exit any existing positions."),
    ]

    for cls, name, desc in stages:
        st.markdown(f"""
<div class="stage-card {cls}">
  <div class="stage-name">{name}</div>
  <div class="stage-sub">{desc}</div>
</div>
""", unsafe_allow_html=True)

    st.divider()
    st.markdown("### The Composite Score (0–100)")
    col1, col2 = st.columns([1.2, 1])
    with col1:
        st.markdown("""
<table class="guide">
<tr><th>Component</th><th>Weight</th><th>What It Measures</th></tr>
<tr><td>Weinstein Stage</td><td>~30 pts</td><td>Trend direction (Stage 2A=30, 4=3)</td></tr>
<tr><td>O'Neil RS</td><td>~25 pts</td><td>Outperformance vs Nifty + sector rank</td></tr>
<tr><td>Volume/Price</td><td>~25 pts</td><td>Accumulation signals, vol surges</td></tr>
<tr><td>Fundamentals</td><td>~12 pts</td><td>Earnings quality (placeholder data currently)</td></tr>
<tr><td>Catalyst</td><td>~8 pts</td><td>News sentiment (auto-fetched)</td></tr>
</table>
""", unsafe_allow_html=True)
        st.markdown("""
<div class="warn-box">⚠️ <strong>Current max score is ~75–78, not 100.</strong> The Fundamentals and Catalyst factors use placeholder/limited data. This equally affects all stocks — relative ranking is still accurate. Once live earnings data is integrated, top stocks will reach 85–95+.</div>
""", unsafe_allow_html=True)

    with col2:
        st.markdown("**Score → Action bucket:**")
        st.markdown("""
<table class="guide">
<tr><th>Score</th><th>Bucket</th><th>Action</th></tr>
<tr><td>80–100</td><td>🟢 Must Buy</td><td>Enter on pullback or breakout</td></tr>
<tr><td>60–79</td><td>🔵 Can Buy</td><td>Add to watchlist, wait for trigger</td></tr>
<tr><td>40–59</td><td>⚪ Neutral</td><td>No action. Skip.</td></tr>
<tr><td>20–39</td><td>🟡 Avoid</td><td>Do not enter. Tighten stops if held.</td></tr>
<tr><td>0–19</td><td>🔴 Sell</td><td>Exit immediately if held.</td></tr>
</table>
""", unsafe_allow_html=True)

    st.divider()
    st.markdown("### N500 Ranker — Grade Tiers")
    st.markdown("""
<table class="guide">
<tr><th>Grade</th><th>Strength Score</th><th>Meaning</th></tr>
<tr><td><strong>S</strong></td><td>≥ 70</td><td>Elite momentum. Strongest stocks in the universe. Highest conviction.</td></tr>
<tr><td><strong>A</strong></td><td>55–69</td><td>Strong setup. Worth detailed analysis and watchlist inclusion.</td></tr>
<tr><td><strong>B</strong></td><td>38–54</td><td>Decent but needs a catalyst or cleaner pattern before entry.</td></tr>
<tr><td><strong>C</strong></td><td>&lt; 38</td><td>Weak or declining. Avoid for new positions.</td></tr>
</table>
""", unsafe_allow_html=True)

    st.divider()
    st.markdown("### RS Percentile — Relative Strength")
    st.markdown("""
**RS Percentile** ranks a stock's 52-week return vs ALL stocks in the universe.

- **RS 90+** = Top 10% performers — these are the market leaders
- **RS 75+** = Strong outperformers — acceptable for Stage 2A entries
- **RS 50–74** = Average — needs other factors to compensate
- **RS <50** = Underperforming the market — avoid even if Stage 2A

**The Minervini Rule:** Never buy a stock with RS below 70 for a new position.

**RS New High (⭐):** When a stock's RS line hits a new 52-week high — very bullish signal. The stock is accelerating its outperformance.
""")

# ═══════════════════════════════════════════════
# TAB 3: DAILY WORKFLOW
# ═══════════════════════════════════════════════
with gtab3:
    st.markdown("### ✅ Step-by-step daily routine (15 minutes total)")

    steps = [
        ("📡 Market Pulse — 2 min", [
            "Open Market Pulse tab",
            "Check the Regime banner at top: 🟢 Strong Bull / 🟡 Cautious / 🔴 Bear Pressure",
            "If Bear Pressure: STOP. Do not look at individual stocks. Protect capital.",
            "If Bull/Cautious: check A/D ratio (want >1.2), Stage 2 count (want >150), % Above MA50 (want >55%)",
            "Note Strength in Weakness stocks if Nifty fell — these are accumulation candidates",
        ]),
        ("◎ Nifty Total Market — 3 min", [
            "Open Nifty Total Market tab",
            "Check TODAY'S HIGHLIGHTS at top: New Buy Signals (Stage 1→2A), Exit Signals, RS New Highs",
            "These 3 panels directly correspond to your evening Telegram alert messages",
            "Set filters: Bucket = MUST_BUY, Stage = 2A, Sort = Score ↓",
            "Review the filtered table — these are today's highest conviction ideas",
        ]),
        ("🏆 N500 Ranker — 5 min", [
            "Open N500 Ranker tab",
            "Select your preferred universe: 🏆 Nifty 500 for broad market, 📊 Midcap 150 for midcap focus",
            "Filter: Bucket = MUST_BUY + CAN_BUY, Grade = S + A",
            "Look for Entry Signal = BUY NOW or BUY DIPS",
            "Note stocks with RS Leader + Breakout signals — these are the cleanest setups",
            "Click Fetch Live Prices to see current CMP (if Breeze connected)",
        ]),
        ("🎯 Manas Arora Scanner — 5 min (optional)", [
            "Only run this if market is in Bull/Cautious mode",
            "Verify green Breeze status bar at top (if red, regenerate token from ICICIdirect API portal)",
            "Click Scan — runs across ~200 stocks for VCP/SVRO patterns",
            "Look for VCP Score >65, RS% >75, Stage 2A, volume drying up (tight range)",
            "Cross-reference with your N500 Ranker shortlist — stocks appearing in BOTH are highest priority",
            "Final check: open TradingView chart to confirm visually before entry",
        ]),
    ]

    for title, substeps in steps:
        with st.expander(f"**{title}**", expanded=True):
            for i, s in enumerate(substeps, 1):
                st.markdown(f'<div style="font-size:13px;padding:4px 0"><span class="step-num">{i}</span>{s}</div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### 📅 Fortnightly routine — N250F")
    st.markdown("""
1. Open **N250F** tab — check "Next Rebalance Date"
2. On rebalance day: sell any stocks showing **red "Exit" chip** at market open
3. Buy any stocks showing **green "Entry" chip** — equal weight (5% each for 20-stock portfolio)
4. No action needed on non-rebalance days
""")

    st.divider()
    st.markdown("""
<div class="warn-box">
⚠️ <strong>Universe coverage warning:</strong> The daily cron scores stocks from the <strong>Nifty Total Market universe (~750 stocks)</strong>. 
The Manas Arora scanner uses a <strong>separate curated list of ~200 stocks</strong> — it does NOT scan the full 750. 
This is a design limitation due to Breeze API rate limits for live intraday data. 
The N500 Ranker and Nifty Total Market tab DO cover the full scored universe.
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════
# TAB 4: TELEGRAM ALERTS
# ═══════════════════════════════════════════════
with gtab4:
    st.markdown("### How to read your evening Telegram messages")
    st.markdown("You receive up to 3 messages every trading day at ~4:45 PM from AlphaRadarBot:")

    st.markdown("#### Message 1 — Daily Summary (always sent)")
    st.markdown("""
```
🎯 AlphaRadar — 2026-05-15
746 stocks scored

🟢 Must Buy: 23 | 🔵 Can Buy: 89
⚪ Neutral: 412 | 🟡 Avoid: 156 | 🔴 Sell: 66

Top 5 (highest conviction):
▸ ANANDRATHI 81.7 · ₹3583 · RS 96%
...
```
**Where to see this on the website:** Market Pulse tab (bucket breakdown), N500 Ranker (top 5 stocks)
""")

    st.markdown("#### Message 2 — ACTION REQUIRED (sent when stocks enter/exit Stage 2)")
    st.markdown("""
```
📢 ACTION REQUIRED — 2026-05-15

🟢 NEW BUY SIGNALS (6):
These stocks just entered Stage 2 (uptrend confirmed)...
▸ DELHIVERY Score 79 · ₹476
  Stage 1B→2A · RS 85%
...
```
**What this means:** These stocks crossed their 30-week MA upward overnight. Weinstein Stage changed from 1A/1B → 2A.

**Where to see this on the website:** Nifty Total Market tab → "Today's Highlights" → left column "New Buy Signals". Also searchable by typing the symbol in the search box.

**What to do:** Add to watchlist. Do NOT chase immediately — wait for a pullback to the 30-week MA or a volume confirmation day.
""")

    st.markdown("#### Message 3 — WATCHLIST (sent when stocks move 1A → 1B)")
    st.markdown("""
```
👀 WATCHLIST — 2026-05-15
2 stocks moved from Stage 1A (early basing) to 1B (late basing).
Watch for breakout above the 30-week moving average.
▸ TI Score 48 · ₹431 · RS 78%
▸ UNITDSPR Score 38 · ₹1321 · RS 31%
```
**What this means:** These stocks are building a base. NOT buy signals yet. Watch for them to break above the 30-week MA with volume.

**Where to see this on the website:** Nifty Total Market tab → filter Stage = 1B
""")

    st.markdown("""
<div class="info-box">
💡 <strong>Why can't I find the Telegram stocks in Nifty Total Market tab?</strong><br><br>
The most common reason: the tab shows today's data but the cron stores ALL dates. 
Make sure the latest score_date is shown in the header (should be today or yesterday). 
Also ensure you're NOT filtering by bucket — set all filters to "All" and search for the symbol directly.
The stage_changed flag that triggers Telegram alerts is separate from the filters visible in the table.
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════
# TAB 5: TECHNICAL SETUP
# ═══════════════════════════════════════════════
with gtab5:
    st.markdown("### Daily setup checklist")
    st.markdown("""
<div class="step-box">
<strong>Step 1 — Regenerate Breeze session token (daily, takes 2 minutes)</strong><br>
<span style="font-size:13px;color:#475569">
1. Go to <a href="https://www.icicidirect.com" target="_blank">icicidirect.com</a> → Login<br>
2. Settings → API Sessions → Click "Generate Session Token"<br>
3. Copy the token<br>
4. Go to <a href="https://share.streamlit.io" target="_blank">Streamlit Cloud</a> → Your App → Settings → Secrets<br>
5. Update: <code>BREEZE_SESSION_TOKEN = "your_new_token"</code><br>
6. Save. The app reconnects automatically (takes ~10 seconds)
</span>
</div>
""", unsafe_allow_html=True)

    st.markdown("""
<div class="step-box">
<strong>Step 2 — Verify cron is running (if scores look stale)</strong><br>
<span style="font-size:13px;color:#475569">
1. Go to <a href="https://github.com/rishabhinai-netizen/alpharadar/actions" target="_blank">GitHub Actions</a><br>
2. Look for the most recent "Daily Scoring Cron" workflow run<br>
3. Should show ✅ green on each weekday after 4:45 PM IST<br>
4. If ❌ red, click the failed run to see the error, then re-run manually
</span>
</div>
""", unsafe_allow_html=True)

    st.markdown("""
<div class="step-box">
<strong>Market Pulse shows blank / "Initialize" button</strong><br>
<span style="font-size:13px;color:#475569">
This means the ar_market_pulse Supabase table is empty (first-time setup or after reset).<br>
Click the "Initialize" button — it runs a one-time scan (~5-8 minutes). After this, the cron keeps it updated daily.
</span>
</div>
""", unsafe_allow_html=True)

    st.markdown("""
<div class="step-box">
<strong>N500 Ranker or Nifty Total Market shows blank</strong><br>
<span style="font-size:13px;color:#475569">
These tabs read from Supabase ar_daily_scores. If blank, it means no scores have been written yet.<br>
Fix: Go to ⚡ Run Scoring tab → click "Initial Load". Takes ~15 minutes. Run once, then daily cron handles it.
</span>
</div>
""", unsafe_allow_html=True)

    st.divider()
    st.markdown("### Key system information")
    st.markdown("""
| Component | Details |
|-----------|---------|
| Supabase Project | nse-scanner-pro (ID: aiebaqvclyzxajigvkfd) |
| Tables | ar_daily_scores, ar_universe, ar_market_pulse, ar_ai_justifications |
| Cron schedule | GitHub Actions · Daily ~4:45 PM IST (weekdays) |
| Data source | yfinance EOD for scoring; Breeze live for CMP overlay |
| Manas Arora universe | ~200 curated stocks (NOT full 750 — Breeze rate limit) |
| N500 Ranker universe | Up to 800 stocks from ar_daily_scores |
| Market Pulse universe | ~1000 stocks from ar_market_pulse |
""")
