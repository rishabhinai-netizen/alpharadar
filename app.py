"""
AlphaRadar — Nifty 1000 Scoring Dashboard
==========================================
Weinstein + O'Neil + Minervini Composite Scoring Engine
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="AlphaRadar", page_icon="◎", layout="wide", initial_sidebar_state="collapsed")

# ── STYLING ──
st.markdown("""
<style>
    .stApp { background-color: #ffffff; }
    .main .block-container { padding: 1rem 1.5rem; max-width: 100%; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; }
    .score-must { color: #059669; font-weight: 700; }
    .score-can { color: #2563eb; font-weight: 700; }
    .score-neutral { color: #64748b; font-weight: 700; }
    .score-avoid { color: #d97706; font-weight: 700; }
    .score-sell { color: #dc2626; font-weight: 700; }
    div[data-testid="stDataFrame"] { border: 1px solid #e2e8f0; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

from data_pipeline import sb_query

# ── LOAD DATA ──
@st.cache_data(ttl=300)
def load_scores():
    today = datetime.now().strftime('%Y-%m-%d')
    data = sb_query('ar_daily_scores', select='*', params={
        'score_date': f'eq.{today}',
        'order': 'composite_score.desc'
    }, limit=1000)
    if not data:
        # Try yesterday
        from datetime import timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        data = sb_query('ar_daily_scores', select='*', params={
            'score_date': f'eq.{yesterday}',
            'order': 'composite_score.desc'
        }, limit=1000)
    if not data:
        # Get latest available
        data = sb_query('ar_daily_scores', select='*', params={
            'order': 'score_date.desc,composite_score.desc',
        }, limit=1000)
    return pd.DataFrame(data) if data else pd.DataFrame()

@st.cache_data(ttl=3600)
def load_universe():
    data = sb_query('ar_universe', select='symbol,company_name,industry,cap_bucket', 
                    params={'is_active': 'eq.true'}, limit=1000)
    return {d['symbol']: d for d in data} if data else {}

df = load_scores()
universe = load_universe()

# ── HEADER ──
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown("# ◎ AlphaRadar")
    st.caption("NIFTY TOTAL MARKET · WEINSTEIN + O'NEIL + MINERVINI SCORING ENGINE")
with c2:
    if not df.empty:
        score_date = df['score_date'].iloc[0] if 'score_date' in df.columns else 'N/A'
        st.metric("Stocks Scored", len(df))
        st.caption(f"Data: {score_date}")

if df.empty:
    st.warning("No scores found. Run the scoring engine first using the '⚡ Run Scoring' page in the sidebar.")
    st.info("Navigate to the **⚡ Run Scoring** page to perform the initial data load and scoring.")
    st.stop()

# Merge company names from universe
if universe:
    df['company_name'] = df['symbol'].map(lambda s: universe.get(s, {}).get('company_name', ''))
    df['industry'] = df['symbol'].apply(lambda s: universe.get(s, {}).get('industry', ''))
    df['cap_bucket'] = df['symbol'].apply(lambda s: universe.get(s, {}).get('cap_bucket', ''))

# ── SUMMARY CARDS ──
BUCKET_CFG = {
    'MUST_BUY': ('🟢', 'Must Buy', '#059669'),
    'CAN_BUY': ('🔵', 'Can Buy', '#2563eb'),
    'NEUTRAL': ('⚪', 'Neutral', '#64748b'),
    'AVOID': ('🟡', 'Avoid', '#d97706'),
    'SELL': ('🔴', 'Sell', '#dc2626'),
}

cols = st.columns(5)
for i, (bucket, (emoji, label, color)) in enumerate(BUCKET_CFG.items()):
    cnt = len(df[df['bucket'] == bucket])
    cols[i].metric(f"{emoji} {label}", cnt)

st.divider()

# ── FILTERS ──
fc1, fc2, fc3, fc4, fc5 = st.columns([2, 1, 1, 1, 1])
with fc1:
    search = st.text_input("🔍 Search symbol or company", "", label_visibility="collapsed", placeholder="Search symbol or company...")
with fc2:
    bucket_filter = st.selectbox("Bucket", ["All"] + list(BUCKET_CFG.keys()), label_visibility="collapsed")
with fc3:
    stage_filter = st.selectbox("Stage", ["All", "2A", "2B", "1B", "1A", "3", "4"], label_visibility="collapsed")
with fc4:
    cap_filter = st.selectbox("Cap", ["All", "large", "mid", "small", "micro"], label_visibility="collapsed")
with fc5:
    sort_by = st.selectbox("Sort", ["Score ↓", "RS% ↓", "Change% ↓", "Score ↑"], label_visibility="collapsed")

# Apply filters
fdf = df.copy()
if search:
    q = search.lower()
    fdf = fdf[fdf['symbol'].str.lower().str.contains(q) | fdf.get('company_name', pd.Series(dtype=str)).str.lower().str.contains(q, na=False)]
if bucket_filter != "All":
    fdf = fdf[fdf['bucket'] == bucket_filter]
if stage_filter != "All":
    fdf = fdf[fdf['weinstein_stage'] == stage_filter]
if cap_filter != "All":
    fdf = fdf[fdf.get('cap_bucket', '') == cap_filter]

sort_map = {"Score ↓": ("composite_score", False), "RS% ↓": ("rs_percentile", False),
            "Change% ↓": ("price_change_pct", False), "Score ↑": ("composite_score", True)}
scol, sasc = sort_map.get(sort_by, ("composite_score", False))
if scol in fdf.columns:
    fdf = fdf.sort_values(scol, ascending=sasc)

st.caption(f"Showing {len(fdf)} of {len(df)} stocks")

# ── MAIN TABLE ──
if not fdf.empty:
    display_cols = ['symbol', 'composite_score', 'bucket', 'weinstein_stage', 'price',
                    'price_change_pct', 'rs_percentile', 'sector_percentile',
                    'stage_score', 'rs_score', 'volume_price_score',
                    'rs_new_high', 'stage_cap_applied']
    
    available = [c for c in display_cols if c in fdf.columns]
    show_df = fdf[available].copy()
    
    rename = {
        'symbol': 'Symbol', 'composite_score': 'Score', 'bucket': 'Bucket',
        'weinstein_stage': 'Stage', 'price': 'Price', 'price_change_pct': 'Chg%',
        'rs_percentile': 'RS Pctl', 'sector_percentile': 'Sec Pctl',
        'stage_score': 'Stg Score', 'rs_score': 'RS Score',
        'volume_price_score': 'VP Score', 'rs_new_high': 'RS★',
        'stage_cap_applied': 'Capped'
    }
    show_df = show_df.rename(columns=rename)
    
    st.dataframe(
        show_df,
        use_container_width=True,
        height=600,
        column_config={
            "Score": st.column_config.NumberColumn(format="%.1f"),
            "Price": st.column_config.NumberColumn(format="₹%.2f"),
            "Chg%": st.column_config.NumberColumn(format="%.2f%%"),
            "RS Pctl": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "Sec Pctl": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "Stg Score": st.column_config.NumberColumn(format="%.1f/30"),
            "RS Score": st.column_config.NumberColumn(format="%.1f/25"),
            "VP Score": st.column_config.NumberColumn(format="%.1f/20"),
            "RS★": st.column_config.CheckboxColumn(),
            "Capped": st.column_config.CheckboxColumn(),
        },
        hide_index=True,
    )

# ── STOCK DETAIL ──
st.divider()
st.subheader("📊 Stock Detail")
if not fdf.empty:
    selected = st.selectbox("Select stock", fdf['symbol'].tolist(), label_visibility="collapsed")
    if selected:
        row = fdf[fdf['symbol'] == selected].iloc[0]
        bucket_cfg = BUCKET_CFG.get(row['bucket'], ('', '', '#000'))
        
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Composite Score", f"{row['composite_score']:.1f}/100")
        d2.metric("Bucket", f"{bucket_cfg[0]} {bucket_cfg[1]}")
        d3.metric("Stage", row['weinstein_stage'])
        d4.metric("RS Percentile", f"{row['rs_percentile']:.0f}%")
        
        # Factor breakdown
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
            fig.add_trace(go.Bar(
                x=[val], y=[label], orientation='h', marker_color=color,
                text=f"{val:.1f}/{mx}", textposition='auto',
                hovertemplate=f"{label}: {val:.1f}/{mx}<extra></extra>"
            ))
        fig.update_layout(
            showlegend=False, height=250, margin=dict(l=0, r=20, t=10, b=10),
            xaxis=dict(range=[0, 30], showticklabels=False),
            yaxis=dict(autorange="reversed"),
            plot_bgcolor='white'
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Key flags
        flags = []
        if row.get('rs_new_high'): flags.append("⭐ RS New High")
        if row.get('stage_cap_applied'): flags.append(f"⚠️ Stage Capped (raw: {row.get('raw_composite', 'N/A')})")
        if flags:
            st.info(" · ".join(flags))

# ── DISTRIBUTION CHARTS ──
st.divider()
c1, c2 = st.columns(2)

with c1:
    st.subheader("Bucket Distribution")
    bucket_counts = df['bucket'].value_counts()
    fig = go.Figure(go.Pie(
        labels=[BUCKET_CFG[b][1] for b in bucket_counts.index if b in BUCKET_CFG],
        values=[bucket_counts[b] for b in bucket_counts.index if b in BUCKET_CFG],
        marker_colors=[BUCKET_CFG[b][2] for b in bucket_counts.index if b in BUCKET_CFG],
        hole=0.4
    ))
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.subheader("Stage Distribution")
    if 'weinstein_stage' in df.columns:
        stage_counts = df['weinstein_stage'].value_counts()
        stage_colors = {'2A': '#059669', '2B': '#10b981', '1B': '#3b82f6', '1A': '#94a3b8', '3': '#d97706', '4': '#dc2626'}
        fig = go.Figure(go.Bar(
            x=[f"Stage {s}" for s in stage_counts.index],
            y=stage_counts.values,
            marker_color=[stage_colors.get(s, '#94a3b8') for s in stage_counts.index]
        ))
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20), plot_bgcolor='white')
        st.plotly_chart(fig, use_container_width=True)

st.caption("AlphaRadar v2.0 · Weinstein Stage + RS Percentile + O'Neil Volume-Price · Stage Hard Gate Active")
