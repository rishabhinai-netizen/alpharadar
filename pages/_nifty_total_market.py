"""
AlphaRadar — Nifty Total Market Scoring Dashboard
===================================================
Weinstein Stage + O'Neil RS + Minervini Trend Template
Reads from Supabase ar_daily_scores (written by daily cron / Run Scoring page).
Live CMP + today's change refreshed via Breeze API (or yfinance fallback).

Architecture note: The composite score (Stage, RS, VP, Fundamentals, Catalyst)
requires weeks of OHLCV + fundamentals — it is genuinely an EOD calculation and
cannot be "real-time". What IS live: CMP, today's % change, today's volume.
The Refresh button pulls latest prices via Breeze and overlays them on the scores.
"""
import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta

try:
    st.set_page_config(page_title="Nifty Total Market — AlphaRadar", page_icon="◎", layout="wide")
except Exception:
    pass

SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]
SB_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

def sb_get(table, select="*", params="", limit=1000):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}&limit={limit}"
    if params: url += "&" + params
    r = requests.get(url, headers=SB_HEADERS)
    return r.json() if r.status_code == 200 else []

# ── Breeze live price overlay ──────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_breeze_ntm():
    try:
        from breeze_connect import BreezeConnect
        b = BreezeConnect(api_key=st.secrets["BREEZE_API_KEY"])
        b.generate_session(
            api_secret=st.secrets["BREEZE_API_SECRET"],
            session_token=st.secrets["BREEZE_SESSION_TOKEN"],
        )
        return b, None
    except Exception as e:
        return None, str(e)

@st.cache_data(ttl=60, show_spinner=False)   # 60-second cache for live prices
def fetch_live_prices_breeze(symbols: tuple) -> dict:
    """Fetch LTP + prev_close from Breeze for a list of symbols. Returns {sym: {cmp, chg_pct}}"""
    breeze, err = get_breeze_ntm()
    if err or not breeze:
        return {}
    result = {}
    for sym in symbols[:200]:  # cap at 200 to avoid timeout
        try:
            resp = breeze.get_quotes(
                stock_code=sym, exchange_code="NSE",
                product_type="cash", expiry_date="", right="", strike_price=""
            )
            if resp and resp.get("Success"):
                d = resp["Success"][0]
                ltp  = float(d.get("last_rate", 0) or 0)
                prev = float(d.get("previous_close", 0) or 0)
                if ltp > 0 and prev > 0:
                    result[sym] = {
                        "cmp_live":     round(ltp, 2),
                        "chg_pct_live": round((ltp - prev) / prev * 100, 2),
                    }
        except Exception:
            continue
    return result

@st.cache_data(ttl=60, show_spinner=False)   # fallback via yfinance
def fetch_live_prices_yf(symbols: tuple) -> dict:
    try:
        import yfinance as yf
        tickers = [s + ".NS" for s in symbols[:200]]
        raw = yf.download(tickers, period="2d", auto_adjust=True,
                          progress=False, group_by="ticker")
        result = {}
        if isinstance(raw.columns, pd.MultiIndex):
            for sym, ts in zip(symbols[:200], tickers):
                try:
                    sub = raw[ts]["Close"].dropna()
                    if len(sub) >= 2:
                        cmp = float(sub.iloc[-1])
                        prev = float(sub.iloc[-2])
                        result[sym] = {
                            "cmp_live":     round(cmp, 2),
                            "chg_pct_live": round((cmp - prev) / prev * 100, 2),
                        }
                except Exception:
                    continue
        return result
    except Exception:
        return {}

@st.cache_data(ttl=300)
def load_scores():
    latest = sb_get("ar_daily_scores", "score_date", "order=score_date.desc&limit=1")
    if not latest: return pd.DataFrame(), "N/A"
    latest_date = latest[0]["score_date"]
    data = sb_get("ar_daily_scores", "*",
                  f"score_date=eq.{latest_date}&order=composite_score.desc", limit=1000)
    return pd.DataFrame(data), latest_date

@st.cache_data(ttl=3600)
def load_universe():
    data = sb_get("ar_universe", "symbol,company_name,industry,cap_bucket", "is_active=eq.true")
    return {d["symbol"]: d for d in data} if data else {}

@st.cache_data(ttl=3600)
def load_score_history():
    data = sb_get("ar_daily_scores", "score_date", "order=score_date.desc&limit=30")
    if data:
        dates = sorted(set(d["score_date"] for d in data), reverse=True)
        return dates
    return []

_ntm_placeholder = st.empty()
with _ntm_placeholder.container():
    st.info("⏳ Loading scores from Supabase…")
df, score_date = load_scores()
universe = load_universe()
history_dates = load_score_history()
_ntm_placeholder.empty()

if df.empty:
    st.error("No scores in database.")
    st.info("""
    **To get started:** Go to **⚡ Run Scoring** in the sidebar → click **🚀 Initial Load**.
    Takes ~15 minutes. After that, daily updates run automatically at 4:45 PM IST.
    """)
    st.warning("⚠️ **Universe:** This tab covers all ~750 Nifty Total Market stocks scored by the daily cron.")
    st.stop()

# ── HEADER ──
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown("## ◎ Nifty Total Market — Scoring Dashboard")
    st.caption("Weinstein Stage Analysis · O'Neil Relative Strength · Minervini Trend Template")
    st.caption(
        "ℹ️ **Score** (Stage/RS/VP/Fundamentals) = EOD calculation, updated daily 4:45 PM. "
        "**CMP + Today's Change** = Live via Breeze (click Refresh ↑). "
        "Run Scoring page re-runs the full engine manually."
    )
with c2:
    if not df.empty:
        days_old = (datetime.now() - datetime.strptime(score_date, "%Y-%m-%d")).days
        st.metric("Stocks Scored", len(df))
        if days_old == 0:   st.caption(f"📅 {score_date} (today)")
        elif days_old == 1: st.caption(f"📅 {score_date} (yesterday)")
        else:               st.caption(f"⚠️ {score_date} ({days_old} days old)")
    if st.button("🔄 Refresh Live Prices", use_container_width=True, key="ntm_refresh"):
        st.cache_data.clear()
        st.rerun()

# ── LIVE PRICE OVERLAY ─────────────────────────────────────────────────────────
if not df.empty and "symbol" in df.columns:
    syms = tuple(df["symbol"].tolist())
    live_prices = fetch_live_prices_breeze(syms)
    if not live_prices:
        live_prices = fetch_live_prices_yf(syms)
    if live_prices:
        df["cmp_live"]     = df["symbol"].map(lambda s: live_prices.get(s, {}).get("cmp_live", None))
        df["chg_pct_live"] = df["symbol"].map(lambda s: live_prices.get(s, {}).get("chg_pct_live", None))
        # Use live where available, fall back to stored
        if "price" in df.columns:
            df["price"]           = df["cmp_live"].fillna(df["price"])
        if "price_change_pct" in df.columns:
            df["price_change_pct"] = df["chg_pct_live"].fillna(df["price_change_pct"])
        live_count = len([v for v in live_prices.values() if v])
        st.caption(f"⚡ Live prices loaded for **{live_count}** stocks via {'Breeze' if live_prices else 'yfinance'}")

if universe:
    df["company_name"] = df["symbol"].map(lambda s: universe.get(s, {}).get("company_name", ""))
    df["industry"]     = df["symbol"].map(lambda s: universe.get(s, {}).get("industry", ""))
    df["cap_bucket"]   = df["symbol"].map(lambda s: universe.get(s, {}).get("cap_bucket", ""))

BCFG = {
    "MUST_BUY": ("🟢", "Must Buy",  "#059669"),
    "CAN_BUY":  ("🔵", "Can Buy",   "#2563eb"),
    "NEUTRAL":  ("⚪", "Neutral",   "#64748b"),
    "AVOID":    ("🟡", "Avoid",     "#d97706"),
    "SELL":     ("🔴", "Sell",      "#dc2626"),
}

# ── BUCKET SUMMARY ──
cols = st.columns(5)
for i, (bk, (em, lb, cl)) in enumerate(BCFG.items()):
    cols[i].metric(f"{em} {lb}", len(df[df["bucket"] == bk]))

st.divider()

# ── TODAY'S HIGHLIGHTS ──
if "stage_changed" in df.columns and "weinstein_stage" in df.columns:
    stage_changed = df[df["stage_changed"] == True]
    new_stage2 = stage_changed[stage_changed["weinstein_stage"].isin(["2A","2B"])] if not stage_changed.empty else pd.DataFrame()
    new_stage4 = stage_changed[stage_changed["weinstein_stage"] == "4"] if not stage_changed.empty else pd.DataFrame()
    new_stage1b = stage_changed[stage_changed["weinstein_stage"] == "1B"] if not stage_changed.empty else pd.DataFrame()
    top_rs_stars = df[
        (df["rs_new_high"] == True) &
        (df["weinstein_stage"].isin(["2A","2B"]))
    ].sort_values("composite_score", ascending=False).head(5) if "rs_new_high" in df.columns else pd.DataFrame()

    if not new_stage2.empty or not new_stage4.empty or not top_rs_stars.empty or not new_stage1b.empty:
        # Main 3 panels — matches the 3 Telegram messages
        h1, h2, h3 = st.columns(3)
        with h1:
            if not new_stage2.empty:
                st.success(f"🟢 **{len(new_stage2)} New Buy Signals** (entered Stage 2)")
                st.caption("These match your ACTION REQUIRED Telegram message")
                for _, r in new_stage2.sort_values("composite_score", ascending=False).iterrows():
                    st.write(f"▸ **{r['symbol']}** Score {r['composite_score']:.0f} · RS {r['rs_percentile']:.0f}%")
            else:
                st.info("No new Stage 2 entries today")
        with h2:
            if not new_stage4.empty:
                st.error(f"🔴 **{len(new_stage4)} Sell Signals** (entered Stage 4)")
                for _, r in new_stage4.sort_values("composite_score").iterrows():
                    st.write(f"▸ **{r['symbol']}** Score {r['composite_score']:.0f}")
            else:
                st.info("No new Stage 4 entries today")
        with h3:
            if not new_stage1b.empty:
                st.warning(f"👀 **{len(new_stage1b)} Watchlist** (moved to Stage 1B)")
                st.caption("These match your WATCHLIST Telegram message")
                for _, r in new_stage1b.sort_values("composite_score", ascending=False).head(5).iterrows():
                    st.write(f"▸ **{r['symbol']}** Score {r['composite_score']:.0f} · RS {r['rs_percentile']:.0f}%")
            elif not top_rs_stars.empty:
                st.markdown("⭐ **Top Stage 2 + RS New High** (strongest leaders)")
                for _, r in top_rs_stars.iterrows():
                    st.write(f"▸ **{r['symbol']}** Score {r['composite_score']:.0f} · RS {r['rs_percentile']:.0f}%")
            else:
                st.info("No Stage 1B movers today")
        st.divider()

# ── FILTERS ──
fc1, fc2, fc3, fc4, fc5, fc6 = st.columns([2.5, 1, 1, 1, 1, 1.2])
with fc1: search = st.text_input("Search", "", placeholder="Symbol or company...", label_visibility="collapsed", key="ntm_search")
with fc6:
    show_changed = st.checkbox("🔄 Stage changed today", value=False, key="ntm_changed")
with fc2: bf = st.selectbox("Bucket", ["All"] + list(BCFG.keys()), label_visibility="collapsed", key="ntm_bucket")
with fc3: sf = st.selectbox("Stage", ["All","2A","2B","1B","1A","3","4"], label_visibility="collapsed", key="ntm_stage")
with fc4: cf = st.selectbox("Cap", ["All","large","mid","small","micro"], label_visibility="collapsed", key="ntm_cap")
with fc5: sort = st.selectbox("Sort", ["Score ↓","RS% ↓","Chg% ↓","Score ↑"], label_visibility="collapsed", key="ntm_sort")

fdf = df.copy()
if search:
    q = search.lower()
    fdf = fdf[
        fdf["symbol"].str.lower().str.contains(q) |
        fdf.get("company_name", pd.Series(dtype=str)).str.lower().str.contains(q, na=False)
    ]
if bf != "All": fdf = fdf[fdf["bucket"] == bf]
if sf != "All": fdf = fdf[fdf["weinstein_stage"] == sf]
if cf != "All" and "cap_bucket" in fdf.columns: fdf = fdf[fdf["cap_bucket"] == cf]
if show_changed and "stage_changed" in fdf.columns: fdf = fdf[fdf["stage_changed"] == True]

sm = {"Score ↓":("composite_score",False),"RS% ↓":("rs_percentile",False),
      "Chg% ↓":("price_change_pct",False),"Score ↑":("composite_score",True)}
sc, sa = sm.get(sort, ("composite_score", False))
if sc in fdf.columns: fdf = fdf.sort_values(sc, ascending=sa)

st.caption(f"Showing **{len(fdf)}** of {len(df)} stocks · Data: {score_date}")

with st.expander("ℹ️ Column Guide", expanded=False):
    st.markdown("""
    | Column | Meaning | Good Value |
    |--------|---------|------------|
    | **Score** | Composite conviction (0-100) | 60+ for entries |
    | **Stage** | Weinstein cycle stage | **2A** = buy zone |
    | **RS Pctl** | Relative Strength rank vs all stocks | >70% = strong |
    | **Sec Pctl** | Rank within sector | >70% = sector leader |
    | **RS★** | RS at 52-week high — very bullish | ⭐ |
    | **Capped** | Score limited by Stage gate | Stage 4 max = 20 |
    """)

# ── MAIN TABLE ──
if not fdf.empty:
    dcols = [c for c in ["symbol","composite_score","score_change","action_label","weinstein_stage",
             "entry_signal","price","price_change_pct","rs_percentile","sector_percentile",
             "stage_score","rs_score","volume_price_score","fundamental_score","catalyst_score",
             "rs_new_high","stage_cap_applied","entry_detail"] if c in fdf.columns]
    show = fdf[dcols].copy().rename(columns={
        "symbol":"Symbol","composite_score":"Score","score_change":"Δ","action_label":"Action",
        "weinstein_stage":"Stage","entry_signal":"Entry Signal","price":"Price",
        "price_change_pct":"Chg%","rs_percentile":"RS Pctl","sector_percentile":"Sec Pctl",
        "stage_score":"Stg","rs_score":"RS","volume_price_score":"VP",
        "fundamental_score":"Fund","catalyst_score":"Cat",
        "rs_new_high":"RS★","stage_cap_applied":"Capped","entry_detail":"Entry Detail",
    })
    st.dataframe(show, use_container_width=True, height=580,
        column_config={
            "Score":        st.column_config.NumberColumn(format="%.1f"),
            "Δ":            st.column_config.NumberColumn(format="%+.1f"),
            "Stage":        st.column_config.TextColumn(),
            "Price":        st.column_config.NumberColumn(format="₹%.2f"),
            "Chg%":        st.column_config.NumberColumn(format="%.2f%%"),
            "RS Pctl":      st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "Sec Pctl":     st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "Stg":          st.column_config.NumberColumn(format="%.1f"),
            "RS":           st.column_config.NumberColumn(format="%.1f"),
            "VP":           st.column_config.NumberColumn(format="%.1f"),
            "Fund":         st.column_config.NumberColumn(format="%.1f"),
            "Cat":          st.column_config.NumberColumn(format="%.1f"),
            "RS★":          st.column_config.CheckboxColumn(),
            "Capped":       st.column_config.CheckboxColumn(),
            "Entry Detail": st.column_config.TextColumn(width="medium"),
        }, hide_index=True)

# ── STOCK DETAIL ──
st.divider()
st.markdown("### 📊 Stock Detail")
if not fdf.empty:
    sel = st.selectbox("Select stock", fdf["symbol"].tolist(), label_visibility="collapsed",
                       key="ntm_detail_sel")
    if sel:
        row = fdf[fdf["symbol"] == sel].iloc[0]
        bcfg = BCFG.get(row["bucket"], ("","","#000"))
        d1,d2,d3,d4,d5 = st.columns(5)
        d1.metric("Score",    f"{row['composite_score']:.1f}/100",
                  delta=f"{row.get('score_change',0) or 0:+.1f}" if row.get("score_change") else None)
        d2.metric("Bucket",   f"{bcfg[0]} {bcfg[1]}")
        d3.metric("Stage",    row["weinstein_stage"])
        d4.metric("RS Pctl",  f"{row['rs_percentile']:.0f}%")
        d5.metric("Price",    f"₹{row.get('price',0):.2f}",
                  delta=f"{row.get('price_change_pct',0):.2f}%")

        factors = [
            ("Trend/Stage (30%)",      row.get("stage_score",0),          30, "#7c3aed"),
            ("Relative Strength (25%)",row.get("rs_score",0),             25, "#2563eb"),
            ("Volume & Price (20%)",   row.get("volume_price_score",0),   20, "#d97706"),
            ("Fundamentals (15%)",     row.get("fundamental_score",7.5),  15, "#059669"),
            ("Catalyst (10%)",         row.get("catalyst_score",1),       10, "#ec4899"),
        ]
        fig = go.Figure()
        for label, val, mx, color in factors:
            fig.add_trace(go.Bar(x=[val], y=[label], orientation="h", marker_color=color,
                                 text=f"{val:.1f}/{mx}", textposition="auto"))
        fig.update_layout(showlegend=False, height=240, margin=dict(l=0,r=20,t=10,b=10),
                          xaxis=dict(range=[0,30], showticklabels=False),
                          yaxis=dict(autorange="reversed"), plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)

        flags = []
        if row.get("rs_new_high"):        flags.append("⭐ RS New High")
        if row.get("stage_cap_applied"):  flags.append(f"⚠️ Stage Capped (raw: {row.get('raw_composite','N/A')})")
        if row.get("stage_changed"):      flags.append("🔄 Stage Changed Today")
        if flags: st.info(" · ".join(flags))

# ── CHARTS ──
st.divider()
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Bucket Distribution**")
    bc = df["bucket"].value_counts()
    fig = go.Figure(go.Pie(
        labels=[BCFG[b][1] for b in bc.index if b in BCFG],
        values=[bc[b] for b in bc.index if b in BCFG],
        marker_colors=[BCFG[b][2] for b in bc.index if b in BCFG], hole=0.4))
    fig.update_layout(height=280, margin=dict(l=20,r=20,t=10,b=10))
    st.plotly_chart(fig, use_container_width=True)
with c2:
    st.markdown("**Stage Distribution**")
    if "weinstein_stage" in df.columns:
        stc = df["weinstein_stage"].value_counts()
        scl = {"2A":"#059669","2B":"#10b981","1B":"#3b82f6","1A":"#94a3b8","3":"#d97706","4":"#dc2626"}
        fig = go.Figure(go.Bar(
            x=[f"Stage {s}" for s in stc.index], y=stc.values,
            marker_color=[scl.get(s,"#94a3b8") for s in stc.index]))
        fig.update_layout(height=280, margin=dict(l=20,r=20,t=10,b=10), plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)

st.caption(f"AlphaRadar · Score date: {score_date} · Auto-updates daily 4:45 PM IST")
