"""
AlphaRadar — Market Pulse
=========================
Live NSE 1000 breadth engine with real-time data via Breeze API.
Fallback: yfinance (15-min delayed).

Research basis:
  William O'Neil   → Relative Strength, A/D ratio, Volume confirmation
  Mark Minervini   → Trend Template (8 criteria)
  Stan Weinstein   → Stage Analysis (150d MA)
  Jesse Livermore  → Strength in weakness principle
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

# ── Light theme CSS matching AlphaRadar exactly ──
st.markdown("""
<style>
    .stApp { background: #ffffff; }
    .main .block-container { padding: 1rem 1.5rem; max-width: 100%; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem; font-weight: 700; }
    div[data-testid="stMetricLabel"] { font-size: 0.78rem; color: #64748b; }
    div[data-testid="stMetricDelta"]  { font-size: 0.78rem; }

    .pulse-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }
    .pulse-section-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: #1e293b;
        margin: 18px 0 8px 0;
        padding-bottom: 4px;
        border-bottom: 2px solid #e2e8f0;
    }
    .tag-green { background:#dcfce7; color:#15803d; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600; }
    .tag-red   { background:#fee2e2; color:#dc2626; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600; }
    .tag-blue  { background:#dbeafe; color:#1d4ed8; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600; }
    .tag-gray  { background:#f1f5f9; color:#475569; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600; }
    .tag-amber { background:#fef3c7; color:#d97706; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600; }

    .sentiment-bull { background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:12px 16px; }
    .sentiment-bear { background:#fef2f2; border:1px solid #fecaca; border-radius:8px; padding:12px 16px; }
    .sentiment-neut { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px 16px; }

    .breeze-ok   { background:#f0fdf4; border:1px solid #bbf7d0; border-radius:6px; padding:8px 14px; font-size:13px; color:#15803d; }
    .breeze-warn { background:#fef9c3; border:1px solid #fde68a; border-radius:6px; padding:8px 14px; font-size:13px; color:#92400e; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  BREEZE CONNECTION  (exact pattern from manas_arora.py)
# ─────────────────────────────────────────────
BREEZE_MAP = {
    "MAZDOCK": "MAZDOC", "COCHINSHIP": "COCHIN", "LGEQUIP": "LGEQU",
    "MIRZAINT": "MIRZAI", "ADANIENT": "ADANIENS", "M&M": "M&M",
    "BAJAJ-AUTO": "BAJAJ-AUTO", "MCDOWELL-N": "MCDOWELL-N",
}

def breeze_code(sym):
    return BREEZE_MAP.get(sym, sym)

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
#  NSE 1000 UNIVERSE
# ─────────────────────────────────────────────
NSE_1000 = [
    # Nifty 50
    "RELIANCE","TCS","HDFCBANK","BHARTIARTL","ICICIBANK","INFOSYS","SBIN","HINDUNILVR",
    "ITC","LT","KOTAKBANK","HCLTECH","BAJFINANCE","ASIANPAINT","MARUTI","AXISBANK",
    "SUNPHARMA","TITAN","ULTRACEMCO","WIPRO","NTPC","POWERGRID","NESTLEIND","TECHM",
    "M&M","ADANIPORTS","ONGC","COALINDIA","JSWSTEEL","TATAMOTORS","TATASTEEL","BPCL",
    "GRASIM","INDUSINDBK","HINDALCO","CIPLA","DRREDDY","DIVISLAB","EICHERMOT","HEROMOTOCO",
    "BAJAJ-AUTO","APOLLOHOSP","BAJAJFINSV","TATACONSUM","BRITANNIA","SBILIFE","HDFCLIFE",
    "ADANIENT","VEDL","UPL",
    # Nifty Next 50
    "DMART","PIDILITIND","SIEMENS","HAL","BEL","CHOLAFIN","MUTHOOTFIN","TORNTPHARM",
    "COLPAL","DABUR","MARICO","BERGEPAINT","GODREJCP","HAVELLS","VOLTAS","MCDOWELL-N",
    "DLF","OBEROIRLTY","PRESTIGE","LODHA","NYKAA","ZOMATO","IRCTC","IRFC","RVNL",
    "NHPC","SJVN","CANBK","BANKBARODA","UNIONBANK","PNB","FEDERALBNK","IDFCFIRSTB",
    "BANDHANBNK","RBLBANK","YESBANK","RECLTD","PFC","HUDCO","NMDC",
    # Midcap / Smallcap
    "ABCAPITAL","ACC","AIAENG","ALKEM","AMARAJABAT","AMBUJACEM","ANGELONE","APLAPOLLO",
    "ATUL","AUBANK","AUROPHARMA","BALKRISIND","BATAINDIA","BOSCHLTD","BSOFT","CANFINHOME",
    "CEATLTD","CENTURYTEX","CESC","CGPOWER","CHAMBLFERT","CONCOR","CROMPTON","CUMMINSIND",
    "CYIENT","DEEPAKNTR","DIXON","ELGIEQUIP","EMAMILTD","ENGINERSIN","ESCORTS","EXIDEIND",
    "FINPIPE","FINEORG","FORTIS","GAIL","GLAXO","GNFC","GODREJIND","GODREJPROP","GRANULES",
    "GRAPHITE","GSPL","GUJGASLTD","HINDPETRO","HONAUT","ICICIPRULI","ICICIGI","IDBI",
    "IEX","IIFL","INDHOTEL","INDIGO","INDUSTOWER","IPCALAB","IRCON","JBCHEPHARM",
    "JKCEMENT","JKLAKSHMI","JKTYRE","JSL","JUBLFOOD","KAJARIACER","KALPATPOWR","KEC",
    "KPITTECH","KPRMILL","LALPATHLAB","LAURUSLABS","LICHSGFIN","LINDEINDIA","LUPIN",
    "MANAPPURAM","MAPMYINDIA","MASTEK","MAXHEALTH","MCX","METROPOLIS","MFSL","MOTHERSON",
    "MPHASIS","MRF","NATCOPHARM","NBCC","NCC","NIACL","NOCIL","OFSS","OLECTRA",
    "PERSISTENT","PETRONET","PFIZER","PHOENIXLTD","PNBHOUSING","POLYCAB","POLYMED",
    "PRAJIND","PTC","PVRINOX","RAILTEL","RAMCOCEM","RATEGAIN","RAYMOND","REDINGTON",
    "RELAXO","RITES","SAFARI","SANOFI","SHREECEM","SKFINDIA","SOBHA","SONACOMS",
    "STARHEALTH","SUMICHEM","SUNDARMFIN","SUNDRMFAST","SUPREMEIND","SYNGENE","TANLA",
    "TATACOMM","TATAELXSI","TATAPOWER","TEAMLEASE","THERMAX","TIMKEN","TRENT","TRIDENT",
    "TVSMOTOR","UJJIVANSFB","UNOMINDA","VBL","VGUARD","VINATIORGA","WELCORP","WOCKPHARMA",
    "ZEEL","ZENSARTECH","ZYDUSLIFE","ZYDUSWELL","AARTIIND","AARTIDRUGS","ADVENZYMES",
    "ALKYLAMINE","ALLCARGO","ANANTRAJ","APARINDS","ARMANFIN","ASAHIINDIA","ASHOKLEY",
    "ASTRAL","ASTEC","ATGL","AURIONPRO","AUTOAXLES","AVANTIFEED","BALKRISIND","BALRAMCHIN",
    "BASF","BAYERCROP","BEML","BIRLACORPN","BIOCON","BRIGADE","CAMPUS","CARBORUNIV",
    "CARERATINGS","CERA","CGPOWER","CHALET","CHEMFAB","CHEMPLASTS","CHOICEIN","CLEAN",
    "COCHINSHIP","COROMANDEL","CRAFTSMAN","CRISIL","CSBBANK","DATAMATICS","DCAL",
    "DEEPAKFERT","DHANUKA","DLINKINDIA","DREDGECORP","EIMCOELECO","EMKAY","EMMBI",
    "EPCIND","EPIGRAL","ESABINDIA","ESAFSFB","EVEREADY","EVERESTIND","EXLSERVICE",
    "FDC","FINCABLES","FORCEMOT","GABRIEL","GARFIBRES","GHCL","GIPCL","GLOBALVECT",
    "GMDC","GPPL","GREENPLY","GREENPANEL","GREENLAM","GRINDWELL","GRSE","GSFC","GTPL",
    "GUFICBIO","GULFOILLUB","HATHWAY","HAWKINCOOK","HCG","HEG","HERITGFOOD",
    "HIKAL","HIMATSEIDE","HOEC","IBULHSGFIN","ICRA","IDFC","IFBIND","IGARASHI",
    "IMFA","INDOCO","INDORAMA","INDOSTAR","INGERRAND","INNOVANA","IONEXCHANG","ISGEC",
    "ITD","ITDCEM","J&KBANK","JAMNAAUTO","JAYAGROGN","JENBURKT","JMFINANCIAL","JPPOWER",
    "JTL","JYOTHYLAB","KALYANKJIL","KANSAINER","KCP","KFIN","KIMS","KIOCL","KITEX",
    "KNRCON","KOLTEPATIL","KOPRAN","KPIGREEN","LAKSHVILAS","LAXMIMACH","LLOYDSENGG",
    "LMWLTD","LUPIN","LUXIND","M&MFIN","MAHLOG","MAITHANALL","MAJESCO","MANINFRA",
    "MARATHON","MARKSANS","MAYURUNIQ","MEDPLUS","MIDHANI","MINDACORP","MINDAIND",
    "MINDSPACE","MOSCHIP","MPSLTD","MSTCLTD","MUKTAARTS","MUNJALSHOW","NAGARFERT",
    "NAHARINDTX","NALCO","NATHBIOGEN","NAVINFLUOR","NBVENTURES","NCLIND","NEULANDLAB",
    "NEWGEN","NIITLTD","NILKAMAL","NMCFINANCE","NORTHARC","NURECA","NUVAMA","NUVOCO",
    "OCCL","OIL","ONMOBILE","OPTIEMUS","ORCHPHARMA","ORIENTBELL","ORIENTCEM","ORIENTELEC",
    "OSWALAGRO","PAGEIND","PAISALO","PANACEABIO","PANAMAPET","PATELENG","PATSPINN",
    "PCBL","PEARLPOLY","PHILIPCARB","PILANIINVS","PIXTRANS","PLASCABLES","POCL",
    "POKARNA","POLYMED","PRADIP","PREMIER","PRINCEPIPE","PRICOLLTD","PRISMJOHNS",
    "PSPPROJECT","PURVA","QUICKHEAL","RADIANT","RADICO","RAJRATAN","RALLIS","RATNAMANI",
    "RCF","RECLTD","REDTAPE","REPCOHOME","REVATHI","RHIMAGN","RICOAUTO","ROSSARI",
    "RSWM","SAFARI","SAKSOFT","SAREGAMA","SELAN","SEQUENT","SHAKTIPUMP","SHALBY",
    "SHANKARA","SHAREINDIA","SHREDIGCEM","SHRIRAMFIN","SIGACHI","SIRCA","SKIPPER",
    "SNOWMAN","SOFTTECH","SOLARA","SOLEX","SONATSOFTW","STCINDIA","STERTOOLS","STOVEKRAFT",
    "SUBROS","SUDARSCHEM","SUPRAJIT","SYMPHONY","SUVENPHARMA","SWSOLAR","SYNCHRON",
    "TARAPUR","TATACHEM","TATVA","TEJAS","TIINDIA","TINPLATE","TTKPRESTIG","TTKHLTCARE",
    "UFO","UJJIVAN","ULTRAMARINE","UNIPARTS","UTIAMC","UTTAMSTL","VAKRANGEE","VARROC",
    "VARDHACRLC","VIMTALABS","VISHNU","VMART","VOLTAMP","VSTIND","VSTLTD","WELSPUNIND",
    "WINDMACHIN","XCHANGING","XELPMOC","YASHO","YATHARTH","ZODIACLOTH","ZUARI",
]
NSE_1000 = list(dict.fromkeys(NSE_1000))
BENCHMARK = "^NSEI"

# ─────────────────────────────────────────────
#  DATA FETCHING
# ─────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_daily_breeze(sym: str, days: int = 400) -> pd.DataFrame:
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
            stock_code=breeze_code(sym),
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


@st.cache_data(ttl=300, show_spinner=False)
def fetch_batch_yfinance(tickers: list, period: str = "1y") -> dict:
    if not YF_AVAILABLE:
        return {}
    try:
        suffixed = [t + ".NS" for t in tickers]
        raw = yf.download(suffixed, period=period, auto_adjust=True,
                          progress=False, threads=True, group_by="ticker")
        result = {}
        for t, ts in zip(tickers, suffixed):
            try:
                df = raw[ts].copy() if ts in raw.columns.get_level_values(0) else pd.DataFrame()
                if df.empty or len(df) < 10:
                    continue
                df.dropna(subset=["Close"], inplace=True)
                # Normalise column names to lowercase
                df.columns = [c.lower() for c in df.columns]
                df = df.rename(columns={"adj close": "close"}) if "adj close" in df.columns else df
                df.index.name = "datetime"
                df = df.reset_index()
                result[t] = df
            except Exception:
                continue
        return result
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_nifty(period="1y") -> pd.DataFrame:
    if not YF_AVAILABLE:
        return pd.DataFrame()
    df = yf.download(BENCHMARK, period=period, auto_adjust=True, progress=False)
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    return df


# ─────────────────────────────────────────────
#  TECHNICAL INDICATORS
# ─────────────────────────────────────────────
def rsi14(series: pd.Series) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, min_periods=14).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/14, min_periods=14).mean()
    rs   = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).round(1)


def ma(series, n):
    return series.rolling(n).mean()


def rs_spread(stock_close: pd.Series, bench_close: pd.Series, n: int = 63) -> float:
    """% outperformance vs benchmark over n days."""
    try:
        aligned = pd.concat([stock_close, bench_close], axis=1).dropna()
        aligned.columns = ["s", "b"]
        if len(aligned) < n:
            return np.nan
        t = aligned.tail(n)
        return round((t["s"].iloc[-1] / t["s"].iloc[0] - t["b"].iloc[-1] / t["b"].iloc[0]) * 100, 2)
    except Exception:
        return np.nan


def minervini_check(close, ma50, ma150, ma200) -> int:
    """8-criteria Minervini Trend Template. Returns count of criteria met (0-8)."""
    try:
        c = close.iloc[-1]
        m50, m150, m200 = ma50.iloc[-1], ma150.iloc[-1], ma200.iloc[-1]
        m200_p = ma200.iloc[-22] if len(ma200.dropna()) > 22 else m200
        hi52 = close.tail(252).max()
        lo52 = close.tail(252).min()
        return sum([
            c > m150,
            c > m200,
            m200 > m200_p,          # 200d MA trending up
            m50 > m150,
            m50 > m200,
            c > m50,
            (c - lo52) / lo52 * 100 >= 25,   # ≥25% above 52w low
            (c - hi52) / hi52 * 100 >= -25,   # ≤25% below 52w high
        ])
    except Exception:
        return 0


def weinstein_stage(close: pd.Series) -> str:
    try:
        m = close.rolling(150).mean()
        if m.dropna().__len__() < 30:
            return "?"
        c, mv, mp = close.iloc[-1], m.iloc[-1], m.iloc[-20]
        pv = (c - mv) / mv * 100
        sl = (mv - mp) / mp * 100
        if pv > 5 and sl > 0.3:   return "Stage 2 ▲"
        if pv < -5 and sl < -0.3: return "Stage 4 ▼"
        if abs(pv) <= 5 and sl > 0.3: return "Stage 3 ⚠"
        return "Stage 1 ◆" if abs(sl) <= 0.3 else ("Stage 2 ▲" if pv > 0 else "Stage 4 ▼")
    except Exception:
        return "?"


# ─────────────────────────────────────────────
#  PER-STOCK METRIC COMPUTATION
# ─────────────────────────────────────────────
def compute_metrics(sym: str, df: pd.DataFrame, bench_close: pd.Series) -> dict | None:
    try:
        close = df["close"].squeeze()
        vol   = df["volume"].squeeze() if "volume" in df.columns else pd.Series(dtype=float)
        high  = df["high"].squeeze()   if "high"   in df.columns else close
        low   = df["low"].squeeze()    if "low"    in df.columns else close

        if len(close) < 20:
            return None

        ltp        = float(close.iloc[-1])
        prev_close = float(close.iloc[-2]) if len(close) > 1 else ltp
        chg_pct    = round((ltp - prev_close) / prev_close * 100, 2) if prev_close else 0.0

        # Volume
        vol_today   = int(vol.iloc[-1]) if len(vol) else 0
        vol_10d_avg = float(vol.iloc[-11:-1].mean()) if len(vol) > 10 else float(vol.mean()) or 1
        vol_ratio   = round(vol_today / vol_10d_avg, 2) if vol_10d_avg else 1.0
        vol_max     = int(vol.max()) if len(vol) else 0

        if vol_ratio >= 2.5:   vol_tag = "🔥 Extreme (2.5x+)"
        elif vol_ratio >= 1.5: vol_tag = "⬆ High (1.5x+)"
        elif vol_ratio >= 1.0: vol_tag = "✅ Above avg"
        else:                  vol_tag = "↘ Low volume"
        if vol_today >= vol_max * 0.95:
            vol_tag = "🏆 Near ATH volume"

        # Price levels
        ath      = round(float(close.max()), 2)
        h3m      = round(float(close.tail(63).max()), 2)  if len(close) >= 63  else ath
        h52w     = round(float(close.tail(252).max()), 2) if len(close) >= 252 else ath
        l52w     = round(float(close.tail(252).min()), 2) if len(close) >= 252 else float(close.min())
        pct_ath  = round((ltp - ath) / ath * 100, 1)
        pct_3m   = round((ltp - h3m) / h3m * 100, 1)
        pct_52wh = round((ltp - h52w) / h52w * 100, 1)
        pct_52wl = round((ltp - l52w) / l52w * 100, 1)

        # Moving averages
        ma50  = ma(close, 50);  ma50v  = round(float(ma50.iloc[-1]), 2)  if ma50.dropna().__len__() else ltp
        ma150 = ma(close, 150); ma150v = round(float(ma150.iloc[-1]), 2) if ma150.dropna().__len__() else ltp
        ma200 = ma(close, 200); ma200v = round(float(ma200.iloc[-1]), 2) if ma200.dropna().__len__() else ltp
        vs50  = round((ltp - ma50v) / ma50v * 100, 1)
        vs200 = round((ltp - ma200v) / ma200v * 100, 1)

        # RSI
        rsi_s   = rsi14(close)
        rsi_val = round(float(rsi_s.iloc[-1]), 1) if rsi_s.dropna().__len__() else 50.0
        if rsi_val >= 70:   rsi_tag = "Overbought"
        elif rsi_val >= 60: rsi_tag = "Bullish"
        elif rsi_val >= 40: rsi_tag = "Neutral"
        elif rsi_val >= 30: rsi_tag = "Bearish"
        else:               rsi_tag = "Oversold"

        # RS vs Nifty 63d
        bench_ser = bench_close
        if hasattr(bench_ser, "squeeze"):
            bench_ser = bench_ser.squeeze()
        # Align indices (Breeze uses datetime column, yfinance uses DatetimeIndex)
        close_for_rs = close.copy()
        close_for_rs.index = range(len(close_for_rs))
        bench_aligned = bench_ser.tail(len(close_for_rs)).copy()
        bench_aligned.index = range(len(bench_aligned))
        rs_val = rs_spread(close_for_rs, bench_aligned, 63)

        # Stage + Minervini
        stage = weinstein_stage(close)
        mv_score = minervini_check(close, ma50, ma150, ma200)
        if mv_score >= 7:   mv_tag = "✅ Trend Template"
        elif mv_score >= 5: mv_tag = "⚠ Partial"
        else:               mv_tag = "✗ Weak"

        # Composite Score (0-100)
        rs_component    = min(30, max(0, ((rs_val or 0) + 20) / 40 * 30))
        price_component = min(20, max(0, (1 - abs(pct_ath) / 50) * 20))
        vol_component   = min(15, max(0, min(vol_ratio / 3, 1) * 15))
        rsi_component   = min(15, max(0, (1 - abs(rsi_val - 55) / 45) * 15))
        mv_component    = mv_score / 8 * 20
        composite       = round(rs_component + price_component + vol_component + rsi_component + mv_component, 1)

        return {
            "Symbol":       sym,
            "LTP":          round(ltp, 2),
            "Chg%":        chg_pct,
            "Volume":       vol_today,
            "Vol Ratio":    vol_ratio,
            "Vol Tag":      vol_tag,
            "ATH":          ath,
            "From ATH%":   pct_ath,
            "3M High%":    pct_3m,
            "52W High%":   pct_52wh,
            "From 52W Low%": pct_52wl,
            "vs MA50%":    vs50,
            "vs MA200%":   vs200,
            "MA200":        ma200v,
            "RSI":          rsi_val,
            "RSI Tag":      rsi_tag,
            "RS Spread":    round(rs_val, 2) if not np.isnan(rs_val or np.nan) else 0.0,
            "Stage":        stage,
            "Minervini":    mv_tag,
            "Score":        composite,
            "Above MA50":   ltp > ma50v,
            "Above MA200":  ltp > ma200v,
            # stored for deep-dive charts
            "_close":   close,
            "_rsi_s":   rsi_s,
            "_vol":     vol,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
#  BREADTH CALCULATION
# ─────────────────────────────────────────────
def calc_breadth(df: pd.DataFrame) -> dict:
    n   = len(df)
    adv = int((df["Chg%"] > 0).sum())
    dec = int((df["Chg%"] < 0).sum())
    unc = n - adv - dec
    return {
        "total": n, "adv": adv, "dec": dec, "unc": unc,
        "ad_ratio":   round(adv / dec, 2)       if dec else adv,
        "up2":        int((df["Chg%"] >= 2).sum()),
        "dn2":        int((df["Chg%"] <= -2).sum()),
        "up5":        int((df["Chg%"] >= 5).sum()),
        "dn5":        int((df["Chg%"] <= -5).sum()),
        "new_52h":    int((df["52W High%"] >= -1.5).sum()),
        "new_52l":    int((df["From 52W Low%"] <= 2.5).sum()),
        "pct_ma50":   round((df["Above MA50"]).mean() * 100, 1),
        "pct_ma200":  round((df["Above MA200"]).mean() * 100, 1),
        "vol_surge":  int((df["Vol Ratio"] >= 1.5).sum()),
        "stage2":     int((df["Stage"] == "Stage 2 ▲").sum()),
        "stage4":     int((df["Stage"] == "Stage 4 ▼").sum()),
        "overbought": int((df["RSI"] >= 70).sum()),
        "oversold":   int((df["RSI"] <= 30).sum()),
    }


# ─────────────────────────────────────────────
#  CHARTS (light theme)
# ─────────────────────────────────────────────
CHART_BG = "rgba(0,0,0,0)"
GRID_COL = "rgba(0,0,0,0.06)"
FONT_COL = "#1e293b"

def donut_ad(adv, dec, unc):
    fig = go.Figure(go.Pie(
        labels=["Advancing", "Declining", "Unchanged"],
        values=[adv, dec, unc],
        hole=0.62,
        marker_colors=["#16a34a", "#dc2626", "#94a3b8"],
        textinfo="label+value",
        textfont=dict(size=12, color=FONT_COL),
    ))
    fig.update_layout(height=260, margin=dict(l=10,r=10,t=30,b=10),
                      paper_bgcolor=CHART_BG, showlegend=False,
                      font=dict(color=FONT_COL),
                      title=dict(text="A/D Ratio", font=dict(size=13)))
    return fig


def bar_ma_health(pct50, pct200):
    fig = go.Figure()
    for val, label, color in [(pct50, "% > MA50", "#3b82f6"), (pct200, "% > MA200", "#7c3aed")]:
        fig.add_trace(go.Bar(x=[val], y=[label], orientation="h",
                             marker_color=color, text=f"{val}%", textposition="outside",
                             width=0.4))
    fig.add_vline(x=50, line_dash="dot", line_color="#94a3b8", line_width=1.5)
    fig.update_layout(height=180, margin=dict(l=10,r=50,t=30,b=10),
                      paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
                      font=dict(color=FONT_COL), xaxis=dict(range=[0,105], showgrid=False),
                      yaxis=dict(showgrid=False), showlegend=False,
                      title=dict(text="MA Health", font=dict(size=13)))
    return fig


def histogram_chg(df):
    cuts = pd.cut(df["Chg%"], bins=25)
    counts = df.groupby(cuts, observed=False)["Chg%"].count()
    mids   = [round(i.mid, 2) for i in counts.index]
    colors = ["#16a34a" if m > 0 else "#dc2626" for m in mids]
    fig = go.Figure(go.Bar(x=mids, y=counts.values, marker_color=colors, opacity=0.85))
    fig.add_vline(x=0, line_dash="solid", line_color="#1e293b", line_width=1.5)
    fig.update_layout(height=200, margin=dict(l=10,r=10,t=30,b=20),
                      paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
                      font=dict(color=FONT_COL), showlegend=False,
                      xaxis_title="% Change", yaxis_title="Count",
                      title=dict(text="Change Distribution", font=dict(size=13)))
    return fig


def rs_scatter(df):
    fig = px.scatter(
        df, x="RS Spread", y="Chg%",
        color="Score",
        color_continuous_scale=[[0,"#dc2626"],[0.5,"#f59e0b"],[1,"#16a34a"]],
        size=df["Score"].clip(lower=5),
        hover_name="Symbol",
        hover_data={"LTP": ":.2f", "RSI": ":.1f", "Vol Ratio": ":.2f", "Stage": True},
        height=360,
        labels={"RS Spread": "RS Spread vs Nifty 63d (%)", "Chg%": "Daily Change (%)"},
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#94a3b8", line_width=1)
    fig.add_vline(x=0, line_dash="dot", line_color="#94a3b8", line_width=1)
    # Label quadrants
    for x, y, txt in [(-0.02, 0.98, "RS Weak / Rising"), (0.98, 0.98, "💪 Strength"),
                      (-0.02, 0.02, "RS Weak / Falling"), (0.98, 0.02, "🛡 Hidden Strength")]:
        fig.add_annotation(x=x, y=y, xref="paper", yref="paper", text=txt,
                           showarrow=False, font=dict(size=10, color="#64748b"),
                           xanchor="left" if x < 0.5 else "right")
    fig.update_layout(paper_bgcolor=CHART_BG, plot_bgcolor="#f8fafc",
                      font=dict(color=FONT_COL),
                      coloraxis_colorbar=dict(title="Score", len=0.7),
                      margin=dict(l=10,r=10,t=30,b=10),
                      title=dict(text="RS vs Nifty 63d  ×  Daily Change", font=dict(size=13)))
    return fig


def rs_bar_top(df, n=20):
    top = df.nlargest(n, "RS Spread").sort_values("RS Spread")
    colors = ["#16a34a" if v >= 0 else "#dc2626" for v in top["RS Spread"]]
    fig = go.Figure(go.Bar(
        x=top["RS Spread"], y=top["Symbol"], orientation="h",
        marker_color=colors, text=top["RS Spread"].apply(lambda v: f"{v:+.1f}%"),
        textposition="outside",
    ))
    fig.add_vline(x=0, line_dash="dot", line_color="#94a3b8")
    fig.update_layout(height=max(320, n*18), margin=dict(l=60,r=50,t=30,b=10),
                      paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
                      font=dict(color=FONT_COL), showlegend=False,
                      title=dict(text=f"Top {n} by RS Spread", font=dict(size=13)))
    return fig


def rsi_chart(sym, rsi_s, rsi_val):
    rsi = rsi_s.dropna().tail(90)
    color = "#16a34a" if rsi_val < 50 else "#dc2626" if rsi_val > 65 else "#2563eb"
    fig = go.Figure()
    fig.add_hrect(y0=70, y1=100, fillcolor="rgba(220,38,38,0.06)", line_width=0)
    fig.add_hrect(y0=0,  y1=30,  fillcolor="rgba(22,163,74,0.06)",  line_width=0)
    for y, col in [(70,"#dc2626"),(50,"#94a3b8"),(30,"#16a34a")]:
        fig.add_hline(y=y, line_dash="dot", line_color=col, line_width=1)
    fig.add_trace(go.Scatter(x=list(range(len(rsi))), y=rsi.values,
                             mode="lines", line=dict(color=color, width=2),
                             fill="tozeroy", fillcolor=f"rgba(37,99,235,0.05)"))
    fig.add_annotation(x=len(rsi)-1, y=rsi_val, text=f"RSI {rsi_val}",
                       showarrow=False, font=dict(size=12, color=color), xanchor="right")
    fig.update_layout(height=200, margin=dict(l=30,r=10,t=30,b=10),
                      paper_bgcolor=CHART_BG, plot_bgcolor="#f8fafc",
                      font=dict(color=FONT_COL), showlegend=False,
                      xaxis=dict(showticklabels=False, showgrid=False),
                      yaxis=dict(range=[0,100], gridcolor=GRID_COL),
                      title=dict(text=f"RSI (14)", font=dict(size=13)))
    return fig


def price_chart(sym, df_stock):
    tail = df_stock.tail(120)
    c = tail["close"].squeeze()
    fig = go.Figure()
    # Candlestick
    if all(col in tail.columns for col in ["open","high","low"]):
        fig.add_trace(go.Candlestick(
            x=tail.index if "datetime" not in tail.columns else tail["datetime"],
            open=tail["open"].squeeze(), high=tail["high"].squeeze(),
            low=tail["low"].squeeze(),   close=c,
            name="OHLC",
            increasing_line_color="#16a34a", decreasing_line_color="#dc2626",
            showlegend=False,
        ))
    else:
        fig.add_trace(go.Scatter(x=list(range(len(c))), y=c.values,
                                 mode="lines", line=dict(color="#2563eb", width=1.5)))
    # MAs
    for n, col, name in [(50,"#2563eb","MA50"),(200,"#7c3aed","MA200")]:
        mv = c.rolling(n).mean()
        xaxis = tail.index if "datetime" not in tail.columns else tail["datetime"]
        fig.add_trace(go.Scatter(x=xaxis, y=mv.values,
                                 mode="lines", line=dict(color=col, width=1.2, dash="dot"),
                                 name=name))
    fig.update_layout(height=280, xaxis_rangeslider_visible=False,
                      margin=dict(l=10,r=10,t=30,b=10),
                      paper_bgcolor=CHART_BG, plot_bgcolor="#f8fafc",
                      font=dict(color=FONT_COL), legend=dict(orientation="h", y=1.05),
                      title=dict(text=f"{sym} — 120 Days", font=dict(size=13)))
    return fig


# ─────────────────────────────────────────────
#  PAGE HEADER
# ─────────────────────────────────────────────
st.markdown("# 📡 Market Pulse")
st.caption("NSE 1000 · Live Breadth · Relative Strength · Volume Intelligence · Real-time via Breeze API")

# Breeze status bar
breeze, b_err = get_breeze()
if b_err:
    st.markdown(f'<div class="breeze-warn">⚠️ <b>Breeze:</b> {b_err} &nbsp;|&nbsp; Using yfinance (15-min delayed). <a href="https://api.icicidirect.com/" target="_blank">Refresh token →</a></div>', unsafe_allow_html=True)
    DATA_SOURCE = "yfinance"
else:
    st.markdown('<div class="breeze-ok">✅ <b>Breeze API connected</b> — Live prices active.</div>', unsafe_allow_html=True)
    DATA_SOURCE = "breeze"

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  CONTROLS
# ─────────────────────────────────────────────
ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 1])
with ctrl1:
    universe_n = st.select_slider(
        "Universe Size",
        options=[50, 100, 200, 500, len(NSE_1000)],
        value=100,
        format_func=lambda x: f"NSE Top {x}" if x < len(NSE_1000) else f"Full NSE ~{x}",
    )
with ctrl2:
    period = st.selectbox("History", ["6mo", "1y", "2y"], index=1,
                          help="More history = better MA200 and RS calculations")
with ctrl3:
    run = st.button("▶ Run Scan", type="primary", use_container_width=True)

if not run and "mp_df" not in st.session_state:
    st.info("Select universe size and click **▶ Run Scan** to load live market data.")
    st.stop()

# ─────────────────────────────────────────────
#  DATA LOAD
# ─────────────────────────────────────────────
tickers = NSE_1000[:universe_n]

if run or "mp_df" not in st.session_state:
    prog   = st.progress(0, "Loading Nifty 50 benchmark…")
    status = st.empty()

    # Nifty benchmark
    bench_df = fetch_nifty(period)
    if bench_df.empty:
        st.error("Could not fetch Nifty 50. Check internet.")
        st.stop()
    bench_close = bench_df["close"].squeeze()
    prog.progress(8)

    # Fetch all stocks
    stock_data = {}
    if DATA_SOURCE == "breeze":
        status.text(f"Fetching {len(tickers)} stocks via Breeze API…")
        for i, t in enumerate(tickers):
            df_t = fetch_daily_breeze(t, 400)
            if not df_t.empty:
                stock_data[t] = df_t
            if i % 10 == 0:
                prog.progress(8 + int(i / len(tickers) * 45))
                status.text(f"Breeze: {t} ({i+1}/{len(tickers)})…")
            time.sleep(0.05)
    else:
        status.text(f"Fetching {len(tickers)} stocks via yfinance…")
        stock_data = fetch_batch_yfinance(tickers, period)

    prog.progress(55)
    status.text("Computing indicators…")

    # Compute metrics
    records = []
    for i, t in enumerate(tickers):
        if t not in stock_data:
            continue
        m = compute_metrics(t, stock_data[t], bench_close)
        if m:
            records.append(m)
        if i % 20 == 0:
            prog.progress(55 + int(i / len(tickers) * 40))

    prog.progress(98)
    if not records:
        st.error("No data returned. Check connection or try smaller universe.")
        st.stop()

    df_all = pd.DataFrame(records)
    df_all["RS Rank"] = df_all["RS Spread"].rank(ascending=False, method="min").astype(int)
    df_all["Score Rank"] = df_all["Score"].rank(ascending=False, method="min").astype(int)

    st.session_state["mp_df"]     = df_all
    st.session_state["mp_stocks"] = stock_data
    st.session_state["mp_bench"]  = bench_close
    st.session_state["mp_ts"]     = datetime.now().strftime("%d %b %Y %H:%M")

    prog.progress(100)
    prog.empty()
    status.empty()

df_all      = st.session_state["mp_df"]
stock_data  = st.session_state["mp_stocks"]
bench_close = st.session_state["mp_bench"]
scan_ts     = st.session_state.get("mp_ts", "")

breadth = calc_breadth(df_all)
nifty_chg = round(
    (float(bench_close.iloc[-1]) - float(bench_close.iloc[-2])) / float(bench_close.iloc[-2]) * 100, 2
) if len(bench_close) > 1 else 0.0

st.caption(f"📅 Scanned {breadth['total']} stocks · Last run: {scan_ts} · Nifty 50 today: {'▲' if nifty_chg > 0 else '▼'} {nifty_chg:+.2f}%")
st.divider()

# ─────────────────────────────────────────────
#  SECTION 1 — MARKET BREADTH
# ─────────────────────────────────────────────
st.markdown('<p class="pulse-section-title">🗺 Market Breadth</p>', unsafe_allow_html=True)

# Sentiment label
ad = breadth["ad_ratio"]
p50 = breadth["pct_ma50"]
if breadth["adv"] > breadth["dec"] * 2 and p50 >= 60:
    sent_cls, sent_txt = "sentiment-bull", "🟢 Strong Bull — broad participation"
elif breadth["adv"] > breadth["dec"] and p50 >= 45:
    sent_cls, sent_txt = "sentiment-bull", "🟡 Cautious Bull — positive but selective"
elif breadth["dec"] > breadth["adv"] * 1.5 and p50 < 40:
    sent_cls, sent_txt = "sentiment-bear", "🔴 Bear Pressure — raise cash, protect capital"
else:
    sent_cls, sent_txt = "sentiment-neut", "⚪ Neutral — wait for clearer signal"

st.markdown(f"""
<div class="{sent_cls}">
  <b>{sent_txt}</b> &nbsp;·&nbsp;
  A/D {breadth['adv']}/{breadth['dec']} (ratio {ad:.2f}) &nbsp;·&nbsp;
  New 52W Highs <b>{breadth['new_52h']}</b> vs Lows <b>{breadth['new_52l']}</b> &nbsp;·&nbsp;
  Volume Surges <b>{breadth['vol_surge']}</b>
</div>
""", unsafe_allow_html=True)

# 6 key metrics
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("🟢 Advancing", breadth["adv"])
m2.metric("🔴 Declining", breadth["dec"])
m3.metric("Up ≥2%",       breadth["up2"])
m4.metric("Dn ≥2%",       breadth["dn2"])
m5.metric("Stage 2 🚀",    breadth["stage2"])
m6.metric("Oversold 🟢",   breadth["oversold"])

# Charts row
ch1, ch2, ch3 = st.columns([1, 1.2, 1.6])
with ch1:
    st.plotly_chart(donut_ad(breadth["adv"], breadth["dec"], breadth["unc"]),
                    use_container_width=True)
with ch2:
    st.plotly_chart(bar_ma_health(breadth["pct_ma50"], breadth["pct_ma200"]),
                    use_container_width=True)
    st.markdown(f"""
    <div style="font-size:12px; color:#64748b; margin-top:4px;">
    Up ≥5%: <b>{breadth['up5']}</b> &nbsp;|&nbsp; Dn ≥5%: <b>{breadth['dn5']}</b> &nbsp;|&nbsp;
    Overbought: <b>{breadth['overbought']}</b>
    </div>""", unsafe_allow_html=True)
with ch3:
    st.plotly_chart(histogram_chg(df_all), use_container_width=True)

st.divider()

# ─────────────────────────────────────────────
#  SECTION 2 — RELATIVE STRENGTH
# ─────────────────────────────────────────────
st.markdown('<p class="pulse-section-title">⚡ Relative Strength vs Nifty 50 — 63 Days</p>', unsafe_allow_html=True)
st.caption("Stocks in bottom-right quadrant (fell less than Nifty) = hidden accumulation = watch for upmove when sentiment turns.")

rs1, rs2 = st.columns([1.6, 1.2])
with rs1:
    st.plotly_chart(rs_scatter(df_all), use_container_width=True)
with rs2:
    st.plotly_chart(rs_bar_top(df_all, 20), use_container_width=True)

# Strength-in-weakness box
if nifty_chg < -0.5:
    resilient = df_all[df_all["Chg%"] > nifty_chg].nlargest(8, "RS Spread")["Symbol"].tolist()
    st.markdown(f"""
    <div class="pulse-card">
      <b>💎 Strength in Weakness (Nifty {nifty_chg:+.2f}%)</b><br>
      <span style="font-size:13px; color:#475569;">
      Stocks outperforming Nifty today — likely to lead the next upmove:<br>
      <b>{' · '.join(resilient)}</b>
      </span>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ─────────────────────────────────────────────
#  SECTION 3 — FILTERS + TABLE
# ─────────────────────────────────────────────
st.markdown('<p class="pulse-section-title">🔍 Filter & Stock Table</p>', unsafe_allow_html=True)

with st.expander("⚙ Filters", expanded=True):
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        min_chg  = st.number_input("Min Chg%",      value=None, step=0.5, placeholder="e.g. 2.0")
        max_chg  = st.number_input("Max Chg%",      value=None, step=0.5, placeholder="e.g. -2.0")
    with f2:
        min_vol  = st.number_input("Min Vol Ratio", value=0.0,  step=0.5, min_value=0.0)
        min_rs   = st.number_input("Min RS Spread%",value=None, step=1.0, placeholder="e.g. 5.0")
    with f3:
        rsi_min  = st.slider("RSI Min", 0,  100, 0)
        rsi_max  = st.slider("RSI Max", 0,  100, 100)
    with f4:
        above200 = st.checkbox("Above MA200")
        above50  = st.checkbox("Above MA50")
        stg2     = st.checkbox("Stage 2 only")
        mv_only  = st.checkbox("Minervini TT only")
    with f5:
        near_ath = st.checkbox("Within 20% of ATH")
        sort_col = st.selectbox("Sort by", ["Score","RS Spread","Chg%","Vol Ratio","RSI","From ATH%"])
        sort_asc = st.checkbox("Ascending")

# Apply filters
fdf = df_all.copy()
if min_chg  is not None:          fdf = fdf[fdf["Chg%"] >= float(min_chg)]
if max_chg  is not None:          fdf = fdf[fdf["Chg%"] <= float(max_chg)]
if min_vol  > 0:                   fdf = fdf[fdf["Vol Ratio"] >= min_vol]
if min_rs   is not None:           fdf = fdf[fdf["RS Spread"] >= float(min_rs)]
if rsi_min  > 0:                   fdf = fdf[fdf["RSI"] >= rsi_min]
if rsi_max  < 100:                 fdf = fdf[fdf["RSI"] <= rsi_max]
if above200:                       fdf = fdf[fdf["Above MA200"] == True]
if above50:                        fdf = fdf[fdf["Above MA50"] == True]
if stg2:                           fdf = fdf[fdf["Stage"] == "Stage 2 ▲"]
if mv_only:                        fdf = fdf[fdf["Minervini"] == "✅ Trend Template"]
if near_ath:                       fdf = fdf[fdf["From ATH%"] >= -20]
fdf = fdf.sort_values(sort_col, ascending=sort_asc)

st.caption(f"Showing **{len(fdf)}** of {len(df_all)} stocks")

# Table — only clean display columns
SHOW_COLS = ["Score Rank","Symbol","LTP","Chg%","RSI","RSI Tag","RS Spread","RS Rank",
             "Vol Ratio","Vol Tag","From ATH%","52W High%","vs MA50%","vs MA200%","Stage","Minervini","Score"]
show = fdf[[c for c in SHOW_COLS if c in fdf.columns]].copy()

# Column configs
col_cfg = {
    "Score Rank":    st.column_config.NumberColumn("#", format="%d"),
    "Symbol":        st.column_config.TextColumn("Symbol"),
    "LTP":           st.column_config.NumberColumn("LTP", format="₹%.2f"),
    "Chg%":         st.column_config.NumberColumn("Chg%", format="%.2f%%"),
    "RSI":           st.column_config.NumberColumn("RSI", format="%.1f"),
    "RSI Tag":       st.column_config.TextColumn("RSI View", width="small"),
    "RS Spread":     st.column_config.NumberColumn("RS Spread", format="%.2f%%"),
    "RS Rank":       st.column_config.NumberColumn("RS Rank", format="%d"),
    "Vol Ratio":     st.column_config.NumberColumn("Vol Ratio", format="%.2fx"),
    "Vol Tag":       st.column_config.TextColumn("Volume", width="medium"),
    "From ATH%":    st.column_config.NumberColumn("vs ATH", format="%.1f%%"),
    "52W High%":    st.column_config.NumberColumn("52W High", format="%.1f%%"),
    "vs MA50%":     st.column_config.NumberColumn("vs MA50", format="%.1f%%"),
    "vs MA200%":    st.column_config.NumberColumn("vs MA200", format="%.1f%%"),
    "Stage":         st.column_config.TextColumn("Stage", width="small"),
    "Minervini":     st.column_config.TextColumn("Minervini", width="small"),
    "Score":         st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
}

st.dataframe(show, use_container_width=True, height=520,
             column_config=col_cfg, hide_index=True)

# Export
csv = fdf[[c for c in SHOW_COLS if c in fdf.columns]].to_csv(index=False).encode()
st.download_button("📥 Export CSV", csv,
                   f"market_pulse_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                   "text/csv")

st.divider()

# ─────────────────────────────────────────────
#  SECTION 4 — DEEP-DIVE
# ─────────────────────────────────────────────
st.markdown('<p class="pulse-section-title">🔬 Stock Deep-Dive</p>', unsafe_allow_html=True)

sel = st.selectbox("Select stock",
                   fdf["Symbol"].tolist() if len(fdf) else df_all["Symbol"].tolist(),
                   label_visibility="collapsed")

if sel and sel in stock_data:
    row = df_all[df_all["Symbol"] == sel].iloc[0]
    sdf = stock_data[sel]

    # Key metrics
    d1, d2, d3, d4, d5, d6 = st.columns(6)
    chg_color = "normal" if row["Chg%"] >= 0 else "inverse"
    d1.metric("LTP",        f"₹{row['LTP']:,.2f}", delta=f"{row['Chg%']:+.2f}%")
    d2.metric("RSI (14)",   f"{row['RSI']}",        delta=row["RSI Tag"])
    d3.metric("RS Spread",  f"{row['RS Spread']:+.1f}%")
    d4.metric("Volume",     f"{row['Vol Ratio']:.2f}x", delta=row["Vol Tag"])
    d5.metric("Score",      f"{row['Score']:.0f}/100")
    d6.metric("Stage",      row["Stage"])

    # Price levels inline
    l1, l2, l3, l4 = st.columns(4)
    l1.metric("vs ATH",     f"{row['From ATH%']:.1f}%")
    l2.metric("vs 3M High", f"{row['3M High%']:.1f}%")
    l3.metric("vs MA50",    f"{row['vs MA50%']:+.1f}%")
    l4.metric("Minervini",  row["Minervini"])

    # Charts
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        st.plotly_chart(price_chart(sel, sdf), use_container_width=True)
    with c2:
        rsi_s = row["_rsi_s"]
        st.plotly_chart(rsi_chart(sel, rsi_s, row["RSI"]), use_container_width=True)
    with c3:
        # RS line vs Nifty 63d
        close_s = row["_close"]
        bench_t = bench_close.tail(len(close_s)).values
        if len(bench_t) >= 10:
            base_s = close_s.values[-min(63, len(close_s)):]
            base_b = bench_t[-min(63, len(bench_t)):]
            rs_line = (base_s / base_s[0]) / (base_b / base_b[0])
            color_rs = "#16a34a" if rs_line[-1] > 1 else "#dc2626"
            fig_rs = go.Figure()
            fig_rs.add_hline(y=1, line_dash="dot", line_color="#94a3b8")
            fig_rs.add_trace(go.Scatter(
                x=list(range(len(rs_line))), y=rs_line,
                mode="lines", line=dict(color=color_rs, width=2),
                fill="tozeroy", fillcolor=f"rgba(22,163,74,0.05)",
            ))
            fig_rs.add_annotation(x=len(rs_line)-1, y=float(rs_line[-1]),
                                   text=f"{float(rs_line[-1]):.3f}",
                                   showarrow=False, font=dict(size=11, color=color_rs),
                                   xanchor="right")
            fig_rs.update_layout(
                height=200, margin=dict(l=30,r=10,t=30,b=10),
                paper_bgcolor=CHART_BG, plot_bgcolor="#f8fafc",
                font=dict(color=FONT_COL), showlegend=False,
                xaxis=dict(showticklabels=False, showgrid=False),
                yaxis=dict(gridcolor=GRID_COL),
                title=dict(text="RS vs Nifty 63d", font=dict(size=13)),
            )
            st.plotly_chart(fig_rs, use_container_width=True)

    # Auto-insights
    insights = []
    if row["Vol Ratio"] >= 1.5:
        insights.append(f"🔊 Volume is **{row['Vol Ratio']:.1f}x** the 10-day average — institutional activity possible")
    if row["From ATH%"] >= -3:
        insights.append("🏆 Trading near **All-Time High** — strong demand zone, breakout watch")
    if row["RSI"] <= 35:
        insights.append(f"🟢 RSI at **{row['RSI']}** — approaching oversold, watch for reversal signal")
    if row["RSI"] >= 70:
        insights.append(f"🔴 RSI at **{row['RSI']}** — extended, may see pause or pullback")
    if (row["RS Spread"] or 0) >= 10:
        insights.append(f"⚡ Outperforming Nifty by **{row['RS Spread']:+.1f}%** over 63 days — leadership stock")
    if row["Minervini"] == "✅ Trend Template":
        insights.append("✅ **Minervini Trend Template** confirmed — all 8 criteria met")
    if row["Stage"] == "Stage 4 ▼":
        insights.append("⚠️ **Weinstein Stage 4** — downtrend active, avoid new entries")
    if row["Stage"] == "Stage 2 ▲":
        insights.append("🚀 **Weinstein Stage 2** — advancing stage, best zone for entries")
    if row["vs MA200%"] < -10:
        insights.append(f"📉 Price is **{row['vs MA200%']:.1f}%** below 200d MA — avoid until reclaim")
    if row["Chg%"] > 0 and nifty_chg < 0:
        insights.append(f"💪 **Rising on a down market day** (Nifty {nifty_chg:.2f}%) — hidden strength signal")
    elif row["Chg%"] < 0 and abs(row["Chg%"]) < abs(nifty_chg) * 0.5 and nifty_chg < 0:
        insights.append(f"🛡 Falling only **{row['Chg%']:.2f}%** vs Nifty {nifty_chg:.2f}% — relative strength in weakness")

    if insights:
        with st.container():
            st.markdown("**📋 Insights**")
            for ins in insights:
                st.markdown(f"- {ins}")

st.divider()

# ─────────────────────────────────────────────
#  SECTION 5 — STRENGTH IN WEAKNESS (contextual)
# ─────────────────────────────────────────────
if nifty_chg < -0.3:
    st.markdown('<p class="pulse-section-title">💎 Strength in Weakness — Today\'s Resilience Leaders</p>', unsafe_allow_html=True)
    st.caption(f"Nifty is {nifty_chg:+.2f}% today. O'Neil principle: stocks outperforming on down days are being accumulated. These lead the next rally.")
    siw = df_all.copy()
    siw["Relative Today"] = siw["Chg%"] - nifty_chg
    siw = siw.nlargest(30, "Relative Today")
    siw_show = siw[["Symbol","LTP","Chg%","Relative Today","RS Spread","Vol Ratio","RSI","Stage","Score"]].copy()
    st.dataframe(siw_show, use_container_width=True, height=420,
                 column_config={
                     "LTP":            st.column_config.NumberColumn(format="₹%.2f"),
                     "Chg%":          st.column_config.NumberColumn(format="%.2f%%"),
                     "Relative Today": st.column_config.NumberColumn("vs Nifty Today", format="+%.2f%%"),
                     "RS Spread":      st.column_config.NumberColumn(format="%.2f%%"),
                     "Vol Ratio":      st.column_config.NumberColumn(format="%.2fx"),
                     "Score":          st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
                 }, hide_index=True)
    st.divider()

# ─────────────────────────────────────────────
#  LEGEND
# ─────────────────────────────────────────────
with st.expander("📖 Methodology"):
    st.markdown("""
    | Metric | Source | Meaning |
    |--------|--------|---------|
    | **Score (0-100)** | Composite | RS(30) + Price position(20) + Volume(15) + RSI(15) + Minervini(20) |
    | **RS Spread** | O'Neil / IBD | % outperformance vs Nifty 50 over 63 trading days (≈ 3 months) |
    | **RS Rank** | IBD-style | 1 = strongest RS in scanned universe |
    | **Vol Ratio** | CANSLIM "S" | Today's volume ÷ 10-day avg. ≥1.5x = institutional signal |
    | **Stage** | Stan Weinstein | Stage 2 ▲ = advancing (buy zone), Stage 4 ▼ = decline (avoid) |
    | **Minervini TT** | Mark Minervini | 8-criteria: price vs MA alignment, MA slope, 52w range |
    | **Strength in Weakness** | Livermore / O'Neil | Stocks falling less than market = hidden accumulation |
    | **A/D Ratio** | Market breadth | Advancing ÷ Declining. >1.5 = broad bull, <0.8 = bear |
    
    **Quick call framework:** Score ≥70 + Stage 2 + Vol ≥1.5x → **strong candidate** · Strength in weakness + RS Rank top 20 → **watch for entry** · Stage 4 → **avoid**
    """)

st.caption(f"AlphaRadar Market Pulse · {scan_ts} · Data: {'Breeze Live' if DATA_SOURCE == 'breeze' else 'yfinance 15-min delay'}")

st.markdown("""
<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:10px 14px;margin-top:8px;">
<p style="font-size:11px;color:#991b1b;margin:0;">
<b>⚠️ DISCLAIMER:</b> Educational/research tool only. Not SEBI-registered. Not investment advice.
All scores are algorithmic. Past performance does not guarantee future results. Trade at your own risk.
</p></div>
""", unsafe_allow_html=True)
