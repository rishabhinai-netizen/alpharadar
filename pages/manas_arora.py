# ============================================================
# MANAS ARORA TAB — AlphaRadar
# File: pages/manas_arora.py  (drop into your pages/ folder)
#
# Streamlit Secrets Required:
#   BREEZE_API_KEY        → from ICICIdirect API portal
#   BREEZE_API_SECRET     → from ICICIdirect API portal
#   BREEZE_SESSION_TOKEN  → refresh DAILY from ICICIdirect.com
#                           Settings → API Sessions → Generate Token
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta, date
import plotly.graph_objects as go
import plotly.express as px
import time
import warnings
warnings.filterwarnings("ignore")

try:
    from breeze_connect import BreezeConnect
    BREEZE_AVAILABLE = True
except ImportError:
    BREEZE_AVAILABLE = False

# ─────────────────────────────────────────────────────────────
# 0. PAGE CONFIG & STYLING
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__" or not hasattr(st, "_alpharadar_config_set"):
    try:
        st.set_page_config(page_title="Manas Arora — AlphaRadar", page_icon="🎯", layout="wide")
    except Exception:
        pass

st.markdown("""
<style>
/* ── Core Variables ── */
:root {
  --accent:   #c0392b;
  --gold:     #b8860b;
  --green:    #1a6b3c;
  --blue:     #1a3c6b;
  --bg-card:  #ffffff;
  --bg-page:  #f7f5f1;
  --border:   #e5e0d8;
  --text:     #0f0f0f;
  --muted:    #6b6b6b;
}

/* ── Header Banner ── */
.ma-banner {
  background: linear-gradient(135deg, #0f0f0f 0%, #1c1c2e 100%);
  padding: 1.5rem 2rem;
  border-radius: 12px;
  border-left: 5px solid #c0392b;
  margin-bottom: 1.5rem;
}
.ma-banner h1 {
  color: white; font-size: 1.6rem; font-weight: 800;
  margin: 0 0 4px 0; letter-spacing: -0.02em;
}
.ma-banner p { color: rgba(255,255,255,0.55); font-size: 0.85rem; margin: 0; }
.ma-banner .tag {
  display: inline-block; background: #c0392b; color: white;
  font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em;
  padding: 2px 10px; border-radius: 20px; margin-right: 8px;
  text-transform: uppercase;
}

/* ── Metric Cards ── */
.metric-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 1rem; }
.metric-card {
  background: white; border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 18px; min-width: 130px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.metric-card .val {
  font-size: 1.5rem; font-weight: 800; color: var(--accent); line-height: 1;
}
.metric-card .lbl {
  font-size: 0.7rem; font-weight: 700; letter-spacing: 0.07em;
  text-transform: uppercase; color: var(--muted); margin-top: 4px;
}

/* ── Score Badge ── */
.score-5 { color: #1a6b3c; font-weight: 800; }
.score-4 { color: #2980b9; font-weight: 700; }
.score-3 { color: #f39c12; font-weight: 700; }
.score-2 { color: #e67e22; font-weight: 600; }
.score-1 { color: #95a5a6; font-weight: 600; }

/* ── Alert Boxes ── */
.alert-warn {
  background: #fff8e1; border: 1px solid #ffd54f;
  border-left: 4px solid #f9a825; border-radius: 8px;
  padding: 12px 16px; font-size: 0.85rem; color: #5d4037;
}
.alert-info {
  background: #e8f4fd; border: 1px solid #90caf9;
  border-left: 4px solid #1565c0; border-radius: 8px;
  padding: 12px 16px; font-size: 0.85rem; color: #0d47a1;
}
.alert-success {
  background: #edf7f1; border: 1px solid #a5d6a7;
  border-left: 4px solid #1a6b3c; border-radius: 8px;
  padding: 12px 16px; font-size: 0.85rem; color: #1b5e20;
}

/* ── Rule Cards ── */
.rule-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 12px 0; }
.rule-card {
  background: white; border: 1px solid var(--border);
  border-radius: 10px; padding: 16px;
}
.rule-card h4 { font-size: 0.85rem; font-weight: 700; margin-bottom: 8px; }
.rule-card li { font-size: 0.82rem; color: var(--muted); margin: 4px 0; }
.rule-never  { border-top: 3px solid #c0392b; }
.rule-always { border-top: 3px solid #1a6b3c; }

/* ── Quote Block ── */
.qblock {
  border-left: 3px solid var(--accent);
  padding: 10px 16px; background: #fdf0ee;
  border-radius: 0 6px 6px 0; font-style: italic;
  font-size: 0.85rem; color: #444; margin: 10px 0;
}

/* ── Setup Card ── */
.setup-card {
  background: white; border: 1px solid var(--border);
  border-radius: 10px; overflow: hidden;
  margin-bottom: 12px;
}
.setup-head {
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  font-weight: 700; font-size: 0.9rem;
  display: flex; align-items: center; gap: 8px;
}
.setup-body { padding: 14px 16px; }
.setup-body li { font-size: 0.82rem; color: var(--muted); margin: 5px 0; }

/* ── Criteria Pills ── */
.pill {
  display: inline-block; padding: 2px 10px; border-radius: 20px;
  font-size: 0.72rem; font-weight: 700; margin: 2px;
}
.pill-pass { background: #edf7f1; color: #1a6b3c; }
.pill-fail { background: #fdf0ee; color: #c0392b; }
.pill-na   { background: #f0f0f0; color: #999; }

/* ── Flow Step ── */
.flow-step {
  display: flex; gap: 14px; padding: 14px 0;
  border-bottom: 1px dashed var(--border);
}
.flow-num {
  width: 30px; height: 30px; background: var(--accent);
  color: white; border-radius: 50%; display: flex;
  align-items: center; justify-content: center;
  font-size: 0.8rem; font-weight: 800; flex-shrink: 0;
}
.flow-title { font-weight: 700; font-size: 0.9rem; margin-bottom: 4px; }
.flow-desc  { font-size: 0.82rem; color: var(--muted); }

/* ── Breadth Table ── */
.btable { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.btable th {
  background: #f0f0f0; padding: 8px 12px; text-align: left;
  font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
  font-size: 0.72rem; color: var(--muted);
}
.btable td { padding: 8px 12px; border-bottom: 1px solid var(--border); }
.bull { color: #1a6b3c; font-weight: 700; }
.bear { color: #c0392b; font-weight: 700; }
.neut { color: #b8860b; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 1. CONSTANTS
# ─────────────────────────────────────────────────────────────

# NSE Small/Mid-Cap universe — Manas's preferred hunting ground
NSE_UNIVERSE_FALLBACK = [
    "ZENTEC","EPACK","MAZDOCK","BSE","RCF","NFL","COCHINSHIP","LGEQUIP",
    "MIRZAINT","ADANIENT","AMBER","AEROFLEX","RHIM","SHRIRAMFIN","TITAGARH",
    "NLCINDIA","POONAWALLA","RVNL","DIXON","KAYNES","SYRMA","JYOTHYLAB",
    "NEWGEN","DATAPATTNS","GARWARE","DEEPAKNTR","GRINDWELL","SOLARINDS",
    "TBOTEK","BLUESTARCO","ELGIEQUIP","SCHAEFFLER","KPITTECH","LTTS",
    "PERSISTENT","COFORGE","MPHASIS","ZENSARTECH","BIRLASOFT","MASTEK",
    "APLAPOLLO","JSPL","RATNAMANI","WELSPUNIND","CENTURYPLY","GREENPLY",
    "CERA","ASTERDM","POLYMED","MAXHEALTH","METROPOLIS","LALPATHLAB",
    "FINCABLES","ENDURANCE","SUPRAJIT","MINDA","MOTHERSON","SUNDRMFAST",
    "TITAN","KALYANKJIL","SENCO","RAJESHEXPO","GOLDIAM","VSTIND","ITC",
    "JUBLFOOD","DEVYANI","WESTLIFE","GRSE","BEL","HAL","BEML","MIDHANI",
    "ELECON","GMRINFRA","PRAJIND","GALAXYSURF","VINATI","AAVAS","UGROCAP",
    "MUTHOOTFIN","MANAPPURAM","NYKAA","CAMPUS","VBL","HATSUN","DODLA",
    "PAGEIND","SYMPHONY","BALAMINES","ASTRAL","FINPIPE","PRINCEPIPE",
    "SAREGAMA","NAZARA","RATEGAIN","HOMEFIRST","APTUS","FIVESTAR",
    "SBICARDS","JIOFIN","BANKBEES","TATAELXSI","INFOEDGE","POLICYBZR",
    "NUVOCO","KFINTECH","CAMSB","ANGELONE","IIFL","MOTILALOFS",
]

@st.cache_data(ttl=3600, show_spinner=False)
def load_manas_universe():
    """Load full NSE universe from Supabase ar_universe. Falls back to hardcoded list."""
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        hdrs = {"apikey": key, "Authorization": f"Bearer {key}"}
        r = requests.get(
            f"{url}/rest/v1/ar_universe?select=symbol&is_active=eq.true&limit=2000",
            headers=hdrs, timeout=8
        )
        if r.status_code == 200:
            data = r.json()
            syms = [d["symbol"] for d in data if "symbol" in d]
            if len(syms) > 50:
                return syms
    except Exception:
        pass
    return NSE_UNIVERSE_FALLBACK

NSE_UNIVERSE = load_manas_universe()
NSE_UNIVERSE = list(dict.fromkeys(NSE_UNIVERSE))  # deduplicate

# Breeze code overrides for stocks with non-standard mapping
BREEZE_MAP = {
    "MAZDOCK":   "MAZDOC",
    "COCHINSHIP":"COCHIN",
    "LGEQUIP":   "LGEQU",
    "MIRZAINT":  "MIRZAI",
    "ADANIENT":  "ADANIENS",
}

def breeze_code(sym):
    return BREEZE_MAP.get(sym, sym)

# Documented trade history — 16 trades from 32 video sources
TRADE_HISTORY = [
    {"stock":"Adani Enterprises","type":"Continuation","entry_date":"2023-04-12","exit_date":"2023-05-19","entry":2313,"exit_price":3124,"setup":"VCP+SS","stop_pct":1.0,"gain_pct":35,"days":37,"r_multiple":35,"outcome":"Win","sector":"Infra"},
    {"stock":"RCF","type":"Continuation","entry_date":"2023-06-05","exit_date":"2023-06-08","entry":98.8,"exit_price":119.5,"setup":"VCP+SS","stop_pct":1.0,"gain_pct":21,"days":3,"r_multiple":21,"outcome":"Win","sector":"Chemicals"},
    {"stock":"Zentec","type":"Continuation","entry_date":"2023-07-18","exit_date":"2023-08-18","entry":215,"exit_price":340,"setup":"VCP+SS+Busted","stop_pct":1.5,"gain_pct":58,"days":31,"r_multiple":39,"outcome":"Win","sector":"Defense"},
    {"stock":"BSE Limited","type":"Continuation","entry_date":"2023-09-04","exit_date":"2023-09-25","entry":1460,"exit_price":2409,"setup":"VCP+SS","stop_pct":0.5,"gain_pct":65,"days":21,"r_multiple":100,"outcome":"Win","sector":"Financial"},
    {"stock":"Mirza International","type":"Continuation","entry_date":"2024-01-08","exit_date":"2024-01-09","entry":48,"exit_price":57.6,"setup":"VCP+SS","stop_pct":1.5,"gain_pct":20,"days":1,"r_multiple":13,"outcome":"Win","sector":"Footwear"},
    {"stock":"Cochin Shipyard","type":"Continuation","entry_date":"2024-02-14","exit_date":"2024-03-05","entry":820,"exit_price":1353,"setup":"VCP+MA","stop_pct":1.5,"gain_pct":65,"days":20,"r_multiple":43,"outcome":"Win","sector":"Defense"},
    {"stock":"LG Equipments","type":"Continuation","entry_date":"2024-03-20","exit_date":"2024-03-25","entry":310,"exit_price":384,"setup":"VCP+SS","stop_pct":1.5,"gain_pct":24,"days":5,"r_multiple":16,"outcome":"Win","sector":"Industrials"},
    {"stock":"Mazagon Dock","type":"Continuation","entry_date":"2024-04-02","exit_date":"2024-04-09","entry":930,"exit_price":1404,"setup":"VCP+Sector","stop_pct":1.5,"gain_pct":51,"days":7,"r_multiple":34,"outcome":"Win","sector":"Defense"},
    {"stock":"PAYTM","type":"Reversal","entry_date":"2024-05-06","exit_date":"2024-05-08","entry":1002,"exit_price":1122,"setup":"Climax Bar","stop_pct":1.5,"gain_pct":12,"days":2,"r_multiple":8,"outcome":"Win","sector":"Fintech"},
    {"stock":"Amber Enterprises","type":"Reversal","entry_date":"2024-06-11","exit_date":"2024-06-12","entry":280,"exit_price":311,"setup":"Falling Knife","stop_pct":1.5,"gain_pct":11,"days":1,"r_multiple":7,"outcome":"Win","sector":"Consumer"},
    {"stock":"NFL","type":"Continuation","entry_date":"2024-07-15","exit_date":"2024-07-16","entry":78,"exit_price":78,"setup":"SVRO","stop_pct":2.0,"gain_pct":0,"days":1,"r_multiple":0,"outcome":"Break-even","sector":"Chemicals"},
    {"stock":"Radhika Jeweltech","type":"Continuation","entry_date":"2024-08-05","exit_date":"2024-08-06","entry":145,"exit_price":145,"setup":"SVRO","stop_pct":2.0,"gain_pct":0,"days":1,"r_multiple":0,"outcome":"Break-even","sector":"Jewellery"},
    {"stock":"RHIM","type":"Continuation","entry_date":"2024-09-10","exit_date":"2024-09-11","entry":265,"exit_price":265,"setup":"SVRO","stop_pct":2.0,"gain_pct":0,"days":1,"r_multiple":0,"outcome":"Break-even","sector":"Industrials"},
    {"stock":"Shriram Properties","type":"Continuation","entry_date":"2024-10-03","exit_date":"2024-10-04","entry":92,"exit_price":92,"setup":"SVRO","stop_pct":2.0,"gain_pct":0,"days":1,"r_multiple":0,"outcome":"Break-even","sector":"Realty"},
    {"stock":"RVNL","type":"Continuation","entry_date":"2024-11-12","exit_date":"2024-11-15","entry":220,"exit_price":216.7,"setup":"VCP","stop_pct":1.5,"gain_pct":-1.5,"days":3,"r_multiple":-1,"outcome":"Loss","sector":"Infra"},
    {"stock":"Poonawalla Fincorp","type":"Continuation","entry_date":"2024-12-09","exit_date":"2024-12-11","entry":310,"exit_price":303.8,"setup":"VCP+RS","stop_pct":2.0,"gain_pct":-2.0,"days":2,"r_multiple":-1,"outcome":"Loss","sector":"NBFC"},
]
TRADE_DF = pd.DataFrame(TRADE_HISTORY)

# ─────────────────────────────────────────────────────────────
# 2. BREEZE CONNECTION
# ─────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_breeze():
    if not BREEZE_AVAILABLE:
        return None, "❌ breeze_connect not installed. Run: pip install breeze-connect"
    try:
        b = BreezeConnect(api_key=st.secrets["BREEZE_API_KEY"])
        b.generate_session(
            api_secret=st.secrets["BREEZE_API_SECRET"],
            session_token=st.secrets["BREEZE_SESSION_TOKEN"],
        )
        return b, None
    except KeyError as e:
        return None, f"❌ Missing secret: {e}"
    except Exception as e:
        err = str(e)
        if "session" in err.lower() or "token" in err.lower() or "auth" in err.lower():
            return None, "🔄 Session token expired. Go to ICICIdirect.com → API → Sessions → Generate Token. Update BREEZE_SESSION_TOKEN in Streamlit Secrets."
        return None, f"❌ Breeze error: {err}"

# ─────────────────────────────────────────────────────────────
# 3. DATA HELPERS
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ohlcv(sym: str, days: int = 400) -> pd.DataFrame:
    breeze, err = get_breeze()
    if err or breeze is None:
        return pd.DataFrame()
    try:
        to_dt  = datetime.now()
        fr_dt  = to_dt - timedelta(days=days)
        resp = breeze.get_historical_data_v2(
            interval="1day",
            from_date=fr_dt.strftime("%Y-%m-%dT07:00:00.000Z"),
            to_date=to_dt.strftime("%Y-%m-%dT07:00:00.000Z"),
            stock_code=breeze_code(sym),
            exchange_code="NSE",
            product_type="cash",
        )
        if not resp or "Success" not in resp or not resp["Success"]:
            return pd.DataFrame()
        df = pd.DataFrame(resp["Success"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
        for c in ["open","high","low","close","volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna(subset=["close"])
    except Exception:
        return pd.DataFrame()

def score_stock(sym: str, df: pd.DataFrame) -> dict:
    """Apply all Manas criteria and compute a composite score."""
    if df.empty or len(df) < 30:
        return {}

    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    v = df["volume"].values if "volume" in df.columns else np.ones(len(c))
    o = df["open"].values

    cmp = float(c[-1])
    hi52 = float(np.nanmax(h[-252:])) if len(h) >= 252 else float(np.nanmax(h))
    lo52 = float(np.nanmin(l[-252:])) if len(l) >= 252 else float(np.nanmin(l))

    def sma(arr, n):
        if len(arr) < n: return np.nan
        return float(np.mean(arr[-n:]))

    ma10  = sma(c, 10)
    ma20  = sma(c, 20)
    ma30  = sma(c, 30)
    ma50  = sma(c, 50)
    ma30_1m = sma(c[:-22], 30) if len(c) > 52 else np.nan

    pct_from_hi = (hi52 - cmp) / hi52 * 100 if hi52 else 999
    pct_from_lo = (cmp - lo52) / lo52 * 100 if lo52 else 0
    perf_3m = (cmp - float(c[-63])) / float(c[-63]) * 100 if len(c) >= 63 else 0
    perf_1m = (cmp - float(c[-22])) / float(c[-22]) * 100 if len(c) >= 22 else 0

    avg_vol = float(np.nanmean(v[-21:-1])) if len(v) > 21 else 1
    rvol    = float(v[-1]) / avg_vol if avg_vol > 0 else 0
    avg_vol_20k = avg_vol >= 200_000

    # Purple Dot (last 6 months)
    rc = c[-126:]; rv = v[-126:]; rh = h[-126:]; rl = l[-126:]; ro = o[-126:]
    daily_ret = np.diff(rc) / rc[:-1] * 100
    vols_aligned = rv[1:]
    pd_green = int(np.sum((daily_ret >= 5)  & (vols_aligned >= 500_000)))
    pd_red   = int(np.sum((daily_ret <= -5) & (vols_aligned >= 500_000)))
    pd_total = pd_green + pd_red

    # Volatility contraction (last 5 days vs prior 20 days)
    rng5  = float(np.mean((h[-5:]  - l[-5:])  / c[-5:]))  * 100
    rng20 = float(np.mean((h[-25:-5] - l[-25:-5]) / c[-25:-5])) * 100 if len(c) >= 25 else rng5
    vol_contract = rng5 < rng20 * 0.75

    # Near 20 MA (within 5%)
    near_20ma = abs(cmp - ma20) / ma20 * 100 < 5 if not np.isnan(ma20) else False
    pct_from_ma20 = abs(cmp - ma20) / ma20 * 100 if not np.isnan(ma20) else 99

    # Strong Start (today)
    gap_pct = (float(o[-1]) - float(c[-2])) / float(c[-2]) * 100 if len(c) >= 2 else 0
    open_eq_low = (float(l[-1]) - float(o[-1])) / float(o[-1]) * 100 < 0.3
    strong_start = gap_pct > 0.5 and open_eq_low

    # ── Criteria Flags ──
    f = {
        "price_ok":           cmp >= 50,
        "within_25_52wh":     pct_from_hi <= 25,
        "above_50_52wl":      pct_from_lo >= 50,
        "above_30ma":         (not np.isnan(ma30)) and cmp > ma30,
        "ma30_rising":        (not np.isnan(ma30)) and (not np.isnan(ma30_1m)) and ma30 > ma30_1m,
        "ma10_above_ma30":    (not np.isnan(ma10)) and (not np.isnan(ma30)) and ma10 > ma30,
        "momentum_3m":        perf_3m >= 30,
        "liquidity_ok":       avg_vol_20k,
        "pd_green_ok":        pd_green >= 2,
        "pd_red_ok":          pd_red <= pd_green,  # more green than red dots
        "vol_contract":       vol_contract,
        "near_20ma":          near_20ma,
        "strong_start":       strong_start,
    }

    # ── Composite Score ──
    s = 0
    weights = {
        "price_ok":5, "within_25_52wh":10, "above_50_52wl":10,
        "above_30ma":10, "ma30_rising":10, "ma10_above_ma30":5,
        "momentum_3m":10, "liquidity_ok":5,
        "pd_green_ok":10, "vol_contract":10, "near_20ma":10, "strong_start":5,
    }
    for k, w in weights.items():
        if f.get(k): s += w
    if not f["pd_red_ok"]: s -= 10
    score = max(0, min(100, s))

    stars = "⭐⭐⭐⭐⭐" if score>=80 else "⭐⭐⭐⭐" if score>=65 else "⭐⭐⭐" if score>=50 else "⭐⭐" if score>=35 else "⭐"
    core_met = all(f.get(k) for k in ["price_ok","within_25_52wh","above_50_52wl","above_30ma","ma30_rising","ma10_above_ma30"])

    return {
        "symbol": sym, "cmp": round(cmp,2),
        "score": score, "grade": stars, "core_met": core_met,
        "hi52w": round(hi52,2), "lo52w": round(lo52,2),
        "pct_from_hi": round(pct_from_hi,1), "pct_from_lo": round(pct_from_lo,1),
        "ma10": round(ma10,2) if not np.isnan(ma10) else None,
        "ma20": round(ma20,2) if not np.isnan(ma20) else None,
        "ma30": round(ma30,2) if not np.isnan(ma30) else None,
        "ma50": round(ma50,2) if not np.isnan(ma50) else None,
        "perf_3m": round(perf_3m,1), "perf_1m": round(perf_1m,1),
        "avg_vol": int(avg_vol), "rvol": round(rvol,2),
        "pd_green": pd_green, "pd_red": pd_red, "pd_total": pd_total,
        "vol_contract": vol_contract, "rng5": round(rng5,2), "rng20": round(rng20,2),
        "near_20ma": near_20ma, "pct_from_ma20": round(pct_from_ma20,1),
        "gap_pct": round(gap_pct,2), "strong_start": strong_start,
        "flags": f,
    }

# ─────────────────────────────────────────────────────────────
# 4. BACKTEST DATA (from 16 documented trades)
# ─────────────────────────────────────────────────────────────

def build_backtest_data():
    df = TRADE_DF.copy()
    df["color"] = df["outcome"].map({"Win":"#1a6b3c","Break-even":"#b8860b","Loss":"#c0392b"})
    # Cumulative equity (per R, starting at 100 with 2% portfolio risk per R)
    r_vals = df["r_multiple"].values
    equity = [100.0]
    for r in r_vals:
        gain_pct = r * 2.0  # 2% portfolio risk per trade
        equity.append(round(equity[-1] * (1 + gain_pct/100), 2))
    df["cumulative_equity"] = equity[1:]

    wins   = df[df["outcome"]=="Win"]
    losses = df[df["outcome"]=="Loss"]
    be     = df[df["outcome"]=="Break-even"]

    win_rate  = len(wins) / len(df) * 100
    avg_win_r = wins["r_multiple"].mean()
    avg_los_r = abs(losses["r_multiple"].mean()) if len(losses) > 0 else 1
    expectancy = (win_rate/100 * avg_win_r) - ((1 - win_rate/100) * avg_los_r)

    return df, {"win_rate": win_rate, "avg_win_r": avg_win_r, "avg_los_r": avg_los_r,
                "expectancy": expectancy, "total": len(df),
                "wins": len(wins), "losses": len(losses), "be": len(be),
                "final_equity": equity[-1]}

def monte_carlo_simulation(win_rate=0.35, avg_r=15, avg_loss=1, n_trades=70, n_sims=1000, port_risk=0.02):
    """Simulate 1-year equity curves based on expected system parameters."""
    results = []
    for _ in range(n_sims):
        eq = 1.0
        curve = [eq]
        for _ in range(n_trades):
            if np.random.random() < win_rate:
                r = np.random.exponential(avg_r * 0.8)  # randomize winner size
                r = min(r, avg_r * 3)
            else:
                r = -avg_loss * np.random.uniform(0.5, 1.5)
            eq *= (1 + r * port_risk)
            curve.append(eq)
        results.append(curve)
    return np.array(results)

# ─────────────────────────────────────────────────────────────
# 5. MAIN UI
# ─────────────────────────────────────────────────────────────

# ── Header ──
st.markdown("""
<div class="ma-banner">
  <h1>🎯 Manas Arora — Momentum Surgeon</h1>
  <p>
    <span class="tag">Cash Only</span>
    <span class="tag">Small/Mid Cap</span>
    <span class="tag">SVRO + VCP</span>
    <span class="tag">AlphaRadar</span>
    Full system scanner · Backtest analytics · Complete playbook
  </p>
</div>
""", unsafe_allow_html=True)

# ── Breeze Status Bar ──
breeze, b_err = get_breeze()
if b_err:
    st.markdown(f'<div class="alert-warn">⚠️ <b>Breeze API:</b> {b_err}</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="alert-info">
    <b>To refresh session token:</b> Go to 
    <a href="https://api.icicidirect.com/" target="_blank">api.icicidirect.com</a> → 
    Login → Generate Token → Copy → Paste in Streamlit Secrets as <code>BREEZE_SESSION_TOKEN</code> → Reboot app.
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown('<div class="alert-success">✅ <b>Breeze API connected.</b> Live market data active.</div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── 3 Main Tabs ──
TAB_SCANNER, TAB_BACKTEST, TAB_PLAYBOOK = st.tabs([
    "🎯  Live Scanner — Today's Candidates",
    "📊  Backtest Results",
    "🧠  Playbook & Psychology",
])

# ═══════════════════════════════════════════════════════════
# TAB 1: LIVE SCANNER
# ═══════════════════════════════════════════════════════════
with TAB_SCANNER:
    st.markdown("### 🔍 Manas Arora Weekly Scanner")
    st.markdown("Applies all 7 core criteria + Purple Dot + Volatility Contraction. Run on weekends to build your Focus List.")

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        min_score = st.slider("Minimum Score", 0, 100, 50, 5, key="ma_min_score")
    with c2:
        show_ss_only = st.checkbox("Strong Start Only", False, key="ma_ss_only")
    with c3:
        show_core_only = st.checkbox("Core Criteria Met", False, key="ma_core_only")
    with c4:
        max_stocks = st.selectbox("Scan Universe Size", [25, 50, 100, len(NSE_UNIVERSE)],
                                  format_func=lambda x: f"Top {x} stocks" if x < len(NSE_UNIVERSE) else "Full universe",
                                  key="ma_universe_size")

    run_col, _ = st.columns([1, 3])
    with run_col:
        run_scan = st.button("▶ Run Scanner", type="primary", use_container_width=True, key="ma_run_scan")

    if run_scan:
        if not breeze:
            st.error("Cannot scan — Breeze API not connected. Fix the session token first.")
        else:
            universe = NSE_UNIVERSE[:max_stocks]
            results = []
            prog = st.progress(0, text="Scanning NSE universe...")
            for i, sym in enumerate(universe):
                prog.progress((i+1)/len(universe), text=f"Scanning {sym} ({i+1}/{len(universe)})...")
                df = fetch_ohlcv(sym, days=400)
                if not df.empty:
                    m = score_stock(sym, df)
                    if m:
                        results.append(m)
                time.sleep(0.08)  # rate limit buffer
            prog.empty()

            if not results:
                st.warning("No results returned. Check Breeze connection and try again.")
            else:
                df_res = pd.DataFrame(results)
                # Apply filters
                df_res = df_res[df_res["score"] >= min_score]
                if show_ss_only:
                    df_res = df_res[df_res["strong_start"] == True]
                if show_core_only:
                    df_res = df_res[df_res["core_met"] == True]
                df_res = df_res.sort_values("score", ascending=False).reset_index(drop=True)

                st.session_state["manas_scan_results"] = df_res
                st.success(f"✅ Scan complete — {len(df_res)} stocks meet your criteria out of {len(results)} scanned.")

    # Show results
    if "manas_scan_results" in st.session_state:
        df_res = st.session_state["manas_scan_results"]

        # Summary metrics
        if not df_res.empty:
            five_star  = len(df_res[df_res["score"] >= 80])
            four_star  = len(df_res[(df_res["score"] >= 65) & (df_res["score"] < 80)])
            ss_count   = len(df_res[df_res["strong_start"] == True])
            vcp_count  = len(df_res[df_res["vol_contract"] == True])
            core_count = len(df_res[df_res["core_met"] == True])

            st.markdown(f"""
            <div class="metric-row">
              <div class="metric-card"><div class="val">{five_star}</div><div class="lbl">5-Star Setups</div></div>
              <div class="metric-card"><div class="val">{four_star}</div><div class="lbl">4-Star Setups</div></div>
              <div class="metric-card"><div class="val">{core_count}</div><div class="lbl">All Core Met</div></div>
              <div class="metric-card"><div class="val">{ss_count}</div><div class="lbl">Strong Start Today</div></div>
              <div class="metric-card"><div class="val">{vcp_count}</div><div class="lbl">VCP Contracting</div></div>
            </div>
            """, unsafe_allow_html=True)

        # Results Table
        # ── Signal Legend ──
        st.markdown("""
        <div style="background:#f7f5f1;border:1px solid #e5e0d8;border-radius:8px;padding:12px 16px;margin-bottom:12px;font-size:12.5px">
        <b>Signal Guide:</b> &nbsp;
        🟣 <b>Purple Dot (Green)</b> — Day with ≥5% gain on volume ≥5L. Signals institutional accumulation. Want ≥2 in last 6 months. &nbsp;|&nbsp;
        🔴 <b>Purple Dot (Red)</b> — Day with ≥5% fall on volume ≥5L. Distribution. Want fewer than green dots. &nbsp;|&nbsp;
        📐 <b>VCP Contracting</b> — 5-day range is ≤75% of 20-day range. Volatility tightening = breakout building. &nbsp;|&nbsp;
        ⚡ <b>Strong Start</b> — Today: gap-up open + open = low (no dip). Ideal entry signal 9:15–9:18 AM. &nbsp;|&nbsp;
        🎯 <b>Core Met</b> — All 6 structural criteria pass (price, MA alignment, momentum). Minimum for consideration.
        </div>
        """, unsafe_allow_html=True)

        st.markdown("#### 📋 Ranked Candidates")
        display_cols = {
            "grade": "Grade",
            "symbol": "Stock",
            "cmp": "CMP ₹",
            "score": "Score",
            "perf_3m": "3M %",
            "perf_1m": "1M %",
            "pct_from_hi": "% from 52W High",
            "pct_from_ma20": "% from 20 MA",
            "pd_green": "🟢 Purple Dots",
            "pd_red": "🔴 Red Dots",
            "rvol": "RVol",
            "vol_contract": "VCP Contracting",
            "strong_start": "Strong Start",
            "core_met": "Core ✓",
        }
        df_disp = df_res[list(display_cols.keys())].rename(columns=display_cols)

        def color_score(val):
            if val >= 80:   return "background-color:#edf7f1;color:#1a6b3c;font-weight:bold"
            elif val >= 65: return "background-color:#e8f4fd;color:#1565c0;font-weight:bold"
            elif val >= 50: return "background-color:#fff8e1;color:#f57f17;font-weight:bold"
            else:           return "color:#999"

        def color_perf(val):
            if val >= 50:  return "color:#1a6b3c;font-weight:bold"
            elif val >= 30: return "color:#2980b9;font-weight:bold"
            elif val >= 0:  return "color:#f39c12"
            else:          return "color:#c0392b"

        styled = (df_disp.style
            .applymap(color_score, subset=["Score"])
            .applymap(color_perf, subset=["3M %","1M %"])
            .format({"CMP ₹": "₹{:.2f}", "3M %": "{:.1f}%", "1M %": "{:.1f}%",
                     "% from 52W High": "{:.1f}%", "% from 20 MA": "{:.1f}%",
                     "RVol": "{:.2f}x", "Score": "{:.0f}"})
        )
        st.dataframe(styled, use_container_width=True, height=400)

        # Detailed stock drilldown
        st.markdown("#### 🔬 Stock Detail Drilldown")
        selected = st.selectbox("Select stock for detail:", df_res["symbol"].tolist(), key="ma_detail_sel")
        if selected:
            row = df_res[df_res["symbol"] == selected].iloc[0]
            flags = row.get("flags", {})

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**{selected}** — Score: **{row['score']}/100** {row['grade']}")
                # Criteria checklist
                criteria_labels = {
                    "price_ok": "Price ≥ ₹50",
                    "within_25_52wh": "Within 25% of 52W High",
                    "above_50_52wl": "50%+ above 52W Low",
                    "above_30ma": "CMP above 30 MA",
                    "ma30_rising": "30 MA Rising (1+ month)",
                    "ma10_above_ma30": "10 MA above 30 MA",
                    "momentum_3m": "3-Month Return ≥ 30%",
                    "liquidity_ok": "Volume ≥ 2L/day",
                    "pd_green_ok": "Purple Dots (green) ≥ 2",
                    "pd_red_ok": "More green than red dots",
                    "vol_contract": "Volatility Contracting",
                    "near_20ma": "Price near 20 MA (≤5%)",
                    "strong_start": "Strong Start Today",
                }
                pills_html = ""
                for k, label in criteria_labels.items():
                    status = flags.get(k, False)
                    cls = "pill-pass" if status else "pill-fail"
                    icon = "✓" if status else "✗"
                    pills_html += f'<span class="pill {cls}">{icon} {label}</span>'
                st.markdown(f'<div style="line-height:2">{pills_html}</div>', unsafe_allow_html=True)

            with col_b:
                # Radar chart of criteria scores
                cats = ["Price/Float", "52W Position", "MA Alignment", "Momentum", "Purple Dot", "VCP", "Entry Signal"]
                vals = [
                    (5 if flags.get("price_ok") else 0) + (3 if row.get("avg_vol",0) > 500000 else 0),
                    (5 if flags.get("within_25_52wh") else 0) + (5 if flags.get("above_50_52wl") else 0),
                    (4 if flags.get("above_30ma") else 0) + (3 if flags.get("ma30_rising") else 0) + (3 if flags.get("ma10_above_ma30") else 0),
                    min(10, max(0, int(row.get("perf_3m",0)/10))),
                    min(10, row.get("pd_green",0)*2),
                    (5 if flags.get("vol_contract") else 0) + (5 if flags.get("near_20ma") else 0),
                    (7 if flags.get("strong_start") else 0) + (3 if row.get("rvol",0) > 2 else 0),
                ]
                fig_radar = go.Figure(go.Scatterpolar(
                    r=vals + [vals[0]],
                    theta=cats + [cats[0]],
                    fill="toself",
                    fillcolor="rgba(192,57,43,0.15)",
                    line=dict(color="#c0392b", width=2),
                ))
                fig_radar.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0,10])),
                    showlegend=False, height=300, margin=dict(l=40,r=40,t=30,b=30),
                    paper_bgcolor="white",
                )
                st.plotly_chart(fig_radar, use_container_width=True)

            # Price chart
            df_chart = fetch_ohlcv(selected, days=180)
            if not df_chart.empty:
                df_chart["ma20"] = df_chart["close"].rolling(20).mean()
                df_chart["ma10"] = df_chart["close"].rolling(10).mean()
                df_chart["ma30"] = df_chart["close"].rolling(30).mean()

                fig = go.Figure()
                fig.add_trace(go.Candlestick(
                    x=df_chart["datetime"], open=df_chart["open"],
                    high=df_chart["high"], low=df_chart["low"], close=df_chart["close"],
                    name="Price", increasing_fillcolor="#1a6b3c", decreasing_fillcolor="#c0392b",
                    increasing_line_color="#1a6b3c", decreasing_line_color="#c0392b",
                ))
                for ma, col, name in [(df_chart["ma10"],"#f39c12","10 MA"),
                                       (df_chart["ma20"],"#2980b9","20 MA"),
                                       (df_chart["ma30"],"#8e44ad","30 MA")]:
                    fig.add_trace(go.Scatter(x=df_chart["datetime"], y=ma,
                        line=dict(color=col, width=1.5), name=name))

                # Mark purple dots
                if "volume" in df_chart.columns:
                    df_chart["ret"] = df_chart["close"].pct_change() * 100
                    pd_up = df_chart[(df_chart["ret"] >= 5) & (df_chart["volume"] >= 500_000)]
                    pd_dn = df_chart[(df_chart["ret"] <= -5) & (df_chart["volume"] >= 500_000)]
                    if not pd_up.empty:
                        fig.add_trace(go.Scatter(x=pd_up["datetime"], y=pd_up["high"],
                            mode="markers", marker=dict(color="purple", size=10, symbol="circle"),
                            name="🟣 Purple Dot (Up)"))
                    if not pd_dn.empty:
                        fig.add_trace(go.Scatter(x=pd_dn["datetime"], y=pd_dn["low"],
                            mode="markers", marker=dict(color="darkred", size=10, symbol="circle"),
                            name="🔴 Purple Dot (Down)"))

                fig.update_layout(
                    title=f"{selected} — 180 Day Daily Chart",
                    xaxis_rangeslider_visible=False,
                    height=420, paper_bgcolor="white", plot_bgcolor="#fafafa",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    margin=dict(l=10,r=10,t=40,b=10),
                )
                st.plotly_chart(fig, use_container_width=True)

    else:
        st.markdown("""
        <div class="alert-info">
        Click <b>Run Scanner</b> above to scan the NSE universe and find today's Manas Arora setups.
        Run this on <b>Friday evenings or weekends</b> to build your Focus List for the week.
        </div>
        """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# TAB 2: BACKTEST RESULTS
# ═══════════════════════════════════════════════════════════
with TAB_BACKTEST:
    st.markdown("### 📊 System Backtest — Documented Trade History")
    st.markdown("""
    <div class="alert-info">
    <b>Data source:</b> 16 trades personally walked through by Manas Arora across 32 YouTube videos (2021–2025).
    These are <em>documented trades</em>, not a full system backtest. Win rate in documented trades may reflect 
    survivorship bias. The mathematical model below uses the conservative 35% win rate cited by his students.
    </div>
    """, unsafe_allow_html=True)

    bt_df, stats = build_backtest_data()

    # ── Stats Row ──
    st.markdown(f"""
    <div class="metric-row">
      <div class="metric-card"><div class="val">{stats['total']}</div><div class="lbl">Documented Trades</div></div>
      <div class="metric-card"><div class="val" style="color:#1a6b3c">{stats['wins']}</div><div class="lbl">Wins</div></div>
      <div class="metric-card"><div class="val" style="color:#c0392b">{stats['losses']}</div><div class="lbl">Losses</div></div>
      <div class="metric-card"><div class="val" style="color:#b8860b">{stats['be']}</div><div class="lbl">Break-Even</div></div>
      <div class="metric-card"><div class="val">{stats['win_rate']:.0f}%</div><div class="lbl">Win Rate (documented)</div></div>
      <div class="metric-card"><div class="val">{stats['avg_win_r']:.1f}R</div><div class="lbl">Avg Winner</div></div>
      <div class="metric-card"><div class="val">{stats['expectancy']:.1f}R</div><div class="lbl">Expectancy/Trade</div></div>
      <div class="metric-card"><div class="val">₹{stats['final_equity']:.0f}</div><div class="lbl">₹100→ (2% risk)</div></div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    # ── R-Multiple Bar Chart ──
    with col1:
        st.markdown("#### 📈 R-Multiple by Trade")
        fig_r = go.Figure(go.Bar(
            x=bt_df["stock"],
            y=bt_df["r_multiple"],
            marker_color=bt_df["color"],
            text=bt_df["r_multiple"].apply(lambda x: f"{x:+.0f}R"),
            textposition="outside",
        ))
        fig_r.update_layout(
            height=380, paper_bgcolor="white", plot_bgcolor="#fafafa",
            xaxis=dict(tickangle=-45, tickfont=dict(size=10)),
            yaxis=dict(title="R-Multiple", zeroline=True, zerolinecolor="#ccc"),
            showlegend=False, margin=dict(l=10,r=10,t=20,b=80),
        )
        fig_r.add_hline(y=0, line_color="#888", line_width=1)
        st.plotly_chart(fig_r, use_container_width=True)

    # ── Equity Curve ──
    with col2:
        st.markdown("#### 💰 Cumulative Equity Curve (2% risk/trade)")
        equity_vals = [100.0]
        for r in bt_df["r_multiple"]:
            equity_vals.append(round(equity_vals[-1] * (1 + r * 0.02), 2))

        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=list(range(len(equity_vals))),
            y=equity_vals,
            fill="tozeroy",
            fillcolor="rgba(26,107,60,0.12)",
            line=dict(color="#1a6b3c", width=2.5),
            mode="lines+markers",
            marker=dict(size=5, color="#1a6b3c"),
        ))
        fig_eq.add_hline(y=100, line_dash="dot", line_color="#888", line_width=1)
        fig_eq.update_layout(
            height=380, paper_bgcolor="white", plot_bgcolor="#fafafa",
            xaxis=dict(title="Trade #"),
            yaxis=dict(title="Portfolio Value (₹100 start)"),
            margin=dict(l=10,r=10,t=20,b=20), showlegend=False,
        )
        st.plotly_chart(fig_eq, use_container_width=True)

    st.markdown("#### 📋 Complete Trade Log — Entry / Exit / P&L")
    st.caption("All 16 documented trades with exact entry dates, prices, exit dates, and P&L. Source: Manas Arora YouTube (2021–2025).")
    
    trade_log_cols = {
        "stock":"Stock","sector":"Sector","type":"Setup Type","setup":"Pattern",
        "entry_date":"Entry Date","entry":"Entry ₹","exit_date":"Exit Date","exit_price":"Exit ₹",
        "stop_pct":"Stop %","gain_pct":"Gain %","days":"Days","r_multiple":"R-Multiple","outcome":"Result"
    }
    tl = bt_df[[c for c in trade_log_cols if c in bt_df.columns]].rename(columns=trade_log_cols)
    
    def color_outcome(val):
        if val == "Win":        return "background:#edf7f1;color:#1a6b3c;font-weight:700"
        elif val == "Loss":     return "background:#fdf0ee;color:#c0392b;font-weight:700"
        else:                   return "background:#fff8e1;color:#b8860b;font-weight:600"
    def color_gain(val):
        try:
            v = float(val)
            if v > 0:   return "color:#1a6b3c;font-weight:700"
            elif v < 0: return "color:#c0392b;font-weight:700"
        except: pass
        return ""
    def color_r(val):
        try:
            v = float(val)
            if v >= 10: return "color:#1a6b3c;font-weight:800"
            elif v > 0: return "color:#2980b9;font-weight:700"
            elif v < 0: return "color:#c0392b"
        except: pass
        return ""

    styled_log = (tl.style
        .applymap(color_outcome, subset=["Result"] if "Result" in tl.columns else [])
        .applymap(color_gain, subset=["Gain %"] if "Gain %" in tl.columns else [])
        .applymap(color_r, subset=["R-Multiple"] if "R-Multiple" in tl.columns else [])
        .format({
            "Entry ₹":    lambda v: f"₹{v:,.1f}" if v and v != 0 else "—",
            "Exit ₹":     lambda v: f"₹{v:,.1f}" if v and v != 0 else "—",
            "Stop %":     "{:.1f}%",
            "Gain %":     lambda v: f"{v:+.1f}%",
            "R-Multiple": lambda v: f"{v:+.0f}R",
        }, na_rep="—")
    )
    st.dataframe(styled_log, use_container_width=True, height=460, hide_index=True)
    col3, col4 = st.columns(2)

    with col3:
        by_type = bt_df.groupby("type").agg(
            Trades=("r_multiple","count"),
            Avg_R=("r_multiple","mean"),
            Total_R=("r_multiple","sum"),
            Win_Trades=("outcome", lambda x: (x=="Win").sum()),
        ).reset_index()
        by_type["Win_Rate"] = (by_type["Win_Trades"] / by_type["Trades"] * 100).round(1)
        by_type["Avg_R"] = by_type["Avg_R"].round(1)
        by_type["Total_R"] = by_type["Total_R"].round(1)

        st.dataframe(
            by_type[["type","Trades","Avg_R","Total_R","Win_Rate"]].rename(columns={
                "type":"Setup Type","Avg_R":"Avg R","Total_R":"Total R","Win_Rate":"Win Rate %"
            }),
            use_container_width=True, hide_index=True,
        )

    with col4:
        by_sector = bt_df.groupby("sector")["r_multiple"].sum().reset_index()
        by_sector = by_sector.sort_values("r_multiple", ascending=True)
        fig_sec = go.Figure(go.Bar(
            x=by_sector["r_multiple"], y=by_sector["sector"],
            orientation="h",
            marker_color=["#c0392b" if v < 0 else "#1a6b3c" for v in by_sector["r_multiple"]],
            text=by_sector["r_multiple"].apply(lambda x: f"{x:+.0f}R"),
            textposition="outside",
        ))
        fig_sec.update_layout(
            height=280, paper_bgcolor="white", plot_bgcolor="#fafafa",
            title="Total R by Sector", margin=dict(l=10,r=60,t=40,b=10),
            xaxis=dict(title="Total R-Multiple"), showlegend=False,
        )
        st.plotly_chart(fig_sec, use_container_width=True)

    # ── Monte Carlo Simulation ──
    st.markdown("#### 🎲 Monte Carlo Simulation — Real System Parameters")
    st.markdown("Based on **35% win rate, avg winner 15R, avg loser 1R, 70 trades/year, 2% risk/trade** (conservative real-world estimates from student data).")

    col5, col6, col7 = st.columns(3)
    with col5: sim_wr = st.slider("Win Rate", 25, 50, 35, 1, format="%d%%", key="ma_mc_wr") / 100
    with col6: sim_ar = st.slider("Avg Winner (R)", 5, 30, 15, 1, key="ma_mc_ar")
    with col7: sim_risk = st.slider("Portfolio Risk/Trade", 1, 5, 2, 1, format="%d%%", key="ma_mc_risk") / 100

    mc_data = monte_carlo_simulation(sim_wr, sim_ar, 1, 70, 500, sim_risk)
    mc_final = mc_data[:, -1]

    pct10 = np.percentile(mc_final, 10)
    pct50 = np.percentile(mc_final, 50)
    pct90 = np.percentile(mc_final, 90)

    st.markdown(f"""
    <div class="metric-row">
      <div class="metric-card"><div class="val" style="color:#c0392b">{(pct10-1)*100:.0f}%</div><div class="lbl">10th Percentile Return</div></div>
      <div class="metric-card"><div class="val">{(pct50-1)*100:.0f}%</div><div class="lbl">Median Return</div></div>
      <div class="metric-card"><div class="val" style="color:#1a6b3c">{(pct90-1)*100:.0f}%</div><div class="lbl">90th Percentile Return</div></div>
      <div class="metric-card"><div class="val">{(mc_final > 1).mean()*100:.0f}%</div><div class="lbl">Profitable Simulations</div></div>
    </div>
    """, unsafe_allow_html=True)

    fig_mc = go.Figure()
    # Fan chart
    p10  = np.percentile(mc_data, 10, axis=0)
    p25  = np.percentile(mc_data, 25, axis=0)
    p50  = np.percentile(mc_data, 50, axis=0)
    p75  = np.percentile(mc_data, 75, axis=0)
    p90  = np.percentile(mc_data, 90, axis=0)
    x_ax = list(range(len(p50)))

    fig_mc.add_trace(go.Scatter(x=x_ax+x_ax[::-1], y=list(p10)+list(p90)[::-1],
        fill="toself", fillcolor="rgba(192,57,43,0.08)", line=dict(width=0), name="10-90%"))
    fig_mc.add_trace(go.Scatter(x=x_ax+x_ax[::-1], y=list(p25)+list(p75)[::-1],
        fill="toself", fillcolor="rgba(41,128,185,0.12)", line=dict(width=0), name="25-75%"))
    fig_mc.add_trace(go.Scatter(x=x_ax, y=p50,
        line=dict(color="#1a6b3c", width=2.5), name="Median"))
    fig_mc.add_hline(y=1, line_dash="dot", line_color="#888")

    fig_mc.update_layout(
        height=350, paper_bgcolor="white", plot_bgcolor="#fafafa",
        title=f"Monte Carlo: 500 simulations | {sim_wr*100:.0f}% win rate | {sim_ar}R avg winner | {sim_risk*100:.0f}% risk/trade",
        xaxis=dict(title="Trade Number"), yaxis=dict(title="Portfolio Multiplier"),
        legend=dict(orientation="h", y=1.02), margin=dict(l=10,r=10,t=50,b=20),
    )
    st.plotly_chart(fig_mc, use_container_width=True)

    # ── Market Environment Analysis ──
    st.markdown("#### 🌍 When His System Works vs Fails")
    env_data = {
        "Market Environment": [
            "Post-correction Bull Run (early stage)", "Mid-Bull — Normal trending",
            "Extended market (Nifty 90° angle)", "Sideways / Choppy range",
            "Sharp market crash (breadth < 100 stocks)", "Sector rotation active",
        ],
        "Breadth Signal": ["<150 above 20DMA", "400–900 above 20DMA", ">1,200 above 20DMA",
                           "Oscillating 400–800", "<100 above 20DMA", "Mixed"],
        "Expected Hit Rate": ["70–80%", "50–60%", "20–30%", "25–35%", "Reversal trades only", "50–65%"],
        "Manas Action": ["MAX size, press hard", "Normal trading", "Close all, stop new entries",
                          "Reduce size 50%, wait", "Hunt falling knives ONLY", "Sector-focus trades"],
        "Colour": ["#1a6b3c","#2980b9","#c0392b","#e67e22","#8e44ad","#16a085"],
    }
    env_df = pd.DataFrame(env_data)

    fig_env = go.Figure(go.Bar(
        x=env_df["Market Environment"],
        y=[80, 55, 25, 30, 40, 57],
        marker_color=env_df["Colour"],
        text=[f"{v}%" for v in [80, 55, 25, 30, 40, 57]],
        textposition="outside",
    ))
    fig_env.update_layout(
        height=320, paper_bgcolor="white", plot_bgcolor="#fafafa",
        yaxis=dict(title="Expected Hit Rate %", range=[0, 100]),
        xaxis=dict(tickangle=-25, tickfont=dict(size=10)),
        showlegend=False, margin=dict(l=10,r=10,t=10,b=100),
    )
    st.plotly_chart(fig_env, use_container_width=True)

    # ── Full Trade History Table ──
    st.markdown("#### 📋 All 16 Documented Trades")
    st.dataframe(
        bt_df[["stock","type","sector","setup","stop_pct","gain_pct","days","r_multiple","outcome"]].rename(columns={
            "stock":"Stock","type":"Setup Type","sector":"Sector","setup":"Entry Pattern",
            "stop_pct":"Stop %","gain_pct":"Gain %","days":"Hold Days",
            "r_multiple":"R-Multiple","outcome":"Outcome",
        }).style
        .applymap(lambda v: "color:#1a6b3c;font-weight:bold" if v=="Win"
                  else "color:#c0392b;font-weight:bold" if v=="Loss"
                  else "color:#b8860b;font-weight:bold", subset=["Outcome"])
        .format({"Stop %": "{:.1f}%", "Gain %": "{:.1f}%", "R-Multiple": "{:+.0f}R"}),
        use_container_width=True, hide_index=True,
    )
    st.caption("Source: 32 YouTube videos (2021–2025) · Documented by Manas Arora personally · May reflect selection bias toward illustrative trades")

# ═══════════════════════════════════════════════════════════
# TAB 3: PLAYBOOK & PSYCHOLOGY
# ═══════════════════════════════════════════════════════════
with TAB_PLAYBOOK:
    st.markdown("### 🧠 The Complete Manas Arora Playbook")
    st.markdown("Extracted from 32 video sources across 12 structured prompts. Use this as your live trading reference.")

    PL1, PL2, PL3, PL4, PL5, PL6 = st.tabs([
        "3 Setups", "Entry: SVRO", "Risk Manager", "Exits", "Golden Rules", "Psychology"
    ])

    # ──────── Playbook: 3 Setups ────────
    with PL1:
        st.markdown("#### The 3 Setups Manas Trades — Repeatedly, for 15 Years")

        st.markdown("""
        <div class="setup-card">
          <div class="setup-head" style="background:#e8f4fd">📊 Setup A: Continuation (SVRO) — Bread & Butter, ~60% of trades</div>
          <div class="setup-body">
          <ul>
            <li>Stock up <b>30–40%+ in last 3 months</b> — prior momentum confirmed via Purple Dot</li>
            <li>Shallow correction <b>max 15–30%</b> from highs. Never buy a 30%+ correction base.</li>
            <li>Pulls back to or near <b>20-day MA</b> — volatility contracting daily range to 1–2%</li>
            <li>Dense Purple Dots during the upmove; <b>zero high-volume red days</b> during the base</li>
            <li>Enter on <b>Strong Start</b> in the first 3–5 minutes of market open</li>
            <li><b>Five-Star version</b>: smooth prior trend + dense purple dots + <em>touching 50 DMA for very first time</em></li>
            <li>Inside bars (IB) on daily chart preceding entry = ideal VCP signal</li>
          </ul>
          </div>
        </div>
        <div class="setup-card">
          <div class="setup-head" style="background:#fdf0ee">⚡ Setup B: Reversal (Falling Knife) — Only during extreme market sell-offs</div>
          <div class="setup-body">
          <ul>
            <li><b>Suspends the 30% momentum filter entirely.</b> This is a mean-reversion play.</li>
            <li>Stock must be down <b>3–8 massive consecutive red days</b> (average swing = 3–5 days)</li>
            <li>Drop must be statistically abnormal — PAYTM was down 8 days, Amber was down 37% in 9 days</li>
            <li>Market breadth must show extreme panic: <b>600–700 stocks hitting lows simultaneously</b></li>
            <li>Drop to <b>15-minute chart</b>. Wait for price to undercut recent low — then make a violent U-turn</li>
            <li>U-turn confirmation: <b>Open = Low</b> on 15-min bar, high volume, speed in the reversal</li>
            <li>Can deploy <b>larger size</b> than continuation (no weak hands, unlimited seller supply)</li>
            <li>Exit same day or Day 2 — this is <b>NOT a hold-for-weeks trade</b></li>
          </ul>
          </div>
        </div>
        <div class="setup-card">
          <div class="setup-head" style="background:#fdf9ec">🔄 Setup C: Busted / Shakeout Entry — Re-entry into existing winners</div>
          <div class="setup-body">
          <ul>
            <li>Stock in a daily uptrend experiencing a short-term pullback within the larger trend</li>
            <li>Set alert at the <b>lowest point of the pullback</b> range</li>
            <li>Price undercuts this low — <b>trapping retail stop-loss sellers</b></li>
            <li>Drop to 15–30 min chart. Wait 30–45 minutes for the U-turn and confirmation</li>
            <li>"I want to see a great U-turn... selling is not coming and these guys have been trapped"</li>
            <li>Enter immediately on reversal — this is how he added back into Zentec after selling half</li>
            <li>Also used to <b>pyramid into existing winners</b> instead of chasing the daily breakout</li>
          </ul>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="qblock">"For me VCP is not just a pattern — it's a principle on which the market operates. Cup and handles, triangles, inside bars — they are all just volatility contracting from wide to narrow."</div>
        """, unsafe_allow_html=True)

    # ──────── Playbook: SVRO Entry ────────
    with PL2:
        st.markdown("#### The SVRO Entry Framework — His Edge vs The Market")
        st.markdown("""
        <div class="alert-warn">
        ⏰ <b>Critical Timing Rule:</b> All entries happen between 9:15–10:30 AM. 
        After 10:30 AM, his historical win rate dropped by 50%. He stops initiating trades.
        Preparation is done the previous evening — "You have to prepare the night before, not during the market."
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="background:white;border:1px solid #e5e0d8;border-radius:10px;padding:20px;margin:12px 0">
        <div class="flow-step">
          <div class="flow-num">S</div>
          <div><div class="flow-title">Strong Start</div>
          <div class="flow-desc">Stock opens <em>above</em> yesterday's close. <b>Open = Low</b> — buyers in control from minute one, sellers nowhere in sight. "Open and low are the same... buyers are so strong they are just taking the stock higher."</div></div>
        </div>
        <div class="flow-step">
          <div class="flow-num">V</div>
          <div><div class="flow-title">Value Area</div>
          <div class="flow-desc">Session Volume Profile on TradingView. Stock must open <em>above</em> the previous day's Value Area — the zone where 70% of yesterday's volume traded. Opening inside or below the VA is a no-trade.</div></div>
        </div>
        <div class="flow-step">
          <div class="flow-num">R</div>
          <div><div class="flow-title">Relative Volume (RVol)</div>
          <div class="flow-desc">In the <b>first 3 minutes</b> (9:15–9:18), volume must already be 7–10% of the daily average. "If in the first three minutes the RVol has come to 7–8% till 9:18, the projection confirms it will be a monster volume day."</div></div>
        </div>
        <div class="flow-step" style="border-bottom:none">
          <div class="flow-num">O</div>
          <div><div class="flow-title">Opening Range Breakout</div>
          <div class="flow-desc">Price breaks above the initial morning range. All four confirmed → <b>"At 9:18, whatever will be the price, I enter the trade by placing a market order."</b></div></div>
        </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("##### Why Anticipatory Entry Beats Confirmation")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("""
            <div style="background:white;border:1px solid #e5e0d8;border-radius:10px;padding:16px">
            <b style="color:#c0392b">❌ Textbook Confirmatory Entry</b><br><br>
            <ul style="font-size:0.85rem;color:#666">
              <li>Wait for daily close above base high</li>
              <li>Enter after stock already moved 13–15%</li>
              <li>Stop must be placed far below → 5–7% stop</li>
              <li>Can only risk 5–10% of capital to stay within portfolio risk</li>
              <li>Result: small position, high entry risk, poor R:R</li>
            </ul>
            </div>""", unsafe_allow_html=True)
        with col_b:
            st.markdown("""
            <div style="background:white;border:1px solid #e5e0d8;border-radius:10px;padding:16px">
            <b style="color:#1a6b3c">✓ Manas: Anticipatory Entry</b><br><br>
            <ul style="font-size:0.85rem;color:#666">
              <li>Enter within first 1–2% of the move (9:15–9:20 AM)</li>
              <li>Stop at LOD — typically only 0.5–2%</li>
              <li>Tight stop → can allocate 20–30% of capital</li>
              <li>Trade off: lower accuracy (~35–40%), but dramatically better R:R</li>
              <li>Result: mammoth position, minimal risk, 15–30R potential</li>
            </ul>
            </div>""", unsafe_allow_html=True)

        st.markdown("""
        <div class="qblock">"You can wait for confirmations but every confirmation has a price. If you wait for the textbook confirmation, you might be entering after the stock has already moved 13–15%, making it high-risk."</div>
        """, unsafe_allow_html=True)

        st.markdown("##### Simultaneous Strong Start — Which Stock to Take?")
        st.markdown("""
        <div style="background:white;border:1px solid #e5e0d8;border-radius:10px;padding:16px;font-size:0.85rem">
        Rule: <b>First-come, first-served.</b> "Whatever triggers first — I go there." 
        Tie-breaker: prefer the stock with superior base-building quality (tighter base, more purple dots, closer to 50 DMA first touch). 
        If stock already moved 6%+ before he could act — he skips it entirely. "I don't buy something which is already 6% up on the day."
        </div>
        """, unsafe_allow_html=True)

    # ──────── Playbook: Risk Manager ────────
    with PL3:
        st.markdown("#### The Risk Manager — Step-by-Step Live Trade Management")
        st.markdown("""
        <div class="qblock">"I realized I'm not a trader. I'm a risk manager. I have to manage risk and just be on the crease — survive and stay on the crease so that you don't die."</div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="background:white;border:1px solid #e5e0d8;border-radius:10px;padding:20px;margin:12px 0">
        <div class="flow-step">
          <div class="flow-num">1</div><div>
          <div class="flow-title">Enter with a Tight Stop (LOD or 1–3%)</div>
          <div class="flow-desc">Stop is placed at the Low of Day or 1–3% below entry — whichever is smaller. <b>If LOD implies >3% stop, skip the trade entirely.</b> Never use ATR. Never widen stop for volatile stocks — instead wait for the stock's volatility to contract to 1–2% daily range before entering.</div>
          </div>
        </div>
        <div class="flow-step">
          <div class="flow-num">2</div><div>
          <div class="flow-title">Begin Manual Trailing Immediately</div>
          <div class="flow-desc">"I kept moving my stop loss by 50 paisa after every 1 rupee rise." As soon as the trade moves in his favor, he starts compressing risk. Original risk of ₹10,000 may drop to ₹2,000–3,000 within the first hour of the trade.</div>
          </div>
        </div>
        <div class="flow-step">
          <div class="flow-num">3</div><div>
          <div class="flow-title">Achieve Break-Even at +6–8%</div>
          <div class="flow-desc">"The objective is to bring the stock to break-even after a 6–7% move." Once stop is moved to cost price, the trade is psychologically free. This is the trigger to add more size.</div>
          </div>
        </div>
        <div class="flow-step">
          <div class="flow-num">4</div><div>
          <div class="flow-title">Create the "Free Entry" — Add Second Tranche</div>
          <div class="flow-desc">"This is basically a free entry — I added the new 10% without putting any stress on the portfolio." First tranche is at break-even (zero risk). Second tranche (5–10% of portfolio) gets its own tight stop. Each tranche has an <b>independent stop</b>.</div>
          </div>
        </div>
        <div class="flow-step">
          <div class="flow-num">5</div><div>
          <div class="flow-title">Pyramid on Pullbacks ONLY — Never Chase Air</div>
          <div class="flow-desc">Third, fourth, fifth adds (Zentec had 7–8 adds) happen only when stock pulls back to 10/20 MA and forms a new tight range or busted shakeout. "My second position is never more than my first size — unless it's trading near the same price as my first entry." Never add when stock is up 20%+ from base. "I am not going to add up in the air — I let it cool down."</div>
          </div>
        </div>
        <div class="flow-step" style="border-bottom:none">
          <div class="flow-num">6</div><div>
          <div class="flow-title">Switch to MA Trailing (Trending Stage)</div>
          <div class="flow-desc">Trail 10 DMA when index is extended (tighter exit). Trail 20 DMA when stock moves smoothly at normal angle. Closes on daily basis — but keeps an emergency hard stop just below the MA for intraday protection. Max final position: 25–30% of portfolio across all tranches.</div>
          </div>
        </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("##### The 5-Stock Knockout Rule")
        st.markdown("""
        <div style="background:#fdf0ee;border:1px solid #f5c6cb;border-left:4px solid #c0392b;border-radius:8px;padding:14px;font-size:0.88rem">
        "If I have five positions open and all get hit on the same day — that's the market kicking me out. Character has changed. <b>I am out for the next four to five days.</b>"<br><br>
        This is not bad luck. It is data. The market has turned hostile. No revenge trading. No bigger bets.
        Go to 100% cash. Test slowly on return with 10% position sizes only.
        </div>
        """, unsafe_allow_html=True)

    # ──────── Playbook: Exits ────────
    with PL4:
        st.markdown("#### Exit Rules — Complete Sell Trigger Hierarchy")
        st.markdown("""
        <div class="qblock">"The only two situations I press the sell button: when it hits my stop, or when the stock gets super extended."</div>
        """, unsafe_allow_html=True)

        exit_data = {
            "Priority": [1,2,3,4,5,6,7,8],
            "Trigger": [
                "Initial Stop Hit",
                "Trailing MA Breach (close)",
                "Emergency MA Stop (intraday)",
                "Parabolic / Climax Extension",
                "Indian Swing Limit (~40–53%)",
                "Gap Down Below Stop",
                "Break-Even Stop Triggered",
                "Pre-Event Cash Exit",
            ],
            "Condition": [
                "Price hits 1–3% stop or breaches LOD",
                "Stock convincingly closes below 10 or 20 DMA",
                "Hard stop just below 20 DMA triggers intraday",
                "90° rise, largest volume bar of rally, detached from all MAs",
                "After 40–53% gain, 90%+ probability of correction begins",
                "Stock opens below stop level — no recovery waiting",
                "Stop moved to cost; stock reverses back to entry",
                "No profit cushion before elections, budgets, binary events",
            ],
            "Action": [
                "Market order — immediate exit. No discussion.",
                "Exit at daily close. Emergency stop as backup.",
                "Hard stop fires — exit at market.",
                "Sell 40–60% into strength. Trail remainder.",
                "Start aggressively booking profits.",
                "SLM order at open — never wait for recovery.",
                "Exit at cost — zero loss, capital free.",
                "100% cash before the event.",
            ],
        }
        exit_df = pd.DataFrame(exit_data)
        st.dataframe(exit_df, use_container_width=True, hide_index=True, height=320)

        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.markdown("##### Trail vs Sell Into Strength Decision")
            st.markdown("""
            <div style="background:white;border:1px solid #e5e0d8;border-radius:10px;padding:16px;font-size:0.85rem">
            <b>Trail when:</b> Stock moving smoothly at a normal (30–45°) angle. Hold and trail the 20 DMA.<br><br>
            <b>Sell into strength when:</b> Stock goes 90° vertical. Volume 6–11x average. Third consecutive big day. 
            "It makes no sense to trail — this is the art of selling."<br><br>
            <b>Real example (E-Pack):</b> Standard trailing would have given back 30% of gains on a 58% move in 10 days. 
            He broke his own trailing rule and force-sold into strength. Adaptability over rigidity.
            </div>
            """, unsafe_allow_html=True)
        with col_e2:
            st.markdown("##### Re-Entering After a Stop-Out")
            st.markdown("""
            <div style="background:white;border:1px solid #e5e0d8;border-radius:10px;padding:16px;font-size:0.85rem">
            He does <em>not</em> hold grudges. Re-entry attempts are actually <b>more powerful</b> than the first.<br><br>
            "Every time the stock sets up again it is better than the previous attempt. Why? Because you bought the first time, 
            it stopped you out — many weak hands are out."<br><br>
            "By second attempt usually it works. Third attempt most likely it works." 
            He averages <b>3–4 re-entry attempts</b> before the main move starts (Zentec example).
            </div>
            """, unsafe_allow_html=True)

    # ──────── Playbook: Golden Rules ────────
    with PL5:
        st.markdown("#### Golden Rules — The Complete Commandments")
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.markdown("""
            <div class="rule-card rule-never">
              <h4 style="color:#c0392b">🚫 NEVER Rules — Absolute</h4>
              <ul style="list-style:none;padding:0">
                <li>🔴 Never trade 5% circuit-limit stocks — "you get trapped and can't come out"</li>
                <li>🔴 Never trade stocks below ₹30 (prefers ₹50+)</li>
                <li>🔴 Never average down into a loser — only average UP into winners</li>
                <li>🔴 Never wait for a gap-down to recover — instant SLM market exit</li>
                <li>🔴 Never add heavy into an extended stock — "I let it cool down"</li>
                <li>🔴 Never trade F&O — destroys position sizing flexibility</li>
                <li>🔴 Never trade on BSE — liquidity issues</li>
                <li>🔴 Never buy corrections deeper than 30% from highs</li>
                <li>🔴 Never have more than 4–6 open positions simultaneously</li>
                <li>🔴 Never take a stop greater than 2–3% — skip the trade</li>
                <li>🔴 Never chase a stock up 6%+ on the day of entry</li>
                <li>🔴 Never look at intraday charts after placing the morning entry</li>
              </ul>
            </div>
            """, unsafe_allow_html=True)
        with col_r2:
            st.markdown("""
            <div class="rule-card rule-always">
              <h4 style="color:#1a6b3c">✅ ALWAYS Rules — Non-Negotiable</h4>
              <ul style="list-style:none;padding:0">
                <li>🟢 Always set a stop loss before entering — no exceptions</li>
                <li>🟢 Always begin manual trailing from minute one</li>
                <li>🟢 Always target break-even at +6–8% gain</li>
                <li>🟢 Always take a break after 3–4 stop-losses in a week</li>
                <li>🟢 Always go to cash before binary events without profit cushion</li>
                <li>🟢 Always prioritize sectors with 10+ names moving together</li>
                <li>🟢 Always execute at market on a gap-down — never hope</li>
                <li>🟢 Always trade only in the first 75 minutes (9:15–10:30)</li>
                <li>🟢 Always scale down 10–20 days after a large loss</li>
                <li>🟢 Always prepare the watchlist night before (not morning of)</li>
                <li>🟢 Always use independent stop for each pyramid tranche</li>
                <li>🟢 Always re-enter a stopped-out stock if the setup re-forms</li>
              </ul>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("#### 🏷️ His Most Quotable Principles")
        quotes = [
            ("On Position Sizing", "Even a 500% move in your stock will not change your life if you never owned a significant size. A mere 20% move, if sized correctly and repeated often, can make you earn your first million much faster."),
            ("On Consistency", "These three videos, spaced about three years apart, show just one thing — I keep doing the same setup again and again to make money. No fancy tricks, no constant reinvention."),
            ("On Identity", "I realized I'm not a trader. I'm a risk manager. I have to manage risk and just be on the crease, survive and stay on the crease so that you don't die."),
            ("On Copying", "Copy the mindset not the trades. You will lose everything otherwise."),
            ("On Human Nature", "Trading is opposite of what human nature is."),
            ("On Charts vs Management", "Charts are 10%. Management is 90%."),
            ("On Beginners", "Change your objective in the first year — you cannot earn money. Your objective in the first year should be to learn and survive, and not earn."),
            ("On the Market", "I will let the market decide my fate. I will only sell it when the market kicks me out."),
        ]
        for topic, quote in quotes:
            st.markdown(f'<div class="qblock"><b>{topic}:</b> "{quote}"</div>', unsafe_allow_html=True)

    # ──────── Playbook: Psychology ────────
    with PL6:
        st.markdown("#### Psychology & Mental Models — The Missing 90%")
        st.markdown("""
        <div class="alert-info">
        The technical setup is only 10% of the game. Manas built his mental framework as systematically as his entry rules.
        Each section below is a direct summary of his stated mental models from 32 video sources.
        </div>
        """, unsafe_allow_html=True)

        psych_items = [
            ("📉", "Losing Streak Protocol",
             "Scale down immediately. Never fight back with bigger positions. 'If I am down 2%, take a break for a week. If I am down another 1%, I am going for a long break — because the phase is bad, the markets are bad. I am not bad.' The distinction matters: it's a market problem, not a trader problem."),
            ("🧠", "Self-Talk on Stop-Loss Hit",
             "Zero hesitation, zero hope, zero second-guessing. Accept the outcome BEFORE placing the trade. The correct self-talk: 'You bought a good trade. It just did not work. Which is very normal.' No different from a business expense."),
            ("🚫", "The FOMO Kill Switch",
             "Intentionally limits focus list to 10 stocks — making FOMO structurally impossible. 'My answer to FOMO: if you are getting FOMO from the 11th name, there are so many things happening in the world you are not part of — why are you not getting FOMO there?' There is no shortage of trades."),
            ("📊", "100 Trades = 1 Cluster",
             "'It's a game of probability. For me, 100 trades are everything — it's a cluster.' Reads Mark Douglas's Trading in the Zone every 6 months. Each trade is one data point in a series. No single trade defines success or failure."),
            ("🌊", "Overconfidence Management",
             "'This is a seasonal business. You get phases — cluster of breakouts in 3–4 months, then a dull period.' After generating 40% in two months, he consciously shifts gears. 'After a 40% kind of move, the next few months are not going to repeat — you correct yourself and play defensive.'"),
            ("⏳", "Patience as the Real Edge",
             "'I know I will find a 20R trade but it will not come in this phase — so just wait for it.' Spotted Mirza International sector strength in September. Waited until January (4 months) to enter. 'If you get a 40% move in two days, the stock dies for the next 1–2 months. Leave it alone.'"),
            ("💰", "Detaching From Money",
             "'To completely detach yourself from money, you have to have another source of income. If this is your ONLY source of income, it is impossible to detach — because every month you need money to pay your bills.' He owns a restaurant. This is structural, not motivational."),
            ("🏏", "Survival as the Only Goal",
             "'I am not a trader. I am a risk manager.' For beginners: 'Your objective in the first year should be to learn and survive, and not earn.' Survival is the only goal that compounds into success."),
            ("🔬", "False Breakout Awareness",
             "His system fails when: (1) Nifty is at 90° angle → breadth overheated → close all. (2) 1,500 stocks above 20 DMA → mathematical limit → stop new entries. (3) Index making gap-ups + doji candles → tighten all stops to 10 DMA immediately."),
            ("📚", "The 3 Books That Built Him",
             "1) Minervini: VCP, free float, risk management — first trade doubled in 4 weeks. 2) O'Neil: base counting, stage analysis, trend maturity. 3) Mark Douglas: probabilistic thinking, detachment, cluster mindset. Re-reads Douglas every 6 months."),
        ]

        for icon, title, body in psych_items:
            with st.expander(f"{icon} {title}"):
                st.markdown(f'<p style="font-size:0.9rem;color:#444;line-height:1.7">{body}</p>', unsafe_allow_html=True)

        st.markdown("#### ⏰ His Daily Routine — Minute by Minute")
        st.markdown("""
        <div style="background:white;border:1px solid #e5e0d8;border-radius:10px;padding:20px">
        <table style="width:100%;font-size:0.85rem;border-collapse:collapse">
        <tr style="background:#f7f5f1">
          <th style="padding:8px 12px;text-align:left;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;color:#666">Time</th>
          <th style="padding:8px 12px;text-align:left;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;color:#666">Activity</th>
        </tr>
        <tr><td style="padding:8px 12px;border-bottom:1px solid #f0ede8;font-weight:700">WEEKEND</td><td style="padding:8px 12px;border-bottom:1px solid #f0ede8">Manual scan entire market. Build Focus List of 4–10 stocks. Check MarketSmith sector rankings. Build pyramid targets.</td></tr>
        <tr><td style="padding:8px 12px;border-bottom:1px solid #f0ede8;font-weight:700">Prev. Evening</td><td style="padding:8px 12px;border-bottom:1px solid #f0ede8">Finalize next day's shortlist (4–5 names max). Set price alerts. Review base quality. Done — no more analysis in the morning.</td></tr>
        <tr><td style="padding:8px 12px;border-bottom:1px solid #f0ede8;font-weight:700">9:00–9:14 AM</td><td style="padding:8px 12px;border-bottom:1px solid #f0ede8">Watch pre-open prices of shortlisted stocks to gauge gap-up likelihood. Do not scan for new names.</td></tr>
        <tr><td style="padding:8px 12px;border-bottom:1px solid #f0ede8;font-weight:700">9:15–9:18 AM</td><td style="padding:8px 12px;border-bottom:1px solid #f0ede8">Check: gap-up opening ✓, Open=Low ✓, RVol 7–8%+ in first 3 minutes ✓. If all 3 confirmed → <b>Market order at 9:18.</b></td></tr>
        <tr><td style="padding:8px 12px;border-bottom:1px solid #f0ede8;font-weight:700">9:18–10:30 AM</td><td style="padding:8px 12px;border-bottom:1px solid #f0ede8">May monitor for secondary entries (busted/shakeout setups on 15-min). Steps away from intraday charts after entry is confirmed. "Many people make the mistake of staring at the intraday chart."</td></tr>
        <tr><td style="padding:8px 12px;border-bottom:1px solid #f0ede8;font-weight:700">After 10:30 AM</td><td style="padding:8px 12px;border-bottom:1px solid #f0ede8"><b>Stops initiating new trades.</b> Historical win rate drops 50% after this point. Does not watch intraday.</td></tr>
        <tr><td style="padding:8px 12px;border-bottom:1px solid #f0ede8;font-weight:700">~3:00 PM EOD</td><td style="padding:8px 12px;border-bottom:1px solid #f0ede8">Checks closing prices. Decides if partial profit booking needed on climax runs. Updates trailing stops on closing basis. Reviews overall portfolio health.</td></tr>
        <tr><td style="padding:8px 12px;font-weight:700">Evening</td><td style="padding:8px 12px">Prepares next day's shortlist. Reviews breadth tool. Checks MarketSmith for sector rank changes. Updates watchlist for tomorrow.</td></tr>
        </table>
        </div>
        """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 6. SIDEBAR — QUICK REFERENCE
# ─────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🎯 Manas Quick Reference")
    st.markdown("---")

    st.markdown("**🔑 Core Setup Filters (Weekend)**")
    st.markdown("""
    1. Price ≥ ₹50, NSE only  
    2. Within 25% of 52W High  
    3. 50%+ above 52W Low  
    4. CMP > 30 MA  
    5. 30 MA rising ≥ 1 month  
    6. 10 MA above 30 MA  
    7. 3-Month Return ≥ 30%  
    """)

    st.markdown("**🟣 Purple Dot Filter**")
    st.markdown("≥2 green dots in last 6M  \nZero red dots in base")

    st.markdown("**⏰ Entry Window**")
    st.markdown("9:15 AM – 10:30 AM only")

    st.markdown("**📐 Stop Loss Rule**")
    st.markdown("LOD or 1–3% (smaller)  \nSkip if LOD > 3%")

    st.markdown("**🏗️ Position Sizing**")
    st.markdown("""
    - Entry: 7–10% portfolio  
    - Max per stock: 25–30%  
    - Portfolio risk: 0.25–0.5%/trade  
    - Max positions: 4–6  
    """)

    st.markdown("**🚨 Drawdown Rules**")
    st.markdown("""
    - 3–4 stops in 1 week → 1-week break  
    - All 5 positions out same day → 4–5 day break  
    - -2% portfolio → full stop  
    """)

    st.markdown("**📚 Required Reading**")
    st.markdown("""
    1. Minervini — Trade Like a Wizard  
    2. O'Neil — How to Make Money  
    3. Douglas — Trading in the Zone  
    """)

    st.markdown("---")
    st.markdown("**🔄 Session Token**")
    if breeze:
        st.success("API Connected ✅")
    else:
        st.error("Token Expired ❌")
        st.markdown("[Refresh at ICICIdirect API](https://api.icicidirect.com/)", unsafe_allow_html=False)
    st.caption("Token expires daily. Update BREEZE_SESSION_TOKEN in Streamlit Secrets.")
