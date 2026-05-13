"""
AlphaRadar — Market Pulse Engine
==================================
Computes daily metrics for all NSE stocks and writes to ar_market_pulse.
Called by:
  1. daily_cron.py  (automatic, GitHub Actions, 4:45 PM IST)
  2. Market Pulse page "Refresh" button (manual trigger)

Design:
  - Fetches universe from ar_daily_scores (latest date) — pre-validated, ~750+ stocks
  - Downloads 1 year daily OHLCV in batches of 100 via yfinance
  - Computes RSI, RS vs Nifty, Volume analysis, MAs, Weinstein, Minervini
  - Upserts everything to ar_market_pulse
  - Returns summary dict for Telegram notification
"""

import io, os, csv, time, requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

# ─────────────────────────────────────────────
#  CONFIG — works standalone (cron) or via st.secrets (UI)
# ─────────────────────────────────────────────
def get_config():
    """Return (SUPABASE_URL, SUPABASE_KEY) from env or st.secrets."""
    try:
        import streamlit as st
        return st.secrets["supabase"]["url"], st.secrets["supabase"]["key"]
    except Exception:
        return (
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )

def sb_headers(key):
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal"}

# ─────────────────────────────────────────────
#  SYMBOL MAP  (NSE → correct yfinance suffix)
# ─────────────────────────────────────────────
YF_OVERRIDE = {
    "INFOSYS":    "INFY",
    "MCDOWELL-N": "UBL",
    "ZOMATO":     "ETERNAL",
}

def to_yf(sym):
    return YF_OVERRIDE.get(sym, sym) + ".NS"

# ─────────────────────────────────────────────
#  INDICATORS
# ─────────────────────────────────────────────
def calc_rsi(s: pd.Series, n=14) -> float:
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1/n, min_periods=n).mean()
    l = (-d).clip(lower=0).ewm(alpha=1/n, min_periods=n).mean()
    r = (100 - 100/(1 + g/l.replace(0, np.nan))).dropna()
    return round(float(r.iloc[-1]), 1) if len(r) else 50.0

def rsi_tag(v):
    if v >= 70: return "Overbought"
    if v >= 60: return "Bullish"
    if v >= 40: return "Neutral"
    if v >= 30: return "Bearish"
    return "Oversold"

def calc_rs63(stock_close, bench_close):
    s, b = np.array(stock_close), np.array(bench_close)
    n = min(63, len(s), len(b))
    if n < 10: return 0.0
    return round((s[-1]/s[-n] - b[-1]/b[-n]) * 100, 2)

def calc_weinstein(close: pd.Series) -> str:
    try:
        m = close.rolling(150).mean()
        if len(m.dropna()) < 30: return "?"
        c, mv, mp = float(close.iloc[-1]), float(m.iloc[-1]), float(m.iloc[-20])
        pv = (c - mv)/mv*100; sl = (mv - mp)/mp*100
        if pv > 5 and sl > 0.3:    return "2A"
        if pv < -5 and sl < -0.3:  return "4"
        if abs(pv) <= 5 and sl > 0.3: return "3"
        if pv > 0: return "2A"
        return "1A"
    except: return "?"

def calc_minervini(close, ma50, ma150, ma200):
    try:
        c = float(close.iloc[-1])
        m50  = float(ma50.iloc[-1])  if ma50.dropna().__len__()  else c
        m150 = float(ma150.iloc[-1]) if ma150.dropna().__len__() else c
        m200 = float(ma200.iloc[-1]) if ma200.dropna().__len__() else c
        m200p = float(ma200.iloc[-22]) if len(ma200.dropna()) > 22 else m200
        hi52 = float(close.tail(252).max())
        lo52 = float(close.tail(252).min())
        score = sum([
            c > m150, c > m200, m200 > m200p,
            m50 > m150, m50 > m200, c > m50,
            (c - lo52)/lo52*100 >= 25,
            (c - hi52)/hi52*100 >= -25,
        ])
        if score >= 7: tag = "✅ Full"
        elif score >= 5: tag = "⚠ Partial"
        else: tag = "✗ Weak"
        return score, tag
    except: return 0, "✗ Weak"

def vol_tag(ratio, is_ath_vol=False):
    if is_ath_vol: return "🏆 ATH Vol"
    if ratio >= 3.0: return "🔥 3x+ Surge"
    if ratio >= 2.0: return "🔥 2x Surge"
    if ratio >= 1.5: return "⬆ High Vol"
    if ratio >= 1.0: return "✅ Above Avg"
    if ratio >= 0.5: return "↘ Below Avg"
    return "🔇 Very Low"

# ─────────────────────────────────────────────
#  DOWNLOAD HELPERS
# ─────────────────────────────────────────────
def download_nifty(period="1y"):
    df = yf.download("^NSEI", period=period, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df.columns = [c.lower() for c in df.columns]
    return df

def download_batch(nse_symbols, period="1y", chunk=80):
    """Download OHLCV for NSE symbols. Returns {symbol: df_lowercase}."""
    result = {}
    for i in range(0, len(nse_symbols), chunk):
        sub = nse_symbols[i:i+chunk]
        yf_tickers = [to_yf(s) for s in sub]
        sym_map = {to_yf(s): s for s in sub}
        try:
            raw = yf.download(yf_tickers, period=period, auto_adjust=True,
                              progress=False, group_by="ticker", threads=True)
            if raw.empty: continue
            if isinstance(raw.columns, pd.MultiIndex):
                level0 = raw.columns.get_level_values(0).unique().tolist()
                for yft in yf_tickers:
                    sym = sym_map.get(yft, yft.replace(".NS",""))
                    if yft not in level0: continue
                    sub_df = raw[yft].copy()
                    sub_df.columns = [c.lower() for c in sub_df.columns]
                    sub_df = sub_df.dropna(subset=["close"])
                    if len(sub_df) >= 20:
                        result[sym] = sub_df
            time.sleep(0.5)
        except Exception as e:
            print(f"  Batch error {i}: {e}")
    return result

# ─────────────────────────────────────────────
#  COMPUTE ONE STOCK
# ─────────────────────────────────────────────
def compute_one(sym, df, bench_close, nifty_chg, universe_meta):
    try:
        close = df["close"].squeeze()
        vol   = df["volume"].squeeze() if "volume" in df.columns else pd.Series(dtype=float)
        high  = df["high"].squeeze()   if "high"   in df.columns else close
        low   = df["low"].squeeze()    if "low"    in df.columns else close

        if len(close) < 20: return None

        cmp   = round(float(close.iloc[-1]), 2)
        prev  = round(float(close.iloc[-2]), 2) if len(close) > 1 else cmp
        chg   = round((cmp - prev)/prev*100, 2) if prev else 0.0
        chg_a = round(cmp - prev, 2)

        # Volume
        vt   = int(vol.iloc[-1]) if len(vol) else 0
        v10  = float(vol.iloc[-11:-1].mean()) if len(vol) > 10 else float(vol.mean() or 1)
        vr   = round(vt / v10, 2) if v10 else 1.0
        vmax = int(vol.max()) if len(vol) else 0
        vtag = vol_tag(vr, vt >= vmax * 0.95 and vmax > 0)

        # Price levels
        ath    = round(float(close.max()), 2)
        h52w   = round(float(close.tail(252).max()), 2) if len(close) >= 252 else ath
        l52w   = round(float(close.tail(252).min()), 2) if len(close) >= 252 else round(float(close.min()), 2)
        p_ath  = round((cmp - ath)  / ath  * 100, 1)
        p_52wh = round((cmp - h52w) / h52w * 100, 1)
        p_52wl = round((cmp - l52w) / l52w * 100, 1)

        # MAs
        ma20s  = close.rolling(20).mean()
        ma50s  = close.rolling(50).mean()
        ma150s = close.rolling(150).mean()
        ma200s = close.rolling(200).mean()
        ma20  = round(float(ma20s.iloc[-1]),  2) if ma20s.dropna().__len__()  else cmp
        ma50  = round(float(ma50s.iloc[-1]),  2) if ma50s.dropna().__len__()  else cmp
        ma200 = round(float(ma200s.iloc[-1]), 2) if ma200s.dropna().__len__() else cmp
        vs20  = round((cmp - ma20)  / ma20  * 100, 1)
        vs50  = round((cmp - ma50)  / ma50  * 100, 1)
        vs200 = round((cmp - ma200) / ma200 * 100, 1)

        # RSI
        rsi_v = calc_rsi(close)
        rtag  = rsi_tag(rsi_v)

        # RS vs Nifty 63d
        rs63 = calc_rs63(close.values, bench_close.values)

        # Stage + Minervini
        stage    = calc_weinstein(close)
        mv_score, mv_tag = calc_minervini(close, ma50s, ma150s, ma200s)

        # Composite score (0-100)
        rs_c  = min(30, max(0, (rs63 + 20) / 40 * 30))
        pr_c  = min(20, max(0, (1 - abs(p_ath) / 50) * 20))
        vl_c  = min(15, max(0, min(vr/3, 1) * 15))
        rs_i  = min(15, max(0, (1 - abs(rsi_v - 55) / 45) * 15))
        mv_c  = mv_score / 8 * 20
        comp  = round(rs_c + pr_c + vl_c + rs_i + mv_c, 1)

        meta = universe_meta.get(sym, {})

        return {
            "symbol":          sym,
            "pulse_date":      datetime.now().strftime("%Y-%m-%d"),
            "company_name":    meta.get("company_name", sym)[:80],
            "sector":          meta.get("industry", "")[:60],
            "cap_bucket":      meta.get("cap_bucket", ""),
            "cmp":             cmp,
            "chg_pct":         chg,
            "chg_abs":         chg_a,
            "vol_today":       vt,
            "vol_10d_avg":     int(v10),
            "vol_ratio":       vr,
            "vol_tag":         vtag,
            "ath":             ath,
            "from_ath_pct":    p_ath,
            "high_52w":        h52w,
            "from_52wh_pct":   p_52wh,
            "low_52w":         l52w,
            "from_52wl_pct":   p_52wl,
            "ma20":            ma20,
            "ma50":            ma50,
            "ma200":           ma200,
            "vs_ma20_pct":     vs20,
            "vs_ma50_pct":     vs50,
            "vs_ma200_pct":    vs200,
            "above_ma50":      bool(cmp > ma50),
            "above_ma200":     bool(cmp > ma200),
            "rsi14":           rsi_v,
            "rsi_tag":         rtag,
            "rs_63d":          rs63,
            "rs_rank":         0,   # filled after ranking
            "weinstein_stage": stage,
            "minervini_score": mv_score,
            "minervini_tag":   mv_tag,
            "composite_score": comp,
            "score_rank":      0,   # filled after ranking
            "nifty_chg_pct":   nifty_chg,
            "rel_vs_nifty":    round(chg - nifty_chg, 2),
        }
    except Exception as e:
        return None

# ─────────────────────────────────────────────
#  MAIN ENTRY POINT
# ─────────────────────────────────────────────
def run_market_pulse(progress_cb=None):
    """
    Compute market pulse for all available stocks and write to Supabase.
    progress_cb(pct: float, msg: str) → optional callback for UI progress.
    Returns summary dict.
    """
    def prog(pct, msg):
        print(f"  [{pct:3.0f}%] {msg}")
        if progress_cb: progress_cb(pct, msg)

    URL, KEY = get_config()
    hdrs_read  = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
    hdrs_write = sb_headers(KEY)

    # ── 1. Load universe from ar_daily_scores + ar_universe ──
    prog(3, "Loading universe from Supabase…")
    
    # Get latest scored symbols
    sym_set = set()
    for offset in range(0, 3000, 1000):
        r = requests.get(
            f"{URL}/rest/v1/ar_daily_scores?select=symbol&order=composite_score.desc"
            f"&limit=1000&offset={offset}",
            headers=hdrs_read
        )
        batch = r.json() if r.status_code == 200 else []
        if not batch or not isinstance(batch, list): break
        sym_set.update(d["symbol"] for d in batch if "symbol" in d)
        if len(batch) < 1000: break

    # Also fetch metadata
    universe_meta = {}
    r2 = requests.get(
        f"{URL}/rest/v1/ar_universe?select=symbol,company_name,industry,cap_bucket&is_active=eq.true&limit=2000",
        headers=hdrs_read
    )
    if r2.status_code == 200:
        for d in r2.json():
            universe_meta[d["symbol"]] = d

    symbols = sorted(sym_set)
    prog(5, f"Universe: {len(symbols)} stocks")

    # ── 2. Download Nifty benchmark ──
    prog(8, "Downloading Nifty 50 benchmark…")
    bench_df = download_nifty("1y")
    if bench_df.empty:
        return {"error": "Could not download Nifty 50 data"}
    bench_close = bench_df["close"].squeeze()
    nifty_chg = round(
        (float(bench_close.iloc[-1]) - float(bench_close.iloc[-2])) /
        float(bench_close.iloc[-2]) * 100, 2
    ) if len(bench_close) > 1 else 0.0
    prog(10, f"Nifty: {nifty_chg:+.2f}% today")

    # ── 3. Download all stock data in batches ──
    prog(12, f"Downloading {len(symbols)} stocks via yfinance (this takes 3-5 min)…")
    stock_data = download_batch(symbols, period="1y", chunk=80)
    prog(65, f"Downloaded {len(stock_data)}/{len(symbols)} stocks")

    # ── 4. Compute metrics ──
    prog(67, "Computing indicators for all stocks…")
    records = []
    for i, sym in enumerate(symbols):
        if sym not in stock_data: continue
        row = compute_one(sym, stock_data[sym], bench_close, nifty_chg, universe_meta)
        if row: records.append(row)
        if i % 50 == 0:
            prog(67 + int(i/len(symbols)*20), f"Computed {i+1}/{len(symbols)}…")

    prog(88, f"Computed {len(records)} stock metrics — ranking…")

    # ── 5. Rank RS and Score ──
    if records:
        df_r = pd.DataFrame(records)
        df_r["rs_rank"]    = df_r["rs_63d"].rank(ascending=False, method="min").astype(int)
        df_r["score_rank"] = df_r["composite_score"].rank(ascending=False, method="min").astype(int)
        records = df_r.to_dict("records")

    # ── 6. Upsert to Supabase ──
    prog(90, f"Writing {len(records)} rows to Supabase ar_market_pulse…")
    total_written = 0
    batch_size = 100
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        # Clean numpy types
        clean = []
        for row in batch:
            cr = {}
            for k, v in row.items():
                if isinstance(v, (np.bool_,)): cr[k] = bool(v)
                elif isinstance(v, (np.integer,)): cr[k] = int(v)
                elif isinstance(v, (np.floating,)): cr[k] = float(v) if not np.isnan(v) else None
                elif isinstance(v, float) and (v != v): cr[k] = None  # NaN check
                else: cr[k] = v
            clean.append(cr)
        r = requests.post(f"{URL}/rest/v1/ar_market_pulse", headers=hdrs_write, json=clean)
        if r.status_code in (200, 201):
            total_written += len(clean)
        else:
            print(f"  Write error batch {i//batch_size}: {r.status_code} {r.text[:100]}")

    prog(99, f"Written {total_written} rows ✅")

    # Build summary
    df_r = pd.DataFrame(records) if records else pd.DataFrame()
    summary = {
        "stocks_computed": len(records),
        "stocks_written":  total_written,
        "nifty_chg":       nifty_chg,
        "advancing":       int((df_r["chg_pct"] > 0).sum()) if not df_r.empty else 0,
        "declining":       int((df_r["chg_pct"] < 0).sum()) if not df_r.empty else 0,
        "new_52w_highs":   int((df_r["from_52wh_pct"] >= -1.5).sum()) if not df_r.empty else 0,
        "new_52w_lows":    int((df_r["from_52wl_pct"] <= 2.5).sum()) if not df_r.empty else 0,
        "vol_surges":      int((df_r["vol_ratio"] >= 1.5).sum()) if not df_r.empty else 0,
        "stage2_count":    int((df_r["weinstein_stage"] == "2A").sum()) if not df_r.empty else 0,
        "pulse_date":      datetime.now().strftime("%Y-%m-%d"),
        "computed_at":     datetime.now().strftime("%d %b %Y %H:%M IST"),
    }
    prog(100, f"✅ Done. {len(records)} stocks computed, {total_written} written.")
    return summary


if __name__ == "__main__":
    print("Running Market Pulse Engine standalone…")
    summary = run_market_pulse()
    print("\n=== SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
