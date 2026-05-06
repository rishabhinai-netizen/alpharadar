"""
AlphaRadar — Run Scoring Engine
================================
Run from the Streamlit UI — no terminal needed.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from data_pipeline import (load_universe_from_nse, download_ohlcv,
                           run_full_scoring, sb_upsert, sb_query, send_telegram)

st.set_page_config(page_title="Run Scoring", page_icon="⚡", layout="wide")
st.title("⚡ Run AlphaRadar Scoring Engine")

st.markdown("""
Run the full scoring pipeline from here. No terminal needed.

**What happens:**
1. Downloads/refreshes the stock universe from NSE
2. Fetches 3 years weekly + 1 year daily data from yfinance
3. Runs Weinstein + O'Neil + Minervini scoring on all stocks
4. Writes results to Supabase
5. Sends summary to Telegram
""")

st.divider()

# Check current state
existing = sb_query('ar_universe', select='count', params={'is_active': 'eq.true'}, limit=1)
universe_count = existing[0].get('count', 0) if existing and isinstance(existing, list) and len(existing) > 0 else 0
st.info(f"Current universe: **{universe_count}** stocks in Supabase")

today = datetime.now().strftime('%Y-%m-%d')
today_scores = sb_query('ar_daily_scores', select='count', params={'score_date': f'eq.{today}'}, limit=1)
score_count = today_scores[0].get('count', 0) if today_scores and isinstance(today_scores, list) and len(today_scores) > 0 else 0
if score_count > 0:
    st.success(f"✅ Today's scores already exist: **{score_count}** stocks scored for {today}")

st.divider()

col1, col2 = st.columns(2)
with col1:
    run_initial = st.button("🚀 Initial Load (First Time)", use_container_width=True, type="primary",
                            help="Downloads universe + 3Y data + scores everything. Takes ~15 min.")
with col2:
    run_daily = st.button("📊 Daily Refresh", use_container_width=True,
                          help="Updates data and re-scores. Takes ~10 min.")

if run_initial or run_daily:
    start_time = datetime.now()
    
    # Step 1: Universe
    st.subheader("Step 1: Loading Universe")
    with st.spinner("Downloading stock lists from NSE..."):
        stocks = load_universe_from_nse()
    st.success(f"✅ Loaded {len(stocks)} stocks from NSE Total Market Index")
    
    # Upsert to Supabase
    with st.spinner("Writing universe to Supabase..."):
        rows = [{
            'symbol': s['symbol'], 'company_name': s['company_name'],
            'isin': s['isin'], 'industry': s['industry'], 'sector': s['sector'],
            'cap_bucket': s['cap_bucket'], 'yf_ticker': s['yf_ticker'], 'is_active': True
        } for s in stocks]
        total = sb_upsert('ar_universe', rows)
    st.success(f"✅ {total} stocks in Supabase universe")
    
    symbols = [s['symbol'] for s in stocks]
    universe_lookup = {s['symbol']: s for s in stocks}
    
    # Step 2: Download Data
    st.subheader("Step 2: Downloading Price Data")
    
    st.write("📥 Downloading 3 years weekly data...")
    pb1 = st.progress(0, "Starting weekly download...")
    weekly_data = download_ohlcv(symbols, period="3y", interval="1wk", progress_bar=pb1)
    pb1.progress(1.0, f"✅ Weekly: {len(weekly_data)} stocks")
    
    st.write("📥 Downloading 1 year daily data...")
    pb2 = st.progress(0, "Starting daily download...")
    daily_data = download_ohlcv(symbols, period="1y", interval="1d", progress_bar=pb2)
    pb2.progress(1.0, f"✅ Daily: {len(daily_data)} stocks")
    
    # Step 3: Score
    st.subheader("Step 3: Running Scoring Engine")
    pb3 = st.progress(0, "Scoring stocks...")
    scores = run_full_scoring(symbols, weekly_data, daily_data, universe_lookup, progress_bar=pb3)
    pb3.progress(1.0, f"✅ Scored {len(scores)} stocks")
    
    # Summary
    from collections import Counter
    bc = Counter(s['bucket'] for s in scores)
    sc = Counter(s['weinstein_stage'] for s in scores)
    
    st.subheader("Scoring Summary")
    cols = st.columns(5)
    bucket_emojis = {'MUST_BUY': '🟢', 'CAN_BUY': '🔵', 'NEUTRAL': '⚪', 'AVOID': '🟡', 'SELL': '🔴'}
    for i, bucket in enumerate(['MUST_BUY', 'CAN_BUY', 'NEUTRAL', 'AVOID', 'SELL']):
        cols[i].metric(f"{bucket_emojis[bucket]} {bucket.replace('_',' ')}", bc.get(bucket, 0))
    
    # Top 10
    top = sorted(scores, key=lambda x: -x['composite_score'])[:10]
    st.subheader("Top 10 Stocks")
    top_df = pd.DataFrame(top)[['symbol', 'composite_score', 'bucket', 'weinstein_stage', 'rs_percentile', 'price']]
    st.dataframe(top_df, hide_index=True, use_container_width=True)
    
    # Step 4: Write to Supabase
    st.subheader("Step 4: Writing to Supabase")
    with st.spinner("Uploading scores..."):
        # Remove non-DB fields before insert
        db_scores = [{k: v for k, v in s.items() if k not in ('company_name', 'industry', 'cap_bucket')} for s in scores]
        written = sb_upsert('ar_daily_scores', db_scores)
    st.success(f"✅ Written {written} scores to Supabase")
    
    # Step 5: Telegram
    elapsed = (datetime.now() - start_time).total_seconds() / 60
    summary = f"""🎯 <b>AlphaRadar Daily Score — {today}</b>

📊 Scored: {len(scores)} stocks
⏱ Time: {elapsed:.1f} min

🟢 Must Buy: {bc.get('MUST_BUY', 0)}
🔵 Can Buy: {bc.get('CAN_BUY', 0)}
⚪ Neutral: {bc.get('NEUTRAL', 0)}
🟡 Avoid: {bc.get('AVOID', 0)}
🔴 Sell: {bc.get('SELL', 0)}

📈 Top 3:
"""
    for t in top[:3]:
        summary += f"  {t['symbol']}: {t['composite_score']:.1f} | Stage {t['weinstein_stage']} | RS {t['rs_percentile']:.0f}%\n"
    
    send_telegram(summary)
    st.success(f"✅ Telegram summary sent")
    
    st.balloons()
    st.success(f"🎉 AlphaRadar scoring complete! {len(scores)} stocks scored in {elapsed:.1f} minutes.")
    st.info("Go to the main **Dashboard** page to view results.")
