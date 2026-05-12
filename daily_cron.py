"""
AlphaRadar Daily Cron — Runs via GitHub Actions
================================================
No Streamlit dependency. Standalone scoring script.
Fetches data, scores all stocks, writes to Supabase, sends Telegram.
"""
import os
import csv
import io
import json
import time
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from collections import Counter
from scipy.stats import percentileofscore, linregress

# ── CONFIG ──
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://aiebaqvclyzxajigvkfd.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFpZWJhcXZjbHl6eGFqaWd2a2ZkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ5NTg1MDQsImV4cCI6MjA5MDUzNDUwNH0.m_WLKdaKwEw82RRepHYhXp3tg-g0pwMiDKM2S7Y7XdY")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8347009897:AAEFlJxNtRbWL7_grWDtQUludo_LCbhNgck")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "705724053")
BENCHMARK = "^NSEI"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal"
}

STAGE_CAPS = {'2A': 100, '2B': 90, '1B': 70, '1A': 55, '3': 40, '4': 20}
BUCKETS_RANGES = {'MUST_BUY': (80, 100), 'CAN_BUY': (60, 79), 'NEUTRAL': (40, 59), 'AVOID': (20, 39), 'SELL': (0, 19)}

INDEX_URLS = {
    'total_market': 'https://www.niftyindices.com/IndexConstituent/ind_niftytotalmarket_list.csv',
    'nifty50': 'https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv',
    'midcap150': 'https://www.niftyindices.com/IndexConstituent/ind_niftymidcap150list.csv',
    'smallcap250': 'https://www.niftyindices.com/IndexConstituent/ind_niftysmallcap250list.csv',
    'microcap250': 'https://www.niftyindices.com/IndexConstituent/ind_niftymicrocap250_list.csv',
}

# ── SUPABASE HELPERS ──
def sb_upsert(table, data, batch_size=50):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    total = 0
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
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
        if r.status_code in (200, 201): total += len(clean)
        else: print(f"  ⚠ Upsert error: {r.status_code} - {r.text[:200]}")
    return total

def sb_query(table, select="*", params=None, limit=1000):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}&limit={limit}"
    if params:
        url += "&" + "&".join(f"{k}={v}" for k, v in params.items())
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    r = requests.get(url, headers=h)
    return r.json() if r.status_code == 200 else []

def send_telegram(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                     data={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"  Telegram error: {e}")

# ── SCORING ENGINE (inline for standalone execution) ──
def classify_stage(wc, wv=None):
    if len(wc) < 35:
        return {'full_stage': 'UNKNOWN', 'score': 0, 'price_vs_ma': 0, 'ma_slope': 0, 'ma_value': 0}
    ma30 = wc.rolling(30).mean()
    price, ma_now = float(wc.iloc[-1]), float(ma30.iloc[-1])
    if np.isnan(ma_now) or ma_now == 0:
        return {'full_stage': 'UNKNOWN', 'score': 0, 'price_vs_ma': 0, 'ma_slope': 0, 'ma_value': 0}
    pvm = (price - ma_now) / ma_now
    s5 = float((ma30.iloc[-1] - ma30.iloc[-6]) / ma30.iloc[-6]) if len(ma30.dropna()) >= 6 else 0
    s10 = float((ma30.iloc[-1] - ma30.iloc[-11]) / ma30.iloc[-11]) if len(ma30.dropna()) >= 11 else 0
    vt = 1.0
    if wv is not None and len(wv) >= 13:
        rv, pv = wv.iloc[-4:].mean(), wv.iloc[-13:-4].mean()
        if pv > 0: vt = rv / pv
    wr = s10 > 0.003 if len(ma30.dropna()) >= 15 else False
    if s5 > 0.003 and pvm > 0.02:
        if pvm > 0.20: stg, sc = '2B', max(20, min(27, 25 - min(5, (pvm - 0.20) * 30)))
        else:
            fb = 2 if s10 < 0.003 else 0
            sc = min(30, 24 + fb + min(3, s5 * 500) + (min(2, max(0, (vt-1)*5)) if vt > 1 else 0))
            stg = '2A'
    elif s5 < -0.003 and pvm < -0.02:
        stg, sc = '4', max(0, 3 - min(3, abs(pvm) * 10))
    elif abs(s5) <= 0.0045 and wr and pvm > -0.05:
        stg, sc = '3', (4 if pvm < 0 else 7)
    else:
        if (s10 < -0.003 and s5 > -0.003) and pvm > -0.05:
            pt = False
            if len(wc) >= 20:
                rr = (wc.iloc[-8:].max() - wc.iloc[-8:].min()) / ma_now
                orr = (wc.iloc[-20:-8].max() - wc.iloc[-20:-8].min()) / ma_now
                pt = rr < orr * 0.7
            if pt or pvm > 0: stg, sc = '1B', min(19, 15 + (2 if pvm > 0 else 0))
            else: stg, sc = '1B', 13
        else: stg, sc = '1A', max(8, min(14, 10 + (2 if abs(pvm) < 0.05 else 0)))
    return {'full_stage': stg, 'score': round(float(sc), 1), 'price_vs_ma': round(float(pvm), 4),
            'ma_slope': round(float(s5), 6), 'ma_value': round(float(ma_now), 2)}

def compute_rs_score(sw, bw, ur=None, sr=None):
    ml = min(len(sw), len(bw))
    if ml < 52: return {'score': 0, 'rs_percentile': 0, 'sector_percentile': 50, 'rs_new_high': False}
    s, b = sw.iloc[-ml:].values, bw.iloc[-ml:].values
    sc = 0.0
    rs = s / b; rs = rs / rs[0]
    rma = pd.Series(rs).rolling(min(52, len(rs)-1)).mean().values
    rvma = (rs[-1] - rma[-1]) / rma[-1] if (not np.isnan(rma[-1]) and rma[-1] > 0) else 0
    sc += min(4, rvma * 40) if rs[-1] > rma[-1] else max(0, 2 + rvma * 20)
    s52r = (s[-1] / s[-52] - 1) if len(s) >= 52 else 0
    rp = percentileofscore(ur, s52r) if ur and len(ur) > 10 else 50
    sc += (rp / 100) * 8
    lk = min(52, len(rs))
    rnh = bool(rs[-1] >= np.nanmax(rs[-lk:]) * 0.97)
    sc += 5 if rnh else (2 if rs[-1] >= np.nanmax(rs[-lk:]) * 0.90 else 0)
    tw = min(10, len(rs)-1)
    if tw >= 5:
        try:
            sn = linregress(np.arange(tw), rs[-tw:]).slope / np.mean(rs[-tw:]) * 100
            sc += min(5, sn * 5) if sn > 0 else max(0, 2 + sn * 3)
        except: pass
    sp = percentileofscore(sr, s52r) if sr and len(sr) > 5 else 50
    sc += 3 if sp > 80 else (2 if sp > 60 else (1 if sp > 40 else 0))
    return {'score': min(25, round(float(sc), 1)), 'rs_percentile': round(float(rp), 1),
            'sector_percentile': round(float(sp), 1), 'rs_new_high': rnh}

def compute_vp_score(dc, dv, dh, dl, wc=None, wh=None, wl=None):
    if len(dc) < 20: return {'score': 0}
    sc = 0.0; n = len(dc); cc = dc.pct_change(); va = dv.rolling(50).mean()
    lb = min(50, n); ud = dd = 0
    for i in range(-lb, 0):
        try:
            if pd.isna(cc.iloc[i]) or pd.isna(va.iloc[i]) or va.iloc[i] == 0: continue
            if cc.iloc[i] > 0 and dv.iloc[i] > va.iloc[i]: ud += 1
            elif cc.iloc[i] < 0 and dv.iloc[i] > va.iloc[i]: dd += 1
        except: pass
    t = ud + dd
    if t > 0: sc += min(5, (ud/t) * 7)
    pb = []
    for i in range(-min(20, n), 0):
        try:
            if cc.iloc[i] < -0.005 and va.iloc[i] > 0: pb.append(dv.iloc[i] / va.iloc[i])
        except: pass
    if pb:
        apv = np.mean(pb)
        sc += 4 if apv < 0.5 else (3 if apv < 0.7 else (1.5 if apv < 0.9 else 0))
    if wc is not None and len(wc) >= 8:
        rw = wc.iloc[-6:]; wr = (rw.max() - rw.min()) / rw.mean()
        sc += 3 if wr < 0.04 else (2 if wr < 0.07 else (1 if wr < 0.10 else 0))
    if wc is not None and wh is not None and len(wc) >= 12:
        pk = wh.iloc[-min(52, len(wc)):].max()
        if pk > 0:
            dp = (pk - wc.iloc[-1]) / pk
            sc += 4 if 0.05 <= dp < 0.15 else (3 if dp < 0.25 else (2 if dp < 0.35 else (2 if dp < 0.05 else 0.5)))
    if len(dh) >= 50:
        h52 = dh.iloc[-252:].max() if len(dh) >= 252 else dh.max()
        dfh = (h52 - dc.iloc[-1]) / h52 if h52 > 0 else 1
        sc += 2 if dfh < 0.03 else (1.5 if dfh < 0.08 else (0.5 if dfh < 0.15 else 0))
    return {'score': min(20, round(float(sc), 1))}

def compute_composite(stage_r, rs_r, vp_r, fund_score=7.5, cat_score=3.0):
    raw = stage_r['score'] + rs_r['score'] + vp_r['score'] + fund_score + cat_score
    fs = stage_r.get('full_stage', 'UNKNOWN')
    cap = STAGE_CAPS.get(fs, 50)
    comp = min(raw, cap)
    bucket = 'NEUTRAL'
    for bn, (lo, hi) in BUCKETS_RANGES.items():
        if lo <= comp <= hi: bucket = bn; break
    if fs == '4' and bucket not in ('SELL', 'AVOID'): bucket = 'AVOID'
    if fs == '3' and bucket == 'MUST_BUY': bucket = 'NEUTRAL'
    return {'composite_score': round(float(comp), 1), 'raw_composite': round(float(raw), 1),
            'bucket': bucket, 'stage_cap_applied': comp < raw}

def detect_entry(dc, dh, dl, dv, wc):
    """Detect breakout, pullback, VCP entry patterns."""
    if len(dc) < 50 or len(wc) < 30: return 'WAIT', ''
    price = float(dc.iloc[-1])
    ma30w = float(wc.rolling(30).mean().iloc[-1])
    ma21d = float(dc.rolling(21).mean().iloc[-1])
    ma50d = float(dc.rolling(50).mean().iloc[-1])
    va = float(dv.rolling(50).mean().iloc[-1])
    vr = float(dv.iloc[-1]) / va if va > 0 else 1
    h52 = float(dh.iloc[-252:].max()) if len(dh) >= 252 else float(dh.max())
    dh52 = (h52 - price) / h52 if h52 > 0 else 1
    rr = (float(dh.iloc[-10:].max()) - float(dl.iloc[-10:].min())) / price if price > 0 else 0
    vc = float(dv.iloc[-5:].mean()) / float(dv.iloc[-20:].mean()) if float(dv.iloc[-20:].mean()) > 0 else 1
    aa = price > ma21d and price > ma50d and price > ma30w
    if dh52 < 0.03 and vr > 1.5: return 'BUY NOW', f'Breakout! Near 52w high on {vr:.1f}x volume'
    if aa and abs(price - ma21d)/ma21d < 0.02 and vc < 0.8: return 'BUY NOW', f'Pullback to 21d MA on low vol'
    if aa and rr < 0.06 and vc < 0.7: return 'BUY NOW', f'VCP: Tight range + volume dry-up'
    if aa and abs(price - ma50d)/ma50d < 0.03: return 'BUY DIPS', f'At 50d MA support'
    if 0.03 <= dh52 < 0.08 and rr < 0.08 and aa: return 'WATCH', f'{dh52:.0%} from high, consolidating'
    if aa and price > ma50d * 1.12: return 'WAIT', f'Extended — wait for pullback'
    if aa: return 'WATCH', f'Uptrend. Wait for pullback to 21d/50d MA'
    if price < ma30w: return 'AVOID', 'Below 30-week MA'
    return 'WAIT', 'No clear pattern'

# ── UNIVERSE LOADER ──
def load_universe():
    h = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.niftyindices.com/'}
    stocks = {}
    r = requests.get(INDEX_URLS['total_market'], headers=h, timeout=15)
    if r.status_code == 200 and not r.text.strip().startswith('<'):
        for row in csv.DictReader(io.StringIO(r.text)):
            sym = row.get('Symbol', '').strip()
            if sym:
                stocks[sym] = {
                    'symbol': sym, 'company_name': row.get('Company Name', '').strip()[:80],
                    'industry': row.get('Industry', '').strip(), 'sector': row.get('Industry', '').strip(),
                    'isin': row.get('ISIN Code', '').strip(), 'cap_bucket': 'large',
                    'yf_ticker': f'{sym}.NS', 'is_active': True
                }
    for idx in ['nifty50', 'midcap150', 'smallcap250', 'microcap250']:
        try:
            r = requests.get(INDEX_URLS[idx], headers=h, timeout=15)
            if r.status_code == 200 and not r.text.strip().startswith('<'):
                cm = {'nifty50': 'large', 'midcap150': 'mid', 'smallcap250': 'small', 'microcap250': 'micro'}
                for row in csv.DictReader(io.StringIO(r.text)):
                    sym = row.get('Symbol', '').strip()
                    if sym in stocks: stocks[sym]['cap_bucket'] = cm.get(idx, 'large')
        except: pass
    return list(stocks.values())

# ── DATA DOWNLOAD ──
def download_batch(symbols, period, interval, batch_size=50):
    all_data = {}
    tickers = [f"{s}.NS" for s in symbols]
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        try:
            data = yf.download(batch, period=period, interval=interval, progress=False, threads=True)
            if not data.empty:
                if len(batch) == 1:
                    sym = batch[0].replace('.NS', '')
                    c = data['Close'].squeeze().dropna()
                    if len(c) >= 20:
                        all_data[sym] = {k: data[k].squeeze().dropna() for k in ['Close','Volume','High','Low']}
                else:
                    for t in batch:
                        sym = t.replace('.NS', '')
                        try:
                            c = data['Close'][t].dropna()
                            if len(c) >= 20:
                                all_data[sym] = {k: data[k][t].dropna() for k in ['Close','Volume','High','Low']}
                        except: pass
            time.sleep(0.3)
        except: pass
    return all_data

# ── MAIN ──
def main():
    start = datetime.now()
    today = start.strftime('%Y-%m-%d')
    print(f"{'='*60}")
    print(f"AlphaRadar Daily Scoring — {today}")
    print(f"{'='*60}")

    # 1. Load universe
    print("\n[1/5] Loading universe from NSE...")
    stocks = load_universe()
    print(f"  Loaded {len(stocks)} stocks")
    
    # Upsert universe
    rows = [{k: v for k, v in s.items()} for s in stocks]
    sb_upsert('ar_universe', rows)
    
    symbols = [s['symbol'] for s in stocks]
    uni_map = {s['symbol']: s for s in stocks}

    # 2. Download weekly data
    print("\n[2/5] Downloading weekly data (3Y)...")
    weekly = download_batch(symbols, "3y", "1wk")
    print(f"  Weekly: {len(weekly)} stocks")

    # 3. Download daily data
    print("\n[3/5] Downloading daily data (1Y)...")
    daily = download_batch(symbols, "1y", "1d")
    print(f"  Daily: {len(daily)} stocks")

    # 4. Benchmark + scoring
    print("\n[4/5] Scoring...")
    nifty = yf.download(BENCHMARK, period="3y", interval="1wk", progress=False)
    nifty_close = nifty['Close'].squeeze().dropna()

    # 52w returns for RS percentile
    univ_rets, sym_rets = [], {}
    for sym, w in weekly.items():
        c = w['Close']
        if len(c) >= 52:
            ret = float((c.iloc[-1] / c.iloc[-52]) - 1)
            univ_rets.append(ret); sym_rets[sym] = ret
    
    sec_rets = {}
    for sym, ret in sym_rets.items():
        sec = uni_map.get(sym, {}).get('industry', 'Unknown')
        sec_rets.setdefault(sec, []).append(ret)

    scores = []
    prev_scores = {}
    prev = sb_query('ar_daily_scores', select='symbol,composite_score,weinstein_stage,bucket',
                    params={'order': 'score_date.desc'}, limit=800)
    for p in prev:
        if p['symbol'] not in prev_scores:
            prev_scores[p['symbol']] = p

    # Phase 1: Score all stocks with technical factors only
    print("  Phase 1: Technical scoring...")
    tech_scores = {}
    for sym in weekly:
        if sym not in daily: continue
        try:
            w, d = weekly[sym], daily[sym]
            sec = uni_map.get(sym, {}).get('industry', 'Unknown')
            stage = classify_stage(w['Close'], w['Volume'])
            rs = compute_rs_score(w['Close'], nifty_close, univ_rets, sec_rets.get(sec, []))
            vp = compute_vp_score(d['Close'], d['Volume'], d['High'], d['Low'], w['Close'], w['High'], w['Low'])
            tech_scores[sym] = {'stage': stage, 'rs': rs, 'vp': vp, 'sec': sec}
        except: pass
    print(f"  Tech scored: {len(tech_scores)}")

    # Phase 2: Fetch real fundamentals for top ~200 stocks (Can Buy candidates + stage changes)
    # This avoids hammering yfinance for all 750 stocks
    print("  Phase 2: Fetching fundamentals for top stocks...")
    fund_cache = {}
    
    # Prioritize: stocks likely to be Can Buy or better
    priority_syms = []
    for sym, ts in tech_scores.items():
        raw = ts['stage']['score'] + ts['rs']['score'] + ts['vp']['score']
        if raw >= 40 or ts['stage']['full_stage'] in ('2A', '2B'):  # Likely to score well
            priority_syms.append(sym)
    priority_syms = priority_syms[:200]  # Cap at 200 to stay within time limits
    
    for i, sym in enumerate(priority_syms):
        try:
            tk = yf.Ticker(f"{sym}.NS")
            info = tk.info
            sc = 0.0
            eg = info.get('earningsGrowth')
            if eg is not None:
                if eg > 0.40: sc += 4
                elif eg > 0.25: sc += 3
                elif eg > 0.10: sc += 2
                elif eg > 0: sc += 1
            else: sc += 1
            rg = info.get('revenueGrowth')
            if rg is not None:
                if rg > 0.25: sc += 3
                elif rg > 0.15: sc += 2
                elif rg > 0.05: sc += 1
            else: sc += 1
            roe = info.get('returnOnEquity')
            if roe is not None:
                if roe > 0.20: sc += 2
                elif roe > 0.12: sc += 1
            else: sc += 0.5
            om = info.get('operatingMargins')
            if om is not None:
                if om > 0.20: sc += 2
                elif om > 0.10: sc += 1.5
                elif om > 0.05: sc += 1
            else: sc += 0.5
            pe = info.get('trailingPE')
            if pe and pe > 0:
                if pe < 15: sc += 2
                elif pe < 30: sc += 1.5
                elif pe < 60: sc += 1
                elif pe < 100: sc += 0.5
            else: sc += 0.5
            fund_cache[sym] = min(15, round(sc, 1))
        except:
            fund_cache[sym] = 7.5
        if (i+1) % 50 == 0:
            print(f"    Fundamentals: {i+1}/{len(priority_syms)}")
            time.sleep(0.5)
    print(f"  Fundamentals fetched: {len(fund_cache)}")

    # Phase 3: News sentiment for top 100 stocks
    print("  Phase 3: News sentiment for top stocks...")
    cat_cache = {}
    top_100_syms = priority_syms[:100]
    for sym in top_100_syms:
        try:
            url = f"https://news.google.com/rss/search?q={sym}+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en"
            r = requests.get(url, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                txt = r.text.lower()
                cnt = txt.count('<item>')
                pos_w = ['surge','rally','profit','growth','record','strong','upgrade','buy','bullish','breakout','bonus','dividend']
                neg_w = ['fall','crash','loss','decline','weak','downgrade','sell','bearish','fraud','scam','probe','penalty']
                pos = sum(txt.count(w) for w in pos_w)
                neg = sum(txt.count(w) for w in neg_w)
                total = pos + neg
                sent = (pos - neg) / max(total, 1)
                sc = 0
                if sent > 0.3 and cnt >= 5: sc = 7
                elif sent > 0.1: sc = 5
                elif sent > -0.1: sc = 3
                else: sc = 1
                if sent < -0.2: sc = max(0, sc - 2)
                cat_cache[sym] = {'score': min(10, sc), 'sentiment': round(sent, 2), 'count': cnt}
            else:
                cat_cache[sym] = {'score': 3, 'sentiment': 0, 'count': 0}
        except:
            cat_cache[sym] = {'score': 3, 'sentiment': 0, 'count': 0}
    print(f"  News scored: {len(cat_cache)}")

    # Phase 4: Assemble final scores with entry signals
    print("  Phase 4: Assembling final scores + entry signals...")
    for sym, ts in tech_scores.items():
        try:
            d = daily[sym]
            w = weekly[sym]
            stage, rs, vp = ts['stage'], ts['rs'], ts['vp']
            
            fs = fund_cache.get(sym, 7.5)
            cs_data = cat_cache.get(sym, {'score': 3, 'sentiment': 0, 'count': 0})
            cs = cs_data['score']
            
            comp = compute_composite(stage, rs, vp, fs, cs)
            
            # Entry signal detection for Stage 2 stocks
            entry_sig, entry_det = 'N/A', ''
            if stage['full_stage'] in ('2A', '2B', '1B'):
                entry_sig, entry_det = detect_entry(d['Close'], d['High'], d['Low'], d['Volume'], w['Close'])

            # Action label for easy reading
            action_map = {
                'MUST_BUY': 'Strong Buy', 'CAN_BUY': 'Buy on Setup',
                'NEUTRAL': 'Hold / No Action', 'AVOID': 'Do Not Buy', 'SELL': 'Exit Position'
            }
            
            price = float(d['Close'].iloc[-1])
            prev_price = float(d['Close'].iloc[-2]) if len(d['Close']) > 1 else price
            chg = (price - prev_price) / prev_price * 100

            prev_sc = prev_scores.get(sym, {}).get('composite_score')
            score_chg = round(comp['composite_score'] - float(prev_sc), 1) if prev_sc else None
            prev_stage = prev_scores.get(sym, {}).get('weinstein_stage')
            stage_changed = prev_stage is not None and prev_stage != stage['full_stage']

            scores.append({
                'symbol': sym, 'score_date': today,
                'composite_score': comp['composite_score'], 'raw_composite': comp['raw_composite'],
                'bucket': comp['bucket'],
                'stage_score': stage['score'], 'rs_score': rs['score'],
                'volume_price_score': vp['score'],
                'fundamental_score': fs, 'catalyst_score': cs,
                'weinstein_stage': stage['full_stage'],
                'rs_percentile': rs['rs_percentile'], 'sector_percentile': rs['sector_percentile'],
                'rs_new_high': bool(rs['rs_new_high']),
                'stage_cap_applied': bool(comp['stage_cap_applied']),
                'price': round(price, 2), 'price_change_pct': round(chg, 2),
                'high_52w': round(float(d['High'].max()), 2),
                'low_52w': round(float(d['Low'].min()), 2),
                'price_vs_ma': round(stage.get('price_vs_ma', 0) * 100, 2),
                'ma_slope': stage.get('ma_slope', 0),
                'data_quality': 'full' if sym in fund_cache else 'tech_only',
                'score_change': score_chg,
                'stage_changed': stage_changed,
                'entry_signal': entry_sig,
                'entry_detail': entry_det[:200] if entry_det else '',
                'news_sentiment': cs_data.get('sentiment', 0),
                'news_count': cs_data.get('count', 0),
                'action_label': action_map.get(comp['bucket'], 'No Action'),
            })
        except: pass

    print(f"  Scored: {len(scores)} stocks")
    bc = Counter(s['bucket'] for s in scores)
    sc = Counter(s['weinstein_stage'] for s in scores)
    for b in ['MUST_BUY','CAN_BUY','NEUTRAL','AVOID','SELL']:
        print(f"    {b}: {bc.get(b,0)}")

    # 5. Write to Supabase
    print("\n[5/5] Writing to Supabase...")
    written = sb_upsert('ar_daily_scores', scores)
    print(f"  Written: {written}")

    elapsed = (datetime.now() - start).total_seconds() / 60

    # ── BUILD ACTIONABLE TELEGRAM ALERTS ──
    stage_changes = [s for s in scores if s.get('stage_changed')]
    big_movers = [s for s in scores if s.get('score_change') and abs(s['score_change']) >= 10]

    # Categorize stage changes by what ACTION they imply
    new_buys = []       # Moved INTO Stage 2 (buy zone)
    exits = []          # Moved OUT of Stage 2 into 3/4 (sell/exit zone)
    improving = []      # Stage 1A→1B (getting ready)
    deteriorating = []  # Moving toward Stage 4

    for s in stage_changes:
        prev_stg = prev_scores.get(s['symbol'], {}).get('weinstein_stage', '?')
        curr_stg = s['weinstein_stage']

        if curr_stg in ('2A', '2B') and prev_stg not in ('2A', '2B'):
            new_buys.append(s)
        elif curr_stg in ('3', '4') and prev_stg in ('2A', '2B'):
            exits.append(s)
        elif curr_stg == '1B' and prev_stg == '1A':
            improving.append(s)
        elif curr_stg == '4' and prev_stg != '4':
            deteriorating.append(s)

    top = sorted(scores, key=lambda x: -x['composite_score'])[:5]

    # ── MESSAGE 1: Daily Summary (concise) ──
    msg1 = f"""🎯 <b>AlphaRadar — {today}</b>
{len(scores)} stocks scored

🟢 Must Buy: {bc.get('MUST_BUY', 0)} | 🔵 Can Buy: {bc.get('CAN_BUY', 0)}
⚪ Neutral: {bc.get('NEUTRAL', 0)} | 🟡 Avoid: {bc.get('AVOID', 0)} | 🔴 Sell: {bc.get('SELL', 0)}

<b>Top 5 (highest conviction):</b>
"""
    for t in top:
        chg_str = f" ({t.get('score_change',0):+.1f})" if t.get('score_change') else ""
        msg1 += f"▸ <b>{t['symbol']}</b> {t['composite_score']:.0f}{chg_str} · ₹{t['price']:.0f} · RS {t['rs_percentile']:.0f}%\n"

    msg1 += f"\n🔗 https://alpharadar.streamlit.app"
    send_telegram(msg1)

    # ── MESSAGE 2: Action Alerts (only if there are actionable events) ──
    if new_buys or exits:
        msg2 = f"📢 <b>ACTION REQUIRED — {today}</b>\n"

        if new_buys:
            msg2 += f"\n🟢 <b>NEW BUY SIGNALS ({len(new_buys)}):</b>\n"
            msg2 += "<i>These stocks just entered Stage 2 (uptrend confirmed). Consider adding to watchlist or buying on pullback.</i>\n\n"
            for s in sorted(new_buys, key=lambda x: -x['composite_score']):
                prev_stg = prev_scores.get(s['symbol'], {}).get('weinstein_stage', '?')
                msg2 += f"▸ <b>{s['symbol']}</b> Score {s['composite_score']:.0f} · ₹{s['price']:.0f}\n"
                msg2 += f"  Stage {prev_stg}→{s['weinstein_stage']} · RS {s['rs_percentile']:.0f}%\n\n"

        if exits:
            msg2 += f"\n🔴 <b>EXIT SIGNALS ({len(exits)}):</b>\n"
            msg2 += "<i>These stocks left Stage 2 and entered distribution/decline. If you hold any, consider exiting.</i>\n\n"
            for s in sorted(exits, key=lambda x: x['composite_score']):
                prev_stg = prev_scores.get(s['symbol'], {}).get('weinstein_stage', '?')
                msg2 += f"▸ <b>{s['symbol']}</b> Score {s['composite_score']:.0f} · ₹{s['price']:.0f}\n"
                msg2 += f"  Stage {prev_stg}→{s['weinstein_stage']} · RS {s['rs_percentile']:.0f}%\n\n"

        send_telegram(msg2)

    # ── MESSAGE 3: Watchlist (improving stocks, only if any) ──
    if improving:
        msg3 = f"👀 <b>WATCHLIST — {today}</b>\n"
        msg3 += f"<i>{len(improving)} stocks moved from Stage 1A (early basing) to 1B (late basing). These are building bases and may break out into Stage 2 soon. Not buy signals yet — watch for breakout above the 30-week moving average.</i>\n\n"
        for s in sorted(improving, key=lambda x: -x['composite_score'])[:8]:
            msg3 += f"▸ <b>{s['symbol']}</b> Score {s['composite_score']:.0f} · ₹{s['price']:.0f} · RS {s['rs_percentile']:.0f}%\n"
        send_telegram(msg3)
    print(f"\n✅ Scoring complete! {len(scores)} stocks, {elapsed:.1f} min")

    # ── MARKET PULSE: compute and store daily breadth metrics ──
    print("\n📡 Running Market Pulse engine…")
    try:
        from market_pulse_engine import run_market_pulse
        pulse_summary = run_market_pulse()
        if "error" not in pulse_summary:
            adv = pulse_summary['advancing']
            dec = pulse_summary['declining']
            ad_r = round(adv/dec, 2) if dec else adv
            pulse_msg = (
                f"\n📡 <b>Market Pulse Updated — {today}</b>\n"
                f"{pulse_summary['stocks_computed']} stocks computed\n\n"
                f"{'🟢' if adv > dec else '🔴'} Advance/Decline: {adv}/{dec} (ratio {ad_r})\n"
                f"📈 New 52W Highs: {pulse_summary['new_52w_highs']} | "
                f"📉 Lows: {pulse_summary['new_52w_lows']}\n"
                f"🚀 Stage 2: {pulse_summary['stage2_count']} | "
                f"🔊 Vol Surges: {pulse_summary['vol_surges']}\n"
                f"\n🔗 https://alpharadar.streamlit.app"
            )
            send_telegram(pulse_msg)
            print(f"✅ Market Pulse: {pulse_summary['stocks_computed']} stocks written")
        else:
            print(f"⚠️ Market Pulse error: {pulse_summary['error']}")
    except Exception as e:
        print(f"⚠️ Market Pulse failed: {e}")

if __name__ == '__main__':
    main()
