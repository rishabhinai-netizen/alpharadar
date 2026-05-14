"""
AlphaRadar — Market Pulse  (v3)
================================
Architecture:
  - Data lives in Supabase ar_market_pulse (updated daily at 4:45 PM by cron)
  - First-time: click "Initialize" — runs engine, writes all stocks to Supabase
  - After that: instant load from Supabase, no downloading
  - NSE rebalances every 6 months; universe stays current automatically

Table columns: symbol, pulse_date, cmp, chg_pct, chg_abs, vol_today, vol_10d_avg,
  vol_ratio, vol_tag, ath, from_ath_pct, high_52w, from_52wh_pct, low_52w,
  from_52wl_pct, ma20, ma50, ma200, vs_ma20_pct, vs_ma50_pct, vs_ma200_pct,
  above_ma50, above_ma200, rsi14, rsi_tag, rs_63d, rs_rank, weinstein_stage,
  minervini_score, minervini_tag, composite_score, score_rank,
  nifty_chg_pct, rel_vs_nifty, company_name, sector, cap_bucket
"""

import requests
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date

try:
    st.set_page_config(
        page_title="Market Pulse — AlphaRadar",
        page_icon="📡",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
except Exception:
    pass

st.markdown("""
<style>
  .stApp { background:#ffffff; }
  .main .block-container { padding:0.7rem 1.1rem; max-width:100%; }
  div[data-testid="stMetricValue"] { font-size:1.3rem; font-weight:700; color:#0f172a; }
  div[data-testid="stMetricLabel"] { font-size:0.71rem; color:#64748b; font-weight:500; }
  .sec { font-size:0.82rem; font-weight:700; color:#1e293b; letter-spacing:.06em;
         text-transform:uppercase; margin:14px 0 6px; padding-bottom:4px;
         border-bottom:2px solid #e2e8f0; }
  .bull { background:#f0fdf4; border:1px solid #86efac; border-radius:8px; padding:9px 15px; }
  .bear { background:#fef2f2; border:1px solid #fca5a5; border-radius:8px; padding:9px 15px; }
  .neut { background:#f8fafc; border:1px solid #cbd5e1; border-radius:8px; padding:9px 15px; }
</style>
""", unsafe_allow_html=True)

# ── Supabase helpers ──────────────────────────
@st.cache_resource
def _sb():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    hr = {"apikey":key,"Authorization":f"Bearer {key}"}
    hw = {**hr,"Content-Type":"application/json","Prefer":"resolution=merge-duplicates,return=minimal"}
    return url, hr, hw

def sb_read(tbl, select="*", params="", limit=2000):
    url, hr, _ = _sb()
    r = requests.get(f"{url}/rest/v1/{tbl}?select={select}&limit={limit}"
                     +(f"&{params}" if params else ""), headers=hr, timeout=15)
    return r.json() if r.status_code == 200 else []

# ── Load data from Supabase ───────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_pulse():
    latest = sb_read("ar_market_pulse","pulse_date","order=pulse_date.desc&limit=1")
    if not latest or not isinstance(latest,list):
        return pd.DataFrame(), ""
    ld = latest[0]["pulse_date"]
    rows = []
    for off in range(0,3000,1000):
        b = sb_read("ar_market_pulse","*",
                    f"pulse_date=eq.{ld}&order=score_rank.asc&offset={off}",limit=1000)
        if not b or not isinstance(b,list): break
        rows.extend(b)
        if len(b)<1000: break
    if not rows: return pd.DataFrame(), ld
    df = pd.DataFrame(rows)
    num = ["cmp","chg_pct","chg_abs","vol_today","vol_10d_avg","vol_ratio",
           "ath","from_ath_pct","high_52w","from_52wh_pct","low_52w","from_52wl_pct",
           "ma20","ma50","ma200","vs_ma20_pct","vs_ma50_pct","vs_ma200_pct",
           "rsi14","rs_63d","rs_rank","composite_score","score_rank",
           "nifty_chg_pct","rel_vs_nifty","minervini_score"]
    for c in num:
        if c in df.columns: df[c] = pd.to_numeric(df[c],errors="coerce")
    return df, ld

# ── Breadth stats ─────────────────────────────
def brd(df):
    n=len(df); adv=int((df.chg_pct>0).sum()); dec=int((df.chg_pct<0).sum())
    return dict(total=n,adv=adv,dec=dec,unc=n-adv-dec,
                adr=round(adv/dec,2) if dec else adv,
                up2=int((df.chg_pct>=2).sum()), dn2=int((df.chg_pct<=-2).sum()),
                up5=int((df.chg_pct>=5).sum()), dn5=int((df.chg_pct<=-5).sum()),
                h52=int((df.from_52wh_pct>=-1.5).sum()),
                l52=int((df.from_52wl_pct<=2.5).sum()),
                pma50=round(df.above_ma50.mean()*100,1),
                pma200=round(df.above_ma200.mean()*100,1),
                vs=int((df.vol_ratio>=1.5).sum()),
                s2=int((df.weinstein_stage=="2A").sum()),
                s4=int((df.weinstein_stage=="4").sum()),
                ob=int((df.rsi14>=70).sum()), os=int((df.rsi14<=30).sum()))

# ── Charts ────────────────────────────────────
BG="rgba(0,0,0,0)"; PL="#f8fafc"; FC="#1e293b"; G="#16a34a"; R="#dc2626"

def donut(a,d,u):
    fig=go.Figure(go.Pie(labels=["Adv","Dec","Unch"],values=[a,d,u],hole=0.6,
        marker_colors=[G,R,"#94a3b8"],textinfo="label+value",
        textfont=dict(size=11,color=FC),sort=False))
    fig.update_layout(height=220,margin=dict(l=5,r=5,t=28,b=5),
        paper_bgcolor=BG,showlegend=False,font=dict(color=FC),
        title=dict(text="Advance / Decline",font=dict(size=11,color=FC)))
    return fig

def ma_bars(p50,p200):
    fig=go.Figure()
    for v,l,c in [(p50,"% > MA50",G if p50>=50 else R),(p200,"% > MA200",G if p200>=50 else R)]:
        fig.add_trace(go.Bar(x=[v],y=[l],orientation="h",marker_color=c,
                             text=f"{v:.0f}%",textposition="outside",width=0.42))
    fig.add_vline(x=50,line_dash="dot",line_color="#94a3b8")
    fig.update_layout(height=160,margin=dict(l=5,r=40,t=28,b=5),
        paper_bgcolor=BG,plot_bgcolor=BG,font=dict(color=FC),
        xaxis=dict(range=[0,108],showgrid=False,showticklabels=False),
        yaxis=dict(showgrid=False),showlegend=False,
        title=dict(text="MA Health",font=dict(size=11,color=FC)))
    return fig

def dist_c(df):
    cuts=pd.cut(df.chg_pct,bins=28); cnt=df.groupby(cuts,observed=False).chg_pct.count()
    m=[round(i.mid,2) for i in cnt.index]
    fig=go.Figure(go.Bar(x=m,y=cnt.values,
        marker_color=["#16a34a" if x>0 else "#dc2626" for x in m],opacity=0.85))
    fig.add_vline(x=0,line_dash="solid",line_color="#0f172a",line_width=1.5)
    fig.update_layout(height=185,margin=dict(l=5,r=5,t=28,b=18),
        paper_bgcolor=BG,plot_bgcolor=BG,font=dict(color=FC),
        xaxis_title="Daily Chg%",yaxis_title="Stocks",showlegend=False,
        title=dict(text="Change Distribution",font=dict(size=11,color=FC)))
    return fig

def scatter_rs(df):
    d=df.dropna(subset=["rs_63d","chg_pct","composite_score"]).copy()
    fig=px.scatter(d,x="rs_63d",y="chg_pct",color="composite_score",
        color_continuous_scale=[[0,R],[0.45,"#f59e0b"],[1,G]],
        size=d.composite_score.clip(lower=8),hover_name="symbol",
        hover_data={"cmp":":.2f","rsi14":":.1f","vol_ratio":":.2f",
                    "weinstein_stage":True,"composite_score":":.1f"},
        height=330,opacity=0.78,
        labels={"rs_63d":"RS vs Nifty 63d (%)","chg_pct":"Daily Chg (%)"})
    fig.add_hline(y=0,line_dash="dot",line_color="#94a3b8",line_width=1)
    fig.add_vline(x=0,line_dash="dot",line_color="#94a3b8",line_width=1)
    for xp,yp,txt in [(0.99,0.03,"🛡 Hidden Strength"),(0.99,0.97,"🚀 Leaders"),
                       (0.01,0.03,"❌ Weak"),(0.01,0.97,"↗ Rising laggard")]:
        fig.add_annotation(x=xp,y=yp,xref="paper",yref="paper",text=txt,
            font=dict(size=9,color="#64748b"),showarrow=False,
            xanchor="right" if xp>0.5 else "left")
    fig.update_layout(paper_bgcolor=BG,plot_bgcolor=PL,font=dict(color=FC),
        margin=dict(l=5,r=5,t=30,b=8),
        coloraxis_colorbar=dict(title="Score",len=0.6),
        title=dict(text="RS vs Nifty × Daily Change",font=dict(size=11,color=FC)))
    return fig

def rs_bar_chart(df,n=20):
    top=df.nlargest(n,"rs_63d").sort_values("rs_63d")
    fig=go.Figure(go.Bar(x=top.rs_63d,y=top.symbol,orientation="h",
        marker_color=[G if v>=0 else R for v in top.rs_63d],
        text=top.rs_63d.apply(lambda v:f"{v:+.1f}%"),textposition="outside"))
    fig.add_vline(x=0,line_dash="dot",line_color="#94a3b8")
    fig.update_layout(height=max(290,n*16),margin=dict(l=55,r=42,t=30,b=8),
        paper_bgcolor=BG,plot_bgcolor=BG,font=dict(color=FC),showlegend=False,
        xaxis=dict(showgrid=False),
        title=dict(text=f"Top {n} RS Leaders (63d)",font=dict(size=11,color=FC)))
    return fig

# ── Row style ─────────────────────────────────
def style_df(df):
    def rs(r):
        s=[]
        for col in r.index:
            if col in("Chg%","Rel/Mkt"):
                try: v=float(r[col]); s.append("color:#16a34a;font-weight:600" if v>0 else("color:#dc2626;font-weight:600" if v<0 else""))
                except: s.append("")
            elif col in("RS 63d%","vs MA50","vs MA200"):
                try: v=float(r[col]); s.append("color:#16a34a" if v>0 else("color:#dc2626" if v<0 else""))
                except: s.append("")
            elif col=="Score":
                try:
                    v=float(r[col])
                    if v>=70: s.append("background:#f0fdf4;color:#15803d;font-weight:700")
                    elif v>=50: s.append("")
                    elif v>=30: s.append("background:#fefce8;color:#92400e")
                    else: s.append("background:#fef2f2;color:#991b1b")
                except: s.append("")
            else: s.append("")
        return s
    return df.style.apply(rs,axis=1)

def fmt_vol(v):
    try:
        v=float(v)
        if v>=1e7: return f"{v/1e7:.2f}Cr"
        if v>=1e5: return f"{v/1e5:.1f}L"
        return str(int(v))
    except: return "—"

# ══════════════════════════════════════════════
#  RENDER
# ══════════════════════════════════════════════
hc1,hc2=st.columns([4,1])
with hc1:
    st.markdown("# 📡 Market Pulse")
    st.caption("NSE 1000 · Breadth · RS Rankings · Volume Intelligence · Updated daily 4:45 PM IST")
with hc2:
    if st.button("🔄 Refresh",use_container_width=True, key="mp_refresh_btn"):
        st.cache_data.clear(); st.rerun()

with st.spinner("Loading…"):
    df_raw, pulse_date = load_pulse()

# ── EMPTY STATE ───────────────────────────────
if df_raw.empty:
    st.markdown("""
    <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:10px;padding:20px 24px;margin:12px 0">
      <h3 style="margin:0 0 8px;color:#0c4a6e">📡 First-Time Setup Required</h3>
      <p style="color:#075985;font-size:14px;margin:0 0 10px">
        Click <b>Initialize</b> to scan all NSE stocks and store results in Supabase.
        Runs once (~5–8 minutes). After that, this page loads <b>instantly</b> every day.
      </p>
      <p style="color:#075985;font-size:13px;margin:0">
        ✅ NSE rebalances indices every 6 months → universe stays current automatically<br>
        ✅ Daily cron at 4:45 PM IST keeps data fresh — no manual action needed<br>
        ✅ Breeze API not needed here — yfinance is sufficient for EOD analysis
      </p>
    </div>""",unsafe_allow_html=True)
    if st.button("🚀 Initialize Market Pulse (run once)",type="primary"):
        from market_pulse_engine import run_market_pulse
        pb=st.progress(0,"Starting…"); sb=st.empty()
        def cb(p,m): pb.progress(int(p),m); sb.info(f"⏳ {m}")
        summary=run_market_pulse(progress_cb=cb)
        pb.empty(); sb.empty()
        if "error" in summary:
            st.error(f"Error: {summary['error']}")
        else:
            st.success(f"✅ {summary['stocks_computed']} stocks written to Supabase."); st.cache_data.clear(); st.rerun()
    st.stop()

# ── DATA READY ────────────────────────────────
df=df_raw.copy()
pd_str=datetime.strptime(pulse_date,"%Y-%m-%d").strftime("%d %b %Y") if pulse_date else "—"
nchg=float(df.nifty_chg_pct.iloc[0]) if "nifty_chg_pct" in df.columns and len(df) else 0.0
b=brd(df)

try:
    days_old=(date.today()-date.fromisoformat(pulse_date)).days
    if days_old>1:
        st.warning(f"⚠️ Data is {days_old} days old (last update: {pd_str}). Cron runs after market close.")
except Exception: pass

st.caption(f"📅 **{pd_str}** · **{b['total']}** stocks · Nifty: {'▲' if nchg>=0 else '▼'} **{nchg:+.2f}%** · Auto-updated 4:45 PM IST daily")
st.divider()

# ══════════════════════════════════════════════
#  1 ─ BREADTH
# ══════════════════════════════════════════════
st.markdown('<p class="sec">🗺 Market Breadth</p>',unsafe_allow_html=True)

if b["adv"]>b["dec"]*1.8 and b["pma50"]>=60: sc,txt="bull",f"🟢 <b>Strong Bull</b> — broad participation ({b['adv']} stocks up)"
elif b["adv"]>b["dec"] and b["pma50"]>=45:   sc,txt="bull",f"🟡 <b>Cautious Bull</b> — positive breadth, stay selective"
elif b["dec"]>b["adv"]*1.5 and b["pma50"]<40:sc,txt="bear",f"🔴 <b>Bear Pressure</b> — {b['dec']} declining, protect capital"
else:                                          sc,txt="neut",f"⚪ <b>Neutral</b> — mixed signals, wait for confirmation"

st.markdown(f'<div class="{sc}">{txt} &nbsp;·&nbsp; A/D <b>{b["adv"]}/{b["dec"]}</b> (ratio {b["adr"]}) &nbsp;·&nbsp; 52W Highs <b>{b["h52"]}</b> vs Lows <b>{b["l52"]}</b></div>',unsafe_allow_html=True)
st.markdown("<br>",unsafe_allow_html=True)

m=st.columns(8)
m[0].metric("🟢 Advancing",b["adv"])
m[1].metric("🔴 Declining",b["dec"])
m[2].metric("⚪ Unchanged",b["unc"])
m[3].metric("Up ≥2%",b["up2"])
m[4].metric("Dn ≥2%",b["dn2"])
m[5].metric("Vol Surges 🔊",b["vs"])
m[6].metric("Stage 2 🚀",b["s2"])
m[7].metric("Oversold 🟢",b["os"])

c1,c2,c3=st.columns([1,1,1.5])
with c1: st.plotly_chart(donut(b["adv"],b["dec"],b["unc"]),use_container_width=True)
with c2:
    st.plotly_chart(ma_bars(b["pma50"],b["pma200"]),use_container_width=True)
    st.caption(f"Up ≥5%: **{b['up5']}** · Dn ≥5%: **{b['dn5']}** · Overbought: **{b['ob']}**")
with c3: st.plotly_chart(dist_c(df),use_container_width=True)
st.divider()

# ══════════════════════════════════════════════
#  2 ─ RELATIVE STRENGTH
# ══════════════════════════════════════════════
st.markdown('<p class="sec">⚡ Relative Strength vs Nifty 50 — 63 Days</p>',unsafe_allow_html=True)
st.caption("Bottom-right = fell less than Nifty + strong RS = hidden accumulation → leads next rally.")

r1,r2=st.columns([1.6,1.2])
with r1: st.plotly_chart(scatter_rs(df),use_container_width=True)
with r2: st.plotly_chart(rs_bar_chart(df,20),use_container_width=True)

if nchg<-0.4:
    siw=df[df.chg_pct>nchg].nlargest(8,"rs_63d")["symbol"].tolist()
    st.markdown(f'<div class="bull"><b>💎 Strength in Weakness — Nifty {nchg:+.2f}%</b><br>'
                f'<span style="font-size:13px;color:#166534">Outperforming today — accumulation candidates for next rally: <b>{" · ".join(siw)}</b></span></div>',
                unsafe_allow_html=True)
st.divider()

# ══════════════════════════════════════════════
#  3 ─ MASTER TABLE
# ══════════════════════════════════════════════
st.markdown('<p class="sec">📊 All Stocks — Full Dashboard Table</p>',unsafe_allow_html=True)

with st.expander("⚙ Filters",expanded=True):
    fa,fb,fc,fd,fe,ff=st.columns(6)
    with fa: srch=st.text_input("🔍 Search","",placeholder="Symbol / company",label_visibility="collapsed",key="mp_search")
    with fb: chg_p=st.selectbox("Change",["All","Up today","Down today","Up ≥2%","Down ≥2%","Up ≥5%","Down ≥5%"],label_visibility="collapsed",key="mp_chg")
    with fc: stg_f=st.selectbox("Stage",["All","2A","1B","1A","3","4"],label_visibility="collapsed",key="mp_stage")
    with fd: cap_f=st.selectbox("Cap",["All","large","mid","small","micro"],label_visibility="collapsed",key="mp_cap")
    with fe: vol_f=st.selectbox("Volume",["All","≥1.5x avg","≥2x avg","≥3x avg"],label_visibility="collapsed",key="mp_vol")
    with ff: rsi_f=st.selectbox("RSI",["All","Oversold <30","Neutral","Bullish","Overbought >70"],label_visibility="collapsed",key="mp_rsi")
    fg,fh,fi,fj=st.columns(4)
    with fg:
        a200=st.checkbox("Above MA200", key="mp_a200")
        s2o=st.checkbox("Stage 2 only", key="mp_s2o")
    with fh:
        min_rs=st.number_input("Min RS Spread%",value=None,step=1.,placeholder="e.g. 5.0",label_visibility="collapsed",key="mp_minrs")
        st.caption("Min RS Spread%")
    with fi:
        ath20=st.checkbox("Within 20% ATH", key="mp_ath20")
        mvo=st.checkbox("Minervini TT only", key="mp_mvo")
    with fj:
        srt=st.selectbox("Sort",["Score ↓","RS Rank ↑","Chg% ↓","Chg% ↑","Vol Ratio ↓","RSI ↑","RSI ↓"],key="mp_sort")

fdf=df.copy()
if srch:
    q=srch.lower()
    m=fdf.symbol.str.lower().str.contains(q,na=False)
    if "company_name" in fdf.columns: m=m|fdf.company_name.str.lower().str.contains(q,na=False)
    fdf=fdf[m]
chg_map={"Up today":("chg_pct",">",0),"Down today":("chg_pct","<",0),
          "Up ≥2%":("chg_pct",">=",2),"Down ≥2%":("chg_pct","<=",-2),
          "Up ≥5%":("chg_pct",">=",5),"Down ≥5%":("chg_pct","<=",-5)}
if chg_p in chg_map:
    c,op,v=chg_map[chg_p]
    if op==">": fdf=fdf[fdf[c]>v]
    elif op=="<": fdf=fdf[fdf[c]<v]
    elif op==">=": fdf=fdf[fdf[c]>=v]
    elif op=="<=": fdf=fdf[fdf[c]<=v]
if stg_f!="All": fdf=fdf[fdf.weinstein_stage==stg_f]
if cap_f!="All" and "cap_bucket" in fdf.columns: fdf=fdf[fdf.cap_bucket==cap_f]
if vol_f=="≥1.5x avg": fdf=fdf[fdf.vol_ratio>=1.5]
elif vol_f=="≥2x avg":  fdf=fdf[fdf.vol_ratio>=2.0]
elif vol_f=="≥3x avg":  fdf=fdf[fdf.vol_ratio>=3.0]
if rsi_f=="Oversold <30": fdf=fdf[fdf.rsi14<30]
elif rsi_f=="Neutral":    fdf=fdf[(fdf.rsi14>=30)&(fdf.rsi14<60)]
elif rsi_f=="Bullish":    fdf=fdf[(fdf.rsi14>=60)&(fdf.rsi14<70)]
elif rsi_f=="Overbought >70": fdf=fdf[fdf.rsi14>=70]
if a200: fdf=fdf[fdf.above_ma200==True]
if s2o:  fdf=fdf[fdf.weinstein_stage=="2A"]
if ath20: fdf=fdf[fdf.from_ath_pct>=-20]
if mvo:   fdf=fdf[fdf.minervini_tag=="✅ Full"]
if min_rs is not None: fdf=fdf[fdf.rs_63d>=float(min_rs)]
sm={"Score ↓":("composite_score",False),"RS Rank ↑":("rs_rank",True),
    "Chg% ↓":("chg_pct",False),"Chg% ↑":("chg_pct",True),
    "Vol Ratio ↓":("vol_ratio",False),"RSI ↑":("rsi14",False),"RSI ↓":("rsi14",True)}
sc2,sa=sm.get(srt,("composite_score",False))
if sc2 in fdf.columns: fdf=fdf.sort_values(sc2,ascending=sa)
st.caption(f"**{len(fdf)}** of {b['total']} stocks")

# Build display frame
def build_show(fdf):
    out=pd.DataFrame()
    out["#"]         =fdf["score_rank"].astype("Int64")
    out["Symbol"]    =fdf["symbol"]
    out["Company"]   =fdf.get("company_name",fdf["symbol"]).str[:22] if "company_name" in fdf.columns else fdf["symbol"]
    out["Cap"]       =fdf["cap_bucket"].str[:5] if "cap_bucket" in fdf.columns else ""
    out["CMP (₹)"]  =fdf["cmp"].round(2)
    out["Chg%"]     =fdf["chg_pct"].round(2)
    out["Chg ₹"]    =fdf["chg_abs"].round(2)
    out["Volume"]    =fdf["vol_today"].apply(fmt_vol)
    out["Vol"]       =fdf["vol_ratio"].round(2)
    out["Vol Signal"]=fdf["vol_tag"]
    out["RSI"]       =fdf["rsi14"].round(1)
    out["RSI View"]  =fdf["rsi_tag"]
    out["RS 63d%"]   =fdf["rs_63d"].round(2)
    out["RS Rank"]   =fdf["rs_rank"].astype("Int64")
    out["vs MA50"]   =fdf["vs_ma50_pct"].round(1)
    out["vs MA200"]  =fdf["vs_ma200_pct"].round(1)
    out["vs ATH"]    =fdf["from_ath_pct"].round(1)
    out["Stage"]     =fdf["weinstein_stage"]
    out["Minervini"] =fdf["minervini_tag"]
    out["Rel/Mkt"]   =fdf["rel_vs_nifty"].round(2)
    out["Score"]     =fdf["composite_score"].round(1)
    return out.reset_index(drop=True)

show=build_show(fdf)
st.dataframe(
    style_df(show), use_container_width=True, height=560, hide_index=True,
    column_config={
        "#":           st.column_config.NumberColumn(width=42,  format="%d"),
        "Symbol":      st.column_config.TextColumn(width=82),
        "Company":     st.column_config.TextColumn(width=155),
        "Cap":         st.column_config.TextColumn(width=48),
        "CMP (₹)":    st.column_config.NumberColumn(width=85,  format="%.2f"),
        "Chg%":       st.column_config.NumberColumn(width=65,  format="%.2f%%"),
        "Chg ₹":      st.column_config.NumberColumn(width=65,  format="%.2f"),
        "Volume":      st.column_config.TextColumn(width=72),
        "Vol":         st.column_config.NumberColumn("Vol Ratio",width=68, format="%.2fx"),
        "Vol Signal":  st.column_config.TextColumn(width=130),
        "RSI":         st.column_config.NumberColumn(width=50,  format="%.1f"),
        "RSI View":    st.column_config.TextColumn(width=90),
        "RS 63d%":     st.column_config.NumberColumn(width=75,  format="%.2f%%"),
        "RS Rank":     st.column_config.NumberColumn(width=65,  format="%d"),
        "vs MA50":     st.column_config.NumberColumn(width=68,  format="%.1f%%"),
        "vs MA200":    st.column_config.NumberColumn(width=75,  format="%.1f%%"),
        "vs ATH":      st.column_config.NumberColumn(width=62,  format="%.1f%%"),
        "Stage":       st.column_config.TextColumn(width=52),
        "Minervini":   st.column_config.TextColumn(width=88),
        "Rel/Mkt":     st.column_config.NumberColumn(width=65,  format="%.2f%%"),
        "Score":       st.column_config.ProgressColumn(width=82,min_value=0,max_value=100,format="%.1f"),
    }
)
csv=fdf.to_csv(index=False).encode()
st.download_button("📥 Export CSV",csv,f"market_pulse_{pulse_date}.csv","text/csv")
st.divider()

# ══════════════════════════════════════════════
#  4 ─ STRENGTH IN WEAKNESS  (only on red days)
# ══════════════════════════════════════════════
if nchg<-0.3:
    st.markdown('<p class="sec">💎 Strength in Weakness</p>',unsafe_allow_html=True)
    st.caption(f"Nifty {nchg:+.2f}% today. Stocks outperforming = being accumulated = will lead next rally (O'Neil).")
    siw=df.copy(); siw["vs Nifty"]=( siw.chg_pct-nchg).round(2)
    siw=siw.nlargest(30,"vs Nifty")[["symbol","cmp","chg_pct","vs Nifty","rs_63d","vol_ratio","rsi14","weinstein_stage","composite_score"]]
    st.dataframe(siw,use_container_width=True,height=400,hide_index=True,
        column_config={"cmp":st.column_config.NumberColumn("CMP",format="₹%.2f"),
                       "chg_pct":st.column_config.NumberColumn("Chg%",format="%.2f%%"),
                       "vs Nifty":st.column_config.NumberColumn("vs Nifty",format="+%.2f%%"),
                       "rs_63d":st.column_config.NumberColumn("RS 63d%",format="%.2f%%"),
                       "vol_ratio":st.column_config.NumberColumn("Vol Ratio",format="%.2fx"),
                       "rsi14":st.column_config.NumberColumn("RSI",format="%.1f"),
                       "composite_score":st.column_config.ProgressColumn("Score",min_value=0,max_value=100,format="%.1f")})
    st.divider()

# ══════════════════════════════════════════════
#  5 ─ QUICK SCREENERS
# ══════════════════════════════════════════════
st.markdown('<p class="sec">🎯 Quick Screeners</p>',unsafe_allow_html=True)
t1,t2,t3,t4=st.tabs(["🚀 Stage 2 Leaders","💎 Volume Breakouts","📉 Oversold Watch","🏆 Near ATH"])

def stbl(d,cols,cfg=None):
    base={"cmp":st.column_config.NumberColumn("CMP",format="₹%.2f"),
          "chg_pct":st.column_config.NumberColumn("Chg%",format="%.2f%%"),
          "vol_ratio":st.column_config.NumberColumn("Vol Ratio",format="%.2fx"),
          "rsi14":st.column_config.NumberColumn("RSI",format="%.1f"),
          "rs_63d":st.column_config.NumberColumn("RS 63d%",format="%.2f%%"),
          "from_ath_pct":st.column_config.NumberColumn("vs ATH",format="%.1f%%"),
          "composite_score":st.column_config.ProgressColumn("Score",min_value=0,max_value=100,format="%.1f")}
    if cfg: base.update(cfg)
    st.dataframe(d[[c for c in cols if c in d.columns]],use_container_width=True,
                 height=360,hide_index=True,column_config=base)

BASE=["symbol","cmp","chg_pct","vol_ratio","rsi14","rs_63d","weinstein_stage","composite_score"]
with t1:
    st.caption("Stage 2A + Score ≥50 — confirmed uptrend, best Weinstein entry zone")
    stbl(df[(df.weinstein_stage=="2A")&(df.composite_score>=50)].nlargest(50,"composite_score"),BASE+["minervini_tag"])
with t2:
    st.caption("Volume ≥2x 10-day avg — unusual institutional activity, potential breakout")
    stbl(df[df.vol_ratio>=2.0].nlargest(50,"vol_ratio"),BASE+["vol_tag"])
with t3:
    st.caption("RSI ≤35 in Stage 1/2 — oversold in healthy structure = mean-reversion opportunity")
    stbl(df[(df.rsi14<=35)&(df.weinstein_stage.isin(["1A","1B","2A"]))].nlargest(50,"rs_63d"),BASE+["rsi_tag"])
with t4:
    st.caption("Within 5% of ATH + Stage 2 — market leaders consolidating near highs")
    stbl(df[(df.from_ath_pct>=-5)&(df.weinstein_stage=="2A")].nlargest(50,"composite_score"),
         ["symbol","cmp","chg_pct","from_ath_pct","rs_63d","rsi14","composite_score"])
st.divider()

# ══════════════════════════════════════════════
#  6 ─ DEEP-DIVE
# ══════════════════════════════════════════════
st.markdown('<p class="sec">🔬 Stock Deep-Dive</p>',unsafe_allow_html=True)
sel=st.selectbox("Select stock",fdf["symbol"].tolist() if len(fdf) else df["symbol"].tolist(),
                 label_visibility="collapsed", key="mp_deepdive_sel")
if sel:
    row=df[df.symbol==sel].iloc[0]
    c=st.columns(7)
    c[0].metric("CMP",       f"₹{row.cmp:,.2f}",      delta=f"{row.chg_pct:+.2f}%")
    c[1].metric("RSI (14)",  f"{row.rsi14:.1f}",       delta=row.rsi_tag)
    c[2].metric("RS Spread", f"{row.rs_63d:+.1f}%")
    c[3].metric("RS Rank",   f"#{int(row.rs_rank)}")
    c[4].metric("Vol Ratio", f"{row.vol_ratio:.2f}x",  delta=row.vol_tag)
    c[5].metric("Score",     f"{row.composite_score:.0f}/100")
    c[6].metric("Stage",     row.weinstein_stage)
    l=st.columns(7)
    l[0].metric("vs ATH",   f"{row.from_ath_pct:.1f}%")
    l[1].metric("vs 52W Hi",f"{row.from_52wh_pct:.1f}%")
    l[2].metric("vs MA50",  f"{row.vs_ma50_pct:+.1f}%")
    l[3].metric("vs MA200", f"{row.vs_ma200_pct:+.1f}%")
    l[4].metric("Minervini",row.minervini_tag)
    l[5].metric("Rel/Mkt",  f"{row.rel_vs_nifty:+.2f}%")
    l[6].metric("Sector",   str(row.get("sector","—"))[:16])

    co=str(row.get("company_name",row.symbol)); sec=str(row.get("sector",""))
    st.markdown(f"""
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:7px;
                padding:10px 15px;font-size:12px;color:#475569;margin:5px 0">
      <b style="color:#0f172a">{row.symbol}</b> · {co[:50]} · {sec[:35]} ·
      {str(row.get("cap_bucket",""))} cap<br>
      <span style="margin-top:4px;display:inline-block">
      ATH ₹{row.ath:,.2f} · 52W Hi ₹{row.high_52w:,.2f} · 52W Lo ₹{row.low_52w:,.2f} ·
      MA20 ₹{row.ma20:,.2f} · MA50 ₹{row.ma50:,.2f} · MA200 ₹{row.ma200:,.2f}
      </span>
    </div>""",unsafe_allow_html=True)

    ins=[]
    if row.vol_ratio>=2.0:    ins.append(f"🔊 Volume **{row.vol_ratio:.1f}x** 10d avg — strong institutional signal")
    elif row.vol_ratio>=1.5:  ins.append(f"⬆ Volume **{row.vol_ratio:.1f}x** avg — above-normal interest")
    if row.from_ath_pct>=-3:  ins.append("🏆 Within 3% of **ATH** — breakout zone, watch closely")
    if row.rsi14<=35:          ins.append(f"🟢 RSI **{row.rsi14:.0f}** — oversold, watch for reversal signal")
    if row.rsi14>=70:          ins.append(f"🔴 RSI **{row.rsi14:.0f}** — overbought, may pause/pull back")
    if row.rs_63d>=10:         ins.append(f"⚡ Outperforming Nifty by **{row.rs_63d:+.1f}%** (63d) — leadership")
    if row.minervini_tag=="✅ Full": ins.append("✅ **Minervini Trend Template** — all 8 criteria met")
    if row.weinstein_stage=="4":    ins.append("⚠️ **Stage 4** — downtrend active, avoid new entries")
    if row.weinstein_stage=="2A":   ins.append("🚀 **Stage 2A** — advancing phase, Weinstein buy zone")
    if row.vs_ma200_pct<-10:        ins.append(f"📉 **{row.vs_ma200_pct:.1f}%** below MA200 — structural weakness")
    if row.chg_pct>0 and nchg<0:   ins.append(f"💪 **Rising on down day** (Nifty {nchg:.2f}%) — hidden strength")
    elif row.chg_pct<0 and abs(row.chg_pct)<abs(nchg)*0.5 and nchg<0:
        ins.append(f"🛡 Fell only **{row.chg_pct:.2f}%** vs Nifty {nchg:.2f}% — accumulation signal")
    if ins:
        st.markdown("**📋 Insights**")
        ic1,ic2=st.columns(2)
        for i,x in enumerate(ins): (ic1 if i%2==0 else ic2).markdown(f"- {x}")

st.divider()
with st.expander("📖 Methodology & Column Guide"):
    st.markdown("""
    | Column | Source | Meaning |
    |--------|--------|---------|
    | **Score** | Composite | RS(30) + Price(20) + Volume(15) + RSI(15) + Minervini(20) = 0–100 |
    | **RS 63d%** | O'Neil/IBD | % outperformance vs Nifty 50 over 63 trading days |
    | **RS Rank** | IBD | 1 = strongest RS in universe |
    | **Vol Ratio** | CANSLIM | Today ÷ 10-day avg. ≥1.5x = institutional interest |
    | **Stage** | Weinstein | 2A = buy zone · 4 = decline (avoid) |
    | **Minervini TT** | Minervini | ✅ Full = all 8 trend template criteria met |
    | **Rel/Mkt** | Livermore | Stock chg% − Nifty chg% (strength vs market today) |
    | **vs ATH** | Price | % below all-time high |
    
    **Data cadence:** Engine runs daily at 4:45 PM IST via GitHub Actions cron.
    NSE rebalances every 6 months — universe auto-updates via ar_universe table.
    """)
st.caption(f"AlphaRadar Market Pulse · {pd_str}")
st.markdown('<div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:7px;padding:7px 14px;margin-top:5px"><p style="font-size:11px;color:#991b1b;margin:0"><b>⚠️ DISCLAIMER:</b> Educational/research tool. Not SEBI-registered. Not investment advice. Trade at your own risk.</p></div>',unsafe_allow_html=True)
