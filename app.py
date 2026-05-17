"""
AlphaRadar — Main Application  (v4)
======================================
Single-URL, four-tab layout:
  🎯  Manas Arora      — SVRO/VCP scanner, backtest, playbook (Breeze live data)
  📊  N250F            — Fortnightly momentum strategy + live portfolio tracker
  ◎   Nifty Total Mkt — Weinstein/O'Neil/Minervini scoring (Supabase, daily cron)
  📡  Market Pulse     — NSE 1000 breadth engine (Supabase, daily cron)
"""
import sys
import os
import streamlit as st

# StopException: raised by st.stop() inside a sub-page.
# We catch it so it only stops that tab's render, not the whole app.
try:
    from streamlit.runtime.scriptrunner import StopException
except ImportError:
    try:
        from streamlit.runtime.scriptrunner.script_runner import StopException
    except ImportError:
        StopException = SystemExit  # safe fallback — should never reach this

st.set_page_config(
    page_title="AlphaRadar",
    page_icon="◎",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  .stApp { background:#ffffff; }
  .main .block-container { padding:0.5rem 1.2rem 1.5rem; max-width:100%; }
  div[data-testid="stMetricValue"] { font-size:1.35rem; font-weight:700; color:#0f172a; }
  div[data-testid="stMetricLabel"] { font-size:0.71rem; color:#64748b; font-weight:500; }
  section[data-testid="stSidebar"] { display:none; }
  div[data-testid="collapsedControl"] { display:none; }
  div[data-testid="stTabs"] > div:first-child { border-bottom:2px solid #e2e8f0; gap:0; }
  button[data-baseweb="tab"] {
    font-size:0.88rem; font-weight:600; color:#64748b;
    padding:10px 22px; border:none; border-bottom:3px solid transparent;
    background:transparent; border-radius:0; transition:all .15s;
  }
  button[data-baseweb="tab"]:hover { color:#1e293b; background:#f8fafc; }
  button[data-baseweb="tab"][aria-selected="true"] {
    color:#2563eb; border-bottom-color:#2563eb; background:transparent;
  }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="display:flex;align-items:baseline;gap:14px;padding:4px 0 8px">
  <span style="font-size:1.45rem;font-weight:800;color:#0f172a;letter-spacing:-0.5px">◎ AlphaRadar</span>
  <span style="font-size:0.75rem;color:#94a3b8;letter-spacing:0.06em;text-transform:uppercase">
    Weinstein · O'Neil · Minervini · Manas Arora
  </span>
</div>
""", unsafe_allow_html=True)

ROOT = os.path.dirname(os.path.abspath(__file__))


def _run_page(relpath: str):
    """
    Execute a page file inside the current tab context via compile + exec.
    No importlib module-naming restrictions. StopException is caught so
    st.stop() in a sub-page only halts that tab, not the whole app.
    """
    abs_path = os.path.join(ROOT, relpath)
    for p in [ROOT, os.path.dirname(abs_path)]:
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        with open(abs_path, "r", encoding="utf-8") as fh:
            source = fh.read()
        code = compile(source, abs_path, "exec")
        exec(code, {"__file__": abs_path, "__name__": "__main__"})  # noqa: S102
    except StopException:
        pass  # st.stop() called — normal flow, just stop rendering this tab
    except Exception as e:
        st.error(f"⚠️ Error loading `{relpath}`:\n\n```\n{e}\n```")
        import traceback
        with st.expander("Full traceback"):
            st.code(traceback.format_exc())


tab_guide, tab_mp, tab_ntm, tab_ranker, tab_ma, tab_n250 = st.tabs([
    "📖  Guide",
    "📡  Market Pulse",
    "◎   Nifty Total Market",
    "🏆  N500 Ranker",
    "🎯  Manas Arora",
    "📊  N250F",
])

with tab_guide:
    _run_page("pages/guide.py")

with tab_mp:
    _run_page("pages/4_📡_Market_Pulse.py")

with tab_ntm:
    _run_page("pages/_nifty_total_market.py")

with tab_ranker:
    _run_page("pages/5_🏆_N500_Strength_Ranker.py")

with tab_ma:
    _run_page("pages/manas_arora.py")

with tab_n250:
    _run_page("pages/3_📊_N250F.py")
