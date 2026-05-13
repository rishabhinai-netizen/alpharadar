"""
AlphaRadar — Main Application  (v4)
======================================
Single-URL, four-tab layout:
  🎯  Manas Arora      — SVRO/VCP scanner, backtest, playbook (Breeze live data)
  📊  N250F            — Fortnightly momentum strategy + live portfolio tracker
  ◎   Nifty Total Mkt — Weinstein/O'Neil/Minervini scoring (Supabase, daily cron)
  📡  Market Pulse     — NSE 1000 breadth engine (Supabase, daily cron)
"""
import importlib.util
import sys
import os
import streamlit as st

# ── Page config — set once here, all sub-pages guard theirs with try/except ──
st.set_page_config(
    page_title="AlphaRadar",
    page_icon="◎",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global light-theme CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background:#ffffff; }
  .main .block-container { padding:0.5rem 1.2rem 1.5rem; max-width:100%; }

  /* Metrics */
  div[data-testid="stMetricValue"] { font-size:1.35rem; font-weight:700; color:#0f172a; }
  div[data-testid="stMetricLabel"] { font-size:0.71rem; color:#64748b; font-weight:500; }

  /* Hide sidebar toggle & default page-nav */
  section[data-testid="stSidebar"] { display:none; }
  div[data-testid="collapsedControl"] { display:none; }

  /* Tab strip styling */
  div[data-testid="stTabs"] > div:first-child {
    border-bottom:2px solid #e2e8f0; gap:0;
  }
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

# ── Brand header ──────────────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex;align-items:baseline;gap:14px;padding:4px 0 8px">
  <span style="font-size:1.45rem;font-weight:800;color:#0f172a;letter-spacing:-0.5px">◎ AlphaRadar</span>
  <span style="font-size:0.75rem;color:#94a3b8;letter-spacing:0.06em;text-transform:uppercase">
    Weinstein · O'Neil · Minervini · Manas Arora
  </span>
</div>
""", unsafe_allow_html=True)


def _run_page(relpath: str):
    """
    Execute a page file inside the current tab context.
    set_page_config calls in sub-pages are guarded with try/except so they
    are silently skipped (config is already set above).
    """
    abs_path = os.path.join(os.path.dirname(__file__), relpath)
    spec = importlib.util.spec_from_file_location("_ar_page", abs_path)
    mod = importlib.util.module_from_spec(spec)
    # Give the module a fresh __name__ so it doesn't collide with __main__
    mod.__name__ = "_ar_page_" + relpath.replace("/","_").replace(".","_")
    spec.loader.exec_module(mod)


# ── Four tabs ─────────────────────────────────────────────────────────────────
tab_ma, tab_n250, tab_ntm, tab_mp = st.tabs([
    "🎯  Manas Arora",
    "📊  N250F",
    "◎   Nifty Total Market",
    "📡  Market Pulse",
])

with tab_ma:
    _run_page("pages/manas_arora.py")

with tab_n250:
    _run_page("pages/3_📊_N250F.py")

with tab_ntm:
    _run_page("pages/_nifty_total_market.py")

with tab_mp:
    _run_page("pages/4_📡_Market_Pulse.py")
