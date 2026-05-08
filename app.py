"""
AlphaRadar — Nifty 1000 Scoring Dashboard
"""
import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="AlphaRadar", page_icon="◎", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background: #ffffff; }
    .main .block-container { padding: 1rem 1.5rem; max-width: 100%; }
    div[data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]
SB_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

def sb_get(table, select="*", params="", limit=1000):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}&limit={limit}"
    if params: url += "&" + params
    r = requests.get(url, headers=SB_HEADERS)
    return r.json() if r.status_code == 200 else []

# ── LOAD LATEST SCORES (always the most recent score_date) ──
@st.cache_data(ttl=300)
def load_scores():
    # Get latest score_date first
    latest = sb_get('ar_daily_scores', 'score_date', 'order=score_date.desc&limit=1')
    if not latest: return pd.DataFrame(), "N/A"
    latest_date = latest[0]['score_date']
    # Now get all scores for that date
    data = sb_get('ar_daily_scores', '*', f'score_date=eq.{latest_date}&order=composite_score.desc')
    return pd.DataFrame(data), latest_date

@st.cache_data(ttl=3600)
def load_universe():
    data = sb_get('ar_universe', 'symbol,company_name,industry,cap_bucket', 'is_active=eq.true')
    return {d['symbol']: d for d in data} if data else {}

@st.cache_data(ttl=3600)
def load_score_history():
    """Load distinct score dates to show update history."""
    data = sb_get('ar_daily_scores', 'score_date', 'order=score_date.desc&limit=30')
    if data:
        dates = list(set(d['score_date'] for d in data))
        dates.sort(reverse=True)
        return dates
    return []

df, score_date = load_scores()
universe = load_universe()
history_dates = load_score_history()

# ── HEADER ──
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown("# ◎ AlphaRadar")
    st.caption("NIFTY TOTAL MARKET · WEINSTEIN + O'NEIL + MINERVINI")
with c2:
    if not df.empty:
        st.metric("Stocks Scored", len(df))
        days_old = (datetime.now() - datetime.strptime(score_date, '%Y-%m-%d')).days
        if days_old == 0:
            st.caption(f"📅 {score_date} (today)")
        elif days_old == 1:
            st.caption(f"📅 {score_date} (yesterday)")
        else:
            st.caption(f"⚠️ {score_date} ({days_old} days old)")
        if len(history_dates) > 1:
            st.caption(f"📊 {len(history_dates)} scoring runs logged")

if df.empty:
    st.error("No scores found in the database.")
    st.info("""
    **To get started:**
    1. Go to **⚡ Run Scoring** in the sidebar
    2. Click **🚀 Initial Load**
    3. Wait ~15 minutes for data to load

    After that, daily updates run automatically via GitHub Actions at 4:45 PM IST.
    """)
    st.stop()

# Merge company info
if universe:
    df['company_name'] = df['symbol'].map(lambda s: universe.get(s, {}).get('company_name', ''))
    df['industry'] = df['symbol'].map(lambda s: universe.get(s, {}).get('industry', ''))
    df['cap_bucket'] = df['symbol'].map(lambda s: universe.get(s, {}).get('cap_bucket', ''))

# ── SUMMARY CARDS ──
BCFG = {
    'MUST_BUY': ('🟢', 'Must Buy', '#059669'),
    'CAN_BUY': ('🔵', 'Can Buy', '#2563eb'),
    'NEUTRAL': ('⚪', 'Neutral', '#64748b'),
    'AVOID': ('🟡', 'Avoid', '#d97706'),
    'SELL': ('🔴', 'Sell', '#dc2626'),
}
cols = st.columns(5)
for i, (bk, (em, lb, cl)) in enumerate(BCFG.items()):
    cols[i].metric(f"{em} {lb}", len(df[df['bucket'] == bk]))

st.divider()

# ── TODAY'S ACTIONABLE HIGHLIGHTS ──
if 'stage_changed' in df.columns and 'weinstein_stage' in df.columns:
    stage_changed = df[df.get('stage_changed', False) == True] if 'stage_changed' in df.columns else pd.DataFrame()
    new_stage2 = stage_changed[stage_changed['weinstein_stage'].isin(['2A', '2B'])] if not stage_changed.empty else pd.DataFrame()
    new_stage4 = stage_changed[stage_changed['weinstein_stage'] == '4'] if not stage_changed.empty else pd.DataFrame()
    top_rs_stars = df[(df.get('rs_new_high', False) == True) & (df['weinstein_stage'].isin(['2A', '2B']))].sort_values('composite_score', ascending=False).head(5) if 'rs_new_high' in df.columns else pd.DataFrame()
    
    if not new_stage2.empty or not new_stage4.empty or not top_rs_stars.empty:
        h1, h2, h3 = st.columns(3)
        with h1:
            if not new_stage2.empty:
                st.success(f"🟢 **{len(new_stage2)} New Buy Signals** (entered Stage 2)")
                for _, r in new_stage2.head(5).iterrows():
                    st.write(f"▸ **{r['symbol']}** Score {r['composite_score']:.0f} · RS {r['rs_percentile']:.0f}%")
            else:
                st.info("No new Stage 2 entries today")
        with h2:
            if not new_stage4.empty:
                st.error(f"🔴 **{len(new_stage4)} Sell Signals** (entered Stage 4)")
                for _, r in new_stage4.head(5).iterrows():
                    st.write(f"▸ **{r['symbol']}** Score {r['composite_score']:.0f}")
            else:
                st.info("No new Stage 4 entries today")
        with h3:
            if not top_rs_stars.empty:
                st.markdown(f"⭐ **Top Stage 2 + RS New High** (strongest leaders)")
                for _, r in top_rs_stars.iterrows():
                    st.write(f"▸ **{r['symbol']}** Score {r['composite_score']:.0f} · RS {r['rs_percentile']:.0f}%")
            else:
                st.info("No Stage 2 RS new highs today")

st.divider()

# ── FILTERS ──
fc1, fc2, fc3, fc4, fc5 = st.columns([2.5, 1, 1, 1, 1])
with fc1:
    search = st.text_input("Search", "", placeholder="Symbol or company...", label_visibility="collapsed")
with fc2:
    bf = st.selectbox("Bucket", ["All"] + list(BCFG.keys()), label_visibility="collapsed")
with fc3:
    sf = st.selectbox("Stage", ["All", "2A", "2B", "1B", "1A", "3", "4"], label_visibility="collapsed")
with fc4:
    cf = st.selectbox("Cap", ["All", "large", "mid", "small", "micro"], label_visibility="collapsed")
with fc5:
    sort = st.selectbox("Sort", ["Score ↓", "RS% ↓", "Chg% ↓", "Score ↑"], label_visibility="collapsed")

fdf = df.copy()
if search:
    q = search.lower()
    fdf = fdf[fdf['symbol'].str.lower().str.contains(q) | fdf.get('company_name', pd.Series(dtype=str)).str.lower().str.contains(q, na=False)]
if bf != "All": fdf = fdf[fdf['bucket'] == bf]
if sf != "All": fdf = fdf[fdf['weinstein_stage'] == sf]
if cf != "All" and 'cap_bucket' in fdf.columns: fdf = fdf[fdf['cap_bucket'] == cf]

sm = {"Score ↓": ("composite_score", False), "RS% ↓": ("rs_percentile", False),
      "Chg% ↓": ("price_change_pct", False), "Score ↑": ("composite_score", True)}
sc, sa = sm.get(sort, ("composite_score", False))
if sc in fdf.columns: fdf = fdf.sort_values(sc, ascending=sa)

st.caption(f"Showing {len(fdf)} of {len(df)} stocks · Data: {score_date}")

# Quick legend
with st.expander("ℹ️ Quick Guide — What do the columns mean?", expanded=False):
    st.markdown("""
    | Column | Meaning | Good Value |
    |--------|---------|------------|
    | **Score** | Overall conviction (0-100) | 60+ for trades |
    | **Stage** | Weinstein cycle stage | **2A** = buy zone |
    | **RS Pctl** | Strength rank vs all stocks | >70% = strong |
    | **Sec Pctl** | Strength rank within sector | >70% = sector leader |
    | **Stg/RS/VP** | Sub-scores: Trend, Strength, Volume | Higher = better |
    | **RS★** | RS at 52-week high | ⭐ = very bullish |
    | **Capped** | Score limited by Stage gate | Stage 4 max = 20 |
    
    📖 **Full guide:** See the "How to Use" page in the sidebar
    """)


# ── MAIN TABLE ──
if not fdf.empty:
    dcols = [c for c in ['symbol', 'composite_score', 'score_change', 'bucket', 'weinstein_stage',
             'price', 'price_change_pct', 'rs_percentile', 'sector_percentile',
             'stage_score', 'rs_score', 'volume_price_score',
             'rs_new_high', 'stage_cap_applied', 'stage_changed'] if c in fdf.columns]
    show = fdf[dcols].copy()
    ren = {'symbol': 'Symbol', 'composite_score': 'Score', 'score_change': 'Δ Score',
           'bucket': 'Bucket', 'weinstein_stage': 'Stage', 'price': 'Price',
           'price_change_pct': 'Chg%', 'rs_percentile': 'RS Pctl',
           'sector_percentile': 'Sec Pctl', 'stage_score': 'Stg',
           'rs_score': 'RS', 'volume_price_score': 'VP',
           'rs_new_high': 'RS★', 'stage_cap_applied': 'Capped', 'stage_changed': 'Stg Chg'}
    show = show.rename(columns=ren)

    ccfg = {
        "Score": st.column_config.NumberColumn(format="%.1f", help="Composite score 0-100. Higher = stronger stock. 60+ = trade worthy"),
        "Δ Score": st.column_config.NumberColumn(format="%+.1f", help="Change vs previous day. Large + = improving momentum, Large - = deteriorating"),
        "Price": st.column_config.NumberColumn(format="₹%.2f"),
        "Chg%": st.column_config.NumberColumn(format="%.2f%%", help="Daily price change"),
        "RS Pctl": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f", help="Rank among all stocks by 52-week return. >70 = strong, >90 = elite leader"),
        "Sec Pctl": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f", help="Rank within its own sector. High RS + High Sec = true sector leader"),
        "Stg": st.column_config.NumberColumn(format="%.1f", help="Trend/Stage score (0-30). Based on Weinstein 30-week MA analysis"),
        "RS": st.column_config.NumberColumn(format="%.1f", help="Relative Strength score (0-25). Measures outperformance vs Nifty 50"),
        "VP": st.column_config.NumberColumn(format="%.1f", help="Volume-Price score (0-20). O'Neil/Minervini accumulation & base quality"),
        "RS★": st.column_config.CheckboxColumn(help="⭐ = RS line at 52-week high. Very bullish — stock is at peak relative performance"),
        "Capped": st.column_config.CheckboxColumn(help="Score was capped by Stage gate. Stage 4 max=20, Stage 3 max=40"),
        "Stg Chg": st.column_config.CheckboxColumn(help="Stage changed vs previous day. Into Stage 2 = buy signal, Into Stage 4 = sell signal"),
    }
    st.dataframe(show, use_container_width=True, height=600, column_config=ccfg, hide_index=True)

# ── STOCK DETAIL ──
st.divider()
st.subheader("📊 Stock Detail")
if not fdf.empty:
    sel = st.selectbox("Select stock", fdf['symbol'].tolist(), label_visibility="collapsed")
    if sel:
        row = fdf[fdf['symbol'] == sel].iloc[0]
        bcfg = BCFG.get(row['bucket'], ('', '', '#000'))
        d1, d2, d3, d4, d5 = st.columns(5)
        d1.metric("Score", f"{row['composite_score']:.1f}/100",
                  delta=f"{row.get('score_change', 0) or 0:+.1f}" if row.get('score_change') else None)
        d2.metric("Bucket", f"{bcfg[0]} {bcfg[1]}")
        d3.metric("Stage", row['weinstein_stage'])
        d4.metric("RS Percentile", f"{row['rs_percentile']:.0f}%")
        d5.metric("Price", f"₹{row.get('price', 0):.2f}",
                  delta=f"{row.get('price_change_pct', 0):.2f}%")

        st.markdown("**Factor Breakdown**")
        factors = [
            ("Trend/Stage (30%)", row.get('stage_score', 0), 30, "#7c3aed"),
            ("Relative Strength (25%)", row.get('rs_score', 0), 25, "#2563eb"),
            ("Volume & Price (20%)", row.get('volume_price_score', 0), 20, "#d97706"),
            ("Fundamentals (15%)", row.get('fundamental_score', 7.5), 15, "#059669"),
            ("Catalyst (10%)", row.get('catalyst_score', 1), 10, "#ec4899"),
        ]
        fig = go.Figure()
        for label, val, mx, color in factors:
            fig.add_trace(go.Bar(x=[val], y=[label], orientation='h', marker_color=color,
                                text=f"{val:.1f}/{mx}", textposition='auto'))
        fig.update_layout(showlegend=False, height=250, margin=dict(l=0, r=20, t=10, b=10),
                         xaxis=dict(range=[0, 30], showticklabels=False),
                         yaxis=dict(autorange="reversed"), plot_bgcolor='white')
        st.plotly_chart(fig, use_container_width=True)

        flags = []
        if row.get('rs_new_high'): flags.append("⭐ RS New High")
        if row.get('stage_cap_applied'): flags.append(f"⚠️ Stage Capped (raw: {row.get('raw_composite', 'N/A')})")
        if row.get('stage_changed'): flags.append("🔄 Stage Changed Today")
        if flags: st.info(" · ".join(flags))

# ── CHARTS ──
st.divider()
c1, c2 = st.columns(2)
with c1:
    st.subheader("Bucket Distribution")
    bc = df['bucket'].value_counts()
    fig = go.Figure(go.Pie(
        labels=[BCFG[b][1] for b in bc.index if b in BCFG],
        values=[bc[b] for b in bc.index if b in BCFG],
        marker_colors=[BCFG[b][2] for b in bc.index if b in BCFG], hole=0.4))
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)
with c2:
    st.subheader("Stage Distribution")
    if 'weinstein_stage' in df.columns:
        stc = df['weinstein_stage'].value_counts()
        scl = {'2A': '#059669', '2B': '#10b981', '1B': '#3b82f6', '1A': '#94a3b8', '3': '#d97706', '4': '#dc2626'}
        fig = go.Figure(go.Bar(x=[f"Stage {s}" for s in stc.index], y=stc.values,
                               marker_color=[scl.get(s, '#94a3b8') for s in stc.index]))
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20), plot_bgcolor='white')
        st.plotly_chart(fig, use_container_width=True)

st.caption(f"AlphaRadar v2.1 · Score date: {score_date} · Stage Hard Gate active · Auto-updates daily at 4:45 PM IST")
