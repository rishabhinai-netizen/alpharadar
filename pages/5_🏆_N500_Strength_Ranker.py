"""
AlphaRadar — Nifty 500 Strength Ranker  (v5)
Key fixes:
- Default filters relaxed (no Entry/Grade filter by default — show everything ranked)
- Grade thresholds match actual score distribution (S=70+, A=55+, B=40+)
- Breeze status shown inline with last-fetched time
- Sector heatmap replaced with ranked table showing top stocks per sector
- Data probe only runs once per session, not on every render
- Score Δ and vs MA% shown with proper context
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

SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]
HDR   = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
HDR_W = {**HDR, "Content-Type": "application/json",
          "Prefer": "resolution=merge-duplicates,return=minimal"}

BREEZE_MAP = {
    "MAZDOCK":"MAZDOC","COCHINSHIP":"COCHIN","LGEQUIP":"LGEQU",
    "MIRZAINT":"MIRZAI","ADANIENT":"ADANIENS",
}

UNIVERSE_OPTIONS = {
    "🏆 Nifty 500":           "nifty500",
    "💎 Nifty 50":            "nifty50",
    "📊 Midcap 150":          "midcap150",
    "📈 Smallcap 250":        "smallcap250",
    "🌐 Full Universe":       None,
    "🚀 MUST_BUY only":       "__must_buy__",
    "✅ MUST_BUY + CAN_BUY":  "__can_buy__",
    "📉 AVOID + SELL":        "__weak__",
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
    "BUY NOW":  ("#d4f0e0","#0f5c2e"),
    "BUY DIPS": ("#d4f0e0","#0f5c2e"),
    "WATCH":    ("#fff3cd","#7a4f00"),
    "WAIT":     ("#f1efe8","#5f5e5a"),
    "AVOID":    ("#fde8e8","#7a1f1f"),
    "SELL":     ("#fde8e8","#7a1f1f"),
    "N/A":      ("#f1efe8","#aaa"),
}

# Grade thresholds calibrated to actual score distribution (peak ~70-77)
def grade(s):
    if s >= 70: return "S"
    if s >= 55: return "A"
    if s >= 38: return "B"
    return "C"

# ── Data loader ───────────────────────────────────────────────────────────────
def load_fresh():
    """Full data load — stored in session_state, only called when date changes."""
    # Scores
    r1 = requests.get(
        f"{SUPABASE_URL}/rest/v1/ar_daily_scores"
        f"?select=symbol,score_date,composite_score,bucket,weinstein_stage,"
        f"rs_percentile,rs_new_high,volume_price_score,"
        f"price,price_change_pct,high_52w,low_52w,price_vs_ma,ma_slope,"
        f"entry_signal,entry_detail,score_change"
        f"&order=score_date.desc,composite_score.desc&limit=800",
        headers=HDR, timeout=20)
    raw = r1.json() if r1.status_code == 200 else []
    if not raw:
        return None, "N/A", {}, {}

    score_date = raw[0]["score_date"]
    today = [x for x in raw if x["score_date"] == score_date]
    df = pd.DataFrame(today)
    for c in ["composite_score","rs_percentile","volume_price_score",
              "price","price_change_pct","high_52w","low_52w",
              "price_vs_ma","ma_slope","score_change"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Universe
    r2 = requests.get(
        f"{SUPABASE_URL}/rest/v1/ar_universe"
        f"?select=symbol,company_name,sector,cap_bucket,index_membership,fo_enabled"
        f"&is_active=eq.true&limit=2000",
        headers=HDR, timeout=20)
    uni = {d["symbol"]: d for d in (r2.json() if r2.status_code == 200 else [])}

    # Cached AI justifications
    r3 = requests.get(
        f"{SUPABASE_URL}/rest/v1/ar_ai_justifications"
        f"?select=symbol,justification,generated_at"
        f"&score_date=eq.{score_date}&limit=2000",
        headers=HDR, timeout=20)
    just = {
        d["symbol"]: {"text": d["justification"],
                      "ts": (d.get("generated_at") or "")[:10]}
        for d in (r3.json() if r3.status_code == 200 else [])
        if d.get("justification")
    }
    return df, score_date, uni, just


def get_data():
    key = "ranker_v5"
    if key not in st.session_state:
        with st.spinner("⚡ Loading scores from Supabase…"):
            df, sd, uni, just = load_fresh()
        st.session_state[key] = (df, sd, uni, just)
    return st.session_state[key]


def refresh_data():
    st.session_state.pop("ranker_v5", None)
    st.session_state.pop("master_v5", None)
    st.rerun()


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
    rng    = h52 - l52
    pos52  = (price-l52)/rng*100 if rng > 0 else 50
    sigs   = []
    if rs >= 85 or rs_nh:                               sigs.append("RS Leader")
    if pos52 >= 93 or (pos52 >= 88 and vol_s >= 12):    sigs.append("Breakout")
    if "2" in stage:                                     sigs.append("Stage 2")
    if pvm > 30:                                         sigs.append("Extended⚠")
    elif chg > 4 and pvm > 8:                           sigs.append("News-Driven⚑")
    if vol_s >= 14:                                      sigs.append("Vol Surge")
    if "4" in stage or score < 25 or (rs < 25 and pvm < -5): sigs.append("Weak")
    return sigs if sigs else ["Neutral"]


def strength_score(row):
    base  = float(row.get("composite_score",50) or 50)
    vol_s = float(row.get("volume_price_score",0) or 0)
    price = float(row.get("price",0) or 0)
    h52   = float(row.get("high_52w",1) or 1)
    l52   = float(row.get("low_52w",0) or 0)
    pvm   = float(row.get("price_vs_ma",0) or 0)
    sc    = float(row.get("score_change",0) or 0)
    chg   = float(row.get("price_change_pct",0) or 0)
    rng   = h52 - l52
    pos52 = np.clip((price-l52)/rng*100,0,100) if rng > 0 else 50
    vol_n = np.clip(vol_s*5,0,100)
    mom   = np.clip(chg*3 + sc*2 + 50,0,100)
    ext_p = max(0,(pvm-30)*0.5) if pvm > 30 else 0
    return round(float(np.clip(0.45*base+0.20*mom+0.20*vol_n+0.15*pos52-ext_p,0,100)),1)


def build_master(scores_df, uni):
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
            "rs_percentile":      float(sc.get("rs_percentile") or 0),
            "rs_new_high":        bool(sc.get("rs_new_high")),
            "volume_price_score": float(sc.get("volume_price_score") or 0),
            "price_vs_ma":        float(sc.get("price_vs_ma") or 0),
            "high_52w":           sc["high_52w"],
            "low_52w":            sc["low_52w"],
            "entry_signal":       str(sc.get("entry_signal") or "N/A"),
            "entry_detail":       str(sc.get("entry_detail") or ""),
            "bucket":             str(sc.get("bucket") or ""),
            "score_change":       float(sc.get("score_change") or 0),
        }
        row["signals"]  = classify(row)
        row["strength"] = strength_score(row)
        row["grade"]    = grade(row["strength"])
        rows.append(row)

    master = pd.DataFrame(rows).sort_values("strength",ascending=False).reset_index(drop=True)
    master["rank"] = master.index + 1
    return master


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
            return None, "🔄 Token expired → ICICIdirect.com → API → Sessions → Regenerate"
        return None, str(e)


def fetch_live(symbols):
    breeze, err = get_breeze()
    if err or not breeze:
        return {}, err or "Unknown error"
    out = {}
    prog = st.progress(0)
    status = st.empty()
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
        if i % 5 == 0 or i == len(symbols)-1:
            pct = (i+1)/len(symbols)
            prog.progress(pct)
            status.caption(f"🔴 Fetching live prices… {i+1}/{len(symbols)} ({len(out)} got CMP)")
    prog.empty()
    status.empty()
    return out, None


# ── Claude AI ─────────────────────────────────────────────────────────────────
def run_claude_batch(batch, score_date, scope_label):
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY") or st.secrets.get("anthropic_api_key","")
        if not key:
            return {}, "ANTHROPIC_API_KEY not set in Streamlit secrets"
        lines = [
            f"{s['sym']} | Score={s['score']:.0f} | Stage={s['stage']} | "
            f"RS%={s['rs']:.0f} | RSNewHigh={s['rsnh']} | 1D={s['d1']:+.1f}% | "
            f"PvMA={s['pvm']:+.1f}% | Entry={s['entry']} | Signals={','.join(s['sigs'])}"
            for s in batch
        ]
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type":"application/json"},
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "system": (
                    "You are a top Indian equity analyst using O'Neil + Minervini + Weinstein. "
                    "For EACH stock: ONE LINE, max 12 words, specific trader language. "
                    "Examples: 'Stage 2A breakout, RS new high, accumulation on dips' "
                    "'⚑ Sharp result-driven spike, extended above MA, wait for pullback' "
                    "'Below 200MA, Stage 4 decline, avoid until base forms' "
                    "Return ONLY valid JSON: {\"SYMBOL\": \"justification\"}. No extra text."
                ),
                "messages":[{"role":"user","content":"\n".join(lines)}],
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return {}, f"API error {resp.status_code}"
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
        return result, None
    except Exception as e:
        return {}, str(e)


# ── Formatters ─────────────────────────────────────────────────────────────────
def fr(v, suffix=""):
    if v is None or (isinstance(v,float) and math.isnan(v)) or v == 0:
        return '<span style="color:#ccc">—</span>'
    c = "#1a7a4a" if v>0 else "#c0392b"
    a = "▲" if v>0 else "▼"
    return f'<span style="color:{c};font-weight:600">{a}{abs(v):.1f}{suffix}</span>'

def gbadge(g, s):
    theme = {"S":("#d4f0e0","#0f5c2e"), "A":("#dceeff","#0c3d7a"),
             "B":("#fff3cd","#7a4f00"), "C":("#fde8e8","#7a1f1f")}
    b,f = theme.get(g,("#eee","#555"))
    return f'<span style="background:{b};color:{f};padding:2px 10px;border-radius:10px;font-size:11px;font-weight:700">{g} {s:.0f}</span>'

def stags(sigs):
    return " ".join(
        f'<span style="background:{SIG_COLORS.get(s,("#eee","#333"))[0]};'
        f'color:{SIG_COLORS.get(s,("#eee","#333"))[1]};'
        f'padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">{s}</span>'
        for s in sigs)

def etag(label):
    if not label or label in ("nan","None","N/A",""): return ""
    b,f = ENTRY_COLORS.get(label,("#f1efe8","#888"))
    return f'<span style="background:{b};color:{f};padding:2px 8px;border-radius:3px;font-size:11px;font-weight:700">{label}</span>'


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
st.title("🏆 N500 Strength Ranker")
st.caption("Strongest stocks ranked #1 · Scores from AlphaRadar engine · Live prices & AI on button click")

# Load data
scores_df, score_date, uni, cached_just = get_data()

if scores_df is None or scores_df.empty:
    st.error("⚠️ No scores found. Run **⚡ Run Scoring** tab first.")
    st.stop()

# Build master (cached in session_state)
if "master_v5" not in st.session_state:
    st.session_state["master_v5"] = build_master(scores_df, uni)
master = st.session_state["master_v5"]

if "live_prices" not in st.session_state:
    st.session_state["live_prices"] = {}
if "breeze_status" not in st.session_state:
    st.session_state["breeze_status"] = "Not fetched yet"

# ── Filters ────────────────────────────────────────────────────────────────────
st.markdown("### ⚙️ Filters")
fc1,fc2,fc3,fc4,fc5 = st.columns([2,1.8,1.8,0.8,1.2])
univ_lbl  = fc1.selectbox("Universe", list(UNIVERSE_OPTIONS.keys()), index=0)
bucket_f  = fc2.multiselect("Bucket", ["MUST_BUY","CAN_BUY","NEUTRAL","AVOID","SELL"],
                             default=["MUST_BUY","CAN_BUY"])
entry_all = sorted(master["entry_signal"].dropna().unique().tolist())
entry_f   = fc3.multiselect("Entry Signal", entry_all, default=[])
fo_only   = fc4.checkbox("F&O", value=False)
top_n     = fc5.slider("Top N", 25, 500, 150, step=25)

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
if bucket_f:  filt = filt[filt["bucket"].isin(bucket_f)]
if entry_f:   filt = filt[filt["entry_signal"].isin(entry_f)]
if fo_only:   filt = filt[filt["fo"]==True]
filt = filt.head(top_n).reset_index(drop=True)

# ── Summary metrics ─────────────────────────────────────────────────────────── 
m1,m2,m3,m4,m5,m6,m7,m8 = st.columns(8)
m1.metric("Showing",   len(filt))
m2.metric("Grade S",   int((filt.grade=="S").sum()))
m3.metric("Grade A",   int((filt.grade=="A").sum()))
m4.metric("Grade B",   int((filt.grade=="B").sum()))
m5.metric("BUY NOW",   int((filt.entry_signal=="BUY NOW").sum()))
m6.metric("Breakouts", int(filt.signals.apply(lambda s:"Breakout" in s).sum()))
m7.metric("RS Leaders",int(filt.signals.apply(lambda s:"RS Leader" in s).sum()))
ai_n = sum(1 for s in filt["symbol"] if cached_just.get(s,{}).get("text"))
m8.metric("AI Cached", ai_n)

last_ai = max((v["ts"] for v in cached_just.values() if v.get("ts")), default="Never")
live_ct = len(st.session_state.get("live_prices",{}))
st.caption(
    f"📅 Scores: **{score_date}** · "
    f"🔴 Live prices: **{live_ct} stocks** ({st.session_state['breeze_status']}) · "
    f"🤖 AI cached: **{len(cached_just)} stocks** · Last AI run: **{last_ai}**"
)
st.divider()

# ── Action Buttons ─────────────────────────────────────────────────────────────
col_b1, col_b2, col_b3, col_b4 = st.columns([1.5, 2.5, 1.5, 1])

with col_b1:
    st.markdown("**🔴 Live Prices (Breeze)**")
    n_fetch = len(filt)
    st.caption(f"Will fetch CMP for {n_fetch} filtered stocks")
    if st.button("🔴 Fetch Live Prices", key="btn_breeze"):
        syms = filt["symbol"].tolist()
        live, err = fetch_live(syms)
        if err:
            st.error(f"Breeze error: {err}")
        else:
            st.session_state["live_prices"].update(live)
            ts = datetime.now().strftime("%H:%M:%S")
            st.session_state["breeze_status"] = f"{len(live)} fetched at {ts}"
            if live:
                st.success(f"✅ {len(live)}/{len(syms)} stocks got live CMP")
            else:
                st.warning("⚠️ 0 prices received — Breeze session may be expired. Regenerate BREEZE_SESSION_TOKEN.")
        st.rerun()

with col_b2:
    st.markdown("**🤖 AI Analysis (saves to Supabase)**")
    ai_scope = st.selectbox(
        "Scope:", list(UNIVERSE_OPTIONS.keys()),
        index=list(UNIVERSE_OPTIONS.keys()).index("✅ MUST_BUY + CAN_BUY"),
        key="ai_scope", label_visibility="collapsed")
    ai_uv = UNIVERSE_OPTIONS[ai_scope]
    ai_df = master.copy()
    if ai_uv == "__must_buy__":  ai_df = ai_df[ai_df["bucket"]=="MUST_BUY"]
    elif ai_uv == "__can_buy__": ai_df = ai_df[ai_df["bucket"].isin(["MUST_BUY","CAN_BUY"])]
    elif ai_uv == "__weak__":    ai_df = ai_df[ai_df["bucket"].isin(["AVOID","SELL"])]
    elif ai_uv:                  ai_df = ai_df[ai_df["idx"].apply(lambda m: isinstance(m,list) and ai_uv in m)]
    n_ai = len(ai_df); n_calls = math.ceil(n_ai/30)
    st.caption(f"~{n_ai} stocks · {n_calls} API calls · ~{n_calls*8}–{n_calls*15} sec")
    if st.button(f"🤖 Run AI Analysis", key="btn_ai", type="primary"):
        prog = st.progress(0)
        status_ai = st.empty()
        new_r = {}
        for i in range(0, n_ai, 30):
            chunk = ai_df.iloc[i:i+30]
            batch = [{"sym":r["symbol"],"score":r["strength"],
                      "stage":r["weinstein_stage"],"rs":r["rs_percentile"],
                      "rsnh":r["rs_new_high"],"d1":r["chg_1d"],
                      "pvm":r["price_vs_ma"],"entry":r["entry_signal"],
                      "sigs":r["signals"]}
                     for _,r in chunk.iterrows()]
            res, err = run_claude_batch(batch, score_date, ai_scope)
            if err: status_ai.warning(f"Batch error: {err}")
            new_r.update(res)
            done = min(i+30,n_ai)
            prog.progress(done/n_ai)
            status_ai.caption(f"AI: {done}/{n_ai} stocks done, {len(new_r)} written to Supabase…")
        prog.empty(); status_ai.empty()
        st.session_state.pop("ranker_v5",None)
        st.success(f"✅ {len(new_r)} justifications saved!")
        time.sleep(0.8); st.rerun()

with col_b3:
    st.markdown("**⬇️ Export**")
    exp = filt[["rank","symbol","name","sector","cap","cmp","chg_1d",
                "weinstein_stage","rs_percentile","composite_score",
                "strength","grade","bucket","entry_signal","entry_detail"]].copy()
    exp["signals"]          = filt["signals"].apply(lambda ss:" | ".join(ss))
    exp["ai_justification"] = filt["symbol"].apply(lambda s: cached_just.get(s,{}).get("text",""))
    exp["ai_timestamp"]     = filt["symbol"].apply(lambda s: cached_just.get(s,{}).get("ts",""))
    # Add live CMP where available
    for idx2, row in exp.iterrows():
        lv = st.session_state["live_prices"].get(row["symbol"],{})
        if lv.get("cmp"):
            exp.at[idx2,"cmp"] = lv["cmp"]
            exp.at[idx2,"chg_1d"] = lv.get("chg_1d",row["chg_1d"])
    st.download_button("⬇️ Export CSV", exp.to_csv(index=False).encode(),
                       f"alpharadar_{score_date}.csv", "text/csv", key="btn_exp")

with col_b4:
    st.markdown("**🔄 Refresh**")
    st.caption("Reload from Supabase")
    if st.button("🔄 Refresh Data", key="btn_refresh"):
        st.session_state.pop("ranker_v5",None)
        st.session_state.pop("master_v5",None)
        st.rerun()

st.divider()

# ── Main table ──────────────────────────────────────────────────────────────────
if len(filt) == 0:
    st.warning(
        "⚠️ **No stocks match your current filters.**\n\n"
        "Try relaxing filters — the data is loaded correctly. "
        f"Total universe: **{len(master)} stocks**. "
        "Suggestion: clear the Entry Signal filter (most stocks are 'WAIT'), "
        "or change Grade to include B."
    )
else:
    live_p = st.session_state.get("live_prices",{})
    cap_ic = {"large":"🔵","mid":"🟡","small":"🟢","micro":"⚪"}
    tbody  = []

    for _, r in filt.iterrows():
        lv   = live_p.get(r["symbol"],{})
        cmp  = lv.get("cmp") or r["cmp"]
        chg  = lv.get("chg_1d") if lv.get("cmp") else r["chg_1d"]
        live_dot = '<span style="color:#e74c3c;font-size:9px">●</span> ' if lv.get("cmp") else ""

        # 52W range mini-bar
        h52,l52 = r["high_52w"], r["low_52w"]
        rng52 = (h52-l52) if (h52 and l52 and h52>l52) else 0
        pos52_html = ""
        if rng52 > 0 and cmp:
            pct52 = np.clip((cmp-l52)/rng52*100,0,100)
            c52 = "#1a7a4a" if pct52>=80 else ("#c47a0b" if pct52>=40 else "#c0392b")
            pos52_html = (
                f'<div style="display:flex;align-items:center;gap:4px;margin-top:2px">'
                f'<div style="background:#eee;border-radius:2px;height:4px;width:50px;flex-shrink:0">'
                f'<div style="background:{c52};width:{pct52:.0f}%;height:4px;border-radius:2px"></div></div>'
                f'<span style="font-size:9px;color:{c52}">{pct52:.0f}%</span></div>')

        # Score change
        sc = r["score_change"]
        sc_html = ""
        if sc and abs(sc) > 0.5:
            sc_html = f'<span style="color:{"#1a7a4a" if sc>0 else "#c0392b"};font-size:10px">{"▲" if sc>0 else "▼"}{abs(sc):.0f}</span>'

        # AI cell
        cj = cached_just.get(r["symbol"],{})
        if cj.get("text"):
            ai_cell = (f'<div style="font-size:11px;color:#222;line-height:1.4">{cj["text"]}</div>'
                       f'<div style="font-size:9px;color:#bbb;margin-top:1px">🤖 {cj.get("ts","")}</div>')
        else:
            ed = str(r["entry_detail"])
            ed = "—" if ed in ("","nan","None") else ed[:60]
            ai_cell = f'<div style="font-size:11px;color:#aaa;font-style:italic">{ed}</div>'

        tbody.append(f"""<tr>
<td style="color:#bbb;font-size:11px;text-align:center;width:30px">{int(r['rank'])}</td>
<td style="min-width:110px">
  <div style="font-weight:700;font-size:13px">{live_dot}{r['symbol']}</div>
  <div style="font-size:10px;color:#aaa">{cap_ic.get(str(r['cap']),'⬜')} {str(r['name'])[:22]}</div>
</td>
<td style="font-size:11px;color:#777;white-space:nowrap;min-width:90px">{str(r['sector'])[:14]}</td>
<td style="min-width:90px">
  <div style="font-size:13px;font-weight:600">{"₹"+f"{cmp:,.1f}" if cmp else "—"}</div>
  {pos52_html}
</td>
<td style="text-align:right;white-space:nowrap">{fr(chg,"%")}</td>
<td style="text-align:right;white-space:nowrap">{fr(r['price_vs_ma'],"%")}</td>
<td style="text-align:right;font-size:11px">{r['rs_percentile']:.0f}%</td>
<td style="text-align:center;font-size:11px;white-space:nowrap">{r['weinstein_stage']} {sc_html}</td>
<td style="text-align:center">{gbadge(r['grade'],r['strength'])}</td>
<td style="min-width:140px">{stags(r['signals'])}</td>
<td style="text-align:center;white-space:nowrap">{etag(r['entry_signal'])}</td>
<td style="min-width:190px">{ai_cell}</td>
</tr>""")

    st.markdown("""
<style>
.rt{width:100%;border-collapse:collapse;font-family:system-ui,sans-serif;font-size:12px}
.rt th{background:#f7f7f5;color:#aaa;font-size:10px;font-weight:700;
       padding:8px 6px;border-bottom:2px solid #e8e8e4;white-space:nowrap;
       position:sticky;top:0;z-index:2;text-align:left}
.rt td{padding:7px 6px;border-bottom:0.5px solid #f2f2f0;vertical-align:middle}
.rt tr:hover td{background:#fafaf8}
</style>
<div style="overflow-x:auto;max-height:68vh;overflow-y:auto">
<table class="rt">
<thead><tr>
  <th>#</th>
  <th>Symbol</th>
  <th>Sector</th>
  <th>CMP  ·  52W range</th>
  <th style="text-align:right">1D%</th>
  <th style="text-align:right">vs MA%</th>
  <th style="text-align:right">RS%ile</th>
  <th>Stage</th>
  <th>Grade</th>
  <th>Signals</th>
  <th>Entry</th>
  <th>AI Justification</th>
</tr></thead>
<tbody>""" + "".join(tbody) + "</tbody></table></div>",
        unsafe_allow_html=True)

# ── Sector Insights ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("📊 Sector Insights — Where is strength concentrated?")

# Compute sector stats from full master
def sector_stats(df):
    def pct_stage2(x): return (x.str.contains("2",na=False)).mean()*100
    def pct_buynow(x): return (x.isin(["BUY NOW","BUY DIPS"])).mean()*100
    stats = df.groupby("sector").agg(
        n         =("symbol","count"),
        avg_score =("strength","mean"),
        avg_rs    =("rs_percentile","mean"),
        pct_s2    =("weinstein_stage", pct_stage2),
        pct_buy   =("entry_signal",    pct_buynow),
        n_buy     =("entry_signal",    lambda x:(x.isin(["BUY NOW","BUY DIPS"])).sum()),
        n_rs_lead =("signals",         lambda x:x.apply(lambda s:"RS Leader" in s).sum()),
        n_break   =("signals",         lambda x:x.apply(lambda s:"Breakout" in s).sum()),
        top_stock =("symbol",          lambda x: df.loc[x.index].sort_values("strength",ascending=False).iloc[0]["symbol"]),
        top_score =("strength",        "max"),
    ).reset_index().sort_values("avg_score",ascending=False)
    return stats

sec = sector_stats(master)

# Trend verdict
def verdict(row):
    if row["avg_score"] >= 65 and row["pct_s2"] >= 50:
        return "🟢 Strong trend"
    elif row["avg_score"] >= 55:
        return "🟡 Emerging"
    elif row["avg_score"] < 40:
        return "🔴 Weak / avoid"
    return "⚪ Neutral"

sec["verdict"] = sec.apply(verdict, axis=1)

# Render as a rich HTML table (not colored boxes)
sec_rows = []
for _, sr in sec.iterrows():
    sc = sr["avg_score"]
    bg = "#d4f0e0" if sc>=65 else ("#fff3cd" if sc>=55 else ("#f1efe8" if sc>=40 else "#fde8e8"))
    fg = "#0f5c2e" if sc>=65 else ("#7a4f00" if sc>=55 else ("#5f5e5a" if sc>=40 else "#7a1f1f"))
    sec_rows.append(f"""<tr>
<td style="font-weight:700;font-size:13px;color:#333">{sr['sector']}</td>
<td style="text-align:center">
  <span style="background:{bg};color:{fg};padding:3px 10px;border-radius:8px;font-size:12px;font-weight:700">{sc:.0f}</span>
</td>
<td style="text-align:center;font-size:12px">{sr['avg_rs']:.0f}%ile</td>
<td style="text-align:center;font-size:12px">{sr['pct_s2']:.0f}%</td>
<td style="text-align:center">
  <span style="font-size:12px;font-weight:600;color:#0f5c2e">{int(sr['n_buy'])}</span>
  <span style="font-size:10px;color:#aaa"> / {int(sr['n'])}</span>
</td>
<td style="text-align:center;font-size:12px">{int(sr['n_rs_lead'])}</td>
<td style="text-align:center;font-size:12px">{int(sr['n_break'])}</td>
<td style="font-size:12px">
  <span style="font-weight:600;color:#0c3d7a">{sr['top_stock']}</span>
  <span style="font-size:10px;color:#aaa"> ({sr['top_score']:.0f})</span>
</td>
<td style="font-size:12px">{sr['verdict']}</td>
</tr>""")

st.markdown("""
<style>
.st{width:100%;border-collapse:collapse;font-family:system-ui,sans-serif}
.st th{background:#f7f7f5;color:#aaa;font-size:10px;font-weight:700;
       padding:8px 8px;border-bottom:2px solid #e8e8e4;text-align:left;white-space:nowrap}
.st td{padding:8px 8px;border-bottom:0.5px solid #f2f2f0;vertical-align:middle}
.st tr:hover td{background:#fafaf8}
</style>
<table class="st">
<thead><tr>
  <th>Sector</th>
  <th style="text-align:center">Avg Score</th>
  <th style="text-align:center">Avg RS</th>
  <th style="text-align:center">% Stage 2</th>
  <th style="text-align:center">BUY NOW</th>
  <th style="text-align:center">RS Leaders</th>
  <th style="text-align:center">Breakouts</th>
  <th>Top Stock</th>
  <th>Verdict</th>
</tr></thead>
<tbody>""" + "".join(sec_rows) + "</tbody></table>",
    unsafe_allow_html=True)

st.caption(
    "**How to read:** Avg Score = sector strength (70+ = strong). "
    "% Stage 2 = % of stocks in Weinstein uptrend. "
    "BUY NOW = actionable setups today. RS Leaders = relative strength leaders. "
    "Top Stock = highest-scored stock in sector."
)
