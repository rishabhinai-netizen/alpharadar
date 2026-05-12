"""
AlphaRadar — Market Pulse
=========================
NSE 1000 live breadth engine.
Data: Breeze API (primary) → yfinance (fallback, 15-min delay).

Fixes vs v1:
  - yfinance 1.3.0: MultiIndex columns — use droplevel(1) for single ticker,
    access via level-0 key for batch
  - Universe: fetched live from Supabase ar_daily_scores (already scored stocks)
    plus a curated fallback list with correct yfinance symbol mappings
  - Symbol map: INFOSYS→INFY, MCDOWELL-N→UBL, etc.
"""

import time
import requests
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

try:
    from breeze_connect import BreezeConnect
    BREEZE_AVAILABLE = True
except ImportError:
    BREEZE_AVAILABLE = False

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

# ─────────────────────────────────────────────
#  PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Market Pulse — AlphaRadar",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .stApp { background: #ffffff; }
    .main .block-container { padding: 1rem 1.5rem; max-width: 100%; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem; font-weight: 700; }
    div[data-testid="stMetricLabel"] { font-size: 0.78rem; color: #64748b; }
    .pulse-section { font-size:1.05rem; font-weight:700; color:#1e293b;
                     margin:18px 0 8px 0; padding-bottom:4px; border-bottom:2px solid #e2e8f0; }
    .sentiment-bull { background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:10px 16px; }
    .sentiment-bear { background:#fef2f2; border:1px solid #fecaca; border-radius:8px; padding:10px 16px; }
    .sentiment-neut { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px 16px; }
    .breeze-ok   { background:#f0fdf4; border:1px solid #bbf7d0; border-radius:6px;
                   padding:8px 14px; font-size:13px; color:#15803d; }
    .breeze-warn { background:#fef9c3; border:1px solid #fde68a; border-radius:6px;
                   padding:8px 14px; font-size:13px; color:#92400e; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  SUPABASE HELPERS
# ─────────────────────────────────────────────
def get_sb():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    hdrs = {"apikey": key, "Authorization": f"Bearer {key}"}
    return url, hdrs

def sb_get(table, select="*", params="", limit=2000):
    url, hdrs = get_sb()
    r = requests.get(f"{url}/rest/v1/{table}?select={select}&limit={limit}" +
                     (f"&{params}" if params else ""), headers=hdrs, timeout=10)
    return r.json() if r.status_code == 200 else []

# ─────────────────────────────────────────────
#  BREEZE CONNECTION
# ─────────────────────────────────────────────
BREEZE_SYM_MAP = {
    # Breeze symbol → yfinance symbol (where they differ)
    "INFOSYS": "INFY", "MCDOWELL-N": "UBL",
}
YF_SYM_MAP = {v: k for k, v in BREEZE_SYM_MAP.items()}  # reverse

def breeze_sym(nse_sym):
    """NSE symbol → Breeze code override if needed."""
    return {"MAZDOCK": "MAZDOC", "COCHINSHIP": "COCHIN",
            "LGEQUIP": "LGEQU", "MIRZAINT": "MIRZAI",
            "ADANIENT": "ADANIENS"}.get(nse_sym, nse_sym)

def yf_sym(nse_sym):
    """NSE symbol → correct yfinance ticker (without .NS suffix)."""
    return BREEZE_SYM_MAP.get(nse_sym, nse_sym)

@st.cache_resource(show_spinner=False)
def get_breeze():
    if not BREEZE_AVAILABLE:
        return None, "❌ breeze_connect not installed."
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
        if any(x in err.lower() for x in ["session", "token", "auth", "expire"]):
            return None, "🔄 Session expired — refresh BREEZE_SESSION_TOKEN in Streamlit Secrets."
        return None, f"❌ {err}"

# ─────────────────────────────────────────────
#  UNIVERSE — from Supabase ar_daily_scores
#  (already has valid, scored stocks)
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def load_universe_from_db():
    """Load symbols from latest ar_daily_scores — these are pre-validated."""
    try:
        latest = sb_get("ar_daily_scores", "score_date",
                        "order=score_date.desc&limit=1")
        if not latest or not isinstance(latest, list):
            return []
        ld = latest[0]["score_date"]
        data = sb_get("ar_daily_scores", "symbol",
                      f"score_date=eq.{ld}&order=composite_score.desc")
        if data and isinstance(data, list):
            syms = [d["symbol"] for d in data if "symbol" in d]
            st.session_state["mp_universe_date"] = ld
            return syms
    except Exception:
        pass
    return []

# Curated fallback — 700+ NSE stocks with correct yfinance mappings
# INFOSYS is stored as INFY in yfinance, MCDOWELL-N as UBL
NSE_FALLBACK = [
    # Nifty 50
    "RELIANCE","TCS","HDFCBANK","BHARTIARTL","ICICIBANK","INFY","SBIN","HINDUNILVR",
    "ITC","LT","KOTAKBANK","HCLTECH","BAJFINANCE","ASIANPAINT","MARUTI","AXISBANK",
    "SUNPHARMA","TITAN","ULTRACEMCO","WIPRO","NTPC","POWERGRID","NESTLEIND","TECHM",
    "M&M","ADANIPORTS","ONGC","COALINDIA","JSWSTEEL","TATASTEEL","BPCL",
    "GRASIM","INDUSINDBK","HINDALCO","CIPLA","DRREDDY","DIVISLAB","EICHERMOT",
    "HEROMOTOCO","BAJAJ-AUTO","APOLLOHOSP","BAJAJFINSV","TATACONSUM","BRITANNIA",
    "SBILIFE","HDFCLIFE","ADANIENT","VEDL","UPL",
    # Nifty Next 50 / Midcap
    "DMART","PIDILITIND","SIEMENS","HAL","BEL","CHOLAFIN","MUTHOOTFIN","TORNTPHARM",
    "COLPAL","DABUR","MARICO","BERGEPAINT","GODREJCP","HAVELLS","VOLTAS","UBL",
    "DLF","OBEROIRLTY","PRESTIGE","LODHA","NYKAA","ZOMATO","IRCTC","IRFC","RVNL",
    "NHPC","SJVN","CANBK","BANKBARODA","UNIONBANK","PNB","FEDERALBNK","IDFCFIRSTB",
    "BANDHANBNK","RBLBANK","YESBANK","RECLTD","PFC","HUDCO","NMDC",
    "ABCAPITAL","ACC","AIAENG","ALKEM","AMARAJABAT","AMBUJACEM","ANGELONE",
    "APLAPOLLO","ATUL","AUBANK","AUROPHARMA","BALKRISIND","BATAINDIA","BOSCHLTD",
    "BSOFT","CANFINHOME","CEATLTD","CENTURYTEX","CESC","CGPOWER","CHAMBLFERT",
    "CONCOR","CROMPTON","CUMMINSIND","CYIENT","DEEPAKNTR","DIXON","ELGIEQUIP",
    "EMAMILTD","ENGINERSIN","ESCORTS","EXIDEIND","FINPIPE","FINEORG","FORTIS",
    "GAIL","GLAXO","GNFC","GODREJIND","GODREJPROP","GRANULES","GRAPHITE","GSPL",
    "GUJGASLTD","HINDPETRO","HONAUT","ICICIPRULI","ICICIGI","IDBI","IEX","IIFL",
    "INDHOTEL","INDIGO","INDUSTOWER","IPCALAB","IRCON","JBCHEPHARM","JKCEMENT",
    "JKLAKSHMI","JKTYRE","JSL","JUBLFOOD","KAJARIACER","KALPATPOWR","KEC",
    "KPITTECH","KPRMILL","LALPATHLAB","LAURUSLABS","LICHSGFIN","LINDEINDIA",
    "LUPIN","MANAPPURAM","MAPMYINDIA","MASTEK","MAXHEALTH","MCX","METROPOLIS",
    "MFSL","MOTHERSON","MPHASIS","MRF","NATCOPHARM","NBCC","NCC","NIACL","NOCIL",
    "OFSS","OLECTRA","PERSISTENT","PETRONET","PFIZER","PHOENIXLTD","PNBHOUSING",
    "POLYCAB","POLYMED","PRAJIND","PTC","PVRINOX","RAILTEL","RAMCOCEM","RATEGAIN",
    "RAYMOND","REDINGTON","RELAXO","RITES","SAFARI","SANOFI","SHREECEM","SKFINDIA",
    "SOBHA","SONACOMS","STARHEALTH","SUMICHEM","SUNDARMFIN","SUNDRMFAST","SUPREMEIND",
    "SYNGENE","TANLA","TATACOMM","TATAELXSI","TATAPOWER","TEAMLEASE","THERMAX",
    "TIMKEN","TRENT","TRIDENT","TVSMOTOR","UJJIVANSFB","UNOMINDA","VBL","VGUARD",
    "VINATIORGA","WELCORP","WOCKPHARMA","ZEEL","ZENSARTECH","ZYDUSLIFE","ZYDUSWELL",
    # Smallcap
    "AARTIIND","AARTIDRUGS","ADVENZYMES","ALKYLAMINE","ALLCARGO","ANANTRAJ",
    "APARINDS","ARMANFIN","ASAHIINDIA","ASHOKLEY","ASTRAL","ASTEC","ATGL",
    "AURIONPRO","AUTOAXLES","AVANTIFEED","BALRAMCHIN","BASF","BAYERCROP","BEML",
    "BIRLACORPN","BIOCON","BRIGADE","CAMPUS","CARBORUNIV","CARERATINGS","CERA",
    "CHALET","CHEMFAB","CHEMPLASTS","CHOICEIN","CLEAN","COCHINSHIP","COROMANDEL",
    "CRAFTSMAN","CRISIL","CSBBANK","DATAMATICS","DEEPAKFERT","DHANUKA","DLINKINDIA",
    "DREDGECORP","EIMCOELECO","EMKAY","EMMBI","EPCIND","EPIGRAL","ESABINDIA",
    "ESAFSFB","EVEREADY","EVERESTIND","FDC","FINCABLES","FORCEMOT","GABRIEL",
    "GARFIBRES","GHCL","GIPCL","GLOBALVECT","GMDC","GPPL","GREENPLY","GREENPANEL",
    "GREENLAM","GRINDWELL","GRSE","GSFC","GTPL","GUFICBIO","GULFOILLUB","HATHWAY",
    "HAWKINCOOK","HCG","HEG","HERITGFOOD","HIKAL","HIMATSEIDE","HOEC",
    "IBULHSGFIN","ICRA","IDFC","IFBIND","IGARASHI","IMFA","INDOCO","INDORAMA",
    "INDOSTAR","INGERRAND","INNOVANA","IONEXCHANG","ISGEC","ITD","ITDCEM",
    "JAMNAAUTO","JAYAGROGN","JENBURKT","JMFINANCIAL","JPPOWER","JTL","JYOTHYLAB",
    "KALYANKJIL","KANSAINER","KCP","KFIN","KIMS","KIOCL","KITEX","KNRCON",
    "KOLTEPATIL","KOPRAN","KPIGREEN","LAKSHVILAS","LAXMIMACH","LLOYDSENGG",
    "LMWLTD","LUXIND","M&MFIN","MAHLOG","MAITHANALL","MAJESCO","MANINFRA",
    "MARATHON","MARKSANS","MAYURUNIQ","MEDPLUS","MIDHANI","MINDACORP","MINDAIND",
    "MINDSPACE","MOSCHIP","MPSLTD","MSTCLTD","MUKTAARTS","MUNJALSHOW","NAGARFERT",
    "NAHARINDTX","NALCO","NATHBIOGEN","NAVINFLUOR","NBVENTURES","NCLIND","NEULANDLAB",
    "NEWGEN","NIITLTD","NILKAMAL","NORTHARC","NURECA","NUVAMA","NUVOCO","OCCL",
    "OIL","ONMOBILE","OPTIEMUS","ORCHPHARMA","ORIENTBELL","ORIENTCEM","ORIENTELEC",
    "OSWALAGRO","PAGEIND","PAISALO","PANACEABIO","PANAMAPET","PATELENG","PATSPINN",
    "PCBL","PHILIPCARB","PILANIINVS","PIXTRANS","PLASCABLES","POKARNA","PRADIP",
    "PREMIER","PRINCEPIPE","PRICOLLTD","PRISMJOHNS","PSPPROJECT","PURVA","QUICKHEAL",
    "RADIANT","RADICO","RAJRATAN","RALLIS","RATNAMANI","RCF","RECLTD","REDTAPE",
    "REPCOHOME","REVATHI","RHIMAGN","RICOAUTO","ROSSARI","RSWM","SAKSOFT",
    "SAREGAMA","SELAN","SEQUENT","SHAKTIPUMP","SHALBY","SHANKARA","SHAREINDIA",
    "SHREDIGCEM","SHRIRAMFIN","SIGACHI","SIRCA","SKIPPER","SNOWMAN","SOFTTECH",
    "SOLARA","SOLEX","SONATSOFTW","STCINDIA","STERTOOLS","STOVEKRAFT","SUBROS",
    "SUDARSCHEM","SUPRAJIT","SYMPHONY","SUVENPHARMA","SWSOLAR","SYNCHRON",
    "TARAPUR","TATACHEM","TATVA","TEJAS","TIINDIA","TINPLATE","TTKPRESTIG",
    "TTKHLTCARE","UFO","UJJIVAN","ULTRAMARINE","UNIPARTS","UTIAMC","UTTAMSTL",
    "VAKRANGEE","VARROC","VARDHACRLC","VIMTALABS","VISHNU","VMART","VOLTAMP",
    "VSTIND","VSTLTD","WELSPUNIND","WINDMACHIN","XCHANGING","XELPMOC","YASHO",
    "YATHARTH","ZODIACLOTH","ZUARI","AAVAS","ABFRL","ADANITRANS","ADANIGREEN",
    "ADANIPOWER","ATGL","ANGELONE","APTUS","BAJAJHFL","BIKAJI","CAMPUS","CARTRADE",
    "DELHIVERY","DEVYANI","EASEMYTRIP","ETHOS","FINOLEX","FIVESTAR","GLAND",
    "GLOBUSSPR","HFCL","HOMEFIRST","INOXWIND","JSWENERGY","KAYNES","LATENTVIEW",
    "LXCHEM","NAZARA","NUVOCO","ONEPOINT","PARADEEP","PAYTM","PCBL","POLICYBZR",
    "RRKABEL","ROUTE","SBICARDS","SBICARD","SENCO","SGBHARAT","SIGNATURE",
    "SOLARINDS","TBOTEK","TRACXN","VRLLOG","WAAREEENER","WEBSOL","ZOMATO",
]
NSE_FALLBACK = list(dict.fromkeys(NSE_FALLBACK))

# ─────────────────────────────────────────────
#  DATA FETCHING — yfinance 1.3.0 compatible
# ─────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_nifty_benchmark(period: str = "1y") -> pd.DataFrame:
    """Download Nifty 50 index data. Handles yfinance 1.3.0 MultiIndex."""
    if not YF_AVAILABLE:
        return pd.DataFrame()
    df = yf.download("^NSEI", period=period, auto_adjust=True, progress=False)
    if df.empty:
        return pd.DataFrame()
    # yfinance 1.3.0 returns MultiIndex even for single ticker
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df.columns = [c.lower() for c in df.columns]
    df.index.name = "datetime"
    return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_batch_yf(nse_symbols: tuple, period: str = "1y") -> dict:
    """
    Batch download from yfinance 1.3.0.
    Returns dict: nse_symbol → DataFrame with lowercase columns.
    """
    if not YF_AVAILABLE:
        return {}
    # Map NSE symbols to yfinance symbols
    yf_to_nse = {}
    yf_tickers = []
    for sym in nse_symbols:
        yf = yf_sym(sym)
        ts = yf + ".NS"
        yf_tickers.append(ts)
        yf_to_nse[ts] = sym

    import yfinance as _yf
    raw = _yf.download(yf_tickers, period=period, auto_adjust=True,
                       progress=False, group_by="ticker")
    if raw.empty:
        return {}

    # Get valid tickers from level-0
    if isinstance(raw.columns, pd.MultiIndex):
        valid_tickers = raw.columns.get_level_values(0).unique().tolist()
    else:
        valid_tickers = []

    result = {}
    for ts in yf_tickers:
        nse_sym = yf_to_nse[ts]
        try:
            if ts not in valid_tickers:
                continue
            sub = raw[ts].copy()
            sub.columns = [c.lower() for c in sub.columns]
            sub = sub.dropna(subset=["close"])
            if len(sub) >= 15:
                sub.index.name = "datetime"
                result[nse_sym] = sub
        except Exception:
            continue
    return result


@st.cache_data(ttl=300, show_spinner=False)
def fetch_single_breeze(sym: str, days: int = 400) -> pd.DataFrame:
    breeze, err = get_breeze()
    if err or not breeze:
        return pd.DataFrame()
    try:
        to_dt = datetime.now()
        fr_dt = to_dt - timedelta(days=days)
        resp = breeze.get_historical_data_v2(
            interval="1day",
            from_date=fr_dt.strftime("%Y-%m-%dT07:00:00.000Z"),
            to_date=to_dt.strftime("%Y-%m-%dT07:00:00.000Z"),
            stock_code=breeze_sym(sym),
            exchange_code="NSE",
            product_type="cash",
        )
        if not resp or "Success" not in resp or not resp["Success"]:
            return pd.DataFrame()
        df = pd.DataFrame(resp["Success"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
        for c in ["open", "high", "low", "close", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna(subset=["close"])
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
#  TECHNICAL INDICATORS
# ─────────────────────────────────────────────
def rsi14(series: pd.Series) -> pd.Series:
    d = series.diff()
    g = d.clip(lower=0).ewm(alpha=1/14, min_periods=14).mean()
    l = (-d).clip(lower=0).ewm(alpha=1/14, min_periods=14).mean()
    return (100 - 100 / (1 + g / l.replace(0, np.nan))).round(1)


def sma(s, n):
    return s.rolling(n).mean()


def rs_spread_63d(stock: pd.Series, bench: pd.Series) -> float:
    try:
        n = min(63, len(stock), len(bench))
        if n < 10:
            return 0.0
        s = stock.iloc[-n:]
        b = bench.iloc[-n:]
        return round((s.iloc[-1]/s.iloc[0] - b.iloc[-1]/b.iloc[0]) * 100, 2)
    except Exception:
        return 0.0


def minervini_score(close, ma50, ma150, ma200) -> int:
    try:
        c = float(close.iloc[-1])
        m50 = float(ma50.iloc[-1]) if ma50.dropna().__len__() else c
        m150 = float(ma150.iloc[-1]) if ma150.dropna().__len__() else c
        m200 = float(ma200.iloc[-1]) if ma200.dropna().__len__() else c
        m200p = float(ma200.iloc[-22]) if len(ma200.dropna()) > 22 else m200
        hi52 = float(close.tail(252).max())
        lo52 = float(close.tail(252).min())
        return sum([
            c > m150, c > m200, m200 > m200p,
            m50 > m150, m50 > m200, c > m50,
            (c - lo52) / lo52 * 100 >= 25,
            (c - hi52) / hi52 * 100 >= -25,
        ])
    except Exception:
        return 0


def weinstein(close: pd.Series) -> str:
    try:
        m = close.rolling(150).mean()
        if len(m.dropna()) < 30:
            return "?"
        c, mv, mp = float(close.iloc[-1]), float(m.iloc[-1]), float(m.iloc[-20])
        pv = (c - mv) / mv * 100
        sl = (mv - mp) / mp * 100
        if pv > 5 and sl > 0.3:    return "Stage 2 ▲"
        if pv < -5 and sl < -0.3:  return "Stage 4 ▼"
        if abs(pv) <= 5 and sl > 0.3: return "Stage 3 ⚠"
        return "Stage 1 ◆"
    except Exception:
        return "?"


def compute_stock_metrics(sym: str, df: pd.DataFrame, bench_close: pd.Series) -> dict | None:
    try:
        close = df["close"].squeeze()
        vol = df["volume"].squeeze() if "volume" in df.columns else pd.Series(dtype=float)

        if len(close) < 20:
            return None

        ltp = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) > 1 else ltp
        chg = round((ltp - prev) / prev * 100, 2) if prev else 0.0

        # Volume
        vt = int(vol.iloc[-1]) if len(vol) else 0
        v10 = float(vol.iloc[-11:-1].mean()) if len(vol) > 10 else float(vol.mean()) or 1
        vr = round(vt / v10, 2) if v10 else 1.0
        vmax = int(vol.max()) if len(vol) else 0
        if vr >= 2.5:   vtag = "🔥 Extreme (2.5x+)"
        elif vr >= 1.5: vtag = "⬆ High (1.5x+)"
        elif vr >= 1.0: vtag = "✅ Above avg"
        else:           vtag = "↘ Below avg"
        if vt >= vmax * 0.95 and vmax > 0:
            vtag = "🏆 Near ATH volume"

        # Price levels
        ath  = round(float(close.max()), 2)
        h3m  = round(float(close.tail(63).max()),  2) if len(close) >= 63  else ath
        h52w = round(float(close.tail(252).max()), 2) if len(close) >= 252 else ath
        l52w = round(float(close.tail(252).min()), 2) if len(close) >= 252 else round(float(close.min()),2)
        p_ath  = round((ltp - ath)  / ath  * 100, 1)
        p_3m   = round((ltp - h3m)  / h3m  * 100, 1)
        p_52wh = round((ltp - h52w) / h52w * 100, 1)
        p_52wl = round((ltp - l52w) / l52w * 100, 1)

        # MAs
        ma50v  = sma(close, 50);  ma50l  = round(float(ma50v.iloc[-1]),  2) if ma50v.dropna().__len__()  else ltp
        ma150v = sma(close, 150); ma150l = round(float(ma150v.iloc[-1]), 2) if ma150v.dropna().__len__() else ltp
        ma200v = sma(close, 200); ma200l = round(float(ma200v.iloc[-1]), 2) if ma200v.dropna().__len__() else ltp
        vs50  = round((ltp - ma50l)  / ma50l  * 100, 1)
        vs200 = round((ltp - ma200l) / ma200l * 100, 1)

        # RSI
        rsi_s = rsi14(close)
        rsi_v = round(float(rsi_s.iloc[-1]), 1) if rsi_s.dropna().__len__() else 50.0
        if rsi_v >= 70:   rtag = "Overbought"
        elif rsi_v >= 60: rtag = "Bullish"
        elif rsi_v >= 40: rtag = "Neutral"
        elif rsi_v >= 30: rtag = "Bearish"
        else:             rtag = "Oversold"

        # RS vs Nifty 63d — align by position (Breeze has no shared date index)
        b = bench_close.values
        s = close.values
        n = min(63, len(s), len(b))
        rs = round((s[-1]/s[-n] - b[-1]/b[-n]) * 100, 2) if n >= 10 else 0.0

        # Stage + Minervini
        stage = weinstein(close)
        mv = minervini_score(close, ma50v, ma150v, ma200v)
        if mv >= 7:   mvtag = "✅ Trend Template"
        elif mv >= 5: mvtag = "⚠ Partial"
        else:         mvtag = "✗ Weak"

        # Composite 0-100
        score = round(
            min(30, max(0, (rs + 20) / 40 * 30)) +
            min(20, max(0, (1 - abs(p_ath) / 50) * 20)) +
            min(15, max(0, min(vr / 3, 1) * 15)) +
            min(15, max(0, (1 - abs(rsi_v - 55) / 45) * 15)) +
            mv / 8 * 20, 1
        )

        return {
            "Symbol": sym, "LTP": round(ltp, 2), "Chg%": chg,
            "Volume": vt, "Vol Ratio": vr, "Vol Tag": vtag,
            "From ATH%": p_ath, "3M High%": p_3m, "52W High%": p_52wh,
            "From 52W Low%": p_52wl,
            "vs MA50%": vs50, "vs MA200%": vs200,
            "RSI": rsi_v, "RSI Tag": rtag,
            "RS Spread": rs, "Stage": stage, "Minervini": mvtag,
            "Score": score,
            "Above MA50": ltp > ma50l, "Above MA200": ltp > ma200l,
            "_close": close, "_rsi": rsi_s, "_vol": vol,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
#  BREADTH
# ─────────────────────────────────────────────
def calc_breadth(df: pd.DataFrame) -> dict:
    n = len(df)
    adv = int((df["Chg%"] > 0).sum())
    dec = int((df["Chg%"] < 0).sum())
    return {
        "total": n, "adv": adv, "dec": dec, "unc": n - adv - dec,
        "ad_ratio": round(adv / dec, 2) if dec else adv,
        "up2": int((df["Chg%"] >= 2).sum()), "dn2": int((df["Chg%"] <= -2).sum()),
        "up5": int((df["Chg%"] >= 5).sum()), "dn5": int((df["Chg%"] <= -5).sum()),
        "new_52h": int((df["52W High%"] >= -1.5).sum()),
        "new_52l": int((df["From 52W Low%"] <= 2.5).sum()),
        "pct_ma50":  round(df["Above MA50"].mean() * 100, 1),
        "pct_ma200": round(df["Above MA200"].mean() * 100, 1),
        "vol_surge": int((df["Vol Ratio"] >= 1.5).sum()),
        "stage2": int((df["Stage"] == "Stage 2 ▲").sum()),
        "stage4": int((df["Stage"] == "Stage 4 ▼").sum()),
        "overbought": int((df["RSI"] >= 70).sum()),
        "oversold":   int((df["RSI"] <= 30).sum()),
    }


# ─────────────────────────────────────────────
#  CHARTS — light theme
# ─────────────────────────────────────────────
BG = "rgba(0,0,0,0)"; PBGA = "#f8fafc"; GRID = "rgba(0,0,0,0.06)"; FC = "#1e293b"

def chart_donut(adv, dec, unc):
    fig = go.Figure(go.Pie(
        labels=["Advancing","Declining","Unchanged"], values=[adv,dec,unc],
        hole=0.62, marker_colors=["#16a34a","#dc2626","#94a3b8"],
        textinfo="label+value", textfont=dict(size=12),
    ))
    fig.update_layout(height=260, margin=dict(l=10,r=10,t=30,b=10),
                      paper_bgcolor=BG, showlegend=False, font=dict(color=FC),
                      title=dict(text="A/D Ratio", font=dict(size=13)))
    return fig

def chart_ma_bars(p50, p200):
    fig = go.Figure()
    for val, lbl, clr in [(p50,"% > MA50","#3b82f6"),(p200,"% > MA200","#7c3aed")]:
        fig.add_trace(go.Bar(x=[val], y=[lbl], orientation="h",
                             marker_color=clr, text=f"{val}%",
                             textposition="outside", width=0.4))
    fig.add_vline(x=50, line_dash="dot", line_color="#94a3b8", line_width=1.5)
    fig.update_layout(height=180, margin=dict(l=10,r=50,t=30,b=10),
                      paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=FC),
                      xaxis=dict(range=[0,110],showgrid=False),
                      yaxis=dict(showgrid=False), showlegend=False,
                      title=dict(text="MA Health", font=dict(size=13)))
    return fig

def chart_dist(df):
    cuts = pd.cut(df["Chg%"], bins=25)
    counts = df.groupby(cuts, observed=False)["Chg%"].count()
    mids = [round(i.mid, 2) for i in counts.index]
    colors = ["#16a34a" if m > 0 else "#dc2626" for m in mids]
    fig = go.Figure(go.Bar(x=mids, y=counts.values, marker_color=colors, opacity=0.85))
    fig.add_vline(x=0, line_dash="solid", line_color="#1e293b", line_width=1.5)
    fig.update_layout(height=200, margin=dict(l=10,r=10,t=30,b=20),
                      paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=FC),
                      xaxis_title="% Change", yaxis_title="Count", showlegend=False,
                      title=dict(text="Change Distribution", font=dict(size=13)))
    return fig

def chart_rs_scatter(df):
    fig = px.scatter(
        df, x="RS Spread", y="Chg%", color="Score",
        color_continuous_scale=[[0,"#dc2626"],[0.5,"#f59e0b"],[1,"#16a34a"]],
        size=df["Score"].clip(lower=5), hover_name="Symbol",
        hover_data={"LTP":":.2f","RSI":":.1f","Vol Ratio":":.2f","Stage":True},
        height=360,
        labels={"RS Spread":"RS Spread vs Nifty 63d (%)","Chg%":"Daily Change (%)"},
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#94a3b8", line_width=1)
    fig.add_vline(x=0, line_dash="dot", line_color="#94a3b8", line_width=1)
    for xp, yp, txt in [(0.98,0.02,"🛡 Hidden Strength"), (-0.02,0.02,"RS Weak / Falling")]:
        fig.add_annotation(x=xp, y=yp, xref="paper", yref="paper", text=txt,
                           showarrow=False, font=dict(size=10,color="#64748b"),
                           xanchor="right" if xp>0.5 else "left")
    fig.update_layout(paper_bgcolor=BG, plot_bgcolor=PBGA, font=dict(color=FC),
                      coloraxis_colorbar=dict(title="Score",len=0.7),
                      margin=dict(l=10,r=10,t=30,b=10),
                      title=dict(text="RS vs Nifty 63d × Daily Change", font=dict(size=13)))
    return fig

def chart_rs_bar(df, n=20):
    top = df.nlargest(n,"RS Spread").sort_values("RS Spread")
    fig = go.Figure(go.Bar(
        x=top["RS Spread"], y=top["Symbol"], orientation="h",
        marker_color=["#16a34a" if v>=0 else "#dc2626" for v in top["RS Spread"]],
        text=top["RS Spread"].apply(lambda v: f"{v:+.1f}%"), textposition="outside",
    ))
    fig.add_vline(x=0, line_dash="dot", line_color="#94a3b8")
    fig.update_layout(height=max(320,n*18), margin=dict(l=60,r=50,t=30,b=10),
                      paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=FC),
                      showlegend=False, title=dict(text=f"Top {n} RS Leaders", font=dict(size=13)))
    return fig

def chart_rsi(sym, rsi_s, rsi_v):
    rsi = rsi_s.dropna().tail(90)
    clr = "#16a34a" if rsi_v < 40 else "#dc2626" if rsi_v > 65 else "#2563eb"
    fig = go.Figure()
    fig.add_hrect(y0=70,y1=100,fillcolor="rgba(220,38,38,0.06)",line_width=0)
    fig.add_hrect(y0=0, y1=30, fillcolor="rgba(22,163,74,0.06)", line_width=0)
    for y, c in [(70,"#dc2626"),(50,"#94a3b8"),(30,"#16a34a")]:
        fig.add_hline(y=y, line_dash="dot", line_color=c, line_width=1)
    fig.add_trace(go.Scatter(x=list(range(len(rsi))), y=rsi.values,
                             mode="lines", line=dict(color=clr,width=2),
                             fill="tozeroy", fillcolor="rgba(37,99,235,0.05)"))
    fig.add_annotation(x=len(rsi)-1, y=rsi_v, text=f"RSI {rsi_v}",
                       showarrow=False, font=dict(size=12,color=clr), xanchor="right")
    fig.update_layout(height=200, margin=dict(l=30,r=10,t=30,b=10),
                      paper_bgcolor=BG, plot_bgcolor=PBGA, font=dict(color=FC),
                      showlegend=False, xaxis=dict(showticklabels=False,showgrid=False),
                      yaxis=dict(range=[0,100],gridcolor=GRID),
                      title=dict(text="RSI (14)", font=dict(size=13)))
    return fig

def chart_price(sym, df_s):
    tail = df_s.tail(120)
    c = tail["close"].squeeze()
    xax = tail.index if "datetime" not in tail.columns else pd.to_datetime(tail.get("datetime", tail.index))
    fig = go.Figure()
    if all(col in tail.columns for col in ["open","high","low"]):
        fig.add_trace(go.Candlestick(
            x=xax, open=tail["open"].squeeze(), high=tail["high"].squeeze(),
            low=tail["low"].squeeze(), close=c, name="OHLC",
            increasing_line_color="#16a34a", decreasing_line_color="#dc2626", showlegend=False,
        ))
    else:
        fig.add_trace(go.Scatter(x=list(range(len(c))), y=c.values,
                                 mode="lines", line=dict(color="#2563eb",width=1.5)))
    for n, clr, nm in [(50,"#2563eb","MA50"),(200,"#7c3aed","MA200")]:
        mv = c.rolling(n).mean()
        fig.add_trace(go.Scatter(x=xax, y=mv.values, mode="lines",
                                 line=dict(color=clr,width=1.2,dash="dot"), name=nm))
    fig.update_layout(height=280, xaxis_rangeslider_visible=False,
                      margin=dict(l=10,r=10,t=30,b=10),
                      paper_bgcolor=BG, plot_bgcolor=PBGA, font=dict(color=FC),
                      legend=dict(orientation="h",y=1.05),
                      title=dict(text=f"{sym} — 120 Days", font=dict(size=13)))
    return fig


# ═══════════════════════════════════════════════════
#  PAGE RENDER
# ═══════════════════════════════════════════════════
st.markdown("# 📡 Market Pulse")
st.caption("NSE 1000 · Live Breadth · Relative Strength · Volume Intelligence · Real-time via Breeze API")

# Breeze status
breeze, b_err = get_breeze()
DATA_SOURCE = "yfinance" if b_err else "breeze"
if b_err:
    st.markdown(f'<div class="breeze-warn">⚠️ <b>Breeze:</b> {b_err}&nbsp;·&nbsp;Using yfinance (15-min delay). '
                f'<a href="https://api.icicidirect.com/" target="_blank">Refresh token →</a></div>',
                unsafe_allow_html=True)
else:
    st.markdown('<div class="breeze-ok">✅ <b>Breeze API connected</b> — Live prices active.</div>',
                unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Controls
c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    universe_n = st.select_slider(
        "Universe Size", options=[50, 100, 200, 500, 750, 1000], value=200,
        format_func=lambda x: f"NSE Top {x}" if x < 1000 else "Full NSE ~1000",
    )
with c2:
    period = st.selectbox("History", ["6mo", "1y", "2y"], index=1)
with c3:
    run = st.button("▶ Run Scan", type="primary", use_container_width=True)

if not run and "mp_df" not in st.session_state:
    st.info("Select universe size and click **▶ Run Scan** to start.")
    st.stop()

# ─── LOAD DATA ───
if run or "mp_df" not in st.session_state:
    prog = st.progress(0, "Loading universe…")
    status = st.empty()

    # Universe — try Supabase first, then fallback
    status.text("📋 Loading universe from database…")
    db_syms = load_universe_from_db()
    if db_syms:
        tickers = db_syms[:universe_n]
        universe_source = f"Supabase ar_daily_scores ({len(db_syms)} stocks)"
    else:
        tickers = NSE_FALLBACK[:universe_n]
        universe_source = f"Curated list ({len(NSE_FALLBACK)} stocks)"
    prog.progress(5)

    # Nifty benchmark
    status.text("📥 Loading Nifty 50 benchmark…")
    bench_df = fetch_nifty_benchmark(period)
    if bench_df.empty:
        st.error("Could not fetch Nifty 50. Check internet connection.")
        st.stop()
    bench_close = bench_df["close"].squeeze()
    prog.progress(12)

    # Stock data
    stock_data = {}
    if DATA_SOURCE == "breeze":
        status.text(f"Fetching {len(tickers)} stocks via Breeze…")
        for i, t in enumerate(tickers):
            df_t = fetch_single_breeze(t, 400)
            if not df_t.empty:
                stock_data[t] = df_t
            if i % 10 == 0:
                prog.progress(12 + int(i / len(tickers) * 50))
                status.text(f"Breeze: {t} ({i+1}/{len(tickers)})…")
            time.sleep(0.04)
    else:
        status.text(f"Batch downloading {len(tickers)} stocks via yfinance…")
        # Chunk into batches of 100 to avoid yfinance timeouts
        CHUNK = 100
        for ci in range(0, len(tickers), CHUNK):
            chunk = tickers[ci:ci+CHUNK]
            status.text(f"yfinance: batch {ci//CHUNK+1}/{(len(tickers)+CHUNK-1)//CHUNK} "
                        f"({ci+1}–{min(ci+CHUNK,len(tickers))} of {len(tickers)})…")
            batch_data = fetch_batch_yf(tuple(chunk), period)
            stock_data.update(batch_data)
            prog.progress(12 + int((ci + CHUNK) / len(tickers) * 50))

    prog.progress(65)
    status.text("Computing indicators…")

    records = []
    for i, t in enumerate(tickers):
        if t not in stock_data:
            continue
        m = compute_stock_metrics(t, stock_data[t], bench_close)
        if m:
            records.append(m)
        if i % 30 == 0:
            prog.progress(65 + int(i / len(tickers) * 30))

    prog.progress(97)
    if not records:
        st.error("No data returned. Try a smaller universe or check connection.")
        st.stop()

    df_all = pd.DataFrame(records)
    df_all["RS Rank"] = df_all["RS Spread"].rank(ascending=False, method="min").astype(int)
    df_all["Score Rank"] = df_all["Score"].rank(ascending=False, method="min").astype(int)

    st.session_state.update({
        "mp_df": df_all, "mp_stocks": stock_data,
        "mp_bench": bench_close, "mp_ts": datetime.now().strftime("%d %b %Y %H:%M"),
        "mp_universe_src": universe_source,
    })
    prog.progress(100); prog.empty(); status.empty()

df_all      = st.session_state["mp_df"]
stock_data  = st.session_state["mp_stocks"]
bench_close = st.session_state["mp_bench"]
scan_ts     = st.session_state.get("mp_ts","")
uni_src     = st.session_state.get("mp_universe_src","")

b = calc_breadth(df_all)
nchg = round((float(bench_close.iloc[-1]) - float(bench_close.iloc[-2])) /
             float(bench_close.iloc[-2]) * 100, 2) if len(bench_close) > 1 else 0.0

st.caption(f"✅ {b['total']} stocks scanned · Source: {uni_src} · {scan_ts} · "
           f"Nifty 50: {'▲' if nchg>0 else '▼'} {nchg:+.2f}%")
st.divider()

# ══════════════════════════════════════════
#  SECTION 1 — MARKET BREADTH
# ══════════════════════════════════════════
st.markdown('<p class="pulse-section">🗺 Market Breadth</p>', unsafe_allow_html=True)

ad = b["ad_ratio"]; p50 = b["pct_ma50"]
if b["adv"] > b["dec"] * 2 and p50 >= 60:
    sc, st_txt = "sentiment-bull", "🟢 Strong Bull — broad market participation"
elif b["adv"] > b["dec"] and p50 >= 45:
    sc, st_txt = "sentiment-bull", "🟡 Cautious Bull — positive but selective"
elif b["dec"] > b["adv"] * 1.5 and p50 < 40:
    sc, st_txt = "sentiment-bear", "🔴 Bear Pressure — raise cash, protect capital"
else:
    sc, st_txt = "sentiment-neut", "⚪ Neutral — wait for confirmation"

st.markdown(f"""
<div class="{sc}">
  <b>{st_txt}</b> &nbsp;·&nbsp;
  A/D {b['adv']}/{b['dec']} (ratio {ad}) &nbsp;·&nbsp;
  New 52W Highs <b>{b['new_52h']}</b> vs Lows <b>{b['new_52l']}</b> &nbsp;·&nbsp;
  Vol Surges <b>{b['vol_surge']}</b> stocks
</div>
""", unsafe_allow_html=True)

m1,m2,m3,m4,m5,m6 = st.columns(6)
m1.metric("🟢 Advancing", b["adv"])
m2.metric("🔴 Declining", b["dec"])
m3.metric("Up ≥2%", b["up2"])
m4.metric("Dn ≥2%", b["dn2"])
m5.metric("Stage 2 🚀", b["stage2"])
m6.metric("Oversold 🟢", b["oversold"])

ch1,ch2,ch3 = st.columns([1,1.2,1.6])
with ch1:
    st.plotly_chart(chart_donut(b["adv"],b["dec"],b["unc"]), use_container_width=True)
with ch2:
    st.plotly_chart(chart_ma_bars(b["pct_ma50"],b["pct_ma200"]), use_container_width=True)
    st.caption(f"Up ≥5%: **{b['up5']}** · Dn ≥5%: **{b['dn5']}** · Overbought: **{b['overbought']}**")
with ch3:
    st.plotly_chart(chart_dist(df_all), use_container_width=True)

st.divider()

# ══════════════════════════════════════════
#  SECTION 2 — RELATIVE STRENGTH
# ══════════════════════════════════════════
st.markdown('<p class="pulse-section">⚡ Relative Strength vs Nifty 50 — 63 Days</p>', unsafe_allow_html=True)
st.caption("Bottom-right = fell less than Nifty = hidden accumulation = leads next rally (O'Neil principle).")

rs1,rs2 = st.columns([1.6,1.2])
with rs1:
    st.plotly_chart(chart_rs_scatter(df_all), use_container_width=True)
with rs2:
    st.plotly_chart(chart_rs_bar(df_all, 20), use_container_width=True)

if nchg < -0.5:
    resilient = df_all[df_all["Chg%"] > nchg].nlargest(8,"RS Spread")["Symbol"].tolist()
    st.markdown(f"""
    <div class="sentiment-bull">
      <b>💎 Strength in Weakness (Nifty {nchg:+.2f}%)</b> — accumulation candidates for next upmove:<br>
      <b>{' · '.join(resilient)}</b>
    </div>""", unsafe_allow_html=True)

st.divider()

# ══════════════════════════════════════════
#  SECTION 3 — FILTERS + TABLE
# ══════════════════════════════════════════
st.markdown('<p class="pulse-section">🔍 Filter & Stock Table</p>', unsafe_allow_html=True)

with st.expander("⚙ Filters", expanded=True):
    f1,f2,f3,f4,f5 = st.columns(5)
    with f1:
        min_chg = st.number_input("Min Chg%", value=None, step=0.5, placeholder="e.g. 2.0")
        max_chg = st.number_input("Max Chg%", value=None, step=0.5, placeholder="e.g. -2.0")
    with f2:
        min_vol = st.number_input("Min Vol Ratio", value=0.0, step=0.5, min_value=0.0)
        min_rs  = st.number_input("Min RS Spread%", value=None, step=1.0, placeholder="e.g. 5.0")
    with f3:
        rsi_min = st.slider("RSI Min", 0, 100, 0)
        rsi_max = st.slider("RSI Max", 0, 100, 100)
    with f4:
        above200 = st.checkbox("Above MA200")
        above50  = st.checkbox("Above MA50")
        stg2     = st.checkbox("Stage 2 only")
        mv_only  = st.checkbox("Minervini TT only")
    with f5:
        near_ath = st.checkbox("Within 20% of ATH")
        sort_col = st.selectbox("Sort by", ["Score","RS Spread","Chg%","Vol Ratio","RSI","From ATH%"])
        sort_asc = st.checkbox("Ascending")

fdf = df_all.copy()
if min_chg  is not None: fdf = fdf[fdf["Chg%"] >= float(min_chg)]
if max_chg  is not None: fdf = fdf[fdf["Chg%"] <= float(max_chg)]
if min_vol  > 0:         fdf = fdf[fdf["Vol Ratio"] >= min_vol]
if min_rs   is not None: fdf = fdf[fdf["RS Spread"] >= float(min_rs)]
if rsi_min  > 0:         fdf = fdf[fdf["RSI"] >= rsi_min]
if rsi_max  < 100:       fdf = fdf[fdf["RSI"] <= rsi_max]
if above200:             fdf = fdf[fdf["Above MA200"] == True]
if above50:              fdf = fdf[fdf["Above MA50"] == True]
if stg2:                 fdf = fdf[fdf["Stage"] == "Stage 2 ▲"]
if mv_only:              fdf = fdf[fdf["Minervini"] == "✅ Trend Template"]
if near_ath:             fdf = fdf[fdf["From ATH%"] >= -20]
fdf = fdf.sort_values(sort_col, ascending=sort_asc)

st.caption(f"Showing **{len(fdf)}** of {len(df_all)} stocks")

SHOW = ["Score Rank","Symbol","LTP","Chg%","RSI","RSI Tag","RS Spread","RS Rank",
        "Vol Ratio","Vol Tag","From ATH%","52W High%","vs MA50%","vs MA200%","Stage","Minervini","Score"]
show = fdf[[c for c in SHOW if c in fdf.columns]].copy()

st.dataframe(show, use_container_width=True, height=520, hide_index=True,
    column_config={
        "Score Rank":  st.column_config.NumberColumn("#",        format="%d"),
        "LTP":         st.column_config.NumberColumn("LTP",      format="₹%.2f"),
        "Chg%":       st.column_config.NumberColumn("Chg%",     format="%.2f%%"),
        "RSI":         st.column_config.NumberColumn("RSI",      format="%.1f"),
        "RSI Tag":     st.column_config.TextColumn("RSI View",   width="small"),
        "RS Spread":   st.column_config.NumberColumn("RS Spread",format="%.2f%%"),
        "RS Rank":     st.column_config.NumberColumn("RS Rank",  format="%d"),
        "Vol Ratio":   st.column_config.NumberColumn("Vol",      format="%.2fx"),
        "Vol Tag":     st.column_config.TextColumn("Volume",     width="medium"),
        "From ATH%":  st.column_config.NumberColumn("vs ATH",   format="%.1f%%"),
        "52W High%":  st.column_config.NumberColumn("52W High",  format="%.1f%%"),
        "vs MA50%":   st.column_config.NumberColumn("vs MA50",   format="%.1f%%"),
        "vs MA200%":  st.column_config.NumberColumn("vs MA200",  format="%.1f%%"),
        "Stage":       st.column_config.TextColumn("Stage",      width="small"),
        "Minervini":   st.column_config.TextColumn("Minervini",  width="small"),
        "Score":       st.column_config.ProgressColumn("Score",  min_value=0, max_value=100, format="%.1f"),
    })

csv = fdf[[c for c in SHOW if c in fdf.columns]].to_csv(index=False).encode()
st.download_button("📥 Export CSV", csv,
                   f"market_pulse_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv")

st.divider()

# ══════════════════════════════════════════
#  SECTION 4 — STOCK DEEP-DIVE
# ══════════════════════════════════════════
st.markdown('<p class="pulse-section">🔬 Stock Deep-Dive</p>', unsafe_allow_html=True)

sel = st.selectbox("Select stock",
                   fdf["Symbol"].tolist() if len(fdf) else df_all["Symbol"].tolist(),
                   label_visibility="collapsed")

if sel and sel in stock_data:
    row = df_all[df_all["Symbol"] == sel].iloc[0]
    sdf = stock_data[sel]

    d1,d2,d3,d4,d5,d6 = st.columns(6)
    d1.metric("LTP",        f"₹{row['LTP']:,.2f}", delta=f"{row['Chg%']:+.2f}%")
    d2.metric("RSI (14)",   f"{row['RSI']}",        delta=row["RSI Tag"])
    d3.metric("RS Spread",  f"{row['RS Spread']:+.1f}%")
    d4.metric("Volume",     f"{row['Vol Ratio']:.2f}x", delta=row["Vol Tag"])
    d5.metric("Score",      f"{row['Score']:.0f}/100")
    d6.metric("Stage",      row["Stage"])

    l1,l2,l3,l4 = st.columns(4)
    l1.metric("vs ATH",      f"{row['From ATH%']:.1f}%")
    l2.metric("vs 3M High",  f"{row['3M High%']:.1f}%")
    l3.metric("vs MA50",     f"{row['vs MA50%']:+.1f}%")
    l4.metric("Minervini",   row["Minervini"])

    c1,c2,c3 = st.columns([2,1,1])
    with c1:
        st.plotly_chart(chart_price(sel, sdf), use_container_width=True)
    with c2:
        st.plotly_chart(chart_rsi(sel, row["_rsi"], row["RSI"]), use_container_width=True)
    with c3:
        # RS vs Nifty line
        s_arr = row["_close"].values
        b_arr = bench_close.values
        n = min(63, len(s_arr), len(b_arr))
        if n >= 10:
            rs_line = (s_arr[-n:] / s_arr[-n]) / (b_arr[-n:] / b_arr[-n])
            clr = "#16a34a" if rs_line[-1] > 1 else "#dc2626"
            fig_rs = go.Figure()
            fig_rs.add_hline(y=1, line_dash="dot", line_color="#94a3b8")
            fig_rs.add_trace(go.Scatter(x=list(range(n)), y=rs_line,
                                        mode="lines", line=dict(color=clr,width=2),
                                        fill="tozeroy", fillcolor="rgba(22,163,74,0.05)"))
            fig_rs.add_annotation(x=n-1, y=float(rs_line[-1]),
                                  text=f"RS {float(rs_line[-1]):.3f}",
                                  showarrow=False, font=dict(size=11,color=clr), xanchor="right")
            fig_rs.update_layout(height=200, margin=dict(l=30,r=10,t=30,b=10),
                                  paper_bgcolor=BG, plot_bgcolor=PBGA, font=dict(color=FC),
                                  showlegend=False, xaxis=dict(showticklabels=False,showgrid=False),
                                  yaxis=dict(gridcolor=GRID),
                                  title=dict(text="RS vs Nifty 63d",font=dict(size=13)))
            st.plotly_chart(fig_rs, use_container_width=True)

    # Auto-insights
    ins = []
    if row["Vol Ratio"] >= 1.5:
        ins.append(f"🔊 Volume is **{row['Vol Ratio']:.1f}x** 10-day avg — institutional activity possible")
    if row["From ATH%"] >= -3:
        ins.append("🏆 Near **All-Time High** — strong demand, breakout watch")
    if row["RSI"] <= 35:
        ins.append(f"🟢 RSI **{row['RSI']}** — approaching oversold, watch for reversal")
    if row["RSI"] >= 70:
        ins.append(f"🔴 RSI **{row['RSI']}** — extended, may pause or pull back")
    if row["RS Spread"] >= 10:
        ins.append(f"⚡ Outperforming Nifty by **{row['RS Spread']:+.1f}%** over 63 days")
    if row["Minervini"] == "✅ Trend Template":
        ins.append("✅ **Minervini Trend Template** — all 8 criteria met, confirmed uptrend")
    if row["Stage"] == "Stage 4 ▼":
        ins.append("⚠️ **Stage 4** — downtrend active, avoid new entries")
    if row["Stage"] == "Stage 2 ▲":
        ins.append("🚀 **Stage 2** — advancing, best zone for entries per Weinstein")
    if row["vs MA200%"] < -10:
        ins.append(f"📉 **{row['vs MA200%']:.1f}%** below MA200 — structural weakness")
    if row["Chg%"] > 0 and nchg < 0:
        ins.append(f"💪 **Rising on a down market day** (Nifty {nchg:.2f}%) — hidden strength")
    elif row["Chg%"] < 0 and abs(row["Chg%"]) < abs(nchg)*0.5 and nchg < 0:
        ins.append(f"🛡 Falling only **{row['Chg%']:.2f}%** vs Nifty {nchg:.2f}% — relative strength in weakness")
    if ins:
        st.markdown("**📋 Insights**")
        for i in ins:
            st.markdown(f"- {i}")

st.divider()

# ══════════════════════════════════════════
#  SECTION 5 — STRENGTH IN WEAKNESS
# ══════════════════════════════════════════
if nchg < -0.3:
    st.markdown('<p class="pulse-section">💎 Strength in Weakness — Today\'s Resilience Leaders</p>', unsafe_allow_html=True)
    st.caption(f"Nifty {nchg:+.2f}% today. Stocks outperforming = being accumulated. These lead the next rally.")
    siw = df_all.copy()
    siw["vs Nifty Today"] = (siw["Chg%"] - nchg).round(2)
    siw = siw.nlargest(30, "vs Nifty Today")
    siw_cols = ["Symbol","LTP","Chg%","vs Nifty Today","RS Spread","Vol Ratio","RSI","Stage","Score"]
    st.dataframe(siw[siw_cols], use_container_width=True, height=400, hide_index=True,
        column_config={
            "LTP":           st.column_config.NumberColumn(format="₹%.2f"),
            "Chg%":         st.column_config.NumberColumn(format="%.2f%%"),
            "vs Nifty Today":st.column_config.NumberColumn("vs Nifty", format="+%.2f%%"),
            "RS Spread":     st.column_config.NumberColumn(format="%.2f%%"),
            "Vol Ratio":     st.column_config.NumberColumn(format="%.2fx"),
            "Score":         st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
        })
    st.divider()

# ══════════════════════════════════════════
#  LEGEND
# ══════════════════════════════════════════
with st.expander("📖 Methodology"):
    st.markdown("""
    | Metric | Source | Meaning |
    |--------|--------|---------|
    | **Score (0-100)** | Composite | RS(30) + Price(20) + Volume(15) + RSI(15) + Minervini(20) |
    | **RS Spread** | O'Neil/IBD | % outperformance vs Nifty 50 over 63 trading days |
    | **RS Rank** | IBD-style | 1 = strongest RS in scanned universe |
    | **Vol Ratio** | CANSLIM "S" | Today's vol ÷ 10-day avg. ≥1.5x = institutional signal |
    | **Stage** | Stan Weinstein | Stage 2 ▲ = buy zone · Stage 4 ▼ = decline (avoid) |
    | **Minervini TT** | Mark Minervini | 8-criteria: price vs MA alignment + slope + 52W range |
    | **Strength in Weakness** | Livermore/O'Neil | Stocks falling less than market = hidden accumulation |
    
    **Quick call:** Score ≥70 + Stage 2 + Vol ≥1.5x → buy candidate · Strength in weakness + top RS Rank → next rally leader
    """)

st.caption(f"AlphaRadar Market Pulse · {scan_ts} · "
           f"{'Breeze Live' if DATA_SOURCE=='breeze' else 'yfinance 15-min delay'}")
st.markdown("""
<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:10px 14px;margin-top:8px;">
<p style="font-size:11px;color:#991b1b;margin:0;">
<b>⚠️ DISCLAIMER:</b> Educational/research tool only. Not SEBI-registered. Not investment advice. Trade at your own risk.
</p></div>
""", unsafe_allow_html=True)
