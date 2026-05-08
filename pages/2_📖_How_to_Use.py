"""
AlphaRadar — How to Use This Tool
==================================
Educational guide explaining every column, stage, and scoring concept.
"""
import streamlit as st

st.set_page_config(page_title="How to Use AlphaRadar", page_icon="📖", layout="wide")

st.title("📖 How to Use AlphaRadar")
st.caption("Everything you need to understand and act on AlphaRadar scores")

# ── QUICK START ──
st.header("🚀 Quick Start — 3 Rules")
st.markdown("""
1. **Only buy Stage 2 stocks** — The 30-week moving average must be rising and price must be above it
2. **Higher score = higher conviction** — Focus on 60+ scores for trade ideas
3. **Never fight the stage gate** — If a stock is Stage 4 (score capped at 20), do NOT buy it no matter how "cheap" it looks
""")

st.divider()

# ── WHAT IS THE COMPOSITE SCORE? ──
st.header("📊 The Composite Score (0–100)")
st.markdown("""
Every stock gets a single number from 0 to 100, combining 5 factors. But here's the critical insight: **Stage is not just a weight — it's a gate.** A stock in Stage 4 (declining trend) is CAPPED at 20 regardless of how good its earnings or RS look. This prevents the #1 retail mistake: buying falling stocks because they "look cheap."
""")

c1, c2 = st.columns(2)
with c1:
    st.markdown("""
    | Score | Bucket | What to Do |
    |-------|--------|------------|
    | **80–100** | 🟢 Must Buy | Strong setup. Consider entering on next pullback or breakout confirmation |
    | **60–79** | 🔵 Can Buy | Good setup forming. Add to watchlist, wait for trigger (volume breakout, earnings) |
    | **40–59** | ⚪ Neutral | No edge. Neither buy nor sell. Ignore unless something changes |
    | **20–39** | 🟡 Avoid | Deteriorating. Do NOT start new positions. If held, tighten stops |
    | **0–19** | 🔴 Sell | Stage 4 decline. Exit immediately if held. Do NOT catch falling knives |
    """)
with c2:
    st.info("""
    **Why is the max score 75 and not 100?**
    
    The Fundamentals (15%) and Catalyst (10%) factors are currently at placeholder values since we don't yet pull quarterly earnings data automatically. The maximum achievable score right now is ~75-78. Once we add real earnings data via yfinance, top stocks will reach 85-90+.
    
    **This doesn't affect ranking** — all stocks are equally affected, so relative positions remain accurate.
    """)

st.divider()

# ── THE 5 FACTORS ──
st.header("🧮 The 5 Scoring Factors")

st.subheader("1️⃣ Trend / Stage — 30 points (30% weight)")
st.markdown("""
**What it measures:** Where is the stock in its market cycle?

Stan Weinstein's Stage Analysis divides every stock's life into 4 repeating stages based on the **30-week moving average** (the average closing price over the last 30 weeks):
""")

st.markdown("""
| Stage | Name | What's Happening | 30-Week MA | Score Cap | Your Action |
|-------|------|-----------------|------------|-----------|-------------|
| **1A** | Early Basing | Stock crashed and is now building a floor. Wide, choppy sideways action. Boring. | Flat or still falling | 55 | ⏳ Too early. Watch from afar |
| **1B** | Late Basing | Base is tightening. Volume is drying up. MA flattening. Getting ready to move | Flattening | 70 | 👀 Add to watchlist. Alert on breakout above MA |
| **2A** | Early Uptrend ⭐ | **THE SWEET SPOT.** Price breaks above rising MA with volume. Institutions are buying | Rising, price above | 100 (no cap) | ✅ **BUY.** This is where the money is made |
| **2B** | Extended Uptrend | Still above rising MA but far extended (20%+ above). Late to the party | Rising, but stretched | 90 | ✅ Hold if already in. New entries risky — wait for pullback to MA |
| **3** | Distribution | MA flattening after advance. Big players are selling to retail. "The smart money exit" | Flattening from above | 40 | ⚠️ **EXIT longs.** Do not buy new. Take profits |
| **4** | Decline | Price below falling MA. Every bounce is a dead cat bounce. This is where most retail traders lose | Falling, price below | 20 | 🚫 **SELL everything.** Never buy Stage 4 |
""")

st.warning("""
**The Stage Hard Gate — Why This Matters for Your Money**

The scoring engine enforces a hard ceiling based on stage. A Stage 4 stock scores maximum 20 no matter what. This means:
- HDFCBANK with great fundamentals but in Stage 4 → Score: 18 (SELL)
- A random microcap with poor fundamentals but in Stage 2A → Score: 65 (CAN BUY)

This feels counterintuitive but is backed by decades of Weinstein's research: **trend > fundamentals for timing.**
""")

st.subheader("2️⃣ Relative Strength (RS) — 25 points (25% weight)")
st.markdown("""
**What it measures:** Is this stock outperforming the market?

A stock going up is good. A stock going up *faster than Nifty 50* is better. RS measures this edge.
""")

st.markdown("""
| Column | What It Shows | How to Read It |
|--------|--------------|----------------|
| **RS Pctl** (RS Percentile) | Where this stock ranks among all 750 stocks by 52-week performance | RS 90% = beats 90% of all stocks. RS 10% = in the bottom 10%. **Above 70% is strong** |
| **Sec Pctl** (Sector Percentile) | Same ranking but within its own sector | RS Pctl 80% + Sec Pctl 90% = stock is strong AND it's the sector leader. Best combo |
| **RS★** (RS New High) | Is the RS line at a new 52-week high? | ⭐ = The stock is at peak relative performance vs Nifty. Very bullish signal |
""")

st.success("""
**Pro tip:** The best trades come from stocks with RS Percentile > 80 AND RS★ = true AND Stage 2A. These are the market's true leaders.
""")

st.subheader("3️⃣ Volume & Price (VP) — 20 points (20% weight)")
st.markdown("""
**What it measures:** Are institutions accumulating (buying) or distributing (selling)?

Based on William O'Neil's CANSLIM and Mark Minervini's VCP patterns. The VP score captures:
- **Accumulation:** Are up-days happening on above-average volume? (Institutions buying)
- **Volume dry-up:** Is volume shrinking on pullbacks? (Selling pressure drying up — bullish)
- **Tight closes:** Are weekly closing prices narrowing? (Volatility contraction — breakout coming)
- **Base quality:** Is the correction shallow (10-25%) or deep (35%+)? Shallow = strong, deep = damaged
- **Distance from pivot:** How close to a breakout point (52-week high)?

**VP Score 15+** = Strong institutional accumulation, tight base, near breakout
**VP Score 8-14** = Moderate, some positive patterns
**VP Score < 8** = Weak price action, distribution, or no clear pattern
""")

st.subheader("4️⃣ Fundamentals — 15 points (15% weight)")
st.markdown("""
**What it measures:** Is the company's business growing?

Currently at a **placeholder value of 7.5/15** for all stocks. When fully integrated, it will score:
- EPS growth (quarter over quarter, year over year)
- Revenue growth
- ROE / ROCE trajectory
- Margin expansion or contraction
- Earnings surprise (beat vs miss)

**Why is it a placeholder?** Fetching quarterly financials for 750 stocks hits API rate limits. This is being built out. The current 7.5 default doesn't affect relative rankings since all stocks get the same value.
""")

st.subheader("5️⃣ Catalyst — 10 points (10% weight)")
st.markdown("""
**What it measures:** Are there near-term triggers?

Currently at **placeholder value of 1/10**. When fully integrated, it will score:
- News sentiment (positive/negative media coverage)
- Bulk/block deals (institutional buying signals)
- Earnings date proximity (catalyst approaching)
- Corporate actions (buyback, bonus, split)
- FII/DII flow data
""")

st.divider()

# ── OTHER COLUMNS ──
st.header("📋 Column Reference")

st.markdown("""
| Column | Full Name | What It Means | How to Use |
|--------|-----------|---------------|------------|
| **Score** | Composite Score | Overall 0-100 rating | Higher = better. 60+ for trade ideas |
| **Δ Score** | Score Change | Change vs previous scoring day | Large positive = momentum improving. Large negative = deteriorating fast |
| **Bucket** | Classification | Must Buy / Can Buy / Neutral / Avoid / Sell | Your primary filter. Focus on Can Buy+ |
| **Stage** | Weinstein Stage | 1A, 1B, 2A, 2B, 3, or 4 | Only buy 2A/2B. See stage table above |
| **Price** | Latest closing price | In Indian Rupees | For reference |
| **Chg%** | Daily price change | Today vs yesterday | For context, not for decisions |
| **RS Pctl** | RS Percentile | Rank among all stocks (0-100) | >70 is strong, >90 is elite |
| **Sec Pctl** | Sector Percentile | Rank within sector (0-100) | >70 = sector leader |
| **Stg** | Stage Score | Points from trend analysis (0-30) | Higher = cleaner uptrend |
| **RS** | RS Score | Points from relative strength (0-25) | Higher = outperforming market |
| **VP** | Volume-Price Score | Points from volume analysis (0-20) | Higher = institutional buying |
| **RS★** | RS New High | Is RS line at 52-week high? | ⭐ = very bullish confirmation |
| **Capped** | Stage Cap Applied | Was the raw score capped by stage? | If capped, the stock would score higher IF it were in a better stage |
| **Stg Chg** | Stage Changed | Did the stage change today? | Transitions into Stage 2 = buy signal. Into Stage 4 = sell signal |
""")

st.divider()

# ── HOW TO USE THIS DAILY ──
st.header("📅 Daily Workflow")

st.markdown("""
### Every Evening (After 4:45 PM IST)

1. **Check Telegram** — You'll get 2-3 messages:
   - 📊 Daily summary (market overview)
   - 🟢 New buy signals (stocks entering Stage 2) — **these are your trade ideas**
   - 🔴 Exit signals (stocks leaving Stage 2) — **check if you hold any**
   - 👀 Watchlist (stocks approaching Stage 2)

2. **Open the Dashboard** — Filter by:
   - **Bucket = Can Buy** to see your trade universe
   - **Stage = 2A** to see the freshest breakouts
   - **Sort by RS% ↓** to see the strongest movers first

3. **For any stock that interests you:**
   - Click it to see the full factor breakdown
   - Check RS Percentile (want >70) and RS★ (want ⭐)
   - Check VP score (want >12 for strong accumulation)
   - Then go to your charting tool (TradingView, Zerodha) to time the entry

### Weekly (Sunday)
- Scan the full "Can Buy" list for new additions
- Remove "Avoid" and "Sell" stocks from your watchlist
- Check which sectors have the most Stage 2 stocks (sector rotation)
""")

st.divider()

# ── DATA SOURCE ──
st.header("🔌 Data Sources")
st.markdown("""
| Data | Source | Update Frequency | Notes |
|------|--------|-----------------|-------|
| **Price & Volume** | yfinance (Yahoo Finance) | Daily EOD | Free, reliable, 15-min delayed. No API key needed |
| **Stock Universe** | NSE Indices official CSVs | Weekly check | Nifty Total Market Index (~755 stocks) |
| **Benchmark** | Nifty 50 (^NSEI via yfinance) | Daily EOD | Used for RS calculation |
| **Scoring** | AlphaRadar Engine | Daily at 4:45 PM IST | GitHub Actions cron job |
| **Storage** | Supabase (PostgreSQL) | Continuous | Free tier, ap-south-1 (Mumbai) |

**Breeze API (ICICI Direct)** is configured but not yet integrated. When added, it will provide:
- Real-time intraday data (no 15-min delay)
- F&O Open Interest data
- Live websocket feed for intraday alerts

Currently, the Breeze session token is NOT needed. All data comes from yfinance which requires no authentication.
""")

st.divider()

st.header("⚠️ Disclaimer")
st.markdown("""
AlphaRadar is a **screening and scoring tool**, not a trading signal service. The scores indicate technical and fundamental quality — they do NOT tell you:
- The exact entry price or stop loss
- Position size
- How long to hold

**Always combine AlphaRadar scores with:**
- Your own chart analysis (support/resistance, patterns)
- Risk management (stop loss, position sizing)
- Fundamental due diligence for larger positions

Past stage accuracy: 100% on validation set of 15 stocks. But markets change and no model is perfect.
""")
