"""
AlphaRadar — Market Pulse  v3
==============================
Professional NSE 1000 market breadth terminal.
Reads from Supabase ar_market_pulse (instant load, pre-computed daily).
Refresh button triggers full recompute (~5 min, writes back to Supabase).
"""

import requests
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

st.set_page_config(
    page_title="Market Pulse — AlphaRadar",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Matching AlphaRadar light theme exactly ──
st.markdown("""
<style>
  .stApp { background:#ffffff; }
  .main .block-container { padding:0.8rem 1.2rem; max-width:100%; }
  div[data-testid="stMetricValue"] { font-size:1.35rem; font-weight:700; }
  div[data-testid="stMetricLabel"] { font-size:0.72rem; color:#64748b; text-transform:uppercase; letter-spacing:0.04em; }

  /* section headers */
  .sec-hdr {
    font-size:0.82rem; font-weight:700; text-transform:uppercase;
    letter-spacing:0.08em; color:#475569;
    margin:14px 0 6px 0; padding-bottom:4px;
    border-bottom:2px solid #e2e8f0;
  }

  /* sentiment banners */
  .bull { background:#f0fdf4; border-left:4px solid #16a34a; border-radius:0 6px 6px 0;
          padding:8px 14px; font-size:13px; margin-bottom:8px; }
  .bear { background:#fef2f2; border-left:4px solid #dc2626; border-radius:0 6px 6px 0;
          padding:8px 14px; font-size:13px; margin-bottom:8px; }
  .neut { background:#f8fafc; border-left:4px solid #94a3b8; border-radius:0 6px 6px 0;
          padding:8px 14px; font-size:13px; margin-bottom:8px; }

  /* stale data warning */
  .stale { background:#fefce8; border:1px solid #fde68a; border-radius:6px;
           padding:7px 12px; font-size:12px; color:#92400e; }

  /* Breeze status */
  .api-ok   { background:#f0fdf4; border:1px solid #bbf7d0; border-radius:5px;
              padding:5px 12px; font-size:12px; color:#15803d; display:inline-block; }
  .api-warn { background:#fef9c3; border:1px solid #fde68a; border-radius:5px;
              padding:5px 12px; font-size:12px; color:#92400e; display:inline-block; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  SUPABASE
# ─────────────────────────────────────────────
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]
SB_R = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

def sb_read(table, select="*", params="", limit=2000):
    all_rows = []
    for offset in range(0, 5000, 1000):
        url = (f"{SUPABASE_URL}/rest/v1/{table}?select={select}"
               f"{'&'+params if params else ''}&limit=1000&offset={offset}")
        r = requests.get(url, headers=SB_R, timeout=15)
        batch = r.json() if r.status_code == 200 else []
        if not batch or not isinstance(batch, list): break
        all_rows.extend(batch)
        if len(batch) < 1000: break
    return all_rows

@st.cache_data(ttl=300)
def load_pulse_data():
    """Load latest ar_market_pulse snapshot. Returns (df, date_str)."""
    # Get latest pulse_date
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/ar_market_pulse?select=pulse_date&order=pulse_date.desc&limit=1",
        headers=SB_R, timeout=10
    )
    if r.status_code != 200 or not r.json():
        return pd.DataFrame(), None
    
    latest_date = r.json()[0]["pulse_date"]
    
    # Fetch all rows for that date
    rows = sb_read("ar_market_pulse", "*", f"pulse_date=eq.{latest_date}&order=composite_score.desc")
    if not rows:
        return pd.DataFrame(), latest_date
    
    df = pd.DataFrame(rows)
    # Ensure numeric cols
    num_cols = ["cmp","chg_pct","chg_abs","vol_ratio","from_ath_pct","from_52wh_pct",
                "from_52wl_pct","vs_ma20_pct","vs_ma50_pct","vs_ma200_pct",
                "rsi14","rs_63d","composite_score","nifty_chg_pct","rel_vs_nifty",
                "vol_today","vol_10d_avg","rs_rank","score_rank","minervini_score"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df, latest_date

def is_stale(date_str):
    """Returns days old; 0=today, 1=yesterday."""
    if not date_str: return 999
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return (datetime.now() - d).days
    except: return 999

# ─────────────────────────────────────────────
#  BREADTH CALCS
# ─────────────────────────────────────────────
def breadth(df):
    n = len(df)
    adv = int((df["chg_pct"] > 0).sum())
    dec = int((df["chg_pct"] < 0).sum())
    unc = n - adv - dec
    return {
        "n": n, "adv": adv, "dec": dec, "unc": unc,
        "ad": round(adv/dec,2) if dec else adv,
        "up2": int((df["chg_pct"]>=2).sum()),   "dn2": int((df["chg_pct"]<=-2).sum()),
        "up5": int((df["chg_pct"]>=5).sum()),   "dn5": int((df["chg_pct"]<=-5).sum()),
        "h52": int((df["from_52wh_pct"]>=-1.5).sum()),
        "l52": int((df["from_52wl_pct"]<=2.5).sum()),
        "p50":  round(df["above_ma50"].mean()*100,1)  if "above_ma50"  in df else 0,
        "p200": round(df["above_ma200"].mean()*100,1) if "above_ma200" in df else 0,
        "vsurge": int((df["vol_ratio"]>=1.5).sum()),
        "s2":    int((df["weinstein_stage"]=="2A").sum()),
        "s4":    int((df["weinstein_stage"]=="4").sum()),
        "overbought": int((df["rsi14"]>=70).sum()),
        "oversold":   int((df["rsi14"]<=30).sum()),
    }

# ─────────────────────────────────────────────
#  CHARTS
# ─────────────────────────────────────────────
W = "rgba(0,0,0,0)"; PB = "#f8fafc"; G = "rgba(0,0,0,0.05)"; F = "#1e293b"

def c_donut(adv, dec, unc):
    fig = go.Figure(go.Pie(
        labels=["Advancing","Declining","Unchanged"], values=[adv,dec,unc],
        hole=0.65, marker_colors=["#16a34a","#dc2626","#94a3b8"],
        textinfo="label+value", textfont=dict(size=11.5),
    ))
    fig.update_layout(height=230, margin=dict(l=5,r=5,t=30,b=5),
                      paper_bgcolor=W, showlegend=False, font=dict(color=F,size=11),
                      title=dict(text="Advance / Decline", font=dict(size=12,color="#475569")))
    return fig

def c_ma_gauge(p50, p200):
    fig = go.Figure()
    for v, lbl, clr in [(p50,"% > MA50","#3b82f6"),(p200,"% > MA200","#7c3aed")]:
        fig.add_trace(go.Bar(x=[v], y=[lbl], orientation="h",
                             marker=dict(color=clr,line=dict(width=0)),
                             text=f"{v:.0f}%", textposition="outside", width=0.45))
    fig.add_vline(x=50, line_dash="dot", line_color="#cbd5e1", line_width=2)
    fig.update_layout(height=155, margin=dict(l=10,r=50,t=30,b=5),
                      paper_bgcolor=W, plot_bgcolor=W, font=dict(color=F,size=11),
                      xaxis=dict(range=[0,115],showgrid=False,showticklabels=False),
                      yaxis=dict(showgrid=False), showlegend=False,
                      title=dict(text="MA Health", font=dict(size=12,color="#475569")))
    return fig

def c_distribution(df):
    cuts = pd.cut(df["chg_pct"].dropna(), bins=24)
    counts = df.groupby(cuts, observed=False)["chg_pct"].count()
    mids = [round(i.mid,2) for i in counts.index]
    fig = go.Figure(go.Bar(
        x=mids, y=counts.values,
        marker_color=["#16a34a" if m>0 else "#dc2626" for m in mids],
        opacity=0.85
    ))
    fig.add_vline(x=0, line_dash="solid", line_color="#334155", line_width=1.5)
    fig.update_layout(height=190, margin=dict(l=10,r=10,t=30,b=20),
                      paper_bgcolor=W, plot_bgcolor=W, font=dict(color=F,size=11),
                      xaxis=dict(title="% Change", gridcolor=G),
                      yaxis=dict(title="Stocks", gridcolor=G),
                      showlegend=False,
                      title=dict(text="Return Distribution", font=dict(size=12,color="#475569")))
    return fig

def c_rs_scatter(df):
    sample = df.copy()
    fig = px.scatter(
        sample, x="rs_63d", y="chg_pct",
        color="composite_score",
        color_continuous_scale=[[0,"#dc2626"],[0.45,"#f59e0b"],[1,"#16a34a"]],
        size=sample["composite_score"].clip(lower=5),
        hover_name="symbol",
        hover_data={"cmp":":.2f","rsi14":":.1f","vol_ratio":":.2f","weinstein_stage":True,"composite_score":":.1f"},
        height=360,
        labels={"rs_63d":"RS Spread vs Nifty 63d (%)","chg_pct":"Today's Change (%)"},
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#cbd5e1", line_width=1)
    fig.add_vline(x=0, line_dash="dot", line_color="#cbd5e1", line_width=1)
    fig.add_annotation(x=0.99, y=0.02, xref="paper", yref="paper",
                       text="🛡 Strength in Weakness", font=dict(size=10,color="#16a34a"),
                       showarrow=False, xanchor="right")
    fig.add_annotation(x=0.99, y=0.98, xref="paper", yref="paper",
                       text="💪 RS Leaders Rising", font=dict(size=10,color="#2563eb"),
                       showarrow=False, xanchor="right")
    fig.update_layout(paper_bgcolor=W, plot_bgcolor=PB, font=dict(color=F,size=11),
                      coloraxis_colorbar=dict(title="Score",len=0.65),
                      margin=dict(l=10,r=10,t=35,b=10),
                      title=dict(text="Relative Strength × Today's Return  (bottom-right = hidden strength)",
                                 font=dict(size=12,color="#475569")))
    return fig

def c_rs_bar(df, n=25):
    top = df.nlargest(n,"rs_63d").sort_values("rs_63d")
    fig = go.Figure(go.Bar(
        x=top["rs_63d"], y=top["symbol"], orientation="h",
        marker_color=["#16a34a" if v>=0 else "#dc2626" for v in top["rs_63d"]],
        text=top["rs_63d"].apply(lambda v:f"{v:+.1f}%"), textposition="outside",
    ))
    fig.add_vline(x=0, line_dash="dot", line_color="#cbd5e1")
    fig.update_layout(height=max(350,n*17), margin=dict(l=70,r=55,t=35,b=5),
                      paper_bgcolor=W, plot_bgcolor=W, font=dict(color=F,size=11),
                      showlegend=False,
                      title=dict(text=f"Top {n} RS Leaders (63d vs Nifty 50)",
                                 font=dict(size=12,color="#475569")))
    return fig

# ─────────────────────────────────────────────
#  PAGE HEADER
# ─────────────────────────────────────────────
h1, h2 = st.columns([5,1])
with h1:
    st.markdown("# 📡 Market Pulse")
    st.caption("NSE 1000 · Daily Breadth Snapshot · RS vs Nifty · Volume Intelligence · Pre-computed nightly")
with h2:
    if st.button("🔄 Refresh Data", type="secondary", use_container_width=True,
                 help="Recompute all ~750 stocks. Takes 3-5 minutes. Writes to Supabase."):
        st.session_state["mp_refresh"] = True

# ─────────────────────────────────────────────
#  REFRESH TRIGGER
# ─────────────────────────────────────────────
if st.session_state.get("mp_refresh"):
    st.session_state.pop("mp_refresh")
    load_pulse_data.clear()
    
    with st.status("🔄 Refreshing Market Pulse data…", expanded=True) as status_box:
        prog_bar = st.progress(0)
        prog_text = st.empty()
        
        def prog_cb(pct, msg):
            prog_bar.progress(int(pct)/100)
            prog_text.text(msg)
        
        try:
            from market_pulse_engine import run_market_pulse
            summary = run_market_pulse(progress_cb=prog_cb)
            prog_bar.progress(1.0)
            if "error" in summary:
                st.error(f"Error: {summary['error']}")
                status_box.update(label="❌ Refresh failed", state="error")
            else:
                status_box.update(
                    label=f"✅ Done — {summary['stocks_computed']} stocks computed, "
                          f"{summary['stocks_written']} written to Supabase",
                    state="complete"
                )
                # Telegram notification
                try:
                    adv = summary['advancing']; dec = summary['declining']
                    nchg = summary['nifty_chg']
                    msg = (f"📡 *Market Pulse Refreshed*\n"
                           f"Date: {summary['pulse_date']}\n"
                           f"Stocks: {summary['stocks_computed']} computed\n"
                           f"Nifty: {nchg:+.2f}%\n"
                           f"A/D: {adv}/{dec} (ratio {adv/dec:.2f})\n"
                           f"52W Highs: {summary['new_52w_highs']} | Lows: {summary['new_52w_lows']}\n"
                           f"Stage 2: {summary['stage2_count']} | Vol Surges: {summary['vol_surges']}")
                    tg_tok = st.secrets.get("telegram",{}).get("bot_token","8347009897:AAEFlJxNtRbWL7_grWDtQUludo_LCbhNgck")
                    tg_chat = st.secrets.get("telegram",{}).get("chat_id","705724053")
                    requests.post(f"https://api.telegram.org/bot{tg_tok}/sendMessage",
                                  json={"chat_id":tg_chat,"text":msg,"parse_mode":"Markdown"},
                                  timeout=5)
                except Exception: pass
                load_pulse_data.clear()
        except Exception as e:
            st.error(f"Engine error: {e}")
            status_box.update(label="❌ Failed", state="error")

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  LOAD DATA
# ─────────────────────────────────────────────
df, pulse_date = load_pulse_data()

if df.empty:
    st.warning("No Market Pulse data found. Click **🔄 Refresh Data** to compute for the first time (~5 min).")
    st.markdown("""
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;">
    <b>How it works:</b>
    <ol style="margin:8px 0 0;line-height:1.9;font-size:13px;">
    <li>Click <b>🔄 Refresh Data</b> — fetches all ~750 NSE stocks via yfinance, computes RSI, RS, volume, MAs, Weinstein, Minervini</li>
    <li>Results stored in Supabase <code>ar_market_pulse</code> — instant load from then on</li>
    <li>Auto-refreshes daily at 4:45 PM IST via GitHub Actions (same cron as scoring engine)</li>
    <li>NSE rebalances indices semi-annually (March & September) — universe stays current</li>
    </ol>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

days_old = is_stale(pulse_date)
nifty_chg = float(df["nifty_chg_pct"].iloc[0]) if "nifty_chg_pct" in df.columns and len(df) else 0.0
b = breadth(df)

# Stale data warning
if days_old >= 2:
    st.markdown(
        f'<div class="stale">⚠️ Data is <b>{days_old} days old</b> (last: {pulse_date}). '
        f'Market was likely closed. Click Refresh for latest.</div>',
        unsafe_allow_html=True
    )

st.caption(
    f"📅 {pulse_date} · {b['n']} stocks · "
    f"Nifty: {'▲' if nifty_chg>0 else '▼'} {nifty_chg:+.2f}% · "
    f"Data refreshed nightly at 4:45 PM IST"
)
st.divider()

# ══════════════════════════════════════════════════════
#  SECTION 1 — MARKET BREADTH
# ══════════════════════════════════════════════════════
st.markdown('<div class="sec-hdr">🗺 Market Breadth</div>', unsafe_allow_html=True)

# Sentiment banner
ad = b["ad"]
if b["adv"] > b["dec"] * 1.8 and b["p50"] >= 60:
    banner_cls, banner_txt = "bull", f"🟢 <b>Strong Bull</b> — Broad participation. A/D {b['adv']}/{b['dec']} · {b['p50']:.0f}% stocks above MA50"
elif b["adv"] > b["dec"] and b["p50"] >= 45:
    banner_cls, banner_txt = "bull", f"🟡 <b>Cautious Bull</b> — Positive breadth, selective entries. A/D {b['adv']}/{b['dec']}"
elif b["dec"] > b["adv"] * 1.5 and b["p50"] < 40:
    banner_cls, banner_txt = "bear", f"🔴 <b>Bear Pressure</b> — Raise cash, protect capital. A/D {b['adv']}/{b['dec']}"
else:
    banner_cls, banner_txt = "neut", f"⚪ <b>Neutral</b> — Mixed signals, wait for confirmation. A/D {b['adv']}/{b['dec']}"

st.markdown(f'<div class="{banner_cls}">{banner_txt} &nbsp;·&nbsp; 52W Highs <b>{b["h52"]}</b> vs Lows <b>{b["l52"]}</b> &nbsp;·&nbsp; Vol Surges <b>{b["vsurge"]}</b></div>', unsafe_allow_html=True)

# 8 key breadth metrics
m = st.columns(8)
m[0].metric("🟢 Advancing",  b["adv"])
m[1].metric("🔴 Declining",  b["dec"])
m[2].metric("A/D Ratio",     f"{ad:.2f}", delta="Bullish" if ad>=1 else "Bearish")
m[3].metric("Up ≥2%",        b["up2"])
m[4].metric("Dn ≥2%",        b["dn2"])
m[5].metric("New 52W Highs", b["h52"])
m[6].metric("Stage 2 🚀",    b["s2"])
m[7].metric("Oversold 🟢",   b["oversold"])

# Three breadth charts
ch1, ch2, ch3 = st.columns([1, 1, 1.6])
with ch1: st.plotly_chart(c_donut(b["adv"],b["dec"],b["unc"]), use_container_width=True)
with ch2:
    st.plotly_chart(c_ma_gauge(b["p50"],b["p200"]), use_container_width=True)
    st.caption(f"Up ≥5%: **{b['up5']}** · Dn ≥5%: **{b['dn5']}** · Overbought: **{b['overbought']}** · Stage 4: **{b['s4']}**")
with ch3: st.plotly_chart(c_distribution(df), use_container_width=True)

st.divider()

# ══════════════════════════════════════════════════════
#  SECTION 2 — RELATIVE STRENGTH
# ══════════════════════════════════════════════════════
st.markdown('<div class="sec-hdr">⚡ Relative Strength vs Nifty 50 — 63 Days</div>', unsafe_allow_html=True)
st.caption("Bottom-right = fell less than Nifty today = institutional accumulation in progress = watch for next upmove  (O'Neil principle)")

rs1, rs2 = st.columns([1.7, 1.3])
with rs1: st.plotly_chart(c_rs_scatter(df), use_container_width=True)
with rs2: st.plotly_chart(c_rs_bar(df, 25), use_container_width=True)

# Strength-in-weakness callout (only on down days)
if nifty_chg < -0.5:
    resilient = df[df["chg_pct"] > nifty_chg].nlargest(10,"rs_63d")["symbol"].tolist()
    st.markdown(
        f'<div class="bull">💎 <b>Strength in Weakness (Nifty {nifty_chg:+.2f}%)</b> — '
        f'Stocks outperforming today = accumulation candidates for next upmove: '
        f'<b>{" · ".join(resilient)}</b></div>',
        unsafe_allow_html=True
    )

st.divider()

# ══════════════════════════════════════════════════════
#  SECTION 3 — STOCK TABLE (the main event)
# ══════════════════════════════════════════════════════
st.markdown('<div class="sec-hdr">📊 NSE Market Table</div>', unsafe_allow_html=True)

# ── Filter Bar ──
with st.expander("⚙ Filters & Sort", expanded=True):
    f1,f2,f3,f4,f5,f6 = st.columns(6)
    with f1:
        search = st.text_input("Symbol / Company", "", placeholder="e.g. HDFC or Bank")
    with f2:
        cap_filter = st.multiselect("Cap", ["large","mid","small","micro"],
                                    placeholder="All caps")
    with f3:
        chg_preset = st.selectbox("Change Filter",
            ["All","Up >2%","Up >5%","Down >2%","Down >5%","Up today","Down today","Hidden Strength"])
    with f4:
        vol_filter = st.selectbox("Volume", ["All",">1.5x avg",">2x avg",">3x avg","ATH Vol"])
        stage_filter = st.multiselect("Weinstein Stage", ["2A","2B","1B","1A","3","4"],
                                       placeholder="All stages")
    with f5:
        rsi_filter = st.selectbox("RSI Zone",
            ["All","Oversold (<30)","Bearish (30-40)","Neutral (40-60)","Bullish (60-70)","Overbought (>70)"])
        mv_filter  = st.selectbox("Minervini", ["All","✅ Full TT","⚠ Partial","✗ Weak"])
    with f6:
        sort_by  = st.selectbox("Sort By",
            ["Score (↓)","RS Spread (↓)","Change % (↓)","Change % (↑)","Vol Ratio (↓)",
             "RSI (↓)","RSI (↑)","From ATH (↑)","Score (↑)"])
        near_ath = st.checkbox("Within 25% of ATH")

# Apply filters
fdf = df.copy()
if search:
    q = search.lower()
    mask = (fdf["symbol"].str.lower().str.contains(q, na=False) |
            fdf.get("company_name", pd.Series(dtype=str)).str.lower().str.contains(q, na=False))
    fdf = fdf[mask]
if cap_filter:
    fdf = fdf[fdf["cap_bucket"].isin(cap_filter)]
if stage_filter:
    fdf = fdf[fdf["weinstein_stage"].isin(stage_filter)]
if chg_preset == "Up >2%":        fdf = fdf[fdf["chg_pct"] >= 2]
elif chg_preset == "Up >5%":      fdf = fdf[fdf["chg_pct"] >= 5]
elif chg_preset == "Down >2%":    fdf = fdf[fdf["chg_pct"] <= -2]
elif chg_preset == "Down >5%":    fdf = fdf[fdf["chg_pct"] <= -5]
elif chg_preset == "Up today":    fdf = fdf[fdf["chg_pct"] > 0]
elif chg_preset == "Down today":  fdf = fdf[fdf["chg_pct"] < 0]
elif chg_preset == "Hidden Strength": fdf = fdf[fdf["rel_vs_nifty"] > 0]
if vol_filter == ">1.5x avg":     fdf = fdf[fdf["vol_ratio"] >= 1.5]
elif vol_filter == ">2x avg":     fdf = fdf[fdf["vol_ratio"] >= 2.0]
elif vol_filter == ">3x avg":     fdf = fdf[fdf["vol_ratio"] >= 3.0]
elif vol_filter == "ATH Vol":     fdf = fdf[fdf["vol_tag"] == "🏆 ATH Vol"]
if rsi_filter == "Oversold (<30)":    fdf = fdf[fdf["rsi14"] < 30]
elif rsi_filter == "Bearish (30-40)": fdf = fdf[(fdf["rsi14"]>=30)&(fdf["rsi14"]<40)]
elif rsi_filter == "Neutral (40-60)": fdf = fdf[(fdf["rsi14"]>=40)&(fdf["rsi14"]<60)]
elif rsi_filter == "Bullish (60-70)": fdf = fdf[(fdf["rsi14"]>=60)&(fdf["rsi14"]<70)]
elif rsi_filter == "Overbought (>70)":fdf = fdf[fdf["rsi14"] >= 70]
if mv_filter == "✅ Full TT":    fdf = fdf[fdf["minervini_tag"] == "✅ Full"]
elif mv_filter == "⚠ Partial":  fdf = fdf[fdf["minervini_tag"] == "⚠ Partial"]
elif mv_filter == "✗ Weak":     fdf = fdf[fdf["minervini_tag"] == "✗ Weak"]
if near_ath:                      fdf = fdf[fdf["from_ath_pct"] >= -25]

sort_map = {
    "Score (↓)":       ("composite_score", False),
    "RS Spread (↓)":   ("rs_63d", False),
    "Change % (↓)":    ("chg_pct", False),
    "Change % (↑)":    ("chg_pct", True),
    "Vol Ratio (↓)":   ("vol_ratio", False),
    "RSI (↓)":         ("rsi14", False),
    "RSI (↑)":         ("rsi14", True),
    "From ATH (↑)":    ("from_ath_pct", False),
    "Score (↑)":       ("composite_score", True),
}
sc, sa = sort_map.get(sort_by, ("composite_score", False))
fdf = fdf.sort_values(sc, ascending=sa)

st.caption(f"Showing **{len(fdf)}** of {len(df)} stocks · Nifty {nifty_chg:+.2f}% · {pulse_date}")

# ── THE TABLE ──
COLS = {
    "score_rank":     "Rank",
    "symbol":         "Symbol",
    "company_name":   "Company",
    "cap_bucket":     "Cap",
    "cmp":            "CMP (₹)",
    "chg_pct":        "Chg %",
    "chg_abs":        "Chg ₹",
    "rel_vs_nifty":   "vs Nifty",
    "vol_ratio":      "Vol Ratio",
    "vol_tag":        "Volume",
    "rsi14":          "RSI",
    "rsi_tag":        "RSI View",
    "rs_63d":         "RS Spread",
    "rs_rank":        "RS Rank",
    "from_ath_pct":   "vs ATH",
    "from_52wh_pct":  "vs 52W Hi",
    "from_52wl_pct":  "vs 52W Lo",
    "vs_ma50_pct":    "vs MA50",
    "vs_ma200_pct":   "vs MA200",
    "weinstein_stage":"Stage",
    "minervini_tag":  "Minervini",
    "composite_score":"Score",
}

avail = [c for c in COLS if c in fdf.columns]
show = fdf[avail].copy().rename(columns=COLS)

col_cfg = {
    "Rank":       st.column_config.NumberColumn("#",       format="%d",      width="small"),
    "Symbol":     st.column_config.TextColumn("Symbol",                       width="small"),
    "Company":    st.column_config.TextColumn("Company",                      width="medium"),
    "Cap":        st.column_config.TextColumn("Cap",                          width="small"),
    "CMP (₹)":    st.column_config.NumberColumn("CMP",    format="₹%.2f",    width="small"),
    "Chg %":      st.column_config.NumberColumn("Chg%",   format="%.2f%%",   width="small"),
    "Chg ₹":      st.column_config.NumberColumn("Chg ₹",  format="₹%.2f",   width="small"),
    "vs Nifty":   st.column_config.NumberColumn("vs Nifty",format="%+.2f%%", width="small"),
    "Vol Ratio":  st.column_config.NumberColumn("Vol",     format="%.2fx",   width="small"),
    "Volume":     st.column_config.TextColumn("Volume",                       width="medium"),
    "RSI":        st.column_config.NumberColumn("RSI",     format="%.1f",    width="small"),
    "RSI View":   st.column_config.TextColumn("RSI View",                     width="small"),
    "RS Spread":  st.column_config.NumberColumn("RS Spread",format="%+.2f%%",width="small"),
    "RS Rank":    st.column_config.NumberColumn("RS#",     format="%d",      width="small"),
    "vs ATH":     st.column_config.NumberColumn("vs ATH",  format="%.1f%%",  width="small"),
    "vs 52W Hi":  st.column_config.NumberColumn("52W Hi",  format="%.1f%%",  width="small"),
    "vs 52W Lo":  st.column_config.NumberColumn("52W Lo",  format="+%.1f%%", width="small"),
    "vs MA50":    st.column_config.NumberColumn("MA50",    format="%+.1f%%", width="small"),
    "vs MA200":   st.column_config.NumberColumn("MA200",   format="%+.1f%%", width="small"),
    "Stage":      st.column_config.TextColumn("Stage",                        width="small"),
    "Minervini":  st.column_config.TextColumn("Minervini",                    width="small"),
    "Score":      st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
}

st.dataframe(show, use_container_width=True, height=560,
             column_config=col_cfg, hide_index=True)

# Export
csv = fdf[avail].to_csv(index=False).encode()
st.download_button(
    "📥 Export Filtered Table (CSV)", csv,
    f"market_pulse_{pulse_date}.csv", "text/csv"
)

st.divider()

# ══════════════════════════════════════════════════════
#  SECTION 4 — STOCK DEEP-DIVE
# ══════════════════════════════════════════════════════
st.markdown('<div class="sec-hdr">🔬 Stock Deep-Dive</div>', unsafe_allow_html=True)

sel = st.selectbox(
    "Pick a stock",
    fdf["symbol"].tolist() if len(fdf) else df["symbol"].tolist(),
    label_visibility="collapsed"
)

if sel:
    row = df[df["symbol"] == sel].iloc[0]

    d1,d2,d3,d4,d5,d6,d7,d8 = st.columns(8)
    d1.metric("CMP",        f"₹{row['cmp']:,.2f}", delta=f"{row['chg_pct']:+.2f}%")
    d2.metric("RS Spread",  f"{row['rs_63d']:+.1f}%", delta=f"Rank #{int(row['rs_rank'])}")
    d3.metric("RSI (14)",   f"{row['rsi14']:.1f}",  delta=row["rsi_tag"])
    d4.metric("Volume",     f"{row['vol_ratio']:.2f}x", delta=row["vol_tag"])
    d5.metric("Score",      f"{row['composite_score']:.0f}/100", delta=f"Rank #{int(row['score_rank'])}")
    d6.metric("Stage",      row["weinstein_stage"])
    d7.metric("Minervini",  row["minervini_tag"])
    d8.metric("vs Nifty",   f"{row['rel_vs_nifty']:+.2f}%")

    l1,l2,l3,l4,l5 = st.columns(5)
    l1.metric("vs ATH",     f"{row['from_ath_pct']:.1f}%")
    l2.metric("vs 52W High",f"{row['from_52wh_pct']:.1f}%")
    l3.metric("vs 52W Low", f"+{row['from_52wl_pct']:.1f}%")
    l4.metric("vs MA50",    f"{row['vs_ma50_pct']:+.1f}%")
    l5.metric("vs MA200",   f"{row['vs_ma200_pct']:+.1f}%")

    # Auto-generated insights
    ins = []
    if row["vol_ratio"] >= 2.0:
        ins.append(f"🔊 Volume **{row['vol_ratio']:.1f}x** the 10-day average — significant institutional activity")
    if row["from_ath_pct"] >= -3:
        ins.append("🏆 **Near All-Time High** — strong demand zone, potential breakout")
    if row["rsi14"] <= 32:
        ins.append(f"🟢 RSI **{row['rsi14']:.1f}** — oversold territory, watch for reversal")
    elif row["rsi14"] >= 72:
        ins.append(f"🔴 RSI **{row['rsi14']:.1f}** — overbought, potential for pause or pullback")
    if row["rs_63d"] >= 15:
        ins.append(f"⚡ **{row['rs_63d']:+.1f}%** vs Nifty over 63 days — strong RS leader")
    if row["minervini_tag"] == "✅ Full":
        ins.append("✅ **Minervini Trend Template** — all 8 criteria met, confirmed uptrend structure")
    if row["weinstein_stage"] == "4":
        ins.append("⚠️ **Weinstein Stage 4** — downtrend in progress, avoid new entries")
    elif row["weinstein_stage"] == "2A":
        ins.append("🚀 **Weinstein Stage 2A** — early advancing stage, best entry zone")
    if row["vs_ma200_pct"] < -15:
        ins.append(f"📉 **{row['vs_ma200_pct']:.1f}%** below 200d MA — avoid until structural reclaim")
    if row["chg_pct"] > 0 and nifty_chg < 0:
        ins.append(f"💪 **Rising on a red market day** (Nifty {nifty_chg:.2f}%) — clear hidden strength signal")
    elif row["rel_vs_nifty"] > 2 and nifty_chg < 0:
        ins.append(f"🛡 **Outperforming Nifty by {row['rel_vs_nifty']:.1f}%** today — institutional accumulation likely")
    if row["from_52wl_pct"] >= 100:
        ins.append(f"📈 Trading at **{row['from_52wl_pct']:.0f}%** above 52-week low — strong multi-month recovery")

    if ins:
        st.markdown("**📋 Insights**")
        for i in ins:
            st.markdown(f"- {i}")

st.divider()

# ══════════════════════════════════════════════════════
#  SECTION 5 — STRENGTH IN WEAKNESS (conditional)
# ══════════════════════════════════════════════════════
if nifty_chg < -0.3:
    st.markdown('<div class="sec-hdr">💎 Strength in Weakness — Today\'s Resilience Leaders</div>', unsafe_allow_html=True)
    st.caption(
        f"Nifty is {nifty_chg:+.2f}% today. Stocks in the top of this list are being "
        f"accumulated. O'Neil: 'The stocks that hold best on down days lead the next rally.'"
    )
    siw = df.copy()
    siw = siw.nlargest(35, "rel_vs_nifty")
    siw_cols = ["symbol","company_name","cmp","chg_pct","rel_vs_nifty","rs_63d","rs_rank",
                "vol_ratio","rsi14","weinstein_stage","composite_score"]
    siw_avail = [c for c in siw_cols if c in siw.columns]
    st.dataframe(siw[siw_avail], use_container_width=True, height=440, hide_index=True,
        column_config={
            "symbol":         st.column_config.TextColumn("Symbol"),
            "company_name":   st.column_config.TextColumn("Company"),
            "cmp":            st.column_config.NumberColumn("CMP",        format="₹%.2f"),
            "chg_pct":        st.column_config.NumberColumn("Chg%",       format="%.2f%%"),
            "rel_vs_nifty":   st.column_config.NumberColumn("vs Nifty",   format="%+.2f%%"),
            "rs_63d":         st.column_config.NumberColumn("RS Spread",   format="%+.2f%%"),
            "rs_rank":        st.column_config.NumberColumn("RS Rank",     format="%d"),
            "vol_ratio":      st.column_config.NumberColumn("Vol",         format="%.2fx"),
            "rsi14":          st.column_config.NumberColumn("RSI",         format="%.1f"),
            "weinstein_stage":st.column_config.TextColumn("Stage"),
            "composite_score":st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
        })
    st.divider()

# ══════════════════════════════════════════════════════
#  LEGEND
# ══════════════════════════════════════════════════════
with st.expander("📖 Methodology & Legend"):
    st.markdown(f"""
    **Data is pre-computed nightly and stored in Supabase. Reads are instant.**
    NSE Nifty Total Market rebalances **semi-annually (March & September)** — universe stays current automatically.
    Last computed: {pulse_date} · Stocks: {b['n']}

    | Metric | Formula | Signal |
    |--------|---------|--------|
    | **Score (0-100)** | RS(30) + Price(20) + Volume(15) + RSI(15) + Minervini(20) | ≥70 = strong candidate |
    | **RS Spread** | Stock 63d return − Nifty 63d return | +ve = outperforming |
    | **RS Rank** | 1 = best RS in universe | Top 20 = leaders |
    | **Vol Ratio** | Today vol ÷ 10-day avg | ≥1.5x = institutional |
    | **vs Nifty** | Today's stock return − Nifty return | +ve on red day = strength |
    | **Stage** | Weinstein: 150d MA slope + price position | 2A = buy zone |
    | **Minervini** | 8-criteria trend template | ✅ Full = confirmed uptrend |
    | **RSI** | 14-day Wilder RSI | <30 oversold, >70 overbought |
    """)

st.caption(
    f"AlphaRadar Market Pulse v3 · {pulse_date} · "
    f"Universe refreshes with NSE semi-annual rebalancing (Mar & Sep)"
)
st.markdown("""
<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:8px 14px;margin-top:6px;">
<p style="font-size:11px;color:#991b1b;margin:0;">
<b>⚠️ DISCLAIMER:</b> Educational tool only. Not SEBI-registered. Not investment advice. Trade at your own risk.
</p></div>
""", unsafe_allow_html=True)
