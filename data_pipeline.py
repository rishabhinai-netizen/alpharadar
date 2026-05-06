"""
AlphaRadar Data Pipeline
========================
Downloads universe from NSE, fetches OHLCV from yfinance, writes to Supabase.
"""
import csv
import io
import json
import time
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
from datetime import datetime

SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal"
}
BENCHMARK = "^NSEI"

INDEX_URLS = {
    'total_market': 'https://www.niftyindices.com/IndexConstituent/ind_niftytotalmarket_list.csv',
    'nifty50': 'https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv',
    'midcap150': 'https://www.niftyindices.com/IndexConstituent/ind_niftymidcap150list.csv',
    'smallcap250': 'https://www.niftyindices.com/IndexConstituent/ind_niftysmallcap250list.csv',
    'microcap250': 'https://www.niftyindices.com/IndexConstituent/ind_niftymicrocap250_list.csv',
}


def sb_upsert(table, data, batch_size=50):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    total = 0
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        # Convert numpy types
        clean = []
        for row in batch:
            cr = {}
            for k, v in row.items():
                if isinstance(v, (np.bool_,)): cr[k] = bool(v)
                elif isinstance(v, (np.integer,)): cr[k] = int(v)
                elif isinstance(v, (np.floating,)): cr[k] = float(v) if not np.isnan(v) else None
                elif isinstance(v, float) and np.isnan(v): cr[k] = None
                else: cr[k] = v
            clean.append(cr)
        r = requests.post(url, headers=HEADERS, json=clean)
        if r.status_code in (200, 201):
            total += len(clean)
        else:
            st.warning(f"Insert error batch {i//batch_size}: {r.status_code}")
    return total


def sb_query(table, select="*", params=None, limit=1000):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}&limit={limit}"
    if params:
        url += "&" + "&".join(f"{k}={v}" for k, v in params.items())
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    r = requests.get(url, headers=h)
    return r.json() if r.status_code == 200 else []


def load_universe_from_nse():
    h = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.niftyindices.com/'}
    stocks = {}
    r = requests.get(INDEX_URLS['total_market'], headers=h, timeout=15)
    if r.status_code == 200 and not r.text.strip().startswith('<'):
        reader = csv.DictReader(io.StringIO(r.text))
        for row in reader:
            sym = row.get('Symbol', '').strip()
            if sym:
                stocks[sym] = {
                    'symbol': sym, 'company_name': row.get('Company Name', '').strip()[:80],
                    'industry': row.get('Industry', '').strip(), 'sector': row.get('Industry', '').strip(),
                    'isin': row.get('ISIN Code', '').strip(), 'cap_bucket': 'large',
                    'yf_ticker': f'{sym}.NS', 'is_active': True
                }
    for idx in ['nifty50', 'midcap150', 'smallcap250', 'microcap250']:
        url = INDEX_URLS.get(idx)
        if not url: continue
        try:
            r = requests.get(url, headers=h, timeout=15)
            if r.status_code == 200 and not r.text.strip().startswith('<'):
                cm = {'nifty50': 'large', 'midcap150': 'mid', 'smallcap250': 'small', 'microcap250': 'micro'}
                for row in csv.DictReader(io.StringIO(r.text)):
                    sym = row.get('Symbol', '').strip()
                    if sym in stocks: stocks[sym]['cap_bucket'] = cm.get(idx, 'large')
        except: pass
    return list(stocks.values())


def download_ohlcv(symbols, period="3y", interval="1wk", batch_size=50, progress_bar=None):
    all_data = {}
    tickers = [f"{s}.NS" for s in symbols]
    total_batches = (len(tickers) + batch_size - 1) // batch_size
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        bn = i // batch_size + 1
        if progress_bar:
            progress_bar.progress(bn / total_batches, f"Batch {bn}/{total_batches}")
        try:
            data = yf.download(batch, period=period, interval=interval, progress=False, threads=True)
            if not data.empty:
                if len(batch) == 1:
                    sym = batch[0].replace('.NS', '')
                    c = data['Close'].squeeze().dropna()
                    if len(c) >= 20:
                        all_data[sym] = {k: data[k].squeeze().dropna() for k in ['Close','Volume','High','Low','Open']}
                else:
                    for t in batch:
                        sym = t.replace('.NS', '')
                        try:
                            c = data['Close'][t].dropna()
                            if len(c) >= 20:
                                all_data[sym] = {k: data[k][t].dropna() for k in ['Close','Volume','High','Low','Open']}
                        except: pass
            time.sleep(0.3)
        except: pass
    return all_data


def run_full_scoring(symbols, weekly_data, daily_data, universe_lookup, progress_bar=None):
    from scoring_engine import classify_stage, compute_rs_score, compute_vp_score, compute_composite

    nifty = yf.download(BENCHMARK, period="3y", interval="1wk", progress=False)
    nifty_close = nifty['Close'].squeeze().dropna()

    univ_rets = []
    sym_rets = {}
    for sym, w in weekly_data.items():
        c = w['Close']
        if len(c) >= 52:
            ret = float((c.iloc[-1] / c.iloc[-52]) - 1)
            univ_rets.append(ret)
            sym_rets[sym] = ret

    sec_rets = {}
    for sym, ret in sym_rets.items():
        sec = universe_lookup.get(sym, {}).get('industry', 'Unknown')
        sec_rets.setdefault(sec, []).append(ret)

    scores = []
    total = len([s for s in weekly_data if s in daily_data])
    done = 0
    today = datetime.now().strftime('%Y-%m-%d')

    for sym in weekly_data:
        if sym not in daily_data: continue
        try:
            w, d = weekly_data[sym], daily_data[sym]
            sec = universe_lookup.get(sym, {}).get('industry', 'Unknown')
            stage = classify_stage(w['Close'], w['Volume'])
            rs = compute_rs_score(w['Close'], nifty_close, univ_rets, sec_rets.get(sec, []))
            vp = compute_vp_score(d['Close'], d['Volume'], d['High'], d['Low'], w['Close'], w['High'], w['Low'])
            comp = compute_composite(stage, rs, vp)

            price = float(d['Close'].iloc[-1])
            prev = float(d['Close'].iloc[-2]) if len(d['Close']) > 1 else price
            chg = (price - prev) / prev * 100

            scores.append({
                'symbol': sym, 'score_date': today,
                'composite_score': comp['composite_score'], 'raw_composite': comp['raw_composite'],
                'bucket': comp['bucket'],
                'stage_score': stage['score'], 'rs_score': rs['score'],
                'volume_price_score': vp['score'],
                'fundamental_score': 7.5, 'catalyst_score': 1.0,
                'weinstein_stage': stage['full_stage'],
                'rs_percentile': rs['rs_percentile'], 'sector_percentile': rs['sector_percentile'],
                'rs_new_high': bool(rs['rs_new_high']),
                'stage_cap_applied': bool(comp['stage_cap_applied']),
                'price': round(price, 2), 'price_change_pct': round(chg, 2),
                'high_52w': round(float(d['High'].max()), 2),
                'low_52w': round(float(d['Low'].min()), 2),
                'price_vs_ma': round(stage.get('price_vs_ma', 0) * 100, 2),
                'ma_slope': stage.get('ma_slope', 0),
                'data_quality': 'full',
                'company_name': universe_lookup.get(sym, {}).get('company_name', ''),
                'industry': sec,
                'cap_bucket': universe_lookup.get(sym, {}).get('cap_bucket', ''),
            })
            done += 1
            if progress_bar and done % 20 == 0:
                progress_bar.progress(done / total, f"Scored {done}/{total}")
        except: pass

    return scores


def send_telegram(message):
    try:
        token = st.secrets["telegram"]["bot_token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
    except: pass
