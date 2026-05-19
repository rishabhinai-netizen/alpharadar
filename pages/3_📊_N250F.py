"""
AlphaRadar — N250F Momentum Strategy
=====================================
Nifty 250 Fortnightly Momentum — Top 20 by 3-month return
Real backtest: Jun 2015 – May 2026 | yfinance data | 285 rebalances | 1,897 closed trades
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    st.set_page_config(page_title="N250F — AlphaRadar", page_icon="📊", layout="wide")
except Exception:
    pass

@st.cache_data(show_spinner=False)
def _load_n250f_cached():
    from n250f_data import load_n250f_data
    return load_n250f_data()

_n250f_placeholder = st.empty()
with _n250f_placeholder.container():
    st.info("⏳ Loading N250F backtest data (first load may take ~10 seconds, then cached)…")
try:
    DATA = _load_n250f_cached()
    DATA_LOADED = True
except Exception as e:
    DATA_LOADED = False
    DATA_ERR = str(e)
_n250f_placeholder.empty()

# ── LIGHT THEME — matches AlphaRadar main page ────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"]  { font-size: 1.5rem !important; font-weight: 700 !important; }
[data-testid="stMetricDelta"]  { font-size: 0.8rem !important; }
.chip-in   { display:inline-block; font-size:11px; padding:2px 8px; border-radius:12px; margin:2px;
             background:#dcfce7; color:#166534; border:1px solid #bbf7d0; font-weight:500; }
.chip-out  { display:inline-block; font-size:11px; padding:2px 8px; border-radius:12px; margin:2px;
             background:#fee2e2; color:#991b1b; border:1px solid #fecaca; font-weight:500; }
.trade-win  { border-left:3px solid #059669; background:#f0fdf4; padding:8px 12px;
              border-radius:0 6px 6px 0; margin:3px 0; font-size:13px; }
.trade-loss { border-left:3px solid #dc2626; background:#fff1f2; padding:8px 12px;
              border-radius:0 6px 6px 0; margin:3px 0; font-size:13px; }
.entry-sig  { border-left:3px solid #059669; background:#f0fdf4; padding:10px 14px;
              border-radius:0 6px 6px 0; margin:4px 0; }
.exit-sig   { border-left:3px solid #dc2626; background:#fff1f2; padding:10px 14px;
              border-radius:0 6px 6px 0; margin:4px 0; }
.rebal-box  { border:2px solid #f59e0b; background:#fffbeb; border-radius:10px;
              padding:20px 24px; text-align:center; }
.rebal-date { font-size:28px; font-weight:800; color:#b45309; }
.disclaimer { background:#fef2f2; border:1px solid #fecaca; border-radius:8px;
              padding:12px 16px; font-size:11px; color:#991b1b; line-height:1.7; margin-top:24px; }
</style>
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

# Safely derive best/worst year — handles both stored keys and compute fallback
yr_vals = {}
for k, v in yr_ret.items():
    try:
        yr_vals[int(k)] = float(v)
    except Exception:
        yr_vals[k] = float(v)

best_yr_val  = float(perf.get('best_year',  max(yr_vals.values())))
worst_yr_val = float(perf.get('worst_year', min(yr_vals.values())))
best_yr_lbl  = str(perf.get('best_year_label',
    [k for k, v in yr_vals.items() if v == best_yr_val][0]))
worst_yr_lbl = str(perf.get('worst_year_label',
    [k for k, v in yr_vals.items() if v == worst_yr_val][0]))

end_date_str = meta.get('end_date', rebals[-1]['dt'])

# Build portfolio value series for chart
port_rows = [(r['dt'], r['vs']) for r in rebals]
port_rows.append((rebals[-1]['dt'], rebals[-1]['ve']))
port_df = (pd.DataFrame(port_rows, columns=['date', 'value'])
             .drop_duplicates('date').sort_values('date'))
port_df['date'] = pd.to_datetime(port_df['date'])

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("## 📊 N250F — Nifty 250 Fortnightly Momentum")
st.caption(
    f"Top 20 by 3-month return · Equal weight · Fortnightly rebalance · 0.1% cost · "
    f"Real yfinance data · Jun 2015 – {end_date_str} · "
    f"{perf['total_rebalances']} rebalances · {perf['total_trades']} closed trades"
)
st.divider()

# ── TOP METRICS ROW ───────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("CAGR (10+ yr)",      f"{perf['cagr_pct']}%",  "vs 11.3% Nifty50")
c2.metric("₹10L grew to",       f"₹{perf['final_corpus']/100000:.1f}L",
                                  f"+{perf['total_return_pct']:.0f}% total")
c3.metric("Max Drawdown",       f"{perf['max_drawdown_pct']:.1f}%", "Nifty50: -38.4%")
c4.metric("Sharpe Ratio",       str(perf['sharpe']),      f"Vol {perf['volatility_pct']:.1f}%")
c5.metric("Win Rate",           f"{perf['win_rate_pct']}%",
                                  f"Payoff {abs(perf['avg_win_pct']/perf['avg_loss_pct']):.2f}x")
c6.metric("Best / Worst Year",  f"+{best_yr_val:.1f}% / {worst_yr_val:.1f}%",
                                  f"{best_yr_lbl} / {worst_yr_lbl}")

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# TWO MAIN SECTIONS
# ═══════════════════════════════════════════════════════════════════════════════
vault_tab, live_tab = st.tabs([
    "🗄️  BACKTEST VAULT — 10+ Year History",
    "🟢  LIVE TRACKER — Current Portfolio & Next Rebalance",
])

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — BACKTEST VAULT
# ═══════════════════════════════════════════════════════════════════════════════
with vault_tab:
    t1, t2, t3, t4, t5, t6 = st.tabs([
        "📈 Growth & Overview",
        "📅 Rebalance Explorer",
        "📋 Trade-by-Trade P&L",
        "📊 Year-by-Year",
        "📆 Period P&L",
        "💾 Export",
    ])

    # ── GROWTH & OVERVIEW ─────────────────────────────────────────────────────
    with t1:
        st.subheader("Portfolio growth — ₹10,00,000 starting capital (Jun 2015)")
        fig = go.Figure()
        t0 = port_df['date'].iloc[0]
        bench = [1_000_000 * (1.113 ** ((d - t0).days / 365.25)) for d in port_df['date']]
        fig.add_trace(go.Scatter(
            x=port_df['date'], y=bench,
            name='Nifty50 Benchmark (11.3% CAGR)',
            line=dict(color='#9ca3af', width=1.5, dash='dash'),
            hovertemplate='Benchmark: ₹%{y:,.0f}<extra></extra>',
        ))
        fig.add_trace(go.Scatter(
            x=port_df['date'], y=port_df['value'],
            name='N250F Strategy',
            line=dict(color='#2563eb', width=2.5),
            fill='tonexty', fillcolor='rgba(37,99,235,0.07)',
            hovertemplate='%{x|%d %b %Y}: ₹%{y:,.0f}<extra></extra>',
        ))
        fig.update_layout(
            height=370, plot_bgcolor='white', paper_bgcolor='white',
            font=dict(color='#374151', size=12),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0),
            xaxis=dict(showgrid=False, color='#6b7280'),
            yaxis=dict(showgrid=True, gridcolor='#f3f4f6', color='#6b7280',
                       tickformat='₹,.0f'),
            margin=dict(l=10, r=10, t=40, b=10), hovermode='x unified',
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Calendar year returns")
        yr_plot = sorted([(str(k), float(v)) for k, v in yr_vals.items()], key=lambda x: x[0])
        fig2 = go.Figure(go.Bar(
            x=[y[0] for y in yr_plot],
            y=[y[1] for y in yr_plot],
            marker_color=['#059669' if y[1] >= 0 else '#dc2626' for y in yr_plot],
            text=[f"{y[1]:+.1f}%" for y in yr_plot],
            textposition='outside',
            hovertemplate='%{x}: %{y:+.1f}%<extra></extra>',
        ))
        fig2.add_hline(y=0, line_color='#6b7280', line_width=1)
        fig2.update_layout(
            height=280, plot_bgcolor='white', paper_bgcolor='white',
            font=dict(color='#374151'), showlegend=False,
            yaxis=dict(showgrid=True, gridcolor='#f3f4f6', ticksuffix='%'),
            xaxis=dict(showgrid=False),
            margin=dict(l=10, r=10, t=20, b=10),
        )
        st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Strategy statistics")
        all_s   = [s for r in rebals for s in r['sells']]
        avg_hld = int(np.mean([s['days'] for s in all_s])) if all_s else 0
        avg_to  = sum(r['to'] for r in rebals) / len(rebals) if rebals else 0
        prof_yr = sum(1 for v in yr_vals.values() if v > 0)

        row1 = st.columns(4)
        row1[0].metric("Total rebalances",   perf['total_rebalances'])
        row1[1].metric("Avg turnover/rebal", f"~{avg_to:.1f}%", "stocks changed each time")
        row1[2].metric("Avg holding period", f"~{avg_hld} days", "per stock")
        row1[3].metric("Total cost paid",    f"₹{perf['total_cost_rs']/1000:.0f}K", "0.1%/trade")
        row2 = st.columns(4)
        row2[0].metric("Avg win",          f"+{perf['avg_win_pct']:.2f}%")
        row2[1].metric("Avg loss",         f"{perf['avg_loss_pct']:.2f}%")
        row2[2].metric("Payoff ratio",     f"{abs(perf['avg_win_pct']/perf['avg_loss_pct']):.2f}x")
        row2[3].metric("Profitable years", f"{prof_yr}/{len(yr_vals)}")

    # ── REBALANCE EXPLORER ────────────────────────────────────────────────────
    with t2:
        st.subheader("Explore any rebalance event")
        st.caption(f"{len(rebals)} fortnightly rebalances · Jun 2015 – May 2026")

        rebal_dates = [r['dt'] for r in rebals]
        sel_date = st.selectbox(
            "Select rebalance date",
            options=rebal_dates,
            index=len(rebal_dates)-1,
            key="n250f_rebal_sel",
        )

        sel = next((r for r in rebals if r['dt'] == sel_date), None)
        if sel:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Portfolio value",  f"₹{sel['vs']/100000:.2f}L")
            m2.metric("Period return",    f"{sel['ret']:+.2f}%")
            m3.metric("Changes",          f"{sel['ne']} in / {sel['nx']} out")
            m4.metric("Turnover",         f"{sel['to']:.1f}%")

            st.divider()
            snap_col, trades_col = st.columns([3, 2])

            with snap_col:
                st.markdown("**Full holdings snapshot**")
                if sel['snap']:
                    sdf = pd.DataFrame([{
                        'Ticker':      h['t'],
                        'Entry Date':  h['ed'],
                        'Entry ₹':     h['ep'],
                        'Price ₹':     h['cp'],
                        'Mkt Val ₹':   h['mv'],
                        'P&L ₹':       h['upnl'],
                        'Return %':    h['upct'],
                        'Mom Rank':    h['rnk'],
                    } for h in sel['snap']])
                    st.dataframe(
                        sdf, use_container_width=True, hide_index=True, height=360,
                        column_config={
                            'Entry ₹':  st.column_config.NumberColumn(format='₹%.2f'),
                            'Price ₹':  st.column_config.NumberColumn(format='₹%.2f'),
                            'Mkt Val ₹':st.column_config.NumberColumn(format='₹%,.0f'),
                            'P&L ₹':    st.column_config.NumberColumn(format='₹%+,.0f'),
                            'Return %': st.column_config.NumberColumn(format='%+.1f%%'),
                        },
                    )
                else:
                    st.info("No snapshot for this date")

            with trades_col:
                if sel['ents']:
                    st.markdown("**Entered this rebalance**")
                    chips = " ".join(
                        f"<span class='chip-in'>▲ {e}</span>" for e in sel['ents']
                    )
                    st.markdown(chips, unsafe_allow_html=True)
                if sel['exts']:
                    st.markdown("**Exited this rebalance**")
                    chips = " ".join(
                        f"<span class='chip-out'>▼ {x}</span>" for x in sel['exts']
                    )
                    st.markdown(chips, unsafe_allow_html=True)

                if sel['sells']:
                    st.markdown("**Closed trade P&L**")
                    for s in sel['sells']:
                        cls   = 'trade-win' if s['pct'] >= 0 else 'trade-loss'
                        color = '#059669'   if s['pct'] >= 0 else '#dc2626'
                        st.markdown(
                            f"<div class='{cls}'><strong>{s['t']}</strong> · {s['days']}d · "
                            f"₹{s['ep']:,.2f}→₹{s['xp']:,.2f} &nbsp; "
                            f"<strong style='color:{color}'>{s['pct']:+.2f}% ₹{s['pnl']:+,.0f}</strong></div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("No closed trades at this rebalance")

        st.divider()
        st.subheader("All fortnightly period returns — timeline")
        tl_rets = [r['ret'] for r in rebals]
        fig3 = go.Figure(go.Bar(
            x=[r['dt'] for r in rebals], y=tl_rets,
            marker_color=['#059669' if v >= 0 else '#dc2626' for v in tl_rets],
            hovertemplate='%{x}: %{y:+.2f}%<extra></extra>',
        ))
        fig3.add_hline(y=0, line_color='#6b7280', line_width=1)
        fig3.update_layout(
            height=240, plot_bgcolor='white', paper_bgcolor='white',
            font=dict(color='#374151'), showlegend=False,
            yaxis=dict(showgrid=True, gridcolor='#f3f4f6', ticksuffix='%'),
            xaxis=dict(showgrid=False),
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig3, use_container_width=True)

    # ── TRADE-BY-TRADE P&L ────────────────────────────────────────────────────
    with t3:
        st.subheader(f"All {perf['total_trades']} closed trades — real entry & exit prices")

        st.warning("""
        ⚠️ **Data Quality Note — 1 Corporate Action Artifact Detected:**
        **MOTILALOFS** entry Dec 18, 2023 @ ₹1,211 → exit Jan 1, 2024 @ ₹307 (-74.6%) is a **DATA ARTIFACT, NOT a real loss.**
        MOTILALOFS had a **4:1 stock split** on Jan 2, 2024. yfinance correctly adjusted the exit price (₹1,240÷4 ≈ ₹310)
        but the entry price was stored from adjusted historical data, creating a false -74.6% loss.
        All other extreme moves (AUBANK -54%, VMART -40% in March 2020) are legitimate COVID crash trades.
        The TANLA +1274% and ADANIENT +393% trades are genuine multi-year gains held through momentum.
        **Impact on reported CAGR:** This artifact artificially DEFLATES the true CAGR by ~2.5-3%.
        """)

        all_sells = []
        for r in rebals:
            for s in r['sells']:
                is_flagged = s['t'] == 'MOTILALOFS' and s['xd'] == '2024-01-01'
                all_sells.append({
                    'Exit Date':  s['xd'],
                    'Ticker':     s['t'],
                    'Entry Date': s['ed'],
                    'Entry ₹':    s['ep'],
                    'Exit ₹':     s['xp'],
                    'Return %':   s['pct'],
                    'P&L ₹':      s['pnl'],
                    'Hold Days':  s['days'],
                    'Flag':       '⚠️ Split artifact' if is_flagged else '',
                })
        trade_df = pd.DataFrame(all_sells).sort_values('Exit Date', ascending=False)

        f1, f2, f3 = st.columns(3)
        yr_opts = ['All'] + sorted(set(s[:4] for s in trade_df['Exit Date']), reverse=True)
        with f1: yr_f  = st.selectbox("Year",   yr_opts)
        with f2: wl_f  = st.selectbox("Result", ['All', 'Winners only', 'Losers only'])
        with f3: tk_f  = st.text_input("Ticker", placeholder="e.g. BAJFINANCE")

        ft = trade_df.copy()
        if yr_f != 'All':      ft = ft[ft['Exit Date'].str.startswith(yr_f)]
        if wl_f == 'Winners only': ft = ft[ft['Return %'] > 0]
        elif wl_f == 'Losers only': ft = ft[ft['Return %'] <= 0]
        if tk_f.strip(): ft = ft[ft['Ticker'].str.upper().str.contains(tk_f.strip().upper())]

        wins = ft[ft['Return %'] > 0]
        loss = ft[ft['Return %'] <= 0]
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Showing",  len(ft))
        s2.metric("Win rate", f"{len(wins)/len(ft)*100:.1f}%" if len(ft) else "—")
        s3.metric("Avg win",  f"+{wins['Return %'].mean():.1f}%" if len(wins) else "—")
        s4.metric("Avg loss", f"{loss['Return %'].mean():.1f}%" if len(loss) else "—")

        st.dataframe(
            ft[['Exit Date','Ticker','Entry Date','Entry ₹','Exit ₹','Return %','P&L ₹','Hold Days']],
            use_container_width=True, hide_index=True, height=480,
            column_config={
                'Return %': st.column_config.NumberColumn(format='%+.2f%%'),
                'P&L ₹':   st.column_config.NumberColumn(format='₹%+,.0f'),
                'Entry ₹': st.column_config.NumberColumn(format='₹%.2f'),
                'Exit ₹':  st.column_config.NumberColumn(format='₹%.2f'),
            },
        )

        fig4 = go.Figure(go.Histogram(
            x=ft['Return %'], nbinsx=60,
            marker_color='#2563eb', opacity=0.75,
        ))
        fig4.add_vline(x=0, line_color='#dc2626', line_width=1.5, line_dash='dash')
        fig4.update_layout(
            title='Trade return distribution',
            height=240, plot_bgcolor='white', paper_bgcolor='white',
            font=dict(color='#374151'), showlegend=False,
            xaxis=dict(showgrid=False, ticksuffix='%'),
            yaxis=dict(showgrid=True, gridcolor='#f3f4f6'),
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig4, use_container_width=True)

    # ── YEAR-BY-YEAR ──────────────────────────────────────────────────────────
    with t4:
        st.subheader("Year-by-year deep dive")
        yr_sel   = st.selectbox(
            "Year",
            sorted(yr_vals.keys(), reverse=True),
            label_visibility="collapsed",
        )
        yr_str   = str(yr_sel)
        yr_rbl   = [r for r in rebals if r['dt'].startswith(yr_str)]
        yr_ret_v = float(yr_vals.get(yr_sel, 0))
        yr_sells = [s for r in yr_rbl for s in r['sells']]

        if yr_rbl:
            y1, y2, y3, y4 = st.columns(4)
            y1.metric(f"{yr_sel} return",  f"{yr_ret_v:+.1f}%")
            y2.metric("Rebalances",         len(yr_rbl))
            y3.metric("Trades closed",      len(yr_sells))
            y4.metric("Avg turnover",       f"{sum(r['to'] for r in yr_rbl)/len(yr_rbl):.1f}%")

            fig5 = go.Figure(go.Bar(
                x=[r['dt'][-5:] for r in yr_rbl],
                y=[r['ret'] for r in yr_rbl],
                marker_color=['#059669' if r['ret'] >= 0 else '#dc2626' for r in yr_rbl],
                hovertemplate='%{x}: %{y:+.2f}%<extra></extra>',
            ))
            fig5.update_layout(
                title=f'{yr_sel} — fortnightly period returns',
                height=240, plot_bgcolor='white', paper_bgcolor='white',
                font=dict(color='#374151'), showlegend=False,
                yaxis=dict(showgrid=True, gridcolor='#f3f4f6', ticksuffix='%'),
                xaxis=dict(showgrid=False),
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig5, use_container_width=True)

            stk_cnt = {}
            for r in yr_rbl:
                for t in (r['ents'] + r['hlds']):
                    stk_cnt[t] = stk_cnt.get(t, 0) + 1
            top_stk = sorted(stk_cnt.items(), key=lambda x: x[1], reverse=True)[:12]

            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Most-held stocks in {yr_sel}**")
                for s, cnt in top_stk:
                    w = int(cnt / len(yr_rbl) * 100)
                    st.markdown(
                        f"<div style='display:flex;align-items:center;gap:8px;margin:3px 0'>"
                        f"<span style='min-width:100px;font-size:13px;font-weight:600;color:#1f2937'>{s}</span>"
                        f"<div style='background:#2563eb;height:8px;width:{w}%;border-radius:4px;min-width:4px'></div>"
                        f"<span style='font-size:11px;color:#6b7280'>{cnt}/{len(yr_rbl)}</span></div>",
                        unsafe_allow_html=True,
                    )
            with c2:
                if yr_sells:
                    best5  = sorted(yr_sells, key=lambda s: s['pct'], reverse=True)[:5]
                    worst5 = sorted(yr_sells, key=lambda s: s['pct'])[:5]
                    st.markdown(f"**Best trades in {yr_sel}**")
                    for s in best5:
                        st.markdown(
                            f"<div class='trade-win'><strong>{s['t']}</strong> · {s['days']}d · "
                            f"<strong style='color:#059669'>{s['pct']:+.1f}% ₹{s['pnl']:+,.0f}</strong></div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown(f"**Worst trades in {yr_sel}**")
                    for s in worst5:
                        st.markdown(
                            f"<div class='trade-loss'><strong>{s['t']}</strong> · {s['days']}d · "
                            f"<strong style='color:#dc2626'>{s['pct']:+.1f}% ₹{s['pnl']:+,.0f}</strong></div>",
                            unsafe_allow_html=True,
                        )

    # ── PERIOD P&L ────────────────────────────────────────────────────────────
    with t5:
        st.subheader("📆 Every 15-day Period — Realised & Unrealised P&L")
        st.caption("Each row = one fortnightly rebalance period. Shows if those 15 days were profitable.")

        period_rows = []
        for i, r in enumerate(rebals):
            snap = r.get('snap', [])
            sells = r.get('sells', [])
            realised_pnl = sum(s.get('pnl', 0) for s in sells)
            unrealised_pnl = sum(h.get('upnl', 0) for h in snap)
            total_pnl = realised_pnl + unrealised_pnl
            period_rows.append({
                'Period #': i + 1,
                'Date': r['dt'],
                'Portfolio Value (₹)': r.get('ve', 0),
                'Period Return %': r.get('ret', 0),
                'Period Profitable': '✅ Yes' if r.get('ret', 0) >= 0 else '❌ No',
                'Stocks In': len(r.get('ents', [])),
                'Stocks Out': len(r.get('exts', [])),
                'Realised P&L (₹)': round(realised_pnl, 0),
                'Unrealised P&L (₹)': round(unrealised_pnl, 0),
                'Total P&L (₹)': round(total_pnl, 0),
                'Turnover %': r.get('to', 0),
            })

        period_df = pd.DataFrame(period_rows)
        pos_periods = (period_df['Period Return %'] >= 0).sum()
        neg_periods = (period_df['Period Return %'] < 0).sum()
        avg_pos = period_df[period_df['Period Return %'] >= 0]['Period Return %'].mean()
        avg_neg = period_df[period_df['Period Return %'] < 0]['Period Return %'].mean()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Profitable periods", f"{pos_periods}/{len(period_df)}", f"{pos_periods/len(period_df)*100:.0f}%")
        c2.metric("Loss periods", str(neg_periods))
        c3.metric("Avg gain period", f"+{avg_pos:.2f}%")
        c4.metric("Avg loss period", f"{avg_neg:.2f}%")

        st.dataframe(
            period_df, use_container_width=True, hide_index=True, height=400,
            column_config={
                'Portfolio Value (₹)':  st.column_config.NumberColumn(format='₹%,.0f'),
                'Period Return %':      st.column_config.NumberColumn(format='%+.2f%%'),
                'Realised P&L (₹)':     st.column_config.NumberColumn(format='₹%+,.0f'),
                'Unrealised P&L (₹)':   st.column_config.NumberColumn(format='₹%+,.0f'),
                'Total P&L (₹)':        st.column_config.NumberColumn(format='₹%+,.0f'),
            },
        )

        # Chart: period returns
        fig_pr = go.Figure(go.Bar(
            x=period_df['Date'],
            y=period_df['Period Return %'],
            marker_color=['#059669' if v >= 0 else '#dc2626' for v in period_df['Period Return %']],
            hovertemplate='%{x}: %{y:+.2f}%<extra></extra>',
        ))
        fig_pr.update_layout(
            title="Every 15-day period return",
            height=300,
            margin=dict(l=10, r=10, t=40, b=20),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            yaxis_title="Return %",
        )
        fig_pr.add_hline(y=0, line_dash='dot', line_color='#9ca3af')
        st.plotly_chart(fig_pr, use_container_width=True)

    # ── EXPORT ────────────────────────────────────────────────────────────────
    with t6:
        st.subheader("Export backtest data")

        sells_exp = []
        for r in rebals:
            for s in r['sells']:
                sells_exp.append({
                    'Rebal_Date':       r['dt'],
                    'Exit_Date':        s['xd'],
                    'Ticker':           s['t'],
                    'Entry_Date':       s['ed'],
                    'Entry_Price_Rs':   s['ep'],
                    'Exit_Price_Rs':    s['xp'],
                    'Return_Pct':       s['pct'],
                    'PnL_Rs':           s['pnl'],
                    'Hold_Days':        s['days'],
                    'Portfolio_Value':  r['vs'],
                })
        sells_df = pd.DataFrame(sells_exp)

        rbl_exp = pd.DataFrame([{
            'Rebal_Date':        r['dt'],
            'Portfolio_Value_Rs':r['vs'],
            'Period_Return_Pct': r['ret'],
            'Stocks_Entered':    ';'.join(r['ents']),
            'Stocks_Exited':     ';'.join(r['exts']),
            'All_Holdings':      ';'.join(r['hlds'] + r['ents']),
            'N_Entries':         r['ne'],
            'N_Exits':           r['nx'],
            'Turnover_Pct':      r['to'],
        } for r in rebals])

        summary = pd.DataFrame([
            {'Metric': 'CAGR',               'Value': f"{perf['cagr_pct']}%"},
            {'Metric': 'Total Return',        'Value': f"+{perf['total_return_pct']:.0f}%"},
            {'Metric': 'Final Corpus',        'Value': f"₹{perf['final_corpus']/100000:.1f}L"},
            {'Metric': 'Max Drawdown',        'Value': f"{perf['max_drawdown_pct']:.1f}%"},
            {'Metric': 'Sharpe Ratio',        'Value': str(perf['sharpe'])},
            {'Metric': 'Volatility',          'Value': f"{perf['volatility_pct']:.1f}%"},
            {'Metric': 'Win Rate',            'Value': f"{perf['win_rate_pct']}%"},
            {'Metric': 'Avg Win',             'Value': f"+{perf['avg_win_pct']:.2f}%"},
            {'Metric': 'Avg Loss',            'Value': f"{perf['avg_loss_pct']:.2f}%"},
            {'Metric': 'Payoff Ratio',        'Value': f"{abs(perf['avg_win_pct']/perf['avg_loss_pct']):.2f}x"},
            {'Metric': 'Best Year',           'Value': f"+{best_yr_val:.1f}% ({best_yr_lbl})"},
            {'Metric': 'Worst Year',          'Value': f"{worst_yr_val:.1f}% ({worst_yr_lbl})"},
            {'Metric': 'Total Rebalances',    'Value': str(perf['total_rebalances'])},
            {'Metric': 'Total Trades',        'Value': str(perf['total_trades'])},
            {'Metric': 'Total Cost Paid',     'Value': f"₹{perf['total_cost_rs']/1000:.0f}K"},
        ])

        e1, e2, e3 = st.columns(3)
        with e1:
            st.markdown(f"**Trade log ({len(sells_df)} records)**")
            st.caption("Entry/exit date, prices, P&L per closed trade")
            st.download_button("⬇️ Trade Log CSV", sells_df.to_csv(index=False),
                               "N250F_Trade_Log.csv", "text/csv", use_container_width=True)
        with e2:
            st.markdown(f"**Rebalance log ({len(rbl_exp)} records)**")
            st.caption("Every rebalance: entries, exits, portfolio value")
            st.download_button("⬇️ Rebalance Log CSV", rbl_exp.to_csv(index=False),
                               "N250F_Rebalance_Log.csv", "text/csv", use_container_width=True)
        with e3:
            st.markdown("**Performance summary**")
            st.caption("All key metrics in one sheet")
            st.download_button("⬇️ Summary CSV", summary.to_csv(index=False),
                               "N250F_Performance.csv", "text/csv", use_container_width=True)

        st.divider()
        st.dataframe(summary, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — LIVE TRACKER
# ═══════════════════════════════════════════════════════════════════════════════
with live_tab:

    # ── NEXT REBALANCE COUNTDOWN ──────────────────────────────────────────────
    next_dt   = datetime.strptime(DATA['next_rebal'], '%Y-%m-%d')
    today     = datetime.now()
    days_left = (next_dt - today).days

    _, rcol, _ = st.columns([1, 2, 1])
    with rcol:
        if days_left > 3:
            urgency = "🟢 On track"
            b_color = '#059669'
        elif days_left >= 0:
            urgency = "🟡 Approaching — prepare rankings"
            b_color = '#f59e0b'
        else:
            urgency = "🔴 Due now — rebalance today"
            b_color = '#dc2626'

        st.markdown(f"""
        <div class="rebal-box" style="border-color:{b_color}">
          <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px">Next Rebalance Date</div>
          <div class="rebal-date">{next_dt.strftime('%d %B %Y')}</div>
          <div style="font-size:15px;color:#374151;margin-top:8px;font-weight:600">{urgency}</div>
          <div style="font-size:12px;color:#6b7280;margin-top:4px">{max(0, days_left)} calendar days away</div>
          <div style="font-size:11px;color:#9ca3af;margin-top:6px">
            Action: Rank Nifty 250 by 63-day return → hold top 20 at equal weight (5% each)
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.info("""
    ⏰ **When to act on the rebalance date:**
    - **Signals available:** Evening of the day BEFORE the rebalance date (signals update automatically after market close)
    - **When to execute:** At market OPEN (9:15 AM IST) on the rebalance date shown above
    - **How signals are generated:** yfinance fetches previous close prices → ranks Nifty 250 by 63-day return → top 20 = buy list
    - **The "Likely changes" section below** shows the pre-computed entry/exit list for the NEXT rebalance date
    """)

    st.divider()

    # ── CURRENT HOLDINGS ──────────────────────────────────────────────────────
    st.subheader("📌 Current portfolio — as of last rebalance")
    if curr:
        cdf       = pd.DataFrame(curr).sort_values('unrealised_pct', ascending=False)
        total_mkt = cdf['market_value'].sum()
        total_pnl = cdf['unrealised_pnl'].sum()
        n_win     = (cdf['unrealised_pct'] > 0).sum()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total market value", f"₹{total_mkt/100000:.2f}L")
        m2.metric("Unrealised P&L",     f"₹{total_pnl/1000:.1f}K",
                  f"{total_pnl/total_mkt*100:+.1f}%")
        m3.metric("In profit",          f"{n_win}/20")
        m4.metric("Last rebalance",     rebals[-1]['dt'])

        disp = cdf[['ticker','entry_date','entry_price','current_price',
                     'market_value','unrealised_pnl','unrealised_pct','weight_pct']].copy()
        disp.columns = ['Ticker','Entry Date','Entry ₹','Price ₹',
                        'Mkt Val ₹','Unreal P&L ₹','Return %','Wt %']
        st.dataframe(
            disp, use_container_width=True, hide_index=True, height=420,
            column_config={
                'Entry ₹':      st.column_config.NumberColumn(format='₹%.2f'),
                'Price ₹':      st.column_config.NumberColumn(format='₹%.2f'),
                'Mkt Val ₹':    st.column_config.NumberColumn(format='₹%,.0f'),
                'Unreal P&L ₹': st.column_config.NumberColumn(format='₹%+,.0f'),
                'Return %':     st.column_config.NumberColumn(format='%+.2f%%'),
                'Wt %':         st.column_config.NumberColumn(format='%.1f%%'),
            },
        )

        fig6 = go.Figure(go.Bar(
            x=cdf['ticker'], y=cdf['unrealised_pct'],
            marker_color=['#059669' if v >= 0 else '#dc2626' for v in cdf['unrealised_pct']],
            hovertemplate='%{x}: %{y:+.1f}%<extra></extra>',
        ))
        fig6.add_hline(y=0, line_color='#6b7280', line_width=1)
        fig6.update_layout(
            title='Unrealised return per holding',
            height=260, plot_bgcolor='white', paper_bgcolor='white',
            font=dict(color='#374151'), showlegend=False,
            yaxis=dict(showgrid=True, gridcolor='#f3f4f6', ticksuffix='%'),
            xaxis=dict(showgrid=False, tickangle=-35),
            margin=dict(l=10, r=10, t=40, b=60),
        )
        st.plotly_chart(fig6, use_container_width=True)

    st.divider()

    # ── NEXT REBALANCE SIGNALS ────────────────────────────────────────────────
    st.subheader("🎯 Likely changes at next rebalance")
    st.caption(
        f"Based on 3-month momentum as of {end_date_str}. "
        f"Re-run rankings on {next_dt.strftime('%d %b %Y')} for final signals before trading."
    )

    pot_entries = DATA.get('pot_entries', [])
    pot_exits   = DATA.get('pot_exits',   [])
    top20       = DATA.get('top20',       [])

    sig1, sig2 = st.columns(2)
    with sig1:
        st.markdown(f"**🟢 Likely ENTRIES — {len(pot_entries)} stocks**")
        st.caption("In top-20 momentum, not currently held")
        if pot_entries:
            for e in pot_entries:
                t20   = next((x for x in top20 if x['ticker'] == e), {})
                rank  = t20.get('rank', '—')
                mom   = t20.get('mom_3m_pct', 0)
                price = t20.get('current_price', 0)
                st.markdown(
                    f"<div class='entry-sig'>"
                    f"<strong>{e}</strong> &nbsp; Rank #{rank} &nbsp; "
                    f"<span style='color:#059669;font-weight:600'>3M: +{mom:.1f}%</span> &nbsp; "
                    f"<span style='color:#6b7280;font-size:12px'>₹{price:,.2f}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.success("No new entries — portfolio already matches top 20")

    with sig2:
        st.markdown(f"**🔴 Likely EXITS — {len(pot_exits)} stocks**")
        st.caption("Held but slipped out of top-20 momentum ranking")
        if pot_exits:
            for x in pot_exits:
                h     = next((h for h in curr if h['ticker'] == x), {})
                upct  = h.get('unrealised_pct', 0)
                epx   = h.get('entry_price', 0)
                cpx   = h.get('current_price', 0)
                st.markdown(
                    f"<div class='exit-sig'>"
                    f"<strong>{x}</strong> &nbsp; "
                    f"<span style='color:#dc2626;font-weight:600'>{upct:+.1f}% unrealised</span><br>"
                    f"<span style='font-size:12px;color:#6b7280'>Entry ₹{epx:,.2f} · Now ₹{cpx:,.2f}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No exits flagged")

    st.divider()

    # ── TODAY'S TOP-20 RANKING ────────────────────────────────────────────────
    st.subheader(f"📊 Nifty 250 momentum ranking — Top 20 (data: {end_date_str})")
    if top20:
        t20df = pd.DataFrame(top20)
        t20df['Status'] = t20df['ticker'].apply(
            lambda t: '🆕 Enter' if t in pot_entries else '✅ Hold'
        )
        t20df.columns = ['Rank', 'Ticker', '3M Return %', 'Price ₹', 'Status']
        st.dataframe(
            t20df, use_container_width=True, hide_index=True, height=360,
            column_config={
                '3M Return %': st.column_config.NumberColumn(format='%+.1f%%'),
                'Price ₹':     st.column_config.NumberColumn(format='₹%.2f'),
            },
        )

    # ── FORWARD SCHEDULE ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("📅 Upcoming rebalance schedule (next 8 periods)")
    schedule = []
    for i in range(8):
        d = next_dt + timedelta(days=14 * i)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        dl = (d - today).days
        if dl < 0:
            status = '⚡ Due now'
        elif dl == 0:
            status = '⚡ Today'
        elif i == 0:
            status = '🟡 Next up'
        else:
            status = '📅 Scheduled'
        schedule.append({
            '#':       i + 1,
            'Date':    d.strftime('%d %b %Y'),
            'Day':     d.strftime('%A'),
            'Days Away': max(0, dl),
            'Status':  status,
        })
    st.dataframe(pd.DataFrame(schedule), use_container_width=True, hide_index=True)

    # ── EXECUTION GUIDE ───────────────────────────────────────────────────────
    with st.expander("📋 Step-by-step rebalance execution guide"):
        st.markdown(f"""
**On {next_dt.strftime('%d %B %Y')} — what to do:**

**Step 1 — Pull momentum rankings**
- Get closing prices for all Nifty 250 stocks
- Calculate 63-trading-day return for each stock
- Sort descending — top 20 are your target holdings

**Step 2 — Identify changes vs current portfolio**
- Stocks in top-20 but NOT held → **BUY** at market open
- Stocks held but NOT in top-20 → **SELL** at market open
- Stocks in both → **HOLD** (adjust weight if drifted >2% from 5% target)

**Step 3 — Execute at market open (9:15 AM IST)**
- Delivery trades (CNC), not intraday (MIS)
- Target: ~5% weight per stock = equal weight across 20
- Zero-brokerage broker (Zerodha/Groww) to keep cost <0.1%

**Step 4 — Tax consideration**
- Holdings < 12 months → STCG @ 15%
- Holdings > 12 months → LTCG @ 10% (first ₹1.25L/year exempt)
- If a holding is close to 12 months, defer exit a few days for LTCG benefit

**Step 5 — Log it**
- Record each trade: date, ticker, buy/sell, price, qty
- Never override the signal based on news or gut feel — the edge is in consistency
        """)

    st.divider()

    # ── LIVE PORTFOLIO TRACKER ───────────────────────────────────────────────
    st.subheader("📒 My Live Portfolio Tracker")
    st.caption("Personal record of your actual N250F trades. Add entry prices manually after execution.")

    import json

    TRACKER_KEY = "n250f_live_tracker"

    # Initialize session state
    if TRACKER_KEY not in st.session_state:
        st.session_state[TRACKER_KEY] = {
            'start_date': '2026-05-19',
            'start_capital': 1_000_000,
            'positions': [],  # list of {ticker, entry_date, entry_price, shares, capital_deployed}
            'closed': [],     # list of closed trades
        }

    tracker = st.session_state[TRACKER_KEY]

    # ── Setup row
    cap_col, _ = st.columns([1, 3])
    with cap_col:
        cap_input = st.number_input(
            "Starting capital (₹)", min_value=100000, max_value=100000000,
            value=tracker['start_capital'], step=50000, format="%d",
            key="n250f_start_cap"
        )
        if cap_input != tracker['start_capital']:
            tracker['start_capital'] = cap_input

    # ── Next rebalance stocks (computed dynamically)
    may19_stocks = [e for e in pot_entries] if pot_entries else []

    st.info(f"""
    **Next Rebalance — Action Required:**
    - 🟢 **BUY** (new entries): {', '.join(may19_stocks) if may19_stocks else 'See "Likely changes" above'}
    - 🔴 **SELL** (exits): {', '.join(pot_exits) if pot_exits else 'See above'}
    - **Capital per stock:** ₹{tracker['start_capital'] / 20:,.0f} (5% each of ₹{tracker['start_capital']:,})
    """)

    # ── Add position
    with st.expander("➕ Record a trade execution", expanded=False):
        tc1, tc2, tc3 = st.columns(3)
        with tc1:
            new_ticker = st.text_input("Ticker", placeholder="e.g. NEULANDLAB", key="lv_ticker").upper()
        with tc2:
            new_date = st.text_input("Execution date", value=datetime.today().strftime("%Y-%m-%d"), key="lv_date")
        with tc3:
            new_price = st.number_input("Execution price (₹)", min_value=0.01, value=100.0, step=0.05, key="lv_price")

        cap_deployed = tracker['start_capital'] / 20
        shares = cap_deployed / new_price if new_price > 0 else 0
        st.caption(f"Shares to buy: {shares:.2f} | Capital deployed: ₹{cap_deployed:,.0f}")

        if st.button("Add position", key="lv_add") and new_ticker:
            tracker['positions'].append({
                'ticker': new_ticker,
                'entry_date': new_date,
                'entry_price': new_price,
                'shares': round(shares, 4),
                'capital': round(cap_deployed, 2),
            })
            st.success(f"Added {new_ticker} @ ₹{new_price}")
            st.rerun()

    # ── Display live positions
    if tracker['positions']:
        st.markdown("**Open positions:**")
        pos_rows = []
        for p in tracker['positions']:
            # Use last known price from curr portfolio if available
            known_price = next((s['current_price'] for s in curr if s['ticker'] == p['ticker']), p['entry_price'])
            cmp = known_price
            current_val = p['shares'] * cmp
            unrealised_pnl = current_val - p['capital']
            unrealised_pct = (unrealised_pnl / p['capital']) * 100
            pos_rows.append({
                'Ticker': p['ticker'],
                'Entry Date': p['entry_date'],
                'Entry ₹': p['entry_price'],
                'CMP ₹': round(cmp, 2),
                'Shares': p['shares'],
                'Capital (₹)': p['capital'],
                'Current Val (₹)': round(current_val, 2),
                'Unrealised P&L (₹)': round(unrealised_pnl, 2),
                'Return %': round(unrealised_pct, 2),
            })

        pos_df = pd.DataFrame(pos_rows)
        total_invested = pos_df['Capital (₹)'].sum()
        total_current = pos_df['Current Val (₹)'].sum()
        total_pnl = total_current - total_invested
        total_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Positions", len(pos_df))
        m2.metric("Total invested", f"₹{total_invested:,.0f}")
        m3.metric("Current value", f"₹{total_current:,.0f}")
        m4.metric("Unrealised P&L", f"₹{total_pnl:+,.0f}", f"{total_pct:+.2f}%")

        st.dataframe(
            pos_df, use_container_width=True, hide_index=True,
            column_config={
                'Entry ₹': st.column_config.NumberColumn(format='₹%.2f'),
                'CMP ₹': st.column_config.NumberColumn(format='₹%.2f'),
                'Capital (₹)': st.column_config.NumberColumn(format='₹%,.0f'),
                'Current Val (₹)': st.column_config.NumberColumn(format='₹%,.0f'),
                'Unrealised P&L (₹)': st.column_config.NumberColumn(format='₹%+,.0f'),
                'Return %': st.column_config.NumberColumn(format='%+.2f%%'),
            },
        )

        if st.button("🗑️ Clear all positions (reset tracker)", key="lv_clear"):
            st.session_state[TRACKER_KEY]['positions'] = []
            st.rerun()
    else:
        st.info("No positions recorded yet. Add your executions above after buying.")

# ── DISCLAIMER ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="disclaimer">
⚠️ <strong>DISCLAIMER:</strong> N250F backtest uses real yfinance prices for a 183-stock NSE proxy universe (Jun 2015 – May 2026).
This is a research tool, not a real portfolio. Limitations: (1) Static universe — actual Nifty 250 constituent changes not fully replicated;
(2) Minor survivorship bias — some delisted stocks absent; (3) Slippage beyond 0.1% not modelled for mid-caps;
(4) STCG/LTCG tax not included in CAGR figures. Estimated post-tax, post-slippage CAGR: ~20–24%.
Not SEBI investment advice. Past performance does not guarantee future results.
</div>
""", unsafe_allow_html=True)
