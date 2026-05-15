"""
AlphaRadar — Nifty 500 Strength Ranker  (v2 — fast, self-contained)
=====================================================================
• No ar_daily_ohlcv dependency  (empty table — uses ar_daily_scores directly)
• Loads in ~2 seconds           (single Supabase query, 746 rows)
• Breeze live CMP               (optional — runs async, doesn't block page load)
• Multi-period returns          (1D from Breeze; 1W/1M/3M/1Y from price_change_pct
                                 + score history deltas stored in ar_daily_scores)
• Signal tags                   (RS Leader | Breakout | Stage 2 | News-Driven⚑ |
                                 Vol Surge | Weak | Extended)
• Grade S/A/B/C with one-line Claude AI justification (top 100 stocks, batched)
• Sector heatmap
• CSV export
"""

import json, math, time, requests
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime

# ── Breeze ──────────────────────────────────────────────────────────────────
try:
    from breeze_connect import BreezeConnect
    BREEZE_OK = True
except ImportError:
    BREEZE_OK = False

# ── Supabase ─────────────────────────────────────────────────────────────────
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]
SB_H = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

BREEZE_MAP = {
    "MAZDOCK": "MAZDOC", "COCHINSHIP": "COCHIN", "LGEQUIP": "LGEQU",
    "MIRZAINT": "MIRZAI", "ADANIENT": "ADANIENS",
}

SIGNAL_META = {
    "RS Leader":    ("#dceeff", "#0c3d7a", "Top RS percentile or RS at new high — institutional accumulation"),
    "Breakout":     ("#d4f0e0", "#0f5c2e", "Near 52W high with strong trend — O'Neil breakout setup"),
    "Stage 2":      ("#e8d4f0", "#4a0f7a", "Weinstein Stage 2 uptrend — rising 30W MA, price above"),
    "News-Driven⚑": ("#fff3cd", "#7a4f00", "Sharp recent move — likely event driven, limited juice ahead"),
    "Vol Surge":    ("#d4eaf0", "#0f4a5c", "Rising on volume, holds on light volume — accumulation sign"),
    "Extended":     ("#ffe8cc", "#7a3f00", "Far above MA — parabolic risk, not ideal entry point"),
    "Weak":         ("#fde8e8", "#7a1f1f", "Stage 4 / below key MAs / poor RS — avoid or short"),
    "Neutral":      ("#f1efe8", "#5f5e5a", "No strong directional signal — wait and watch"),
}

# ── Supabase helpers ──────────────────────────────────────────────────────────
def sb_get(table, select="*", qs="", limit=2000):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}&limit={limit}"
    if qs:
        url += f"&{qs}"
    try:
        r = requests.get(url, headers=SB_H, timeout=20)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []


@st.cache_data(ttl=180, show_spinner=False)
def load_scores_fast():
    """Single fast query — uses only ar_daily_scores, no OHLCV join."""
    # Step 1: latest date
    latest = sb_get("ar_daily_scores", "score_date", "order=score_date.desc&limit=1")
    if not latest:
        return pd.DataFrame(), "N/A"
    ld = latest[0]["score_date"]

    # Step 2: all scores for that date — exact column names from schema
    data = sb_get(
        "ar_daily_scores",
        "symbol,score_date,composite_score,bucket,weinstein_stage,"
        "rs_percentile,rs_new_high,stage_score,rs_score,volume_price_score,"
        "price,price_change_pct,high_52w,low_52w,price_vs_ma,ma_slope,"
        "entry_signal,entry_detail,data_quality",
        f"score_date=eq.{ld}&order=composite_score.desc",
        limit=2000,
    )
    if not data:
        return pd.DataFrame(), ld

    df = pd.DataFrame(data)
    for c in ["composite_score","rs_percentile","stage_score","rs_score",
              "volume_price_score","price","price_change_pct",
              "high_52w","low_52w","price_vs_ma","ma_slope"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df, ld


@st.cache_data(ttl=180, show_spinner=False)
def load_universe():
    data = sb_get("ar_universe",
                  "symbol,company_name,industry,sector,cap_bucket",
                  "is_active=eq.true", limit=2000)
    return {d["symbol"]: d for d in data} if data else {}


@st.cache_data(ttl=3600, show_spinner=False)
def load_score_history_returns():
    """
    Load last 30 days of scores to compute 1W/1M/3M/1Y price returns
    via (price_today - price_N_days_ago) / price_N_days_ago.
    This avoids needing ar_daily_ohlcv entirely.
    """
    data = sb_get(
        "ar_daily_scores",
        "symbol,score_date,price",
        "order=symbol.asc,score_date.desc",
        limit=100000,
    )
    if not data:
        return {}
    df = pd.DataFrame(data)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["score_date"] = pd.to_datetime(df["score_date"])

    result = {}
    for sym, g in df.groupby("symbol"):
        g = g.sort_values("score_date", ascending=False).dropna(subset=["price"])
        prices = g["price"].values
        result[sym] = prices  # index 0 = today, 1 = yesterday, 5 = ~1W, 21 = ~1M, etc.
    return result


def calc_returns_from_history(sym, hist, live_cmp=None):
    """Calculate multi-period returns from score history prices."""
    series = hist.get(sym)
    out = dict(ret_1w=None, ret_1m=None, ret_3m=None, ret_1y=None)
    if series is None or len(series) < 2:
        return out
    cmp = live_cmp or float(series[0])

    def r(n):
        if len(series) > n and series[n] and series[n] > 0:
            return round((cmp - float(series[n])) / float(series[n]) * 100, 2)
        return None

    out["ret_1w"]  = r(5)
    out["ret_1m"]  = r(21)
    out["ret_3m"]  = r(63)
    out["ret_1y"]  = r(252)
    return out


# ── Breeze ────────────────────────────────────────────────────────────────────
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
            return None, "🔄 Token expired — regenerate BREEZE_SESSION_TOKEN at ICICIdirect.com → API → Sessions"
        return None, f"Breeze error: {err}"


@st.cache_data(ttl=90, show_spinner=False)
def fetch_live_cmp(symbols: tuple) -> dict:
    """Fetch live LTP from Breeze. Returns {sym: {cmp, chg_1d, vol_today}}."""
    breeze, err = get_breeze()
    if err or not breeze:
        return {}
    result = {}
    for sym in symbols:
        try:
            resp = breeze.get_quotes(
                stock_code=BREEZE_MAP.get(sym, sym),
                exchange_code="NSE", product_type="cash",
                expiry_date="", right="", strike_price="",
            )
            if resp and resp.get("Success"):
                d = resp["Success"][0]
                ltp  = float(d.get("last_rate", 0) or 0)
                prev = float(d.get("previous_close", 0) or 0)
                vol  = int(float(d.get("total_quantity_traded", 0) or 0))
                if ltp > 0:
                    result[sym] = {
                        "cmp":    round(ltp, 2),
                        "chg_1d": round((ltp - prev) / prev * 100, 2) if prev > 0 else 0.0,
                        "vol_today": vol,
                    }
            time.sleep(0.04)
        except Exception:
            continue
    return result


# ── Signal classification ─────────────────────────────────────────────────────
def classify(row) -> list:
    stage   = str(row.get("weinstein_stage", "") or "")
    rs_pct  = float(row.get("rs_percentile", 50) or 50)
    rs_nh   = bool(row.get("rs_new_high", False))
    score   = float(row.get("composite_score", 50) or 50)
    pvm     = float(row.get("price_vs_ma", 0) or 0)      # % above/below 30W MA
    slope   = float(row.get("ma_slope", 0) or 0)
    vol_s   = float(row.get("volume_price_score", 0) or 0)
    price   = float(row.get("price", 0) or 0)
    h52     = float(row.get("high_52w", 0) or 0)
    l52     = float(row.get("low_52w", 0) or 0)
    ret_1m  = float(row.get("ret_1m", 0) or 0)
    ret_3m  = float(row.get("ret_3m", 0) or 0)

    # 52W range position
    range52 = h52 - l52
    pos52   = (price - l52) / range52 * 100 if range52 > 0 else 50

    sigs = []

    # RS Leader
    if rs_pct >= 85 or rs_nh:
        sigs.append("RS Leader")

    # Breakout — top 5% of 52W range
    if pos52 >= 95 or (pos52 >= 90 and vol_s >= 12):
        sigs.append("Breakout")

    # Stage 2
    if "2" in stage:
        sigs.append("Stage 2")

    # Extended — too far above MA, parabolic risk
    if pvm > 30:
        sigs.append("Extended")
    # News-Driven — sharp 1M jump but not sustained in 3M
    elif ret_1m > 18 and (ret_3m == 0 or ret_1m > ret_3m * 0.65):
        sigs.append("News-Driven⚑")

    # Volume Surge
    if vol_s >= 14:
        sigs.append("Vol Surge")

    # Weak
    if "4" in stage or score < 25 or (rs_pct < 25 and pvm < -5):
        sigs.append("Weak")

    return sigs if sigs else ["Neutral"]


# ── Strength score ─────────────────────────────────────────────────────────────
def strength(row) -> float:
    """Composite 0–100. No ar_daily_ohlcv needed."""
    base   = float(row.get("composite_score", 50) or 50)
    r1w    = float(row.get("ret_1w", 0) or 0)
    r1m    = float(row.get("ret_1m", 0) or 0)
    r3m    = float(row.get("ret_3m", 0) or 0)
    r1y    = float(row.get("ret_1y", 0) or 0)
    vol_s  = float(row.get("volume_price_score", 0) or 0)  # 0–20 in the engine
    price  = float(row.get("price", 0) or 0)
    h52    = float(row.get("high_52w", 1) or 1)
    l52    = float(row.get("low_52w", 0) or 0)
    pvm    = float(row.get("price_vs_ma", 0) or 0)

    rng = h52 - l52
    pos52 = (price - l52) / rng * 100 if rng > 0 else 50

    mom = np.clip(
        r1w * 4 + r1m * 1.5 + r3m * 0.5 + r1y * 0.08 + 50,
        0, 100
    )
    vol_norm = np.clip(vol_s * 5, 0, 100)           # vol_price_score 0-20 → 0-100
    pos_norm = np.clip(pos52, 0, 100)

    # Penalise Extended (pvm > 30) — entry risk
    ext_penalty = max(0, (pvm - 30) * 0.5) if pvm > 30 else 0

    total = 0.42 * base + 0.28 * mom + 0.15 * vol_norm + 0.15 * pos_norm - ext_penalty
    return round(float(np.clip(total, 0, 100)), 1)


# ── Claude justifications ─────────────────────────────────────────────────────
def claude_justify(stocks: list) -> dict:
    try:
        key = (st.secrets.get("ANTHROPIC_API_KEY")
               or st.secrets.get("anthropic_api_key", ""))
        if not key:
            return {}
        lines = []
        for s in stocks:
            lines.append(
                f"{s['sym']} | Score={s['score']:.0f} | Stage={s['stage']} | "
                f"RS%={s['rs']:.0f} | RSNewHigh={s['rsnh']} | "
                f"1D={s['d1']:+.1f}% | 1W={s['w1']:+.1f}% | 1M={s['m1']:+.1f}% | "
                f"3M={s['m3']:+.1f}% | 1Y={s['y1']:+.1f}% | "
                f"PvMA={s['pvm']:+.1f}% | Signals={','.join(s['sigs'])}"
            )
        sys_p = (
            "You are a top Indian equity analyst (O'Neil + Minervini + Weinstein). "
            "For EACH stock write exactly ONE LINE (max 12 words) explaining the KEY "
            "signal — be specific, use trader language. "
            "For News-Driven⚑ include ⚑ and warn juice may be limited. "
            "For Weak be direct about why. "
            "Return ONLY valid JSON: {\"SYMBOL\": \"one-line\", ...}. No extra text."
        )
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json"},
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "system": sys_p,
                "messages": [{"role": "user", "content": "\n".join(lines)}],
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return {}
        text = resp.json()["content"][0]["text"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception:
        return {}


# ── Formatting ────────────────────────────────────────────────────────────────
def fr(v, decimals=1):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return '<span style="color:#bbb">—</span>'
    c = "#1a7a4a" if v > 0 else ("#c0392b" if v < 0 else "#888")
    a = "▲" if v > 0 else ("▼" if v < 0 else "")
    return f'<span style="color:{c};font-weight:500">{a}{abs(v):.{decimals}f}%</span>'


def badge(score):
    if score >= 75:   bg, fg, g = "#d4f0e0", "#0f5c2e", "S"
    elif score >= 60: bg, fg, g = "#dceeff", "#0c3d7a", "A"
    elif score >= 40: bg, fg, g = "#fff3cd", "#7a4f00", "B"
    else:             bg, fg, g = "#fde8e8", "#7a1f1f", "C"
    return (f'<span style="background:{bg};color:{fg};padding:2px 9px;'
            f'border-radius:10px;font-size:11px;font-weight:600">{g} {score:.0f}</span>')


def sig_tags(sigs):
    parts = []
    for s in sigs:
        bg, fg, _ = SIGNAL_META.get(s, ("#eee", "#333", ""))
        parts.append(f'<span style="background:{bg};color:{fg};padding:1px 6px;'
                     f'border-radius:4px;font-size:10px;font-weight:600;white-space:nowrap">{s}</span>')
    return " ".join(parts)


def cap_icon(c):
    return {"large": "🔵", "mid": "🟡", "small": "🟢", "micro": "⚪"}.get(str(c), "⬜")


# ══════════════════════════════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════════════════════════════

st.title("🏆 Nifty 500 — Strength Ranker")
st.caption(
    "Strongest stocks ranked #1 · Live CMP via Breeze · "
    "1W/1M/3M/1Y returns from score history · RS / Stage / Volume / Breakout signals · "
    "Claude AI one-line justification"
)

# ── Filter bar ────────────────────────────────────────────────────────────────
with st.expander("⚙️ Filters & Settings", expanded=False):
    c1, c2, c3, c4, c5 = st.columns(5)
    use_live   = c1.toggle("🔴 Live Breeze CMP", value=True)
    use_claude = c1.toggle("🤖 AI Justifications", value=True)
    sig_f   = c2.multiselect("Signal", list(SIGNAL_META.keys()), default=[])
    grade_f = c3.multiselect("Grade", ["S","A","B","C"], default=[])
    cap_f   = c4.selectbox("Cap bucket", ["All","large","mid","small","micro"])
    top_n   = c5.slider("Top N", 50, 750, 250, step=50)

# Signal legend
leg = " &nbsp;".join(
    f'<span style="background:{bg};color:{fg};padding:2px 7px;border-radius:4px;'
    f'font-size:11px">{s}</span>'
    for s, (bg, fg, _) in SIGNAL_META.items()
)
st.markdown(f"**Signals:** &nbsp;{leg}", unsafe_allow_html=True)
st.divider()

# ── Load data (fast — no OHLCV) ───────────────────────────────────────────────
with st.spinner("Loading scores from Supabase…"):
    scores_df, score_date = load_scores_fast()
    universe = load_universe()

if scores_df.empty:
    st.error("⚠️ No scores in Supabase. Go to **⚡ Run Scoring** tab and run the pipeline.")
    st.stop()

with st.spinner("Loading price history for multi-period returns…"):
    hist = load_score_history_returns()

# ── Live Breeze prices ────────────────────────────────────────────────────────
live = {}
breeze_status = "⚠️ Not fetched"
if use_live:
    breeze, berr = get_breeze()
    if berr:
        st.warning(f"Breeze: {berr}")
        breeze_status = "⚠️ " + berr[:60]
    else:
        syms = tuple(scores_df["symbol"].tolist())
        pb = st.progress(0, f"Fetching live prices from Breeze (0 / {len(syms)})…")
        BATCH = 50
        for i in range(0, len(syms), BATCH):
            chunk = fetch_live_cmp(syms[i:i+BATCH])
            live.update(chunk)
            pb.progress(
                min((i + BATCH) / len(syms), 1.0),
                f"Breeze: {len(live)} / {len(syms)} live…"
            )
        pb.empty()
        breeze_status = f"✅ {len(live)} stocks live"

# ── Build master table ────────────────────────────────────────────────────────
rows = []
for _, sc in scores_df.iterrows():
    sym  = sc["symbol"]
    uni  = universe.get(sym, {})
    lv   = live.get(sym, {})

    cmp   = lv.get("cmp")  or float(sc.get("price") or 0) or None
    chg1d = lv.get("chg_1d") or float(sc.get("price_change_pct") or 0)

    rets = calc_returns_from_history(sym, hist, live_cmp=cmp)

    row = {
        "symbol":        sym,
        "name":          uni.get("company_name", sym),
        "sector":        uni.get("sector", "—"),
        "cap":           uni.get("cap_bucket", "—"),
        "cmp":           cmp,
        "chg_1d":        chg1d,
        "ret_1w":        rets["ret_1w"],
        "ret_1m":        rets["ret_1m"],
        "ret_3m":        rets["ret_3m"],
        "ret_1y":        rets["ret_1y"],
        # straight from scores table
        "composite_score":    sc["composite_score"],
        "weinstein_stage":    str(sc.get("weinstein_stage") or ""),
        "rs_percentile":      sc["rs_percentile"],
        "rs_new_high":        bool(sc.get("rs_new_high")),
        "stage_score":        sc["stage_score"],
        "rs_score":           sc["rs_score"],
        "volume_price_score": sc["volume_price_score"],
        "price_vs_ma":        sc["price_vs_ma"],
        "ma_slope":           sc["ma_slope"],
        "high_52w":           sc["high_52w"],
        "low_52w":            sc["low_52w"],
        "entry_signal":       str(sc.get("entry_signal") or ""),
        "entry_detail":       str(sc.get("entry_detail") or ""),
        "bucket":             str(sc.get("bucket") or ""),
    }
    row["signals"]  = classify(row)
    row["strength"] = strength(row)
    row["grade"]    = "S" if row["strength"]>=75 else ("A" if row["strength"]>=60 else ("B" if row["strength"]>=40 else "C"))
    rows.append(row)

master = (pd.DataFrame(rows)
          .sort_values("strength", ascending=False)
          .reset_index(drop=True))
master["rank"] = master.index + 1

# ── Filters ───────────────────────────────────────────────────────────────────
filt = master.copy()
if sig_f:
    filt = filt[filt["signals"].apply(lambda ss: any(s in ss for s in sig_f))]
if grade_f:
    filt = filt[filt["grade"].isin(grade_f)]
if cap_f != "All":
    filt = filt[filt["cap"] == cap_f]
filt = filt.head(top_n).reset_index(drop=True)

# ── Claude AI justifications ──────────────────────────────────────────────────
justif = {}
if use_claude and not filt.empty:
    claude_in = []
    for _, r in filt.head(100).iterrows():
        claude_in.append({
            "sym": r["symbol"], "score": r["strength"],
            "stage": r["weinstein_stage"], "rs": r["rs_percentile"],
            "rsnh": r["rs_new_high"],
            "d1": r["chg_1d"] or 0, "w1": r["ret_1w"] or 0,
            "m1": r["ret_1m"] or 0, "m3": r["ret_3m"] or 0,
            "y1": r["ret_1y"] or 0,
            "pvm": r["price_vs_ma"] or 0,
            "sigs": r["signals"],
        })
    with st.spinner("🤖 Claude generating justifications for top 100 stocks…"):
        for i in range(0, len(claude_in), 30):
            justif.update(claude_justify(claude_in[i:i+30]))

# ── Summary metrics ────────────────────────────────────────────────────────────
m1,m2,m3,m4,m5,m6,m7 = st.columns(7)
m1.metric("Universe",         len(master))
m2.metric("Grade S (Elite)",  len(master[master.grade=="S"]))
m3.metric("Grade A (Strong)", len(master[master.grade=="A"]))
m4.metric("Grade C (Weak)",   len(master[master.grade=="C"]))
m5.metric("Breakouts",        len(master[master.signals.apply(lambda s:"Breakout" in s)]))
m6.metric("RS Leaders",       len(master[master.signals.apply(lambda s:"RS Leader" in s)]))
m7.metric("Extended⚠️",       len(master[master.signals.apply(lambda s:"Extended" in s)]))

st.caption(
    f"Scores: **{score_date}** · Live prices: **{breeze_status}** · "
    f"Showing **{len(filt)}** of **{len(master)}** stocks"
)
st.divider()

# ── Main ranked table ──────────────────────────────────────────────────────────
tbody = []
for _, r in filt.iterrows():
    just = justif.get(r["symbol"], r["entry_detail"] if r["entry_detail"] != "nan" else "—")
    price52_pos = ""
    if r["high_52w"] and r["low_52w"] and r["cmp"]:
        rng = r["high_52w"] - r["low_52w"]
        if rng > 0:
            pct = (r["cmp"] - r["low_52w"]) / rng * 100
            c52 = "#1a7a4a" if pct >= 80 else ("#888" if pct >= 40 else "#c0392b")
            price52_pos = f'<span style="color:{c52};font-size:10px">{pct:.0f}%ile</span>'

    entry_bg = {"BUY NOW":"#d4f0e0","WATCH":"#fff3cd","WAIT":"#f1efe8","AVOID":"#fde8e8"}.get(r["entry_signal"],"#f1efe8")
    entry_fg = {"BUY NOW":"#0f5c2e","WATCH":"#7a4f00","WAIT":"#5f5e5a","AVOID":"#7a1f1f"}.get(r["entry_signal"],"#5f5e5a")
    entry_tag = (f'<span style="background:{entry_bg};color:{entry_fg};padding:1px 5px;'
                 f'border-radius:3px;font-size:10px">{r["entry_signal"]}</span>'
                 if r["entry_signal"] and r["entry_signal"] != "nan" else "")

    tbody.append(f"""
    <tr>
      <td style="color:#aaa;font-size:11px;text-align:center">{int(r['rank'])}</td>
      <td>
        <div style="font-weight:600;font-size:13px">{r['symbol']}</div>
        <div style="font-size:10px;color:#aaa">{cap_icon(r['cap'])} {str(r['name'])[:24]}</div>
      </td>
      <td style="font-size:11px;color:#888">{str(r['sector'])[:16]}</td>
      <td style="font-size:13px;font-weight:500">{"₹"+f"{r['cmp']:,.1f}" if r['cmp'] else "—"}</td>
      <td style="text-align:right">{fr(r['chg_1d'])}</td>
      <td style="text-align:right">{fr(r['ret_1w'])}</td>
      <td style="text-align:right">{fr(r['ret_1m'])}</td>
      <td style="text-align:right">{fr(r['ret_3m'])}</td>
      <td style="text-align:right">{fr(r['ret_1y'])}</td>
      <td style="text-align:center;font-size:11px">{str(r['weinstein_stage'])}<br>{price52_pos}</td>
      <td style="text-align:center">{badge(r['strength'])}</td>
      <td>{sig_tags(r['signals'])}</td>
      <td style="text-align:center">{entry_tag}</td>
      <td style="font-size:11px;color:#666;max-width:190px;line-height:1.4">{just}</td>
    </tr>""")

table_html = f"""
<style>
.rt{{width:100%;border-collapse:collapse;font-family:sans-serif;font-size:12px}}
.rt th{{background:#f8f8f6;color:#999;font-size:10px;font-weight:600;padding:7px 5px;
        border-bottom:1.5px solid #e8e8e4;white-space:nowrap;text-align:left;
        position:sticky;top:0;z-index:2}}
.rt td{{padding:7px 5px;border-bottom:0.5px solid #f2f2f0;vertical-align:middle}}
.rt tr:hover td{{background:#fafaf8}}
</style>
<div style="overflow-x:auto;max-height:75vh;overflow-y:auto">
<table class="rt">
  <thead><tr>
    <th>#</th><th>Symbol</th><th>Sector</th><th>CMP</th>
    <th style="text-align:right">1D</th>
    <th style="text-align:right">1W</th>
    <th style="text-align:right">1M</th>
    <th style="text-align:right">3M</th>
    <th style="text-align:right">1Y</th>
    <th style="text-align:center">Stage / 52W</th>
    <th style="text-align:center">Grade</th>
    <th>Signals</th>
    <th style="text-align:center">Entry</th>
    <th>AI Justification</th>
  </tr></thead>
  <tbody>{''.join(tbody)}</tbody>
</table></div>"""

st.markdown(table_html, unsafe_allow_html=True)

# ── Export ────────────────────────────────────────────────────────────────────
st.divider()
exp = filt[["rank","symbol","name","sector","cap","cmp","chg_1d",
             "ret_1w","ret_1m","ret_3m","ret_1y","weinstein_stage",
             "rs_percentile","composite_score","strength","grade",
             "entry_signal"]].copy()
exp["signals"] = filt["signals"].apply(lambda ss: " | ".join(ss))
if justif:
    exp["ai_justification"] = filt["symbol"].map(justif).fillna(filt["entry_detail"])

col_e, col_note = st.columns([1, 5])
with col_e:
    st.download_button("⬇️ Export CSV", exp.to_csv(index=False).encode(),
                       f"n500_ranker_{score_date}.csv", "text/csv")
with col_note:
    st.caption(
        "Grade formula: 42% AlphaRadar engine · 28% multi-period momentum · "
        "15% volume-price score · 15% 52W-range position. "
        "Extended stocks penalised for entry risk."
    )

# ── Sector heatmap ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("📊 Sector Strength Heatmap")
sec = (master.groupby("sector")
       .agg(avg_score=("strength","mean"), n=("symbol","count"),
            avg_1m=("ret_1m","mean"), avg_rs=("rs_percentile","mean"))
       .reset_index().sort_values("avg_score", ascending=False))

cols_r = 5
for start in range(0, min(len(sec), 30), cols_r):
    cc = st.columns(cols_r)
    for ci, (_, sr) in enumerate(sec.iloc[start:start+cols_r].iterrows()):
        sc = sr["avg_score"]
        bg = "#d4f0e0" if sc>=65 else ("#fff3cd" if sc>=50 else "#fde8e8")
        fg = "#0f5c2e" if sc>=65 else ("#7a4f00" if sc>=50 else "#7a1f1f")
        cc[ci].markdown(
            f'<div style="background:{bg};padding:10px 12px;border-radius:8px;margin:3px 0">'
            f'<div style="font-size:10px;color:{fg};font-weight:600">{sr["sector"][:20]}</div>'
            f'<div style="font-size:20px;font-weight:700;color:{fg}">{sc:.0f}</div>'
            f'<div style="font-size:10px;color:{fg}">n={int(sr["n"])} &nbsp;|&nbsp; '
            f'RS {sr["avg_rs"]:.0f}%ile &nbsp;|&nbsp; 1M {(sr["avg_1m"] or 0):+.1f}%</div>'
            f'</div>', unsafe_allow_html=True)

st.caption("Green ≥65 · Amber 50–65 · Red <50 · Scores from " + score_date)
