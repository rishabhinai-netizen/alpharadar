"""
AlphaRadar — N250F Momentum Strategy
=====================================
Nifty 250 Fortnightly Momentum — Top 20 by 3-month return
Real backtest: Jan 2015 – Apr 2025 | yfinance data | 258 rebalances | 1,715 trades

Two sections:
  1. BACKTEST VAULT — Full 10-year history, interactive, exportable
  2. LIVE TRACKER  — Current portfolio, next rebalance signal, entry/exit list
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import io
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from n250f_data import load_n250f_data
    DATA = load_n250f_data()
    DATA_LOADED = True
except Exception as e:
    DATA_LOADED = False
    DATA_ERR = str(e)

st.set_page_config(page_title="N250F — AlphaRadar", page_icon="📊", layout="wide")

# ── STYLES ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background: #0a0d13; color: #e2e8f0; }
.main .block-container { padding: 1.5rem 2rem; max-width: 100%; }
[data-testid="stMetricValue"] { font-size: 1.5rem !important; font-weight: 700 !important; }
[data-testid="stMetricDelta"] { font-size: 0.85rem !important; }
.n250f-header {
    background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
    border-radius: 12px; padding: 24px 28px; margin-bottom: 24px;
    border: 1px solid rgba(56,189,248,0.2);
}
.n250f-header h1 { font-size: 28px; font-weight: 800; color: #38bdf8; margin: 0 0 6px 0; }
.n250f-header p  { font-size: 13px; color: #94a3b8; margin: 0; }
.section-card {
    background: #111827; border: 1px solid #1f2937;
    border-radius: 10px; padding: 20px 22px; margin-bottom: 16px;
}
.metric-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.mcard {
    background: #1e293b; border-radius: 8px; padding: 14px 18px;
    border: 1px solid #334155; min-width: 130px; flex: 1;
}
.mcard-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 5px; }
.mcard-val { font-size: 22px; font-weight: 700; color: #e2e8f0; }
.mcard-val.green { color: #22d3a0; }
.mcard-val.red { color: #f87171; }
.mcard-val.amber { color: #fbbf24; }
.mcard-val.blue { color: #60a5fa; }
.rebal-chip {
    display: inline-block; font-size: 11px; padding: 2px 8px;
    border-radius: 12px; margin: 2px; font-weight: 500;
}
.chip-in  { background: rgba(34,211,160,0.15); color: #22d3a0; border: 1px solid rgba(34,211,160,0.3); }
.chip-out { background: rgba(248,113,113,0.15); color: #f87171; border: 1px solid rgba(248,113,113,0.3); }
.chip-hold { background: rgba(100,116,139,0.2); color: #94a3b8; border: 1px solid #334155; }
.next-rebal-box {
    background: rgba(251,191,36,0.08); border: 2px solid rgba(251,191,36,0.4);
    border-radius: 10px; padding: 16px 20px; text-align: center;
}
.next-rebal-date { font-size: 26px; font-weight: 800; color: #fbbf24; }
.signal-enter { background: rgba(34,211,160,0.12); border-left: 3px solid #22d3a0; padding: 10px 14px; border-radius: 0 6px 6px 0; margin: 4px 0; }
.signal-exit  { background: rgba(248,113,113,0.12); border-left: 3px solid #f87171; padding: 10px 14px; border-radius: 0 6px 6px 0; margin: 4px 0; }
.disclaimer { background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25); border-radius: 8px; padding: 12px 16px; font-size: 11px; color: #fca5a5; line-height: 1.7; margin-top: 24px; }
</style>
""", unsafe_allow_html=True)

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="n250f-header">
  <h1>📊 N250F — Nifty 250 Fortnightly Momentum</h1>
  <p>Top 20 stocks by 3-month return · Rebalanced every fortnight · Equal weight · 0.1% transaction cost applied</p>
  <p style="margin-top:6px;color:#475569">Real yfinance data · Jan 2015 – Apr 2025 · 258 rebalances · 1,715 closed trades</p>
</div>
""", unsafe_allow_html=True)

if not DATA_LOADED:
    st.error(f"Could not load backtest data: {DATA_ERR}")
    st.stop()

# ── PARSE DATA ────────────────────────────────────────────────────────────────
perf   = DATA['perf']
meta   = DATA['meta']
rebals = DATA['rebal']
curr   = DATA['curr']
yr_ret = perf['yearly_returns']

# Build portfolio value series from rebalances
port_vals = [(r['dt'], r['vs']) for r in rebals] + [(rebals[-1]['dt'], rebals[-1]['ve'])]
port_df   = pd.DataFrame(port_vals, columns=['date', 'value'])
port_df['date'] = pd.to_datetime(port_df['date'])
port_df = port_df.drop_duplicates('date').sort_values('date')

# ═══════════════════════════════════════════════════════════════════════════════
# TOP METRICS
# ═══════════════════════════════════════════════════════════════════════════════
c1, c2, c3, c4, c5, c6 = st.columns(6)
metrics = [
    (c1, "CAGR (10yr)", f"{perf['cagr_pct']}%", "green", "vs 11.3% Nifty50"),
    (c2, "₹10L → ", f"₹{perf['final_corpus']/100000:.1f}L", "green", f"Total +{perf['total_return_pct']:.0f}%"),
    (c3, "Max Drawdown", f"{perf['max_drawdown_pct']:.1f}%", "red", "Benchmark: -38.4%"),
    (c4, "Sharpe Ratio", f"{perf['sharpe']}", "amber", f"Volatility {perf['volatility_pct']:.1f}%"),
    (c5, "Win Rate", f"{perf['win_rate_pct']}%", "blue", f"{perf['total_trades']} trades"),
    (c6, "Avg Win / Loss", f"+{perf['avg_win_pct']:.1f}% / {perf['avg_loss_pct']:.1f}%", "green", f"Payoff {abs(perf['avg_win_pct']/perf['avg_loss_pct']):.1f}x"),
]
for col, label, val, color, sub in metrics:
    col.metric(label, val, sub)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# TWO MAIN SECTIONS
# ═══════════════════════════════════════════════════════════════════════════════
sec1_tab, sec2_tab = st.tabs(["🗄️  BACKTEST VAULT — 10 Year History", "🟢  LIVE TRACKER — Current & Next Rebalance"])

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: BACKTEST VAULT
# ═══════════════════════════════════════════════════════════════════════════════
with sec1_tab:

    v1, v2, v3, v4, v5 = st.tabs(["📈 Growth & Overview", "📅 Rebalance Explorer", "📋 Trade-by-Trade P&L", "📊 Yearly Breakdown", "💾 Export"])

    # ── 1.1 GROWTH CHART ──────────────────────────────────────────────────────
    with v1:
        st.subheader("Portfolio growth — ₹10,00,000 starting capital")

        # Build growth chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=port_df['date'], y=port_df['value'],
            name='N250F Strategy', line=dict(color='#22d3a0', width=2.5),
            fill='tozeroy', fillcolor='rgba(34,211,160,0.05)',
            hovertemplate='%{x|%d %b %Y}<br>₹%{y:,.0f}<extra></extra>'
        ))
        # Nifty50 approximation (11.3% CAGR from 1M)
        nifty_vals = [1_000_000 * (1.113 ** ((d - port_df['date'].iloc[0]).days / 365.25)) for d in port_df['date']]
        fig.add_trace(go.Scatter(
            x=port_df['date'], y=nifty_vals,
            name='Nifty50 (11.3% CAGR)', line=dict(color='#6b7280', width=1.5, dash='dash'),
            hovertemplate='Nifty50: ₹%{y:,.0f}<extra></extra>'
        ))
        fig.update_layout(
            height=380, plot_bgcolor='#111827', paper_bgcolor='#0a0d13',
            font=dict(color='#94a3b8', size=12),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0, font=dict(size=11)),
            xaxis=dict(showgrid=False, color='#475569'),
            yaxis=dict(showgrid=True, gridcolor='#1f2937', color='#475569',
                       tickformat='₹,.0f'),
            margin=dict(l=10, r=10, t=40, b=10), hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True)

        # Calendar return heatmap
        st.subheader("Calendar year returns")
        yr_df = pd.DataFrame(list(yr_ret.items()), columns=['Year','Return'])
        yr_df['Year'] = yr_df['Year'].astype(str)
        yr_df['Color'] = yr_df['Return'].apply(lambda r: '#22d3a0' if r >= 0 else '#f87171')
        yr_df['Label'] = yr_df['Return'].apply(lambda r: f"{r:+.1f}%")

        fig2 = go.Figure(go.Bar(
            x=yr_df['Year'], y=yr_df['Return'],
            marker_color=yr_df['Color'], text=yr_df['Label'], textposition='outside',
            hovertemplate='%{x}: %{y:+.1f}%<extra></extra>'
        ))
        fig2.add_hline(y=0, line_color='#475569', line_width=1)
        fig2.update_layout(
            height=280, plot_bgcolor='#111827', paper_bgcolor='#0a0d13',
            font=dict(color='#94a3b8'), showlegend=False,
            yaxis=dict(showgrid=True, gridcolor='#1f2937', ticksuffix='%'),
            xaxis=dict(showgrid=False), margin=dict(l=10, r=10, t=20, b=10)
        )
        st.plotly_chart(fig2, use_container_width=True)

        # Key stats grid
        st.subheader("Strategy deep-dive stats")
        cols = st.columns(4)
        stats = [
            ("Total rebalances", perf['total_rebalances'], ""),
            ("Avg turnover/rebal", f"~{sum(r['to'] for r in rebals)/len(rebals):.1f}%", "(stocks changed)"),
            ("Total transaction cost", f"₹{perf['total_cost_rs']/1000:.0f}K", "0.1% per trade"),
            ("Best year", f"+{perf['best_year']:.1f}%", "2023"),
            ("Worst year", f"{perf['worst_year']:.1f}%", "2025 YTD"),
            ("Payoff ratio", f"{abs(perf['avg_win_pct']/perf['avg_loss_pct']):.2f}x", "Win/loss size"),
            ("Avg holding period", f"~{sum(r['hold_days'] for rbl in rebals for r in rbl['sells'] if 'hold_days' in r) // max(1,sum(len(rbl['sells']) for rbl in rebals)):.0f} days" if any(rbl['sells'] for rbl in rebals) else "~28d", "per stock"),
            ("Profitable years", f"{sum(1 for v in yr_ret.values() if v > 0)}/{len(yr_ret)}", "out of 11"),
        ]
        for i, (lb, vl, sb) in enumerate(stats):
            cols[i % 4].metric(lb, vl, sb)

    # ── 1.2 REBALANCE EXPLORER ────────────────────────────────────────────────
    with v2:
        st.subheader("Explore any rebalance date")
        st.caption(f"258 fortnightly rebalances from Jun 2015 to Apr 2025")

        # Date picker from actual rebalance dates
        all_dates = [r['dt'] for r in rebals]
        selected_date = st.select_slider(
            "Select rebalance date",
            options=all_dates,
            value=all_dates[-1],
            label_visibility="collapsed"
        )

        sel = next((r for r in rebals if r['dt'] == selected_date), None)
        if sel:
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Portfolio value", f"₹{sel['vs']/100000:.2f}L")
            d2.metric("Period return", f"{sel['ret']:+.2f}%",
                      delta_color="normal" if sel['ret'] >= 0 else "inverse")
            d3.metric("Stocks changed", f"{sel['ne']} in / {sel['nx']} out")
            d4.metric("Turnover", f"{sel['to']:.1f}%")

            st.markdown("---")
            c_snap, c_trades = st.columns([3, 2])

            with c_snap:
                st.markdown("**Portfolio snapshot on this date**")
                if sel['snap']:
                    snap_df = pd.DataFrame(sel['snap'])
                    snap_df.columns = ['Ticker', 'Entry Date', 'Entry ₹', 'Price ₹', 'Mkt Val ₹', 'Unreal P&L ₹', 'Unreal %', 'Mom Rank']
                    snap_df['Unreal %'] = snap_df['Unreal %'].apply(lambda x: f"{x:+.1f}%")
                    snap_df['Entry ₹'] = snap_df['Entry ₹'].apply(lambda x: f"₹{x:,.2f}")
                    snap_df['Price ₹'] = snap_df['Price ₹'].apply(lambda x: f"₹{x:,.2f}")
                    snap_df['Mkt Val ₹'] = snap_df['Mkt Val ₹'].apply(lambda x: f"₹{x:,.0f}")
                    snap_df['Unreal P&L ₹'] = snap_df['Unreal P&L ₹'].apply(lambda x: f"₹{x:+,.0f}")
                    st.dataframe(snap_df, use_container_width=True, hide_index=True, height=350)
                else:
                    st.info("No snapshot data for this date")

            with c_trades:
                st.markdown("**Stocks entered this rebalance**")
                for e in sel['ents']:
                    st.markdown(f"<div class='rebal-chip chip-in'>▲ {e}</div>", unsafe_allow_html=True)
                if not sel['ents']:
                    st.caption("No new entries")

                st.markdown("**Stocks exited this rebalance**")
                for x in sel['exts']:
                    st.markdown(f"<div class='rebal-chip chip-out'>▼ {x}</div>", unsafe_allow_html=True)
                if not sel['exts']:
                    st.caption("No exits")

                st.markdown("**Closed trade details**")
                if sel['sells']:
                    for s in sel['sells']:
                        pnl_color = '#22d3a0' if s['pct'] >= 0 else '#f87171'
                        st.markdown(f"""
                        <div style="background:#1e293b;border-radius:6px;padding:8px 12px;margin:4px 0;border-left:3px solid {pnl_color}">
                          <strong>{s['t']}</strong> &nbsp;
                          <span style="color:#94a3b8;font-size:12px">Held {s['days']}d</span><br>
                          <span style="font-size:12px">Buy ₹{s['ep']:,.2f} → Sell ₹{s['xp']:,.2f}</span><br>
                          <span style="color:{pnl_color};font-weight:600">{s['pct']:+.2f}% &nbsp; ₹{s['pnl']:+,.0f}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.caption("No closes (first rebalance or all holds)")

        # Rebalance timeline
        st.markdown("---")
        st.subheader("All rebalances — timeline view")
        timeline_df = pd.DataFrame([{
            'Date': r['dt'], 'Value (₹L)': round(r['vs']/100000, 2),
            'Period Return': r['ret'], 'Entries': r['ne'], 'Exits': r['nx'], 'Turnover%': r['to']
        } for r in rebals])
        timeline_df['Date'] = pd.to_datetime(timeline_df['Date'])

        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            x=timeline_df['Date'], y=timeline_df['Period Return'],
            name='Period Return',
            marker_color=['#22d3a0' if v >= 0 else '#f87171' for v in timeline_df['Period Return']],
            hovertemplate='%{x|%d %b %Y}<br>Return: %{y:+.2f}%<extra></extra>'
        ))
        fig3.update_layout(
            height=250, plot_bgcolor='#111827', paper_bgcolor='#0a0d13',
            font=dict(color='#94a3b8'), showlegend=False,
            yaxis=dict(showgrid=True, gridcolor='#1f2937', ticksuffix='%'),
            xaxis=dict(showgrid=False), margin=dict(l=10, r=10, t=20, b=10)
        )
        st.plotly_chart(fig3, use_container_width=True)

    # ── 1.3 TRADE-BY-TRADE P&L ───────────────────────────────────────────────
    with v3:
        st.subheader("All closed trades — 1,715 real trade records")

        # Build full trade table
        all_sells = []
        for r in rebals:
            for s in r['sells']:
                all_sells.append({
                    'Exit Date': s['xd'], 'Ticker': s['t'],
                    'Entry Date': s['ed'], 'Entry ₹': s['ep'],
                    'Exit ₹': s['xp'], 'Return %': s['pct'],
                    'P&L ₹': s['pnl'], 'Hold Days': s['days'],
                    'Rebal Date': r['dt']
                })
        trade_full = pd.DataFrame(all_sells)
        if not trade_full.empty:
            trade_full = trade_full.sort_values('Exit Date', ascending=False)

            # Filters
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                yr_filter = st.selectbox("Year", ['All'] + sorted(set(s[:4] for s in trade_full['Exit Date']), reverse=True))
            with fc2:
                wl_filter = st.selectbox("Result", ['All', 'Winners', 'Losers'])
            with fc3:
                ticker_filter = st.text_input("Ticker filter", placeholder="e.g. BAJFINANCE")

            ftrades = trade_full.copy()
            if yr_filter != 'All':
                ftrades = ftrades[ftrades['Exit Date'].str.startswith(yr_filter)]
            if wl_filter == 'Winners':
                ftrades = ftrades[ftrades['Return %'] > 0]
            elif wl_filter == 'Losers':
                ftrades = ftrades[ftrades['Return %'] <= 0]
            if ticker_filter:
                ftrades = ftrades[ftrades['Ticker'].str.upper().str.contains(ticker_filter.upper())]

            c1, c2, c3, c4 = st.columns(4)
            visible_wins = ftrades[ftrades['Return %'] > 0]
            visible_loss = ftrades[ftrades['Return %'] <= 0]
            c1.metric("Showing", len(ftrades))
            c2.metric("Win rate", f"{len(visible_wins)/len(ftrades)*100:.1f}%" if len(ftrades) else "—")
            c3.metric("Avg win", f"+{visible_wins['Return %'].mean():.1f}%" if len(visible_wins) else "—")
            c4.metric("Avg loss", f"{visible_loss['Return %'].mean():.1f}%" if len(visible_loss) else "—")

            # Style the table
            def color_return(val):
                if isinstance(val, (int, float)):
                    if val > 0: return 'color: #22d3a0'
                    elif val < 0: return 'color: #f87171'
                return ''

            display_df = ftrades[['Exit Date','Ticker','Entry Date','Entry ₹','Exit ₹','Return %','P&L ₹','Hold Days']].copy()
            st.dataframe(
                display_df,
                use_container_width=True, hide_index=True, height=500,
                column_config={
                    'Return %': st.column_config.NumberColumn(format='%+.2f%%'),
                    'P&L ₹': st.column_config.NumberColumn(format='₹%+,.0f'),
                    'Entry ₹': st.column_config.NumberColumn(format='₹%.2f'),
                    'Exit ₹': st.column_config.NumberColumn(format='₹%.2f'),
                }
            )

            # P&L distribution
            fig4 = go.Figure()
            fig4.add_trace(go.Histogram(
                x=ftrades['Return %'], nbinsx=60,
                marker_color=['#22d3a0' if True else '#f87171'],
                marker=dict(color='#22d3a0', opacity=0.7),
                name='Trade Returns'
            ))
            fig4.add_vline(x=0, line_color='#f87171', line_width=1.5, line_dash='dash')
            fig4.update_layout(
                title='Trade return distribution', height=260,
                plot_bgcolor='#111827', paper_bgcolor='#0a0d13',
                font=dict(color='#94a3b8'), showlegend=False,
                xaxis=dict(showgrid=False, ticksuffix='%'),
                yaxis=dict(showgrid=True, gridcolor='#1f2937'),
                margin=dict(l=10, r=10, t=40, b=10)
            )
            st.plotly_chart(fig4, use_container_width=True)

    # ── 1.4 YEARLY BREAKDOWN ─────────────────────────────────────────────────
    with v4:
        st.subheader("Year-by-year deep dive")

        yr_sel = st.selectbox("Select year", sorted(yr_ret.keys(), reverse=True))
        yr_str = str(yr_sel)
        yr_rebals = [r for r in rebals if r['dt'].startswith(yr_str)]

        if yr_rebals:
            y1, y2, y3, y4 = st.columns(4)
            yr_return = yr_ret.get(int(yr_sel), yr_ret.get(yr_sel, 0))
            y1.metric(f"{yr_sel} Return", f"{yr_return:+.1f}%")
            y2.metric("Rebalances", len(yr_rebals))
            all_sells_yr = [s for r in yr_rebals for s in r['sells']]
            y3.metric("Trades closed", len(all_sells_yr))
            avg_to = sum(r['to'] for r in yr_rebals) / len(yr_rebals)
            y4.metric("Avg turnover", f"{avg_to:.1f}%")

            # Monthly breakdown (rebalance returns)
            fig5 = go.Figure(go.Bar(
                x=[r['dt'][-5:] for r in yr_rebals],
                y=[r['ret'] for r in yr_rebals],
                marker_color=['#22d3a0' if r['ret'] >= 0 else '#f87171' for r in yr_rebals],
                hovertemplate='%{x}<br>Return: %{y:+.2f}%<extra></extra>'
            ))
            fig5.update_layout(
                title=f'{yr_sel} — Fortnightly returns', height=250,
                plot_bgcolor='#111827', paper_bgcolor='#0a0d13',
                font=dict(color='#94a3b8'), showlegend=False,
                yaxis=dict(showgrid=True, gridcolor='#1f2937', ticksuffix='%'),
                xaxis=dict(showgrid=False), margin=dict(l=10, r=10, t=40, b=10)
            )
            st.plotly_chart(fig5, use_container_width=True)

            # Top stocks that appeared in this year
            stock_appearances = {}
            for r in yr_rebals:
                for t in (r['ents'] + r['hlds']):
                    stock_appearances[t] = stock_appearances.get(t, 0) + 1
            top_stocks = sorted(stock_appearances.items(), key=lambda x: x[1], reverse=True)[:15]

            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Most-held stocks in {yr_sel}**")
                for s, cnt in top_stocks:
                    bar_w = int(cnt / len(yr_rebals) * 100)
                    st.markdown(f"""
                    <div style="display:flex;align-items:center;gap:8px;margin:3px 0">
                      <span style="min-width:90px;font-size:13px;font-weight:500">{s}</span>
                      <div style="background:#22d3a0;height:8px;width:{bar_w}%;border-radius:4px;min-width:4px"></div>
                      <span style="font-size:11px;color:#64748b">{cnt}/{len(yr_rebals)} periods</span>
                    </div>""", unsafe_allow_html=True)

            with c2:
                if all_sells_yr:
                    sells_yr_df = pd.DataFrame(all_sells_yr)
                    top_win = sells_yr_df[sells_yr_df['pct'] > 0].nlargest(5, 'pct')
                    top_loss = sells_yr_df[sells_yr_df['pct'] <= 0].nsmallest(5, 'pct')
                    st.markdown(f"**Best trades in {yr_sel}**")
                    for _, row in top_win.iterrows():
                        st.markdown(f"<div class='signal-enter'><strong>{row['t']}</strong> &nbsp; <span style='color:#22d3a0;font-weight:700'>+{row['pct']:.1f}%</span> &nbsp; <span style='font-size:11px;color:#64748b'>₹{row['pnl']:+,.0f}</span></div>", unsafe_allow_html=True)
                    st.markdown(f"**Worst trades in {yr_sel}**")
                    for _, row in top_loss.iterrows():
                        st.markdown(f"<div class='signal-exit'><strong>{row['t']}</strong> &nbsp; <span style='color:#f87171;font-weight:700'>{row['pct']:.1f}%</span> &nbsp; <span style='font-size:11px;color:#64748b'>₹{row['pnl']:+,.0f}</span></div>", unsafe_allow_html=True)

    # ── 1.5 EXPORT ────────────────────────────────────────────────────────────
    with v5:
        st.subheader("Export backtest data")

        # Build full trade CSV
        all_sells_csv = []
        for r in rebals:
            for s in r['sells']:
                all_sells_csv.append({
                    'Rebal_Date': r['dt'], 'Exit_Date': s['xd'], 'Ticker': s['t'],
                    'Entry_Date': s['ed'], 'Entry_Price': s['ep'],
                    'Exit_Price': s['xp'], 'Shares': None, 'Return_Pct': s['pct'],
                    'PnL_Rs': s['pnl'], 'Hold_Days': s['days'],
                    'Portfolio_Value': r['vs']
                })

        trade_csv_df = pd.DataFrame(all_sells_csv)

        rebal_csv = pd.DataFrame([{
            'Rebal_Date': r['dt'], 'Portfolio_Value': r['vs'],
            'Period_Return_Pct': r['ret'], 'Entries': ';'.join(r['ents']),
            'Exits': ';'.join(r['exts']), 'Holdings': ';'.join(r['hlds'] + r['ents']),
            'N_Entries': r['ne'], 'N_Exits': r['nx'], 'Turnover_Pct': r['to']
        } for r in rebals])

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Trade log (1,715 closed trades)**")
            st.markdown("Every closed trade with entry date, exit date, entry price, exit price, P&L")
            csv1 = trade_csv_df.to_csv(index=False)
            st.download_button("⬇️ Download Trade Log CSV", csv1,
                               "n250f_trade_log.csv", "text/csv", use_container_width=True)

        with col2:
            st.markdown("**Rebalance log (258 rebalances)**")
            st.markdown("Every rebalance: date, portfolio value, entries, exits, period return")
            csv2 = rebal_csv.to_csv(index=False)
            st.download_button("⬇️ Download Rebalance Log CSV", csv2,
                               "n250f_rebalance_log.csv", "text/csv", use_container_width=True)

        st.markdown("---")
        # Performance summary
        st.markdown("**Performance summary**")
        summary_data = {
            'Metric': ['CAGR', 'Total Return', 'Final Corpus (₹10L)', 'Max Drawdown', 'Sharpe Ratio',
                       'Volatility', 'Win Rate', 'Avg Win', 'Avg Loss', 'Payoff Ratio',
                       'Total Rebalances', 'Total Trades', 'Total Cost'],
            'Value': [f"{perf['cagr_pct']}%", f"+{perf['total_return_pct']:.0f}%",
                      f"₹{perf['final_corpus']/100000:.1f}L", f"{perf['max_drawdown_pct']:.1f}%",
                      str(perf['sharpe']), f"{perf['volatility_pct']:.1f}%",
                      f"{perf['win_rate_pct']}%", f"+{perf['avg_win_pct']:.2f}%",
                      f"{perf['avg_loss_pct']:.2f}%",
                      f"{abs(perf['avg_win_pct']/perf['avg_loss_pct']):.2f}x",
                      str(perf['total_rebalances']), str(perf['total_trades']),
                      f"₹{perf['total_cost_rs']/1000:.0f}K"],
        }
        summary_df = pd.DataFrame(summary_data)
        csv3 = summary_df.to_csv(index=False)
        st.download_button("⬇️ Download Performance Summary CSV", csv3,
                           "n250f_performance.csv", "text/csv")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: LIVE TRACKER
# ═══════════════════════════════════════════════════════════════════════════════
with sec2_tab:

    # ── NEXT REBALANCE COUNTDOWN ───────────────────────────────────────────────
    next_rebal_dt = datetime.strptime(DATA['next_rebal'], '%Y-%m-%d')
    today         = datetime.now()
    days_to_rebal = (next_rebal_dt - today).days

    r1, r2, r3 = st.columns([1, 2, 1])
    with r2:
        color = '#22d3a0' if days_to_rebal > 3 else '#fbbf24' if days_to_rebal > 0 else '#f87171'
        urgency = "🟢 On Track" if days_to_rebal > 3 else "🟡 Approaching" if days_to_rebal > 0 else "🔴 DUE NOW"
        st.markdown(f"""
        <div class="next-rebal-box" style="border-color:{color}40;background:rgba(0,0,0,0.3)">
          <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px">Next Rebalance Date</div>
          <div class="next-rebal-date" style="color:{color}">{next_rebal_dt.strftime('%d %B %Y')}</div>
          <div style="font-size:14px;color:#94a3b8;margin-top:6px">{urgency} · {max(0,days_to_rebal)} days away</div>
          <div style="font-size:11px;color:#475569;margin-top:6px">Check prices on this date, rank Nifty250 by 3-month return, rebalance top 20</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── CURRENT HOLDINGS ──────────────────────────────────────────────────────
    st.subheader("📌 Current portfolio (as of last rebalance)")

    if curr:
        curr_df = pd.DataFrame(curr)
        curr_df = curr_df.sort_values('unrealised_pct', ascending=False)

        # Summary
        total_invested = sum(h['market_value'] for h in curr)
        total_unreal   = sum(h['unrealised_pnl'] for h in curr)
        winners_count  = sum(1 for h in curr if h['unrealised_pct'] > 0)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total market value", f"₹{total_invested/100000:.2f}L")
        m2.metric("Unrealised P&L", f"₹{total_unreal/1000:.1f}K",
                  delta=f"{total_unreal/total_invested*100:+.1f}%")
        m3.metric("In profit", f"{winners_count}/20")
        m4.metric("Cash balance", f"₹{rebals[-1]['cash'] if 'cash' in rebals[-1] else 'N/A'}")

        # Holdings table
        disp_curr = curr_df[['ticker','entry_date','entry_price','current_price','market_value','unrealised_pnl','unrealised_pct','weight_pct']].copy()
        disp_curr.columns = ['Ticker','Entry Date','Entry ₹','Current ₹','Mkt Value ₹','Unreal P&L ₹','Unreal %','Weight %']
        st.dataframe(
            disp_curr,
            use_container_width=True, hide_index=True, height=380,
            column_config={
                'Entry ₹': st.column_config.NumberColumn(format='₹%.2f'),
                'Current ₹': st.column_config.NumberColumn(format='₹%.2f'),
                'Mkt Value ₹': st.column_config.NumberColumn(format='₹%,.0f'),
                'Unreal P&L ₹': st.column_config.NumberColumn(format='₹%+,.0f'),
                'Unreal %': st.column_config.NumberColumn(format='%+.2f%%'),
                'Weight %': st.column_config.NumberColumn(format='%.1f%%'),
            }
        )

        # Holdings chart
        fig6 = go.Figure(go.Bar(
            x=curr_df['ticker'],
            y=curr_df['unrealised_pct'],
            marker_color=['#22d3a0' if v >= 0 else '#f87171' for v in curr_df['unrealised_pct']],
            hovertemplate='%{x}<br>%{y:+.1f}%<extra></extra>'
        ))
        fig6.add_hline(y=0, line_color='#475569', line_width=1)
        fig6.update_layout(
            title='Current holdings — unrealised return per stock',
            height=250, plot_bgcolor='#111827', paper_bgcolor='#0a0d13',
            font=dict(color='#94a3b8'), showlegend=False,
            yaxis=dict(showgrid=True, gridcolor='#1f2937', ticksuffix='%'),
            xaxis=dict(showgrid=False, tickangle=-30), margin=dict(l=10, r=10, t=40, b=60)
        )
        st.plotly_chart(fig6, use_container_width=True)

    st.markdown("---")

    # ── NEXT REBALANCE SIGNALS ────────────────────────────────────────────────
    st.subheader("🎯 Next rebalance signals (based on current momentum)")
    st.caption("Based on 3-month return rankings as of last data pull. Verify on actual rebalance date.")

    pot_entries = DATA.get('pot_entries', [])
    pot_exits   = DATA.get('pot_exits', [])
    top20       = DATA.get('top20', [])

    sig_col1, sig_col2 = st.columns(2)

    with sig_col1:
        st.markdown("**🟢 Likely ENTRIES** (in top 20 today, not currently held)")
        if pot_entries:
            for e in pot_entries:
                # Find in top20 list
                t20 = next((x for x in top20 if x['ticker'] == e), None)
                if t20:
                    st.markdown(f"""
                    <div class="signal-enter">
                      <strong>{e}</strong> &nbsp;
                      <span style="color:#22d3a0;font-weight:600">Rank #{t20['rank']}</span> &nbsp;
                      <span style="color:#64748b;font-size:12px">3M: +{t20['mom_3m_pct']:.1f}%</span> &nbsp;
                      <span style="color:#94a3b8;font-size:12px">₹{t20['current_price']:,.2f}</span>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='signal-enter'><strong>{e}</strong></div>", unsafe_allow_html=True)
        else:
            st.success("No new entries — current portfolio matches top 20")

    with sig_col2:
        st.markdown("**🔴 Likely EXITS** (currently held, slipped out of top 20)")
        if pot_exits:
            for x in pot_exits:
                h = next((h for h in curr if h['ticker'] == x), None)
                if h:
                    st.markdown(f"""
                    <div class="signal-exit">
                      <strong>{x}</strong> &nbsp;
                      <span style="color:#f87171;font-weight:600">{h['unrealised_pct']:+.1f}% unrealised</span><br>
                      <span style="font-size:12px;color:#64748b">Entry ₹{h['entry_price']:,.2f} · Now ₹{h['current_price']:,.2f}</span>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='signal-exit'><strong>{x}</strong></div>", unsafe_allow_html=True)
        else:
            st.info("No exits flagged yet")

    st.markdown("---")

    # ── TODAY'S FULL TOP 20 RANKING ───────────────────────────────────────────
    st.subheader("📊 Current Nifty250 momentum ranking — Top 20")
    if top20:
        top20_df = pd.DataFrame(top20)
        top20_df['In Portfolio'] = top20_df['ticker'].apply(
            lambda t: '✅ Holding' if t not in [e for e in pot_entries] else '🆕 Enter'
        )
        top20_df.columns = ['Rank', 'Ticker', '3M Return %', 'Price ₹', 'Status']
        st.dataframe(
            top20_df,
            use_container_width=True, hide_index=True, height=360,
            column_config={
                '3M Return %': st.column_config.NumberColumn(format='%+.1f%%'),
                'Price ₹': st.column_config.NumberColumn(format='₹%.2f'),
            }
        )

    # ── REBALANCING SCHEDULE ──────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📅 Upcoming rebalance schedule")
    next_dates = []
    base = next_rebal_dt
    for i in range(6):
        d = base + timedelta(days=14*i)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        next_dates.append({
            'Rebalance #': i+1,
            'Date': d.strftime('%d %b %Y'),
            'Day': d.strftime('%A'),
            'Action': 'DUE NOW ⚡' if i == 0 and days_to_rebal <= 0 else ('Upcoming 🗓️' if i < 3 else 'Future 📆')
        })
    sched_df = pd.DataFrame(next_dates)
    st.dataframe(sched_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── EXECUTION GUIDE ───────────────────────────────────────────────────────
    with st.expander("📋 How to execute the rebalance — Step by step"):
        st.markdown(f"""
        ### On {next_rebal_dt.strftime('%d %B %Y')} (rebalance day):

        **Step 1 — Download rankings**
        - Pull Nifty 250 stock list and their closing prices for the past 63 trading days
        - Rank by 3-month (63-day) price return, highest to lowest
        - Take top 20 stocks

        **Step 2 — Identify changes**
        - Stocks in top 20 but NOT in your portfolio → **BUY**
        - Stocks in your portfolio but NOT in top 20 → **SELL**
        - Stocks in both → **HOLD** (rebalance to equal weight if significantly off)

        **Step 3 — Execute trades**
        - Use market orders at market open (9:15 AM IST) or limit orders near open
        - Target: equal weight = approximately {round(100/20, 1)}% each
        - Use Zerodha/Groww for zero brokerage on delivery trades
        - Cost budget: ~0.1% on each trade (brokerage + minor slippage)

        **Step 4 — Tax note**
        - Stocks held < 12 months → STCG at 15%
        - Stocks held > 12 months → LTCG at 10% (above ₹1.25L annual threshold)
        - Consider timing exits near the 12-month anniversary for LTCG benefit

        **Step 5 — Record keeping**
        - Log each trade: date, ticker, buy/sell, price, quantity
        - AlphaRadar N250F tab auto-tracks all historical data
        """)

# ── DISCLAIMER ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="disclaimer">
⚠️ <strong>BACKTEST DISCLAIMER:</strong> All results shown are from a backtest on real yfinance data for a proxy universe of 183 NSE stocks (2015–2025). 
This is NOT a real trading account. Backtest results have inherent limitations: (1) Static universe — actual Nifty250 constituent changes not fully replicated; 
(2) Survivorship bias — some delisted stocks absent from universe; (3) Slippage beyond 0.1% not modelled, especially for mid-cap stocks during rebalances; 
(4) Tax impact (STCG/LTCG) not included in CAGR figures; (5) Past performance does not guarantee future results.
Real-world CAGR after tax and realistic slippage: approximately 20–24%. This tool is for educational research only. Not SEBI investment advice.
</div>
""", unsafe_allow_html=True)
