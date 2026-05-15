"""
AlphaRadar — Nifty 500 Strength Ranker  (v4 — truly instant)
=============================================================
ONE query, ONE render, zero background loops.

What changed from v3:
- Removed load_price_history() entirely (only 6 dates exist — 1W/1M/3M/1Y were all None)
  Instead use price_change_pct (1D), price_vs_ma (trend proxy), and score_change (momentum)
- @st.cache_data on inner functions breaks inside exec() — moved ALL data loading
  into a single cached wrapper called ONCE at module level
- Removed use_container_width=True (causes 4500 log spam on Streamlit 1.57)
- Phase 1 renders instantly with NO spinner loops
- Phase 2 (Breeze) and Phase 3 (Claude AI) still button-triggered
"""

import json, math, time, requests
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

try:
    from breeze_connect import BreezeConnect
    BREEZE_OK = True
except ImportError:
    BREEZE_OK = False

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]
HDR = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
HDR_W = {**HDR, "Content-Type": "application/json",
          "Prefer": "resolution=merge-duplicates,return=minimal"}

BREEZE_MAP = {
    "MAZDOCK":"MAZDOC","COCHINSHIP":"COCHIN","LGEQUIP":"LGEQU",
    "MIRZAINT":"MIRZAI","ADANIENT":"ADANIENS",
}

UNIVERSE_OPTIONS = {
    "🏆 Nifty 500":                       "nifty500",
    "💎 Nifty 50":                        "nifty50",
    "📊 Midcap 150":                      "midcap150",
    "📈 Smallcap 250":                    "smallcap250",
    "🌐 Full Universe":                   None,
    "🚀 MUST_BUY only":                   "__must_buy__",
    "✅ MUST_BUY + CAN_BUY":              "__can_buy__",
    "📉 AVOID + SELL":                    "__weak__",
}

SIG_COLORS = {
    "RS Leader":    ("#dceeff","#0c3d7a"),
    "Breakout":     ("#d4f0e0","#0f5c2e"),
    "Stage 2":      ("#e8d4f0","#4a0f7a"),
    "News-Driven⚑": ("#fff3cd","#7a4f00"),
    "Vol Surge":    ("#d4eaf0","#0f4a5c"),
    "Extended⚠":   ("#ffe8cc","#7a3f00"),
    "Weak":         ("#fde8e8","#7a1f1f"),
    "Neutral":      ("#f1efe8","#5f5e5a"),
}

ENTRY_COLORS = {
    "BUY NOW":("#d4f0e0","#0f5c2e"),
    "WATCH":  ("#fff3cd","#7a4f00"),
    "WAIT":   ("#f1efe8","#5f5e5a"),
    "AVOID":  ("#fde8e8","#7a1f1f"),
    "SELL":   ("#fde8e8","#7a1f1f"),
}

# ── Single data loader (called once, cached in session_state) ─────────────────
def _load_all():
    """
    Loads scores + universe in 2 parallel-ish requests.
    Results stored in st.session_state so exec() re-runs don't re-fetch.
    Cache key = latest score_date so it auto-refreshes when scoring runs.
    """
    # 1. Scores
    url = (f"{SUPABASE_URL}/rest/v1/ar_daily_scores"
           f"?select=symbol,score_date,composite_score,bucket,weinstein_stage,"
           f"rs_percentile,rs_new_high,volume_price_score,"
           f"price,price_change_pct,high_52w,low_52w,price_vs_ma,ma_slope,"
           f"entry_signal,entry_detail,score_change"
           f"&order=score_date.desc,composite_score.desc&limit=800")
    resp = requests.get(url, headers=HDR, timeout=20)
    if resp.status_code != 200:
        return pd.DataFrame(), "N/A", {}
    raw = resp.json()
    if not raw:
        return pd.DataFrame(), "N/A", {}

    # Keep only latest score_date
    score_date = raw[0]["score_date"]
    today_rows = [r for r in raw if r["score_date"] == score_date]

    df = pd.DataFrame(today_rows)
    for c in ["composite_score","rs_percentile","volume_price_score",
              "price","price_change_pct","high_52w","low_52w",
              "price_vs_ma","ma_slope","score_change"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 2. Universe (index membership + metadata)
    url2 = (f"{SUPABASE_URL}/rest/v1/ar_universe"
            f"?select=symbol,company_name,sector,cap_bucket,index_membership,fo_enabled"
            f"&is_active=eq.true&limit=2000")
    resp2 = requests.get(url2, headers=HDR, timeout=20)
    uni = {}
    if resp2.status_code == 200:
        for d in resp2.json():
            uni[d["symbol"]] = d

    # 3. Cached AI justifications
    url3 = (f"{SUPABASE_URL}/rest/v1/ar_ai_justifications"
            f"?select=symbol,justification,generated_at,universe_scope"
            f"&score_date=eq.{score_date}&limit=2000")
    resp3 = requests.get(url3, headers=HDR, timeout=20)
    just = {}
    if resp3.status_code == 200:
        for d in resp3.json():
            if d.get("justification"):
                just[d["symbol"]] = {
                    "text": d["justification"],
                    "ts": (d.get("generated_at","") or "")[:10],
                }

    return df, score_date, uni, just


def get_data():
    """Return cached data from session_state; reload only if date changed."""
    if "ranker_date" not in st.session_state:
        st.session_state["ranker_date"] = None
        st.session_state["ranker_data"] = None

    # Quick probe for latest date (tiny query — 1 row)
    try:
        probe = requests.get(
            f"{SUPABASE_URL}/rest/v1/ar_daily_scores?select=score_date&order=score_date.desc&limit=1",
            headers=HDR, timeout=10
        ).json()
        latest = probe[0]["score_date"] if probe else None
    except Exception:
        latest = st.session_state["ranker_date"]

    if latest != st.session_state["ranker_date"] or st.session_state["ranker_data"] is None:
        with st.spinner("⚡ Loading scores from Supabase…"):
            st.session_state["ranker_data"] = _load_all()
            st.session_state["ranker_date"] = latest

    return st.session_state["ranker_data"]


# ── Scoring ───────────────────────────────────────────────────────────────────
def classify(row):
    stage  = str(row.get("weinstein_stage","") or "")
    rs     = float(row.get("rs_percentile",50) or 50)
    rs_nh  = bool(row.get("rs_new_high"))
    score  = float(row.get("composite_score",50) or 50)
    pvm    = float(row.get("price_vs_ma",0) or 0)
    vol_s  = float(row.get("volume_price_score",0) or 0)
    price  = float(row.get("price",0) or 0)
    h52    = float(row.get("high_52w",0) or 0)
    l52    = float(row.get("low_52w",0) or 0)
    chg    = float(row.get("price_change_pct",0) or 0)

    rng   = h52 - l52
    pos52 = (price - l52) / rng * 100 if rng > 0 else 50
    sigs  = []

    if rs >= 85 or rs_nh:                          sigs.append("RS Leader")
    if pos52 >= 95 or (pos52 >= 88 and vol_s>=12): sigs.append("Breakout")
    if "2" in stage:                                sigs.append("Stage 2")
    if pvm > 30:                                    sigs.append("Extended⚠")
    elif chg > 5 and pvm > 10:                     sigs.append("News-Driven⚑")
    if vol_s >= 14:                                 sigs.append("Vol Surge")
    if "4" in stage or score < 25 or (rs < 25 and pvm < -5): sigs.append("Weak")
    return sigs if sigs else ["Neutral"]


def strength(row):
    base  = float(row.get("composite_score",50) or 50)
    vol_s = float(row.get("volume_price_score",0) or 0)
    price = float(row.get("price",0) or 0)
    h52   = float(row.get("high_52w",1) or 1)
    l52   = float(row.get("low_52w",0) or 0)
    pvm   = float(row.get("price_vs_ma",0) or 0)
    sc    = float(row.get("score_change",0) or 0)  # momentum proxy
    chg   = float(row.get("price_change_pct",0) or 0)

    rng   = h52 - l52
    pos52 = np.clip((price-l52)/rng*100, 0, 100) if rng > 0 else 50
    vol_n = np.clip(vol_s*5, 0, 100)
    mom   = np.clip(chg*3 + sc*2 + 50, 0, 100)   # 1D price chg + score momentum
    ext_p = max(0,(pvm-30)*0.5) if pvm > 30 else 0

    return round(float(np.clip(
        0.45*base + 0.20*mom + 0.20*vol_n + 0.15*pos52 - ext_p,
        0, 100)), 1)


# ── Breeze ────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_breeze():
    if not BREEZE_OK:
        return None, "breeze_connect not installed"
    try:
        b = BreezeConnect(api_key=st.secrets["BREEZE_API_KEY"])
        b.generate_session(api_secret=st.secrets["BREEZE_API_SECRET"],
                           session_token=st.secrets["BREEZE_SESSION_TOKEN"])
        return b, None
    except Exception as e:
        err = str(e)
        if any(w in err.lower() for w in ["session","token","auth","invalid"]):
            return None, "Token expired — regenerate at ICICIdirect → API → Sessions"
        return None, f"Breeze: {err}"


def fetch_live(symbols):
    breeze, err = get_breeze()
    if err or not breeze:
        st.warning(f"⚠️ {err}")
        return {}
    out = {}
    prog = st.progress(0, f"Fetching {len(symbols)} live prices from Breeze…")
    for i, sym in enumerate(symbols):
        try:
            resp = breeze.get_quotes(stock_code=BREEZE_MAP.get(sym,sym),
                                     exchange_code="NSE", product_type="cash",
                                     expiry_date="", right="", strike_price="")
            if resp and resp.get("Success"):
                d = resp["Success"][0]
                ltp = float(d.get("last_rate",0) or 0)
                prv = float(d.get("previous_close",0) or 0)
                if ltp > 0:
                    out[sym] = {"cmp": round(ltp,2),
                                "chg_1d": round((ltp-prv)/prv*100,2) if prv>0 else 0.0}
            time.sleep(0.04)
        except Exception:
            continue
        if i % 10 == 0:
            prog.progress((i+1)/len(symbols), f"Breeze: {len(out)}/{len(symbols)}…")
    prog.empty()
    return out


# ── Claude AI ─────────────────────────────────────────────────────────────────
def run_claude_batch(batch, score_date, scope_label):
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY") or st.secrets.get("anthropic_api_key","")
        if not key:
            st.warning("⚠️ ANTHROPIC_API_KEY not set in Streamlit secrets.")
            return {}
        lines = [
            f"{s['sym']} | Score={s['score']:.0f} | Stage={s['stage']} | "
            f"RS%={s['rs']:.0f} | RSNewHigh={s['rsnh']} | "
            f"1D={s['d1']:+.1f}% | PvMA={s['pvm']:+.1f}% | Signals={','.join(s['sigs'])}"
            for s in batch
        ]
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json"},
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "system": (
                    "You are a top Indian equity analyst (O'Neil + Minervini + Weinstein). "
                    "For EACH stock write exactly ONE LINE (max 12 words) on the KEY signal. "
                    "Specific trader language. News-Driven⚑: add ⚑, note limited juice ahead. "
                    "Extended⚠: warn parabolic risk. Weak: be direct and specific. "
                    "Return ONLY valid JSON: {\"SYMBOL\": \"one-line\", ...}. No extra text."
                ),
                "messages": [{"role":"user","content":"\n".join(lines)}],
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return {}
        text = resp.json()["content"][0]["text"].strip()
        text = text.replace("```json","").replace("```","").strip()
        result = json.loads(text)

        now = datetime.now(timezone.utc).isoformat()
        recs = [
            {"symbol":sym,"score_date":score_date,"justification":just,
             "signals":" | ".join(next((s["sigs"] for s in batch if s["sym"]==sym),[])),
             "strength_score":next((s["score"] for s in batch if s["sym"]==sym),None),
             "generated_at":now,"model_used":"claude-sonnet-4-20250514",
             "universe_scope":scope_label}
            for sym,just in result.items()
        ]
        requests.post(f"{SUPABASE_URL}/rest/v1/ar_ai_justifications",
                      headers=HDR_W, json=recs, timeout=30)
        return result
    except Exception as e:
        st.warning(f"Claude batch error: {e}")
        return {}


# ── HTML helpers ──────────────────────────────────────────────────────────────
def fr(v):
    if v is None or (isinstance(v,float) and math.isnan(v)):
        return '<span style="color:#ccc">—</span>'
    c = "#1a7a4a" if v>0 else ("#c0392b" if v<0 else "#888")
    a = "▲" if v>0 else ("▼" if v<0 else "")
    return f'<span style="color:{c};font-weight:600">{a}{abs(v):.1f}%</span>'

def gbadge(s):
    if s>=75:   b,f,g="#d4f0e0","#0f5c2e","S"
    elif s>=60: b,f,g="#dceeff","#0c3d7a","A"
    elif s>=40: b,f,g="#fff3cd","#7a4f00","B"
    else:       b,f,g="#fde8e8","#7a1f1f","C"
    return f'<span style="background:{b};color:{f};padding:2px 9px;border-radius:10px;font-size:11px;font-weight:700">{g} {s:.0f}</span>'

def stags(sigs):
    return " ".join(
        f'<span style="background:{b};color:{f};padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">{s}</span>'
        for s in sigs for b,f in [SIG_COLORS.get(s,("#eee","#333"))]
    )

def etag(label):
    if not label or label in ("nan","None",""): return ""
    b,f = ENTRY_COLORS.get(label,("#f1efe8","#5f5e5a"))
    return f'<span style="background:{b};color:{f};padding:1px 7px;border-radius:3px;font-size:11px;font-weight:700">{label}</span>'


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
st.title("🏆 N500 Strength Ranker")
st.caption("Ranked strongest→weakest · ⚡ Instant load · Live prices & AI on-demand")

# ── Load data (session_state cache — survives exec() re-runs) ─────────────────
result = get_data()
if len(result) == 3:   # old cache format
    st.session_state["ranker_data"] = None
    st.rerun()
scores_df, score_date, uni, cached_just = result

if scores_df is None or scores_df.empty:
    st.error("⚠️ No scores found in Supabase. Run **⚡ Run Scoring** tab first.")
    st.stop()

# ── Build master table (pure in-memory, no I/O) ────────────────────────────────
if "master_df" not in st.session_state or st.session_state.get("master_date") != score_date:
    rows = []
    for _, sc in scores_df.iterrows():
        sym = sc["symbol"]
        u   = uni.get(sym, {})
        row = {
            "symbol":             sym,
            "name":               u.get("company_name", sym),
            "sector":             u.get("sector","—"),
            "cap":                u.get("cap_bucket","—"),
            "fo":                 bool(u.get("fo_enabled",False)),
            "idx":                u.get("index_membership") or [],
            "cmp":                float(sc.get("price") or 0) or None,
            "chg_1d":             float(sc.get("price_change_pct") or 0),
            "composite_score":    sc["composite_score"],
            "weinstein_stage":    str(sc.get("weinstein_stage") or ""),
            "rs_percentile":      sc["rs_percentile"],
            "rs_new_high":        bool(sc.get("rs_new_high")),
            "volume_price_score": sc["volume_price_score"],
            "price_vs_ma":        sc["price_vs_ma"],
            "high_52w":           sc["high_52w"],
            "low_52w":            sc["low_52w"],
            "entry_signal":       str(sc.get("entry_signal") or ""),
            "entry_detail":       str(sc.get("entry_detail") or ""),
            "bucket":             str(sc.get("bucket") or ""),
            "score_change":       sc.get("score_change"),
        }
        row["signals"]  = classify(row)
        row["strength"] = strength(row)
        row["grade"]    = "S" if row["strength"]>=75 else ("A" if row["strength"]>=60 else ("B" if row["strength"]>=40 else "C"))
        rows.append(row)

    master = pd.DataFrame(rows).sort_values("strength",ascending=False).reset_index(drop=True)
    master["rank"] = master.index + 1
    st.session_state["master_df"]   = master
    st.session_state["master_date"] = score_date
else:
    master = st.session_state["master_df"]

if "live_prices" not in st.session_state:
    st.session_state["live_prices"] = {}

# ── Filters ────────────────────────────────────────────────────────────────────
st.markdown("### ⚙️ Filters")
fc1,fc2,fc3,fc4,fc5,fc6 = st.columns([2,1.8,1.8,1.4,0.8,1.2])

univ_lbl = fc1.selectbox("Universe", list(UNIVERSE_OPTIONS.keys()), index=0)
bucket_f = fc2.multiselect("Bucket",["MUST_BUY","CAN_BUY","NEUTRAL","AVOID","SELL"],
                            default=["MUST_BUY","CAN_BUY"])
entry_f  = fc3.multiselect("Entry",["BUY NOW","WATCH","WAIT","AVOID","SELL"],
                            default=["BUY NOW","WATCH"])
grade_f  = fc4.multiselect("Grade",["S","A","B","C"],default=["S","A"])
fo_only  = fc5.checkbox("F&O",value=False)
top_n    = fc6.slider("Top N",25,500,100,step=25)

# Signal legend
st.markdown(
    "**Signals:** " + "  ".join(
        f'<span style="background:{b};color:{f};padding:2px 7px;border-radius:3px;font-size:11px">{s}</span>'
        for s,(b,f) in SIG_COLORS.items()),
    unsafe_allow_html=True)
st.divider()

# Apply filters
filt = master.copy()
uv = UNIVERSE_OPTIONS[univ_lbl]
if uv == "__must_buy__":  filt = filt[filt["bucket"]=="MUST_BUY"]
elif uv == "__can_buy__": filt = filt[filt["bucket"].isin(["MUST_BUY","CAN_BUY"])]
elif uv == "__weak__":    filt = filt[filt["bucket"].isin(["AVOID","SELL"])]
elif uv:                  filt = filt[filt["idx"].apply(lambda m: isinstance(m,list) and uv in m)]
if bucket_f: filt = filt[filt["bucket"].isin(bucket_f)]
if entry_f:  filt = filt[filt["entry_signal"].isin(entry_f)]
if grade_f:  filt = filt[filt["grade"].isin(grade_f)]
if fo_only:  filt = filt[filt["fo"]==True]
filt = filt.head(top_n).reset_index(drop=True)

# ── Summary ─────────────────────────────────────────────────────────────────── 
m1,m2,m3,m4,m5,m6,m7 = st.columns(7)
m1.metric("Showing",   len(filt))
m2.metric("Grade S",   len(filt[filt.grade=="S"]))
m3.metric("Grade A",   len(filt[filt.grade=="A"]))
m4.metric("BUY NOW",   len(filt[filt.entry_signal=="BUY NOW"]))
m5.metric("Breakouts", len(filt[filt.signals.apply(lambda s:"Breakout" in s)]))
m6.metric("RS Leaders",len(filt[filt.signals.apply(lambda s:"RS Leader" in s)]))
ai_n = sum(1 for s in filt["symbol"] if cached_just.get(s,{}).get("text"))
m7.metric("AI Cached", ai_n)

last_ai = max(
    (v["ts"] for v in cached_just.values() if v.get("ts")),
    default="Never")
st.caption(f"📅 Scores: **{score_date}** · 🤖 AI cached: **{len(cached_just)}** stocks · Last run: **{last_ai}**")
st.divider()

# ── Action Buttons ─────────────────────────────────────────────────────────────
col_b1, col_b2, col_b3 = st.columns([2, 3, 1.5])

with col_b1:
    st.markdown("**🔴 Phase 2 — Live Prices via Breeze**")
    st.caption(f"Fetches CMP for {len(filt)} filtered stocks only")
    if st.button("🔴 Fetch Live Prices", key="btn_breeze"):
        live = fetch_live(filt["symbol"].tolist())
        st.session_state["live_prices"].update(live)
        st.success(f"✅ Live prices for {len(live)} stocks")
        st.rerun()

with col_b2:
    st.markdown("**🤖 Phase 3 — AI Analysis (saves to Supabase)**")
    ai_scope = st.selectbox("Scope for AI run:", list(UNIVERSE_OPTIONS.keys()),
                             index=list(UNIVERSE_OPTIONS.keys()).index("✅ MUST_BUY + CAN_BUY"),
                             key="ai_scope", label_visibility="collapsed")
    # Count how many stocks would be analysed
    ai_uv = UNIVERSE_OPTIONS[ai_scope]
    ai_df = master.copy()
    if ai_uv == "__must_buy__":  ai_df = ai_df[ai_df["bucket"]=="MUST_BUY"]
    elif ai_uv == "__can_buy__": ai_df = ai_df[ai_df["bucket"].isin(["MUST_BUY","CAN_BUY"])]
    elif ai_uv == "__weak__":    ai_df = ai_df[ai_df["bucket"].isin(["AVOID","SELL"])]
    elif ai_uv:                  ai_df = ai_df[ai_df["idx"].apply(lambda m: isinstance(m,list) and ai_uv in m)]
    n_ai = len(ai_df)
    n_calls = math.ceil(n_ai/30)
    st.caption(f"~{n_ai} stocks · {n_calls} API calls · ~{n_calls*8}–{n_calls*15} sec")
    if st.button(f"🤖 Run AI — {ai_scope}", key="btn_ai", type="primary"):
        prog = st.progress(0, f"AI analysis for {n_ai} stocks…")
        new_r = {}
        for i in range(0, n_ai, 30):
            chunk = ai_df.iloc[i:i+30]
            batch = [{"sym":r["symbol"],"score":r["strength"],
                      "stage":r["weinstein_stage"],"rs":r["rs_percentile"] or 50,
                      "rsnh":r["rs_new_high"],"d1":r["chg_1d"] or 0,
                      "pvm":r["price_vs_ma"] or 0,"sigs":r["signals"]}
                     for _,r in chunk.iterrows()]
            res = run_claude_batch(batch, score_date, ai_scope)
            new_r.update(res)
            prog.progress(min(i+30,n_ai)/n_ai, f"AI: {min(i+30,n_ai)}/{n_ai}…")
        prog.empty()
        # Force data reload
        st.session_state["ranker_date"] = None
        st.success(f"✅ {len(new_r)} justifications saved! Reloading…")
        time.sleep(0.8)
        st.rerun()

with col_b3:
    st.markdown("**⬇️ Export**")
    exp = filt[["rank","symbol","name","sector","cap",
                "cmp","chg_1d","weinstein_stage","rs_percentile",
                "composite_score","strength","grade","bucket",
                "entry_signal","entry_detail"]].copy()
    exp["signals"]  = filt["signals"].apply(lambda ss:" | ".join(ss))
    exp["ai_justification"] = filt["symbol"].apply(
        lambda s: cached_just.get(s,{}).get("text",""))
    exp["ai_timestamp"] = filt["symbol"].apply(
        lambda s: cached_just.get(s,{}).get("ts",""))
    st.download_button(
        "⬇️ Export CSV", exp.to_csv(index=False).encode(),
        f"alpharadar_{score_date}.csv", "text/csv", key="btn_export")

st.divider()

# ── Table ──────────────────────────────────────────────────────────────────────
live_p = st.session_state.get("live_prices", {})
cap_ic = {"large":"🔵","mid":"🟡","small":"🟢","micro":"⚪"}
tbody = []
for _, r in filt.iterrows():
    lv   = live_p.get(r["symbol"],{})
    cmp  = lv.get("cmp") or r["cmp"]
    chg  = lv.get("chg_1d") or r["chg_1d"]
    live_dot = "🔴 " if lv.get("cmp") else ""

    # 52W range bar
    h52,l52 = r["high_52w"], r["low_52w"]
    pos_html = ""
    if h52 and l52 and cmp and h52>l52:
        pct = (cmp-l52)/(h52-l52)*100
        c52 = "#1a7a4a" if pct>=80 else ("#c47a0b" if pct>=40 else "#c0392b")
        pos_html = (f'<div style="font-size:9px;color:{c52};margin-top:2px">{pct:.0f}% of range</div>'
                    f'<div style="background:#eee;border-radius:2px;height:3px;width:55px;margin-top:1px">'
                    f'<div style="background:{c52};width:{min(pct,100):.0f}%;height:3px;border-radius:2px"></div></div>')

    # Score change badge
    sc_html = ""
    try:
        sc = float(r.get("score_change") or 0)
        if sc>1:    sc_html=f'<span style="color:#1a7a4a;font-size:10px"> ▲{sc:.0f}</span>'
        elif sc<-1: sc_html=f'<span style="color:#c0392b;font-size:10px"> ▼{abs(sc):.0f}</span>'
    except Exception: pass

    # AI cell
    cj = cached_just.get(r["symbol"],{})
    ai_txt = cj.get("text","")
    if ai_txt:
        ai_cell = (f'<span style="font-size:11px;color:#222">{ai_txt}</span>'
                   f'<br><span style="font-size:9px;color:#bbb">🤖 {cj.get("ts","")}</span>')
    else:
        ed = str(r["entry_detail"])
        ed = "—" if ed in ("","nan","None") else ed
        ai_cell = f'<span style="font-size:11px;color:#aaa;font-style:italic">{ed}</span>'

    tbody.append(f"""<tr>
<td style="color:#bbb;font-size:11px;text-align:center">{int(r['rank'])}</td>
<td><div style="font-weight:700;font-size:13px">{live_dot}{r['symbol']}</div>
    <div style="font-size:10px;color:#aaa">{cap_ic.get(str(r['cap']),'⬜')} {str(r['name'])[:24]}</div></td>
<td style="font-size:11px;color:#888;white-space:nowrap">{str(r['sector'])[:16]}</td>
<td><div style="font-size:13px;font-weight:600">{"₹"+f"{cmp:,.1f}" if cmp else "—"}</div>{pos_html}</td>
<td style="text-align:right">{fr(chg)}</td>
<td style="text-align:right">{fr(r['price_vs_ma'])}</td>
<td style="text-align:right">{fr(float(r['score_change'] or 0)) if r['score_change'] else '<span style="color:#ccc">—</span>'}</td>
<td style="text-align:center;font-size:12px">{r['weinstein_stage']}{sc_html}</td>
<td style="text-align:right;font-size:11px;color:#555">{float(r['rs_percentile'] or 0):.0f}%</td>
<td style="text-align:center">{gbadge(r['strength'])}</td>
<td>{stags(r['signals'])}</td>
<td style="text-align:center">{etag(r['entry_signal'])}</td>
<td style="max-width:190px">{ai_cell}</td>
</tr>""")

st.markdown("""
<style>
.rt{width:100%;border-collapse:collapse;font-family:system-ui,sans-serif;font-size:12px}
.rt th{background:#f7f7f5;color:#aaa;font-size:10px;font-weight:700;padding:8px 5px;
       border-bottom:2px solid #e8e8e4;white-space:nowrap;
       position:sticky;top:0;z-index:2;text-align:left}
.rt td{padding:7px 5px;border-bottom:0.5px solid #f2f2f0;vertical-align:middle}
.rt tr:hover td{background:#fafaf8}
</style>
<div style="overflow-x:auto;max-height:70vh;overflow-y:auto">
<table class="rt">
<thead><tr>
  <th>#</th><th>Symbol</th><th>Sector</th><th>CMP</th>
  <th style="text-align:right">1D Chg</th>
  <th style="text-align:right">vs MA%</th>
  <th style="text-align:right">Score Δ</th>
  <th>Stage</th>
  <th style="text-align:right">RS%ile</th>
  <th>Grade</th>
  <th>Signals</th>
  <th>Entry</th>
  <th>AI Justification</th>
</tr></thead>
<tbody>""" + "".join(tbody) + "</tbody></table></div>",
    unsafe_allow_html=True)

# ── Sector heatmap ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("📊 Sector Strength")
sec = (master.groupby("sector")
       .agg(avg=("strength","mean"), n=("symbol","count"),
            avg_rs=("rs_percentile","mean"),
            buy_now=("entry_signal",lambda x:(x=="BUY NOW").sum()))
       .reset_index().sort_values("avg",ascending=False))
for start in range(0, min(len(sec),30), 5):
    cc = st.columns(5)
    for ci,(_,sr) in enumerate(sec.iloc[start:start+5].iterrows()):
        sc=sr["avg"]
        bg="#d4f0e0" if sc>=65 else ("#fff3cd" if sc>=50 else "#fde8e8")
        fg="#0f5c2e" if sc>=65 else ("#7a4f00" if sc>=50 else "#7a1f1f")
        cc[ci].markdown(
            f'<div style="background:{bg};padding:10px;border-radius:8px;margin:2px">'
            f'<div style="font-size:10px;color:{fg};font-weight:700">{sr["sector"][:20]}</div>'
            f'<div style="font-size:20px;font-weight:700;color:{fg}">{sc:.0f}</div>'
            f'<div style="font-size:10px;color:{fg}">n={int(sr["n"])} · RS {sr["avg_rs"]:.0f}% · 🟢{int(sr["buy_now"])}</div>'
            f'</div>', unsafe_allow_html=True)
st.caption(f"Green ≥65 · Amber 50–65 · Red <50 · Scores: {score_date}")
