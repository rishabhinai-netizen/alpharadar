"""
AlphaRadar — Nifty 500 Strength Ranker  (v3)
============================================
PHASE 1 — Instant load (<2 sec): Supabase scores + cached AI justifications
PHASE 2 — [Button] Live prices via Breeze (filtered stocks only)
PHASE 3 — [Button] AI analysis saved to ar_ai_justifications table permanently
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
SB_H_READ = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
SB_H_WRITE = {**SB_H_READ, "Content-Type": "application/json",
              "Prefer": "resolution=merge-duplicates,return=minimal"}

BREEZE_MAP = {
    "MAZDOCK": "MAZDOC", "COCHINSHIP": "COCHIN", "LGEQUIP": "LGEQU",
    "MIRZAINT": "MIRZAI", "ADANIENT": "ADANIENS",
}

UNIVERSE_OPTIONS = {
    "🌐 Full Universe (~750 stocks)":       None,
    "🏆 Nifty 500":                         "nifty500",
    "💎 Nifty 50":                          "nifty50",
    "📊 Nifty Midcap 150":                  "midcap150",
    "📈 Nifty Smallcap 250":                "smallcap250",
    "🚀 MUST_BUY only":                     "__must_buy__",
    "✅ MUST_BUY + CAN_BUY":                "__can_buy__",
    "📉 AVOID + SELL (short candidates)":   "__weak__",
}

SIGNAL_META = {
    "RS Leader":    ("#dceeff", "#0c3d7a"),
    "Breakout":     ("#d4f0e0", "#0f5c2e"),
    "Stage 2":      ("#e8d4f0", "#4a0f7a"),
    "News-Driven⚑": ("#fff3cd", "#7a4f00"),
    "Vol Surge":    ("#d4eaf0", "#0f4a5c"),
    "Extended⚠":   ("#ffe8cc", "#7a3f00"),
    "Weak":         ("#fde8e8", "#7a1f1f"),
    "Neutral":      ("#f1efe8", "#5f5e5a"),
}

ENTRY_STYLE = {
    "BUY NOW": ("#d4f0e0","#0f5c2e"),
    "WATCH":   ("#fff3cd","#7a4f00"),
    "WAIT":    ("#f1efe8","#5f5e5a"),
    "AVOID":   ("#fde8e8","#7a1f1f"),
    "SELL":    ("#fde8e8","#7a1f1f"),
}

# ── Supabase helpers ──────────────────────────────────────────────────────────
def sb_get(table, select="*", qs="", limit=5000):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}&limit={limit}"
    if qs:
        url += f"&{qs}"
    try:
        r = requests.get(url, headers=SB_H_READ, timeout=25)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

def sb_upsert(table, records):
    try:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}",
                          headers=SB_H_WRITE, json=records, timeout=30)
        return r.status_code in (200, 201, 204)
    except Exception:
        return False

@st.cache_data(ttl=120, show_spinner=False)
def load_scores():
    latest = sb_get("ar_daily_scores","score_date","order=score_date.desc&limit=1")
    if not latest:
        return pd.DataFrame(), "N/A"
    ld = latest[0]["score_date"]
    data = sb_get(
        "ar_daily_scores",
        "symbol,score_date,composite_score,bucket,weinstein_stage,"
        "rs_percentile,rs_new_high,stage_score,rs_score,volume_price_score,"
        "price,price_change_pct,high_52w,low_52w,price_vs_ma,ma_slope,"
        "entry_signal,entry_detail,score_change,data_quality",
        f"score_date=eq.{ld}&order=composite_score.desc", limit=2000)
    if not data:
        return pd.DataFrame(), ld
    df = pd.DataFrame(data)
    for c in ["composite_score","rs_percentile","stage_score","rs_score",
              "volume_price_score","price","price_change_pct",
              "high_52w","low_52w","price_vs_ma","ma_slope","score_change"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df, ld

@st.cache_data(ttl=120, show_spinner=False)
def load_universe():
    data = sb_get("ar_universe",
                  "symbol,company_name,sector,cap_bucket,index_membership,fo_enabled",
                  "is_active=eq.true", limit=2000)
    return {d["symbol"]: d for d in data} if data else {}

@st.cache_data(ttl=3600, show_spinner=False)
def load_price_history():
    data = sb_get("ar_daily_scores","symbol,score_date,price",
                  "order=symbol.asc,score_date.desc", limit=150000)
    if not data:
        return {}
    df = pd.DataFrame(data)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    hist = {}
    for sym, g in df.groupby("symbol"):
        hist[sym] = g.sort_values("score_date",ascending=False)["price"].values
    return hist

@st.cache_data(ttl=60, show_spinner=False)
def load_cached_justifications(score_date):
    data = sb_get("ar_ai_justifications",
                  "symbol,justification,signals,strength_score,generated_at,universe_scope",
                  f"score_date=eq.{score_date}", limit=2000)
    return {
        d["symbol"]: {
            "text": d.get("justification",""),
            "generated_at": d.get("generated_at",""),
            "universe_scope": d.get("universe_scope",""),
        }
        for d in data if d.get("justification")
    } if data else {}

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
            return None, "Token expired — regenerate at ICICIdirect.com → API → Sessions"
        return None, f"Breeze: {err}"

def fetch_live(symbols):
    breeze, err = get_breeze()
    if err or not breeze:
        st.warning(f"⚠️ {err}")
        return {}
    out = {}
    pb = st.progress(0, f"Fetching live prices for {len(symbols)} stocks…")
    for i, sym in enumerate(symbols):
        try:
            resp = breeze.get_quotes(stock_code=BREEZE_MAP.get(sym, sym),
                                     exchange_code="NSE", product_type="cash",
                                     expiry_date="", right="", strike_price="")
            if resp and resp.get("Success"):
                d = resp["Success"][0]
                ltp = float(d.get("last_rate",0) or 0)
                prev = float(d.get("previous_close",0) or 0)
                if ltp > 0:
                    out[sym] = {"cmp": round(ltp,2),
                                "chg_1d": round((ltp-prev)/prev*100,2) if prev > 0 else 0.0}
            time.sleep(0.04)
        except Exception:
            continue
        if i % 10 == 0:
            pb.progress((i+1)/len(symbols), f"Breeze: {len(out)}/{len(symbols)}…")
    pb.empty()
    return out

# ── Scoring ───────────────────────────────────────────────────────────────────
def calc_returns(sym, hist, cmp=None):
    s = hist.get(sym)
    out = dict(ret_1w=None, ret_1m=None, ret_3m=None, ret_1y=None)
    if s is None or len(s) < 2:
        return out
    p0 = cmp or float(s[0])
    def r(n):
        if len(s) > n and s[n] and float(s[n]) > 0:
            return round((p0 - float(s[n])) / float(s[n]) * 100, 2)
        return None
    out["ret_1w"] = r(5); out["ret_1m"] = r(21)
    out["ret_3m"] = r(63); out["ret_1y"] = r(252)
    return out

def classify(row):
    stage  = str(row.get("weinstein_stage","") or "")
    rs_pct = float(row.get("rs_percentile",50) or 50)
    rs_nh  = bool(row.get("rs_new_high"))
    score  = float(row.get("composite_score",50) or 50)
    pvm    = float(row.get("price_vs_ma",0) or 0)
    vol_s  = float(row.get("volume_price_score",0) or 0)
    price  = float(row.get("price",0) or 0)
    h52    = float(row.get("high_52w",0) or 0)
    l52    = float(row.get("low_52w",0) or 0)
    r1m    = float(row.get("ret_1m",0) or 0)
    r3m    = float(row.get("ret_3m",0) or 0)
    rng    = h52 - l52
    pos52  = (price - l52) / rng * 100 if rng > 0 else 50
    sigs   = []
    if rs_pct >= 85 or rs_nh:                              sigs.append("RS Leader")
    if pos52 >= 95 or (pos52 >= 88 and vol_s >= 12):       sigs.append("Breakout")
    if "2" in stage:                                        sigs.append("Stage 2")
    if pvm > 30:                                            sigs.append("Extended⚠")
    elif r1m > 18 and (r3m == 0 or r1m > r3m * 0.65):     sigs.append("News-Driven⚑")
    if vol_s >= 14:                                         sigs.append("Vol Surge")
    if "4" in stage or score < 25 or (rs_pct < 25 and pvm < -5): sigs.append("Weak")
    return sigs if sigs else ["Neutral"]

def strength_score(row):
    base  = float(row.get("composite_score",50) or 50)
    vol_s = float(row.get("volume_price_score",0) or 0)
    price = float(row.get("price",0) or 0)
    h52   = float(row.get("high_52w",1) or 1)
    l52   = float(row.get("low_52w",0) or 0)
    pvm   = float(row.get("price_vs_ma",0) or 0)
    r1w   = float(row.get("ret_1w",0) or 0)
    r1m   = float(row.get("ret_1m",0) or 0)
    r3m   = float(row.get("ret_3m",0) or 0)
    r1y   = float(row.get("ret_1y",0) or 0)
    rng   = h52 - l52
    pos52 = np.clip((price-l52)/rng*100, 0, 100) if rng > 0 else 50
    mom   = np.clip(r1w*4 + r1m*1.5 + r3m*0.5 + r1y*0.08 + 50, 0, 100)
    vol_n = np.clip(vol_s*5, 0, 100)
    ext_p = max(0,(pvm-30)*0.5) if pvm > 30 else 0
    return round(float(np.clip(0.42*base + 0.28*mom + 0.15*vol_n + 0.15*pos52 - ext_p, 0, 100)), 1)

# ── Claude AI ─────────────────────────────────────────────────────────────────
def run_claude_batch(batch, score_date, scope_label):
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY") or st.secrets.get("anthropic_api_key","")
        if not key:
            return {}
        lines = [
            f"{s['sym']} | Score={s['score']:.0f} | Stage={s['stage']} | "
            f"RS%={s['rs']:.0f} | RSNewHigh={s['rsnh']} | "
            f"1D={s['d1']:+.1f}% | 1W={s['w1']:+.1f}% | 1M={s['m1']:+.1f}% | "
            f"3M={s['m3']:+.1f}% | 1Y={s['y1']:+.1f}% | "
            f"PvMA={s['pvm']:+.1f}% | Signals={','.join(s['sigs'])}"
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
                    "Use specific trader language. News-Driven⚑: include ⚑, note limited juice. "
                    "Extended⚠: warn parabolic risk. Weak: be direct. "
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
            {"symbol": sym, "score_date": score_date, "justification": just,
             "signals": " | ".join(next((s["sigs"] for s in batch if s["sym"]==sym),[])),
             "strength_score": next((s["score"] for s in batch if s["sym"]==sym), None),
             "generated_at": now, "model_used": "claude-sonnet-4-20250514",
             "universe_scope": scope_label}
            for sym, just in result.items()
        ]
        sb_upsert("ar_ai_justifications", recs)
        return result
    except Exception as e:
        st.warning(f"Claude batch error: {e}")
        return {}

# ── Formatting ────────────────────────────────────────────────────────────────
def fr(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return '<span style="color:#ccc">—</span>'
    c = "#1a7a4a" if v > 0 else ("#c0392b" if v < 0 else "#888")
    a = "▲" if v > 0 else ("▼" if v < 0 else "")
    return f'<span style="color:{c};font-weight:500">{a}{abs(v):.1f}%</span>'

def grade_badge(s):
    if s>=75:   b,f,g="#d4f0e0","#0f5c2e","S"
    elif s>=60: b,f,g="#dceeff","#0c3d7a","A"
    elif s>=40: b,f,g="#fff3cd","#7a4f00","B"
    else:       b,f,g="#fde8e8","#7a1f1f","C"
    return f'<span style="background:{b};color:{f};padding:2px 9px;border-radius:10px;font-size:11px;font-weight:700">{g} {s:.0f}</span>'

def sig_tags(sigs):
    parts=[]
    for s in sigs:
        b,f=SIGNAL_META.get(s,("#eee","#333"))
        parts.append(f'<span style="background:{b};color:{f};padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">{s}</span>')
    return " ".join(parts)

def etag(label):
    if not label or label=="nan": return ""
    b,f=ENTRY_STYLE.get(label,("#f1efe8","#5f5e5a"))
    return f'<span style="background:{b};color:{f};padding:1px 7px;border-radius:3px;font-size:11px;font-weight:600">{label}</span>'

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN UI
# ══════════════════════════════════════════════════════════════════════════════
st.title("🏆 Nifty 500 — Strength Ranker")
st.caption("Strongest stocks ranked #1 · ⚡ Loads instantly · Live prices & AI on-demand buttons")

# PHASE 1: Load data
with st.spinner("⚡ Loading scores…"):
    scores_df, score_date = load_scores()
    universe = load_universe()

if scores_df.empty:
    st.error("⚠️ No scores found. Run **⚡ Run Scoring** tab first.")
    st.stop()

with st.spinner("Loading price history…"):
    hist = load_price_history()

cached_just = load_cached_justifications(score_date)

# Build master
rows = []
for _, sc in scores_df.iterrows():
    sym = sc["symbol"]
    uni = universe.get(sym, {})
    rets = calc_returns(sym, hist)
    row = {
        "symbol": sym,
        "name": uni.get("company_name", sym),
        "sector": uni.get("sector","—"),
        "cap": uni.get("cap_bucket","—"),
        "fo": bool(uni.get("fo_enabled", False)),
        "index_membership": uni.get("index_membership") or [],
        "cmp": float(sc.get("price") or 0) or None,
        "chg_1d": float(sc.get("price_change_pct") or 0),
        **rets,
        "composite_score": sc["composite_score"],
        "weinstein_stage": str(sc.get("weinstein_stage") or ""),
        "rs_percentile": sc["rs_percentile"],
        "rs_new_high": bool(sc.get("rs_new_high")),
        "volume_price_score": sc["volume_price_score"],
        "price_vs_ma": sc["price_vs_ma"],
        "high_52w": sc["high_52w"],
        "low_52w": sc["low_52w"],
        "entry_signal": str(sc.get("entry_signal") or ""),
        "entry_detail": str(sc.get("entry_detail") or ""),
        "bucket": str(sc.get("bucket") or ""),
        "score_change": sc.get("score_change"),
    }
    row["signals"]  = classify(row)
    row["strength"] = strength_score(row)
    row["grade"]    = "S" if row["strength"]>=75 else ("A" if row["strength"]>=60 else ("B" if row["strength"]>=40 else "C"))
    cj = cached_just.get(sym, {})
    row["ai_just"]      = cj.get("text","")
    row["ai_generated"] = cj.get("generated_at","")
    rows.append(row)

master = pd.DataFrame(rows).sort_values("strength", ascending=False).reset_index(drop=True)
master["rank"] = master.index + 1

if "live_prices" not in st.session_state:
    st.session_state["live_prices"] = {}

# ── Filters ────────────────────────────────────────────────────────────────────
st.markdown("### ⚙️ Filters")
fc1,fc2,fc3,fc4,fc5,fc6 = st.columns([2,1.5,1.5,1.5,1,1.5])
univ_label = fc1.selectbox("Universe", list(UNIVERSE_OPTIONS.keys()), index=1)
bucket_f   = fc2.multiselect("Scoring Bucket",["MUST_BUY","CAN_BUY","NEUTRAL","AVOID","SELL"],default=["MUST_BUY","CAN_BUY"])
entry_f    = fc3.multiselect("Entry Signal",["BUY NOW","WATCH","WAIT","AVOID","SELL"],default=["BUY NOW","WATCH"])
grade_f    = fc4.multiselect("Grade",["S","A","B","C"],default=["S","A"])
fo_only    = fc5.checkbox("F&O only",value=False)
top_n      = fc6.slider("Show top N",25,750,100,step=25)

st.markdown(
    "**Signals:** " + " &nbsp;".join(
        f'<span style="background:{b};color:{f};padding:2px 6px;border-radius:3px;font-size:11px">{s}</span>'
        for s,(b,f) in SIGNAL_META.items()),
    unsafe_allow_html=True)
st.divider()

# Apply filters
filt = master.copy()
uv = UNIVERSE_OPTIONS[univ_label]
if uv == "__must_buy__":   filt = filt[filt["bucket"]=="MUST_BUY"]
elif uv == "__can_buy__":  filt = filt[filt["bucket"].isin(["MUST_BUY","CAN_BUY"])]
elif uv == "__weak__":     filt = filt[filt["bucket"].isin(["AVOID","SELL"])]
elif uv:                   filt = filt[filt["index_membership"].apply(lambda mm: isinstance(mm,list) and uv in mm)]
if bucket_f:  filt = filt[filt["bucket"].isin(bucket_f)]
if entry_f:   filt = filt[filt["entry_signal"].isin(entry_f)]
if grade_f:   filt = filt[filt["grade"].isin(grade_f)]
if fo_only:   filt = filt[filt["fo"]==True]
filt = filt.head(top_n).reset_index(drop=True)

# Summary
m1,m2,m3,m4,m5,m6,m7 = st.columns(7)
m1.metric("Showing",    len(filt))
m2.metric("Grade S",    len(filt[filt.grade=="S"]))
m3.metric("Grade A",    len(filt[filt.grade=="A"]))
m4.metric("BUY NOW",    len(filt[filt.entry_signal=="BUY NOW"]))
m5.metric("Breakouts",  len(filt[filt.signals.apply(lambda s:"Breakout" in s)]))
m6.metric("RS Leaders", len(filt[filt.signals.apply(lambda s:"RS Leader" in s)]))
ai_count = sum(1 for s in filt["symbol"] if cached_just.get(s,{}).get("text"))
m7.metric("AI Cached",  ai_count)

last_ai = max((v["generated_at"][:16].replace("T"," ") for v in cached_just.values() if v.get("generated_at")), default="Never")
st.caption(f"Scores: **{score_date}** · AI cached for **{len(cached_just)}** stocks · Last run: **{last_ai}** UTC")
st.divider()

# ── Action buttons ─────────────────────────────────────────────────────────────
col_b1, col_b2, col_b3 = st.columns([2,2.5,1.5])

with col_b1:
    st.markdown("**⚡ Phase 2 — Live Prices (Breeze)**")
    if st.button(f"🔴 Fetch Live CMP for {len(filt)} filtered stocks",
                 use_container_width=True,
                 help="Fetches live prices only for stocks currently visible"):
        live = fetch_live(filt["symbol"].tolist())
        st.session_state["live_prices"].update(live)
        st.success(f"✅ Live prices for {len(live)} stocks")
        st.rerun()

with col_b2:
    st.markdown("**🤖 Phase 3 — AI Analysis (saved to Supabase)**")
    ai_scope_label = st.selectbox(
        "Scope", list(UNIVERSE_OPTIONS.keys()),
        index=list(UNIVERSE_OPTIONS.keys()).index("✅ MUST_BUY + CAN_BUY"),
        label_visibility="collapsed", key="ai_scope")
    if st.button(f"🤖 Run AI Analysis — {ai_scope_label.split('(')[0].strip()}",
                 use_container_width=True, type="primary",
                 help="Sends selected universe to Claude. Saves results to Supabase permanently."):
        ai_uv = UNIVERSE_OPTIONS[ai_scope_label]
        ai_df = master.copy()
        if ai_uv == "__must_buy__":   ai_df = ai_df[ai_df["bucket"]=="MUST_BUY"]
        elif ai_uv == "__can_buy__":  ai_df = ai_df[ai_df["bucket"].isin(["MUST_BUY","CAN_BUY"])]
        elif ai_uv == "__weak__":     ai_df = ai_df[ai_df["bucket"].isin(["AVOID","SELL"])]
        elif ai_uv:                   ai_df = ai_df[ai_df["index_membership"].apply(lambda mm: isinstance(mm,list) and ai_uv in mm)]
        total = len(ai_df)
        est   = math.ceil(total/30)
        st.info(f"🤖 **{total} stocks** · **{est} API calls** · est. **{est*8}–{est*15} sec**")
        prog = st.progress(0, f"Starting AI analysis for {total} stocks…")
        new_results = {}
        for i in range(0, total, 30):
            batch_rows = ai_df.iloc[i:i+30]
            batch = [{"sym":r["symbol"],"score":r["strength"],"stage":r["weinstein_stage"],
                      "rs":r["rs_percentile"] or 50,"rsnh":r["rs_new_high"],
                      "d1":r["chg_1d"] or 0,"w1":r["ret_1w"] or 0,"m1":r["ret_1m"] or 0,
                      "m3":r["ret_3m"] or 0,"y1":r["ret_1y"] or 0,
                      "pvm":r["price_vs_ma"] or 0,"sigs":r["signals"]}
                     for _,r in batch_rows.iterrows()]
            result = run_claude_batch(batch, score_date, ai_scope_label)
            new_results.update(result)
            done = min(i+30, total)
            prog.progress(done/total, f"AI: {done}/{total} done…")
        prog.empty()
        load_cached_justifications.clear()
        st.success(f"✅ **{len(new_results)} justifications** saved to Supabase!")
        time.sleep(1)
        st.rerun()

with col_b3:
    st.markdown("**⬇️ Export**")
    exp = filt[["rank","symbol","name","sector","cap","cmp","chg_1d",
                "ret_1w","ret_1m","ret_3m","ret_1y","weinstein_stage",
                "rs_percentile","composite_score","strength","grade",
                "bucket","entry_signal","entry_detail","ai_just","ai_generated"]].copy()
    exp["signals"] = filt["signals"].apply(lambda ss:" | ".join(ss))
    exp.rename(columns={"ai_just":"ai_justification","ai_generated":"ai_timestamp"}, inplace=True)
    st.download_button("⬇️ Export CSV", exp.to_csv(index=False).encode(),
                       f"alpharadar_ranker_{score_date}.csv","text/csv",
                       use_container_width=True)

st.divider()

# ── Main table ──────────────────────────────────────────────────────────────────
live_prices = st.session_state.get("live_prices", {})
tbody = []
for _, r in filt.iterrows():
    lv     = live_prices.get(r["symbol"], {})
    cmp    = lv.get("cmp") or r["cmp"]
    chg1d  = lv.get("chg_1d") or r["chg_1d"]
    live_dot = "🔴 " if lv.get("cmp") else ""

    # 52W range bar
    pos_str = ""
    h52, l52 = r["high_52w"], r["low_52w"]
    if h52 and l52 and cmp and h52 > l52:
        pct = (cmp-l52)/(h52-l52)*100
        c52 = "#1a7a4a" if pct>=80 else ("#c47a0b" if pct>=40 else "#c0392b")
        pos_str = (f'<div style="font-size:9px;color:{c52};margin-top:2px">{pct:.0f}% of 52W range</div>'
                   f'<div style="background:#eee;border-radius:2px;height:3px;width:60px;margin-top:1px">'
                   f'<div style="background:{c52};width:{min(pct,100):.0f}%;height:3px;border-radius:2px"></div></div>')

    # Score change
    sc_str = ""
    try:
        sc = float(r.get("score_change") or 0)
        if sc > 1:    sc_str = f'<span style="color:#1a7a4a;font-size:10px"> ▲{sc:.0f}</span>'
        elif sc < -1: sc_str = f'<span style="color:#c0392b;font-size:10px"> ▼{abs(sc):.0f}</span>'
    except Exception:
        pass

    # AI justification
    ai_text = r.get("ai_just","")
    ai_ts   = str(r.get("ai_generated",""))
    if ai_text:
        ts_str = ai_ts[:10] if ai_ts else ""
        just_cell = (f'<span style="font-size:11px;color:#333">{ai_text}</span>'
                     f'<br><span style="font-size:9px;color:#bbb">🤖 {ts_str}</span>')
    else:
        ed = r["entry_detail"] if str(r["entry_detail"]) not in ("","nan","None") else "—"
        just_cell = f'<span style="font-size:11px;color:#aaa;font-style:italic">{ed}</span>'

    cap_ic = {"large":"🔵","mid":"🟡","small":"🟢","micro":"⚪"}.get(str(r["cap"]),"")

    tbody.append(f"""<tr>
      <td style="color:#aaa;font-size:11px;text-align:center">{int(r['rank'])}</td>
      <td><div style="font-weight:700;font-size:13px">{live_dot}{r['symbol']}</div>
          <div style="font-size:10px;color:#aaa">{cap_ic} {str(r['name'])[:22]}</div></td>
      <td style="font-size:11px;color:#888">{str(r['sector'])[:15]}</td>
      <td><div style="font-size:13px;font-weight:600">{"₹"+f"{cmp:,.1f}" if cmp else "—"}</div>{pos_str}</td>
      <td style="text-align:right">{fr(chg1d)}</td>
      <td style="text-align:right">{fr(r['ret_1w'])}</td>
      <td style="text-align:right">{fr(r['ret_1m'])}</td>
      <td style="text-align:right">{fr(r['ret_3m'])}</td>
      <td style="text-align:right">{fr(r['ret_1y'])}</td>
      <td style="text-align:center;font-size:12px">{r['weinstein_stage']}{sc_str}</td>
      <td style="text-align:center">{grade_badge(r['strength'])}</td>
      <td>{sig_tags(r['signals'])}</td>
      <td style="text-align:center">{etag(r['entry_signal'])}</td>
      <td style="max-width:200px">{just_cell}</td>
    </tr>""")

st.markdown("""
<style>
.rt{width:100%;border-collapse:collapse;font-family:sans-serif;font-size:12px}
.rt th{background:#f8f8f6;color:#999;font-size:10px;font-weight:700;padding:7px 5px;
       border-bottom:1.5px solid #e8e8e4;white-space:nowrap;text-align:left;
       position:sticky;top:0;z-index:2}
.rt td{padding:7px 5px;border-bottom:0.5px solid #f2f2f0;vertical-align:middle}
.rt tr:hover td{background:#fafaf8}
</style>
<div style="overflow-x:auto;max-height:72vh;overflow-y:auto">
<table class="rt">
<thead><tr>
  <th>#</th><th>Symbol</th><th>Sector</th><th>CMP</th>
  <th style="text-align:right">1D</th><th style="text-align:right">1W</th>
  <th style="text-align:right">1M</th><th style="text-align:right">3M</th>
  <th style="text-align:right">1Y</th>
  <th style="text-align:center">Stage</th><th style="text-align:center">Grade</th>
  <th>Signals</th><th style="text-align:center">Entry</th><th>AI Justification</th>
</tr></thead>
<tbody>""" + "".join(tbody) + "</tbody></table></div>",
    unsafe_allow_html=True)

# ── Sector heatmap ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("📊 Sector Strength Heatmap")
sec = (master.groupby("sector")
       .agg(avg=("strength","mean"), n=("symbol","count"),
            avg_1m=("ret_1m","mean"), avg_rs=("rs_percentile","mean"),
            buy_now=("entry_signal", lambda x:(x=="BUY NOW").sum()))
       .reset_index().sort_values("avg", ascending=False))
for start in range(0, min(len(sec),30), 5):
    cc = st.columns(5)
    for ci,(_, sr) in enumerate(sec.iloc[start:start+5].iterrows()):
        sc = sr["avg"]
        bg = "#d4f0e0" if sc>=65 else ("#fff3cd" if sc>=50 else "#fde8e8")
        fg = "#0f5c2e" if sc>=65 else ("#7a4f00" if sc>=50 else "#7a1f1f")
        cc[ci].markdown(
            f'<div style="background:{bg};padding:10px 12px;border-radius:8px;margin:2px">'
            f'<div style="font-size:10px;color:{fg};font-weight:700">{sr["sector"][:22]}</div>'
            f'<div style="font-size:20px;font-weight:700;color:{fg}">{sc:.0f}</div>'
            f'<div style="font-size:10px;color:{fg}">n={int(sr["n"])} · RS {sr["avg_rs"]:.0f}%ile · '
            f'1M {(sr["avg_1m"] or 0):+.1f}% · 🟢{int(sr["buy_now"])}</div></div>',
            unsafe_allow_html=True)
st.caption(f"Green ≥65 · Amber 50–65 · Red <50 · 🟢 = BUY NOW count · Scores from {score_date}")
