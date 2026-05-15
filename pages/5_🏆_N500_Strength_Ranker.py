"""
AlphaRadar — Nifty 500 Strength Ranker
=======================================
Ranks all Nifty 500 stocks from strongest to weakest using:
  • Breeze API  → live CMP + 1D return (real-time during market hours)
  • Supabase    → OHLCV history for 1W / 1M / 3M / 1Y returns
  • Scoring     → RS percentile, Stage, Volume pattern, Breakout flags
  • Claude API  → one-line signal justification per stock
  • Signal tags → RS Leader | Breakout | Stage-2 | News-Driven⚑ | Vol-Surge | Weak
"""

import math
import time
import json
import requests
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import sys, os

# ── Breeze ─────────────────────────────────────────────────────────────────
try:
    from breeze_connect import BreezeConnect
    BREEZE_OK = True
except ImportError:
    BREEZE_OK = False

# ── Constants ───────────────────────────────────────────────────────────────
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]
SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

BREEZE_MAP = {
    "MAZDOCK":    "MAZDOC",
    "COCHINSHIP": "COCHIN",
    "LGEQUIP":    "LGEQU",
    "MIRZAINT":   "MIRZAI",
    "ADANIENT":   "ADANIENS",
    "M&M":        "M&M",
    "M&MFIN":     "M&MFIN",
}

SIGNAL_COLORS = {
    "RS Leader":    ("#dceeff", "#0c3d7a"),
    "Breakout":     ("#d4f0e0", "#0f5c2e"),
    "Stage 2":      ("#e8d4f0", "#4a0f7a"),
    "News-Driven⚑": ("#fff3cd", "#7a4f00"),
    "Vol Surge":    ("#d4eaf0", "#0f4a5c"),
    "Weak":         ("#fde8e8", "#7a1f1f"),
    "Neutral":      ("#f1efe8", "#5f5e5a"),
}

# ── Supabase helpers ─────────────────────────────────────────────────────────
def sb_get(table, select="*", qs="", limit=2000):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}&limit={limit}"
    if qs:
        url += f"&{qs}"
    try:
        r = requests.get(url, headers=SB_HEADERS, timeout=30)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def load_latest_scores():
    """Load most-recent ar_daily_scores from Supabase."""
    latest = sb_get("ar_daily_scores", "score_date", "order=score_date.desc&limit=1")
    if not latest:
        return pd.DataFrame(), "N/A"
    ld = latest[0]["score_date"]
    data = sb_get(
        "ar_daily_scores",
        "symbol,composite_score,bucket,weinstein_stage,rs_percentile,"
        "rs_new_high,volume_score,stage_score,breakout_flag,"
        "price_vs_ma30w,ma30w_slope,score_date",
        f"score_date=eq.{ld}&order=composite_score.desc",
        limit=2000,
    )
    return pd.DataFrame(data) if data else pd.DataFrame(), ld


@st.cache_data(ttl=600, show_spinner=False)
def load_universe():
    data = sb_get("ar_universe", "symbol,company_name,industry,sector,cap_bucket,yf_ticker", "is_active=eq.true", limit=2000)
    return {d["symbol"]: d for d in data} if data else {}


@st.cache_data(ttl=600, show_spinner=False)
def load_daily_ohlcv_batch():
    """Load 1 year of daily OHLCV for all stocks from Supabase."""
    cutoff = (datetime.now() - timedelta(days=380)).strftime("%Y-%m-%d")
    data = sb_get(
        "ar_daily_ohlcv",
        "symbol,trade_date,close,volume",
        f"trade_date=gte.{cutoff}&order=symbol.asc,trade_date.asc",
        limit=200000,
    )
    if not data:
        return {}
    df = pd.DataFrame(data)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    grouped = {}
    for sym, g in df.groupby("symbol"):
        grouped[sym] = g.sort_values("trade_date").reset_index(drop=True)
    return grouped


# ── Breeze connection ─────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_breeze():
    if not BREEZE_OK:
        return None, "breeze_connect not installed"
    try:
        b = BreezeConnect(api_key=st.secrets["BREEZE_API_KEY"])
        b.generate_session(
            api_secret=st.secrets["BREEZE_API_SECRET"],
            session_token=st.secrets["BREEZE_SESSION_TOKEN"],
        )
        return b, None
    except KeyError as e:
        return None, f"Missing secret: {e}"
    except Exception as e:
        err = str(e)
        if any(w in err.lower() for w in ["session", "token", "auth", "invalid"]):
            return None, "🔄 Session token expired — go to ICICIdirect.com → API → Generate Session → update BREEZE_SESSION_TOKEN in Streamlit Secrets."
        return None, f"Breeze error: {err}"


@st.cache_data(ttl=90, show_spinner=False)
def fetch_live_prices(symbols: tuple) -> dict:
    """Fetch live LTP + prev_close from Breeze for up to 500 symbols in batches."""
    breeze, err = get_breeze()
    result = {}
    if err or not breeze:
        return result

    for sym in symbols:
        try:
            resp = breeze.get_quotes(
                stock_code=BREEZE_MAP.get(sym, sym),
                exchange_code="NSE",
                product_type="cash",
                expiry_date="",
                right="",
                strike_price="",
            )
            if resp and resp.get("Success"):
                d = resp["Success"][0]
                ltp  = float(d.get("last_rate", 0) or 0)
                prev = float(d.get("previous_close", 0) or 0)
                vol  = float(d.get("total_quantity_traded", 0) or 0)
                avg5 = float(d.get("average_price", 0) or 0)
                open_ = float(d.get("open_rate", 0) or 0)
                high_ = float(d.get("high_rate", 0) or 0)
                low_  = float(d.get("low_rate", 0) or 0)
                if ltp > 0:
                    result[sym] = {
                        "cmp":        round(ltp, 2),
                        "prev_close": round(prev, 2) if prev > 0 else ltp,
                        "chg_1d":     round((ltp - prev) / prev * 100, 2) if prev > 0 else 0.0,
                        "vol_today":  int(vol),
                        "open":       round(open_, 2),
                        "high":       round(high_, 2),
                        "low":        round(low_, 2),
                    }
            time.sleep(0.05)  # ~20 req/s — safe within Breeze limits
        except Exception:
            continue
    return result


# ── Return calculations ───────────────────────────────────────────────────────
def calc_returns(sym: str, daily_map: dict, live_cmp: float | None = None) -> dict:
    """Given daily OHLCV dataframe for a symbol, calculate multi-period returns."""
    out = {"ret_1w": None, "ret_1m": None, "ret_3m": None, "ret_1y": None,
           "vol_ratio_20d": None, "at_52w_high_pct": None, "above_200d_ma": None,
           "avg_vol_20d": None}
    df = daily_map.get(sym)
    if df is None or len(df) < 5:
        return out

    closes = df["close"].values
    vols   = df["volume"].values
    cmp    = live_cmp if live_cmp else float(closes[-1])

    def pret(n):
        if len(closes) > n:
            base = float(closes[-(n+1)])
            return round((cmp - base) / base * 100, 2) if base > 0 else None
        return None

    out["ret_1w"]  = pret(5)
    out["ret_1m"]  = pret(21)
    out["ret_3m"]  = pret(63)
    out["ret_1y"]  = pret(252)

    # Volume ratio: avg last 5 days vs avg last 20 days
    if len(vols) >= 20:
        recent_vol = float(np.mean(vols[-5:]))
        base_vol   = float(np.mean(vols[-20:]))
        out["vol_ratio_20d"] = round(recent_vol / base_vol, 2) if base_vol > 0 else None
        out["avg_vol_20d"]   = int(base_vol)

    # 52-week high proximity
    if len(closes) >= 52:
        h52 = float(np.max(closes[-252:])) if len(closes) >= 252 else float(np.max(closes))
        out["at_52w_high_pct"] = round((cmp - h52) / h52 * 100, 2) if h52 > 0 else None

    # 200d MA
    if len(closes) >= 200:
        ma200 = float(np.mean(closes[-200:]))
        out["above_200d_ma"] = cmp > ma200

    return out


# ── Signal classification ─────────────────────────────────────────────────────
def classify_signal(row: dict) -> list[str]:
    """
    Returns a list of signal tags based on scoring metrics + return patterns.
    Mirrors how O'Neil, Minervini, Weinstein, and Darvas would classify.
    """
    signals = []
    score   = row.get("composite_score", 0) or 0
    rs_pct  = row.get("rs_percentile", 50) or 50
    rs_nh   = row.get("rs_new_high", False)
    stage   = str(row.get("weinstein_stage", "") or "")
    bk_flag = row.get("breakout_flag", False)
    vol_r   = row.get("vol_ratio_20d") or 1.0
    at52h   = row.get("at_52w_high_pct") or -999
    ret1m   = row.get("ret_1m") or 0
    ret3m   = row.get("ret_3m") or 0
    ret1y   = row.get("ret_1y") or 0
    above200 = row.get("above_200d_ma", False)

    # 1. RS Leader — top RS percentile, RS new high
    if rs_pct >= 85 or rs_nh:
        signals.append("RS Leader")

    # 2. Breakout — near/at 52w high with good volume OR explicit breakout_flag
    if bk_flag or (at52h is not None and at52h >= -3.0 and vol_r >= 1.5):
        signals.append("Breakout")

    # 3. Stage 2 — Weinstein Stage 2A or 2B
    if "2" in stage:
        signals.append("Stage 2")

    # 4. News-Driven⚑ — large 1M jump but 3M not proportionally large
    # Heuristic: big 1M spike (>15%) relative to the 3M trend could be event-driven
    if ret1m and ret3m and ret1m > 15 and (ret3m == 0 or ret1m > ret3m * 0.6):
        signals.append("News-Driven⚑")

    # 5. Volume Surge — rising on volume, resilient on lower volume
    if vol_r >= 1.8 and (ret1m or 0) > 0:
        signals.append("Vol Surge")

    # 6. Weak — Stage 4, below 200 MA, weak RS
    if (rs_pct < 30 and not above200) or "4" in stage or score < 30:
        signals.append("Weak")

    # Default
    if not signals:
        signals.append("Neutral")

    return signals


def strength_score(row: dict) -> float:
    """
    Composite strength score combining:
      40% — existing AlphaRadar composite_score (Weinstein+RS+Volume from Supabase)
      30% — multi-timeframe momentum (1W, 1M, 3M, 1Y)
      15% — volume character (vol_ratio)
      15% — proximity to 52W high (breakout readiness)
    Range: 0–100
    """
    base  = float(row.get("composite_score", 50) or 50)  # already 0–100
    r1w   = row.get("ret_1w") or 0
    r1m   = row.get("ret_1m") or 0
    r3m   = row.get("ret_3m") or 0
    r1y   = row.get("ret_1y") or 0
    vol_r = row.get("vol_ratio_20d") or 1.0
    at52h = row.get("at_52w_high_pct") or -50

    # Momentum sub-score (0–100)
    mom = (
        np.clip(r1w  * 4,   -10, 10) +
        np.clip(r1m  * 1.5, -20, 20) +
        np.clip(r3m  * 0.5, -20, 20) +
        np.clip(r1y  * 0.1, -10, 10) +
        50  # center at 50
    )
    mom = np.clip(mom, 0, 100)

    # Volume sub-score (0–100)
    vol_s = np.clip((vol_r - 1) * 30 + 50, 0, 100)

    # 52W High proximity (0–100); at ATH = 100, 20% away = 0
    h52_s = np.clip(100 + at52h * 5, 0, 100)

    total = 0.40 * base + 0.30 * mom + 0.15 * vol_s + 0.15 * h52_s
    return round(float(total), 2)


# ── Claude API — batch justifications ────────────────────────────────────────
def get_claude_justifications(stocks_batch: list[dict]) -> dict:
    """
    Call Claude API once with a batch of up to 30 stocks.
    Returns {symbol: "one-line justification"} dict.
    """
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY") or st.secrets.get("anthropic_api_key", "")
        if not api_key:
            return {}

        prompt_lines = []
        for s in stocks_batch:
            prompt_lines.append(
                f"{s['symbol']} | Score={s['score']:.0f} | Stage={s['stage']} | "
                f"RS%ile={s['rs_pct']:.0f} | 1D={s['ret_1d']:+.1f}% | "
                f"1W={s['ret_1w']:+.1f}% | 1M={s['ret_1m']:+.1f}% | "
                f"3M={s['ret_3m']:+.1f}% | 1Y={s['ret_1y']:+.1f}% | "
                f"VolRatio={s['vol_r']:.1f} | 52WH={s['at52h']:+.1f}% | "
                f"Signals={','.join(s['signals'])}"
            )

        system = (
            "You are a top equity analyst (O'Neil + Minervini + Weinstein methodology). "
            "For each NSE stock given, write EXACTLY ONE LINE (max 12 words) explaining "
            "why it is strong or weak. Be specific — mention the exact strength/weakness. "
            "Use trader language: 'Stage 2 breakout with volume', 'RS new high, expanding margins', "
            "'Extended after earnings pop — limited upside near term', 'Below 200MA, Stage 4 decline'. "
            "For News-Driven stocks with ⚑, flag with '⚑' in the justification. "
            "Return ONLY a JSON object: {\"SYMBOL\": \"one-line justification\", ...}. "
            "No extra text, no markdown, no preamble."
        )

        user = "Analyse these stocks:\n" + "\n".join(prompt_lines)

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json"},
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return {}
        text = resp.json()["content"][0]["text"].strip()
        # Strip markdown fences if present
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception:
        return {}


# ── Formatting helpers ────────────────────────────────────────────────────────
def fmt_ret(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    color = "#1a7a4a" if v > 0 else ("#c0392b" if v < 0 else "#888")
    arrow = "▲" if v > 0 else ("▼" if v < 0 else "")
    return f'<span style="color:{color};font-weight:500">{arrow}{abs(v):.1f}%</span>'


def fmt_cmp(v):
    if v is None:
        return "—"
    return f"₹{v:,.2f}"


def render_signals(signals: list[str]) -> str:
    parts = []
    for s in signals:
        bg, fg = SIGNAL_COLORS.get(s, ("#eee", "#333"))
        parts.append(
            f'<span style="background:{bg};color:{fg};padding:2px 7px;'
            f'border-radius:4px;font-size:11px;font-weight:500;white-space:nowrap">{s}</span>'
        )
    return " ".join(parts)


def score_badge(score: float) -> str:
    if score >= 75:
        bg, fg, g = "#d4f0e0", "#0f5c2e", "S"
    elif score >= 60:
        bg, fg, g = "#dceeff", "#0c3d7a", "A"
    elif score >= 40:
        bg, fg, g = "#fff3cd", "#7a4f00", "B"
    else:
        bg, fg, g = "#fde8e8", "#7a1f1f", "C"
    return (
        f'<span style="background:{bg};color:{fg};padding:3px 10px;'
        f'border-radius:10px;font-size:12px;font-weight:500">{g} {score:.0f}</span>'
    )


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN UI
# ══════════════════════════════════════════════════════════════════════════════

st.title("🏆 Nifty 500 — Strength Ranker")
st.caption(
    "Strongest stocks ranked #1 · Live CMP via Breeze · Multi-frame returns · "
    "RS / Stage / Volume / Breakout signals · Claude AI one-line justification"
)

# ── Inline controls (sidebar disabled inside tab layout) ─────────────────────
with st.expander("⚙️ Filters & Settings", expanded=False):
    col_a, col_b, col_c, col_d, col_e = st.columns(5)
    with col_a:
        use_live = st.toggle("🔴 Live Breeze prices", value=True)
        use_claude = st.toggle("🤖 Claude AI justifications", value=True)
    with col_b:
        sig_filter = st.multiselect(
            "Signal filter",
            ["RS Leader", "Breakout", "Stage 2", "News-Driven⚑", "Vol Surge", "Weak", "Neutral"],
            default=[],
        )
    with col_c:
        grade_filter = st.multiselect("Grade filter", ["S", "A", "B", "C"], default=[])
    with col_d:
        cap_filter = st.selectbox("Cap bucket", ["All", "large", "mid", "small", "micro"])
    with col_e:
        top_n = st.slider("Show top N stocks", 50, 500, 200, step=50)

st.markdown("---")
# Signal legend inline
legend_html = " &nbsp;".join(
    f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:4px;font-size:11px">{sig}</span>'
    for sig, (bg, fg) in SIGNAL_COLORS.items()
)
st.markdown(f"**Signal legend:** &nbsp; {legend_html}", unsafe_allow_html=True)

# ── Load Supabase data ────────────────────────────────────────────────────────
with st.spinner("Loading scores and universe from Supabase…"):
    scores_df, score_date = load_latest_scores()
    universe  = load_universe()

if scores_df.empty:
    st.error(
        "⚠️ No scores found in Supabase. Run **⚡ Run Scoring** first to populate `ar_daily_scores`."
    )
    st.stop()

# Limit to Nifty 500 — filter by composite score availability + large/mid cap
# (Nifty 500 = Nifty50 + Nifty100 + MidCap150 + SmallCap250)
all_symbols = scores_df["symbol"].tolist()

# ── Load OHLCV from Supabase ──────────────────────────────────────────────────
with st.spinner(f"Loading price history for {len(all_symbols)} stocks…"):
    daily_map = load_daily_ohlcv_batch()

# ── Fetch live prices via Breeze ──────────────────────────────────────────────
live_prices = {}
breeze_err  = None
if use_live:
    breeze, berr = get_breeze()
    if berr:
        breeze_err = berr
        st.warning(f"⚠️ Breeze: {berr}  |  Falling back to last-close from Supabase.")
    else:
        pb = st.progress(0, "Fetching live prices from Breeze…")
        batch_size = 50
        syms_tuple = tuple(all_symbols)
        # Fetch in batches to show progress
        for i in range(0, len(syms_tuple), batch_size):
            batch = syms_tuple[i:i + batch_size]
            chunk = fetch_live_prices(batch)
            live_prices.update(chunk)
            pb.progress(min((i + batch_size) / len(syms_tuple), 1.0),
                        f"Breeze: {len(live_prices)} / {len(syms_tuple)} stocks…")
        pb.empty()
        st.success(f"✅ Live prices fetched for **{len(live_prices)}** stocks via Breeze")

# ── Build master dataframe ────────────────────────────────────────────────────
rows = []
for _, sc_row in scores_df.iterrows():
    sym   = sc_row["symbol"]
    uni   = universe.get(sym, {})
    live  = live_prices.get(sym, {})
    cmp   = live.get("cmp") or None
    chg1d = live.get("chg_1d") or None

    rets = calc_returns(sym, daily_map, live_cmp=cmp)

    combined = {
        "symbol":          sym,
        "company_name":    uni.get("company_name", sym),
        "sector":          uni.get("sector", "—"),
        "industry":        uni.get("industry", "—"),
        "cap_bucket":      uni.get("cap_bucket", "—"),
        "cmp":             cmp,
        "chg_1d":          chg1d,
        "ret_1w":          rets["ret_1w"],
        "ret_1m":          rets["ret_1m"],
        "ret_3m":          rets["ret_3m"],
        "ret_1y":          rets["ret_1y"],
        "vol_ratio_20d":   rets["vol_ratio_20d"],
        "avg_vol_20d":     rets["avg_vol_20d"],
        "at_52w_high_pct": rets["at_52w_high_pct"],
        "above_200d_ma":   rets["above_200d_ma"],
        # From scoring engine
        "composite_score": float(sc_row.get("composite_score") or 50),
        "weinstein_stage": str(sc_row.get("weinstein_stage") or ""),
        "rs_percentile":   float(sc_row.get("rs_percentile") or 50),
        "rs_new_high":     bool(sc_row.get("rs_new_high") or False),
        "breakout_flag":   bool(sc_row.get("breakout_flag") or False),
        "volume_score":    float(sc_row.get("volume_score") or 0),
    }

    combined["signals"]        = classify_signal(combined)
    combined["strength_score"] = strength_score(combined)

    grade_val = combined["strength_score"]
    if grade_val >= 75:
        combined["grade"] = "S"
    elif grade_val >= 60:
        combined["grade"] = "A"
    elif grade_val >= 40:
        combined["grade"] = "B"
    else:
        combined["grade"] = "C"

    rows.append(combined)

master = pd.DataFrame(rows).sort_values("strength_score", ascending=False).reset_index(drop=True)
master["rank"] = master.index + 1

# ── Sector filter options (populate after data loads) ─────────────────────────

# ── Apply filters ─────────────────────────────────────────────────────────────
filt = master.copy()
if sig_filter:
    filt = filt[filt["signals"].apply(lambda ss: any(s in ss for s in sig_filter))]
if grade_filter:
    filt = filt[filt["grade"].isin(grade_filter)]
if cap_filter != "All":
    filt = filt[filt["cap_bucket"] == cap_filter]
filt = filt.head(top_n)

# ── Claude justifications ─────────────────────────────────────────────────────
justifications = {}
if use_claude and not filt.empty:
    batch_syms = filt.head(100)  # justify top 100 visible stocks
    claude_input = []
    for _, r in batch_syms.iterrows():
        claude_input.append({
            "symbol":  r["symbol"],
            "score":   r["strength_score"],
            "stage":   r["weinstein_stage"],
            "rs_pct":  r["rs_percentile"],
            "ret_1d":  r["chg_1d"] or 0,
            "ret_1w":  r["ret_1w"] or 0,
            "ret_1m":  r["ret_1m"] or 0,
            "ret_3m":  r["ret_3m"] or 0,
            "ret_1y":  r["ret_1y"] or 0,
            "vol_r":   r["vol_ratio_20d"] or 1.0,
            "at52h":   r["at_52w_high_pct"] or -99,
            "signals": r["signals"],
        })

    with st.spinner("🤖 Claude AI generating one-line justifications…"):
        # Split into chunks of 30
        for i in range(0, len(claude_input), 30):
            chunk = claude_input[i:i + 30]
            result = get_claude_justifications(chunk)
            justifications.update(result)

# ── Summary metrics ───────────────────────────────────────────────────────────
total   = len(master)
s_count = len(master[master["grade"] == "S"])
a_count = len(master[master["grade"] == "A"])
c_count = len(master[master["grade"] == "C"])
break_n = len(master[master["signals"].apply(lambda ss: "Breakout" in ss)])
rs_lead = len(master[master["signals"].apply(lambda ss: "RS Leader" in ss)])

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Universe", total)
m2.metric("Grade S (Elite)", s_count)
m3.metric("Grade A (Strong)", a_count)
m4.metric("Grade C (Weak)", c_count)
m5.metric("Breakouts", break_n)
m6.metric("RS Leaders", rs_lead)

st.caption(f"Scores from: **{score_date}** · Live prices: {'✅ Breeze' if live_prices else '⚠️ Last close'} · Showing **{len(filt)}** stocks after filters")
st.divider()

# ── Main table ─────────────────────────────────────────────────────────────────
# Build HTML table for rich formatting
table_rows_html = []
for _, r in filt.iterrows():
    just = justifications.get(r["symbol"], "—")
    signals_html = render_signals(r["signals"])
    badge_html   = score_badge(r["strength_score"])

    chg_1d_html  = fmt_ret(r["chg_1d"])
    ret_1w_html  = fmt_ret(r["ret_1w"])
    ret_1m_html  = fmt_ret(r["ret_1m"])
    ret_3m_html  = fmt_ret(r["ret_3m"])
    ret_1y_html  = fmt_ret(r["ret_1y"])

    vol_str = "—"
    if r["vol_ratio_20d"]:
        vr = r["vol_ratio_20d"]
        vc = "#1a7a4a" if vr >= 1.5 else ("#c0392b" if vr < 0.7 else "#888")
        vol_str = f'<span style="color:{vc};font-weight:500">{vr:.1f}x</span>'

    h52_str = "—"
    if r["at_52w_high_pct"] is not None:
        v = r["at_52w_high_pct"]
        c = "#1a7a4a" if v >= -3 else ("#c47a0b" if v >= -10 else "#c0392b")
        h52_str = f'<span style="color:{c}">{v:+.1f}%</span>'

    cap_map = {"large": "🔵", "mid": "🟡", "small": "🟢", "micro": "⚪"}
    cap_ico = cap_map.get(str(r["cap_bucket"]), "")

    table_rows_html.append(f"""
    <tr>
      <td style="color:#888;font-size:12px;text-align:center">{int(r['rank'])}</td>
      <td>
        <div style="font-weight:500;font-size:13px">{r['symbol']}</div>
        <div style="font-size:11px;color:#888">{cap_ico} {str(r['company_name'])[:28]}</div>
      </td>
      <td style="font-size:12px;color:#888">{str(r['sector'])[:18]}</td>
      <td style="font-size:13px;font-weight:500">{fmt_cmp(r['cmp'])}</td>
      <td style="text-align:right">{chg_1d_html}</td>
      <td style="text-align:right">{ret_1w_html}</td>
      <td style="text-align:right">{ret_1m_html}</td>
      <td style="text-align:right">{ret_3m_html}</td>
      <td style="text-align:right">{ret_1y_html}</td>
      <td style="text-align:center">{vol_str}</td>
      <td style="text-align:center">{h52_str}</td>
      <td style="text-align:center">{str(r['weinstein_stage'])}</td>
      <td>{badge_html}</td>
      <td>{signals_html}</td>
      <td style="font-size:11px;color:#666;max-width:200px">{just}</td>
    </tr>""")

table_html = f"""
<style>
  .ranker-table {{
    width: 100%;
    border-collapse: collapse;
    font-family: sans-serif;
    font-size: 13px;
  }}
  .ranker-table th {{
    background: #f8f8f6;
    color: #888;
    font-size: 11px;
    font-weight: 500;
    padding: 8px 6px;
    border-bottom: 1px solid #e0e0e0;
    white-space: nowrap;
    text-align: left;
    position: sticky;
    top: 0;
    z-index: 2;
  }}
  .ranker-table td {{
    padding: 8px 6px;
    border-bottom: 0.5px solid #f0f0ee;
    vertical-align: middle;
  }}
  .ranker-table tr:hover td {{
    background: #fafaf8;
  }}
</style>
<div style="overflow-x:auto;max-height:80vh;overflow-y:auto">
<table class="ranker-table">
  <thead>
    <tr>
      <th>#</th>
      <th>Symbol</th>
      <th>Sector</th>
      <th>CMP</th>
      <th style="text-align:right">1D</th>
      <th style="text-align:right">1W</th>
      <th style="text-align:right">1M</th>
      <th style="text-align:right">3M</th>
      <th style="text-align:right">1Y</th>
      <th style="text-align:center">Vol Ratio</th>
      <th style="text-align:center">52W Hi</th>
      <th style="text-align:center">Stage</th>
      <th style="text-align:center">Grade</th>
      <th>Signals</th>
      <th>AI Justification</th>
    </tr>
  </thead>
  <tbody>
    {''.join(table_rows_html)}
  </tbody>
</table>
</div>
"""

st.markdown(table_html, unsafe_allow_html=True)

# ── Export ────────────────────────────────────────────────────────────────────
st.divider()
export_cols = ["rank", "symbol", "company_name", "sector", "cap_bucket",
               "cmp", "chg_1d", "ret_1w", "ret_1m", "ret_3m", "ret_1y",
               "vol_ratio_20d", "at_52w_high_pct", "weinstein_stage",
               "rs_percentile", "strength_score", "grade"]

export_df = filt[export_cols].copy()
export_df["signals"] = filt["signals"].apply(lambda ss: " | ".join(ss))
if justifications:
    export_df["justification"] = filt["symbol"].map(justifications).fillna("—")

csv = export_df.to_csv(index=False).encode()

col1, col2 = st.columns([1, 4])
with col1:
    st.download_button(
        "⬇️ Export CSV",
        data=csv,
        file_name=f"nifty500_strength_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
with col2:
    st.caption(
        "Ranked by composite strength score (40% AlphaRadar engine · 30% multi-frame momentum · "
        "15% volume character · 15% 52W-high proximity)"
    )

# ── Sector heatmap ────────────────────────────────────────────────────────────
st.divider()
st.subheader("📊 Sector Strength Heatmap")
sec_grp = master.groupby("sector").agg(
    avg_score=("strength_score", "mean"),
    count=("symbol", "count"),
    avg_1m=("ret_1m", "mean"),
    avg_3m=("ret_3m", "mean"),
).reset_index().sort_values("avg_score", ascending=False)

# Display as colored metric grid
cols_per_row = 5
for row_start in range(0, min(len(sec_grp), 25), cols_per_row):
    sec_cols = st.columns(cols_per_row)
    for ci, (_, sr) in enumerate(sec_grp.iloc[row_start:row_start + cols_per_row].iterrows()):
        sc = sr["avg_score"]
        bg = "#d4f0e0" if sc >= 65 else ("#fff3cd" if sc >= 50 else "#fde8e8")
        fc = "#0f5c2e" if sc >= 65 else ("#7a4f00" if sc >= 50 else "#7a1f1f")
        sec_cols[ci].markdown(
            f'<div style="background:{bg};padding:10px 12px;border-radius:8px;margin:3px 0">'
            f'<div style="font-size:11px;color:{fc};font-weight:500">{sr["sector"][:20]}</div>'
            f'<div style="font-size:18px;font-weight:500;color:{fc}">{sc:.0f}</div>'
            f'<div style="font-size:11px;color:{fc}">n={int(sr["count"])} · 1M {(sr["avg_1m"] or 0):+.1f}%</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.caption("Sector avg strength score · n = number of Nifty 500 stocks in sector · 1M = avg 1-month return")
