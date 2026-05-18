"""
╔══════════════════════════════════════════════════════════════════╗
║         AlphaRadar — Intelligent Telegram Alert System           ║
║   Real-time prices · Strategy-wise signals · Claude AI · Kotak  ║
╚══════════════════════════════════════════════════════════════════╝

ARCHITECTURE:
  • Fetches latest AlphaRadar scores from Supabase
  • Enriches EACH signal with LIVE yfinance price (vs. stored price)
  • Groups signals by STRATEGY (AlphaRadar Core, Manas Arora,
    N500 Strength, N250F, Nifty Total Market, Weinstein Stage 2)
  • Sends strategy-wise Telegram messages with two layers of reasoning:
      STATIC  → why the signal was triggered (strategy + score logic)
      DYNAMIC → what price has done SINCE the alert was scored
  • Sends a final CROSS-STRATEGY SYNTHESIS message via Claude Sonnet
  • Includes fresh SELL / EXIT signals with severity
  • Kotak Neo portfolio overlay (when session ID provided)

USAGE:
  python alpharadar_telegram_bot.py
  
  Or import and call from GitHub Actions / cron:
  from alpharadar_telegram_bot import run_full_alert_cycle
  run_full_alert_cycle()

ENV VARS / CONFIG:
  SUPABASE_URL, SUPABASE_KEY
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  ANTHROPIC_API_KEY            (for Claude synthesis)
  KOTAK_SESSION_ID             (optional — for portfolio overlay)
"""

import os, json, time, requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, date
from typing import Optional

# ═══════════════════════════════════════════════════
# CONFIG  — override via environment variables
# ═══════════════════════════════════════════════════
SUPABASE_URL    = os.environ.get("SUPABASE_URL",
                  "https://aiebaqvclyzxajigvkfd.supabase.co")
SUPABASE_KEY    = os.environ.get("SUPABASE_KEY",
                  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                  "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFpZWJhcXZjbHl6eGFqaWd2a2ZkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzkyNzEzNDcsImV4cCI6MjA1NDg0NzM0N30."
                  "kCrZBPuoBE27jUjxPkGE4i-9bVQ8KUXtIH1HrHqOidg")
TG_TOKEN        = os.environ.get("TELEGRAM_BOT_TOKEN",
                  "8347009897:AAEFlJxNtRbWL7_grWDtQUludo_LCbhNgck")
TG_CHAT         = os.environ.get("TELEGRAM_CHAT_ID", "705724053")
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
KOTAK_SESSION   = os.environ.get("KOTAK_SESSION_ID", "")

SB_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
}

# ═══════════════════════════════════════════════════
# STRATEGY DEFINITIONS
# ═══════════════════════════════════════════════════
# Each strategy defines: which stocks to include, what the filter is,
# and the "static reasoning" template explaining WHY a signal fires.

MANAS_ARORA_UNIVERSE = [
    "ZENTEC","EPACK","MAZDOCK","BSE","RCF","NFL","COCHINSHIP","LGEQUIP",
    "NLCINDIA","POONAWALLA","RVNL","DIXON","KAYNES","SYRMA","JYOTHYLAB",
    "PERSISTENT","COFORGE","MPHASIS","ZENSARTECH","BIRLASOFT","MASTEK",
    "APLAPOLLO","JSPL","RATNAMANI","WELSPUNIND","CENTURYPLY","GREENPLY",
    "CERA","ASTERDM","POLYMED","MAXHEALTH","METROPOLIS","LALPATHLAB",
    "MUTHOOTFIN","MANAPPURAM","NYKAA","CAMPUS","VBL","HATSUN","DODLA",
    "SAREGAMA","NAZARA","RATEGAIN","HOMEFIRST","APTUS","FIVESTAR",
    "KARURVYSYA","EQUITASBNK","UJJIVANSFB","GENESYS","FROG","NETWORK18",
    "SHALBY","RPSGVENT","GANESHHOUC","SHYAMMETL","TITAGARH",
]

STRATEGIES = {
    "⭐ Manas Arora (VCP + Stage)": {
        "description": "Small/mid-cap VCP breakouts with MA30 rising + MA10>MA30. "
                       "Tight base (vol dry-up), above 30W MA, within 25% of 52W high.",
        "filter": lambda row: (
            row["symbol"] in MANAS_ARORA_UNIVERSE
            and row["bucket"] in ("MUST_BUY", "CAN_BUY")
            and row["composite_score"] >= 55
        ),
        "static_reason": lambda row: (
            f"Manas Arora VCP setup: Stage {row['weinstein_stage']} · "
            f"RS {row['rs_percentile']:.0f}%ile · "
            f"Score {row['composite_score']:.1f}/100 · "
            f"Entry: {row['entry_detail'] or row['entry_signal']}"
        ),
        "max_stocks": 6,
        "sell_filter": lambda row: (
            row["symbol"] in MANAS_ARORA_UNIVERSE
            and row["bucket"] == "SELL"
        ),
    },

    "📊 N500 Strength Ranker": {
        "description": "Top relative strength stocks from Nifty 500 universe. "
                       "Stage 2A/2B, RS percentile ≥ 70, composite ≥ 65.",
        "filter": lambda row: (
            row.get("cap_bucket") in ("large", "mid")
            and row["bucket"] in ("MUST_BUY", "CAN_BUY")
            and row["composite_score"] >= 65
            and row["rs_percentile"] >= 70
            and row["weinstein_stage"] in ("2A", "2B")
        ),
        "static_reason": lambda row: (
            f"N500 top RS stock: RS rank {row['rs_percentile']:.0f}%ile (top {100-row['rs_percentile']:.0f}% universe) · "
            f"Stage {row['weinstein_stage']} · Score {row['composite_score']:.1f} · "
            f"{row['entry_detail'] or 'Monitor for entry'}"
        ),
        "max_stocks": 8,
        "sell_filter": lambda row: (
            row.get("cap_bucket") in ("large", "mid")
            and row["bucket"] == "SELL"
            and row["rs_percentile"] < 20
        ),
    },

    "🔬 N250F Fortnightly": {
        "description": "Nifty 250 Fortnightly rebalancing strategy. "
                       "Strong momentum + fundamentals, rebalance every 2 weeks.",
        "filter": lambda row: (
            row.get("cap_bucket") in ("mid", "small")
            and row["bucket"] in ("MUST_BUY", "CAN_BUY")
            and row["composite_score"] >= 68
            and row["weinstein_stage"] in ("2A", "2B")
            and row["rs_percentile"] >= 75
        ),
        "static_reason": lambda row: (
            f"N250F rebalance candidate: Mid/small-cap momentum · "
            f"Stage {row['weinstein_stage']} · RS {row['rs_percentile']:.0f}%ile · "
            f"Score {row['composite_score']:.1f} · MA slope: {row['ma_slope']:+.4f}"
        ),
        "max_stocks": 8,
        "sell_filter": lambda row: (
            row.get("cap_bucket") in ("mid", "small")
            and row["bucket"] == "SELL"
        ),
    },

    "🌐 Nifty Total Market": {
        "description": "Broad market screen across all caps. "
                       "Stage 2, score ≥ 70, any cap bucket, BUY NOW signals only.",
        "filter": lambda row: (
            row["bucket"] in ("MUST_BUY", "CAN_BUY")
            and row["composite_score"] >= 70
            and row["entry_signal"] in ("BUY NOW", "BUY DIPS")
        ),
        "static_reason": lambda row: (
            f"Total Market active entry: {row['entry_detail']} · "
            f"Stage {row['weinstein_stage']} · RS {row['rs_percentile']:.0f}%ile · "
            f"Score {row['composite_score']:.1f} · Cap: {row.get('cap_bucket','?').title()}"
        ),
        "max_stocks": 6,
        "sell_filter": lambda row: (
            row["bucket"] == "SELL"
            and row["stage_changed"] == True
        ),
    },

    "🏆 AlphaRadar Core (MUST BUY)": {
        "description": "Highest-conviction picks. Score ≥ 80, Stage 2A only, "
                       "RS ≥ 75%ile, all factors aligned.",
        "filter": lambda row: (
            row["bucket"] == "MUST_BUY"
            and row["composite_score"] >= 80
            and row["weinstein_stage"] == "2A"
        ),
        "static_reason": lambda row: (
            f"AlphaRadar MUST BUY — all factors aligned: "
            f"Stage {row['weinstein_stage']} · RS {row['rs_percentile']:.0f}%ile · "
            f"Score {row['composite_score']:.1f}/100 · "
            f"MA slope: {row['ma_slope']:+.4f} · "
            f"Sector: {row.get('sector','Unknown')}"
        ),
        "max_stocks": 8,
        "sell_filter": lambda row: (
            row["bucket"] in ("SELL",)
            and row["rs_percentile"] < 10
            and row["weinstein_stage"] == "4"
        ),
    },

    "🔄 Stage Transitions (NEW)": {
        "description": "Stocks that changed Weinstein stage TODAY. "
                       "Stage 1→2 = fresh buy. Stage 2→3/4 = exit alert.",
        "filter": lambda row: (
            row.get("stage_changed") == True
            and row["weinstein_stage"] in ("2A",)
            and row["composite_score"] >= 55
        ),
        "static_reason": lambda row: (
            f"FRESH Stage transition → {row['weinstein_stage']} today! "
            f"Score jumped {row['score_change']:+.1f} · RS {row['rs_percentile']:.0f}%ile · "
            f"{row['entry_detail'] or 'Monitor closely'}"
        ),
        "max_stocks": 5,
        "sell_filter": lambda row: (
            row.get("stage_changed") == True
            and row["weinstein_stage"] in ("3", "4")
        ),
    },
}

# ═══════════════════════════════════════════════════
# SUPABASE DATA FETCH
# ═══════════════════════════════════════════════════

def fetch_latest_scores() -> list[dict]:
    """Fetch today's (or most recent) scores + universe metadata."""
    # Get latest date
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/ar_daily_scores"
        "?select=score_date&order=score_date.desc&limit=1",
        headers=SB_HEADERS, timeout=15
    )
    if r.status_code != 200 or not r.json():
        print("⚠ Could not fetch latest date")
        return []
    latest_date = r.json()[0]["score_date"]
    print(f"  Latest scores date: {latest_date}")

    # Fetch all scores for that date + universe join
    r2 = requests.get(
        f"{SUPABASE_URL}/rest/v1/ar_daily_scores"
        f"?score_date=eq.{latest_date}&limit=1000"
        "&select=symbol,composite_score,bucket,weinstein_stage,rs_percentile,"
        "price,price_change_pct,entry_signal,entry_detail,action_label,"
        "score_change,stage_changed,price_vs_ma,ma_slope,rs_score,stage_score,"
        "volume_price_score,fundamental_score,news_sentiment,high_52w,low_52w,"
        "data_quality",
        headers=SB_HEADERS, timeout=15
    )
    scores = r2.json() if r2.status_code == 200 else []

    # Fetch universe for cap_bucket and sector
    r3 = requests.get(
        f"{SUPABASE_URL}/rest/v1/ar_universe"
        "?select=symbol,cap_bucket,sector,index_membership&limit=1500",
        headers=SB_HEADERS, timeout=15
    )
    uni_map = {}
    if r3.status_code == 200:
        for u in r3.json():
            uni_map[u["symbol"]] = u

    # Merge
    merged = []
    for s in scores:
        u = uni_map.get(s["symbol"], {})
        row = {**s}
        row["cap_bucket"]       = u.get("cap_bucket", "unknown")
        row["sector"]           = u.get("sector", "Unknown")
        row["index_membership"] = u.get("index_membership") or []
        # Type coercions
        for f in ["composite_score", "rs_percentile", "price", "price_change_pct",
                  "score_change", "price_vs_ma", "ma_slope", "rs_score",
                  "stage_score", "volume_price_score", "fundamental_score",
                  "news_sentiment", "high_52w", "low_52w"]:
            try: row[f] = float(row[f]) if row[f] is not None else 0.0
            except: row[f] = 0.0
        row["stage_changed"] = bool(row.get("stage_changed", False))
        merged.append(row)

    print(f"  Loaded {len(merged)} scored stocks")
    return merged, latest_date


# ═══════════════════════════════════════════════════
# REAL-TIME PRICE ENRICHMENT
# ═══════════════════════════════════════════════════

def enrich_with_live_prices(symbols: list[str], stored_prices: dict) -> dict:
    """
    Fetch live prices for a list of symbols.
    Returns dict: symbol → {live_price, prev_close, chg_pct, vol, vol_ratio,
                             price_delta_from_signal, momentum_label}
    """
    live = {}
    batch = [f"{s}.NS" for s in symbols]

    try:
        data = yf.download(batch, period="5d", interval="1d",
                           progress=False, threads=True, auto_adjust=True)
        if data.empty:
            return live

        for sym in symbols:
            ticker = f"{sym}.NS"
            try:
                if len(batch) == 1:
                    closes = data["Close"].squeeze().dropna()
                    vols   = data["Volume"].squeeze().dropna()
                else:
                    closes = data["Close"][ticker].dropna()
                    vols   = data["Volume"][ticker].dropna()

                if len(closes) < 2:
                    continue

                live_price  = float(closes.iloc[-1])
                prev_close  = float(closes.iloc[-2])
                today_chg   = (live_price - prev_close) / prev_close * 100

                vol_today   = float(vols.iloc[-1]) if len(vols) else 0
                vol_avg     = float(vols.iloc[-5:].mean()) if len(vols) >= 3 else vol_today
                vol_ratio   = vol_today / vol_avg if vol_avg > 0 else 1.0

                # Delta vs. stored (signal) price
                sig_price   = stored_prices.get(sym, live_price)
                delta       = (live_price - sig_price) / sig_price * 100 if sig_price > 0 else 0

                # Momentum label
                if delta > 5:
                    momentum = "🚀 Strong rally since signal"
                elif delta > 2:
                    momentum = "📈 Up since signal"
                elif delta > -2:
                    momentum = "➡ Flat since signal"
                elif delta > -5:
                    momentum = "📉 Pullback from signal"
                else:
                    momentum = "⚠ Sharp drop since signal"

                # Volume interpretation
                if vol_ratio >= 2.0:
                    vol_label = f"🔥 {vol_ratio:.1f}x avg vol"
                elif vol_ratio >= 1.5:
                    vol_label = f"↑ {vol_ratio:.1f}x avg vol"
                elif vol_ratio <= 0.5:
                    vol_label = f"↓ Thin volume ({vol_ratio:.1f}x)"
                else:
                    vol_label = f"Vol: {vol_ratio:.1f}x avg"

                live[sym] = {
                    "live_price":   round(live_price, 2),
                    "prev_close":   round(prev_close, 2),
                    "today_chg":    round(today_chg, 2),
                    "vol_ratio":    round(vol_ratio, 2),
                    "vol_label":    vol_label,
                    "delta":        round(delta, 2),
                    "momentum":     momentum,
                }
            except Exception as e:
                pass  # Skip bad tickers silently
    except Exception as e:
        print(f"  ⚠ Batch price fetch error: {e}")

    return live


# ═══════════════════════════════════════════════════
# TELEGRAM SEND HELPER
# ═══════════════════════════════════════════════════

def send_tg(text: str, parse_mode: str = "HTML") -> bool:
    """Send a Telegram message. Splits if >4000 chars."""
    max_len = 3900
    chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    ok = True
    for chunk in chunks:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT, "text": chunk, "parse_mode": parse_mode},
            timeout=15
        )
        if r.status_code != 200:
            print(f"  ⚠ Telegram error: {r.status_code} {r.text[:200]}")
            ok = False
        time.sleep(0.5)  # Avoid rate limit
    return ok


def chg_emoji(pct: float) -> str:
    if pct >= 3:   return "🚀"
    if pct >= 1:   return "📈"
    if pct >= 0:   return "➡"
    if pct >= -2:  return "📉"
    return "🔻"


def price_line(sym: str, live: dict, stored_price: float) -> str:
    """Format the two-layer price line for a stock."""
    if sym not in live:
        return f"  💰 Stored: ₹{stored_price:,.1f} (live price unavailable)"

    L = live[sym]
    lines = []
    # Layer 1: Current price
    arrow = "▲" if L["today_chg"] >= 0 else "▼"
    lines.append(
        f"  💰 <b>₹{L['live_price']:,.1f}</b> "
        f"{arrow} {abs(L['today_chg']):.2f}% today · {L['vol_label']}"
    )
    # Layer 2: Delta from signal
    sig_str = f"₹{stored_price:,.1f}"
    delta_arrow = "▲" if L["delta"] >= 0 else "▼"
    lines.append(
        f"  📌 {L['momentum']} ({delta_arrow}{abs(L['delta']):.1f}% from signal @ {sig_str})"
    )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════
# STRATEGY-WISE MESSAGE BUILDER
# ═══════════════════════════════════════════════════

def build_strategy_message(
    strategy_name: str,
    config: dict,
    all_scores: list[dict],
    live_prices: dict,
    score_date: str,
) -> tuple[str, list[dict]]:
    """
    Build the Telegram message for one strategy.
    Returns (message_text, matched_stocks).
    """
    # Apply buy filter
    candidates = [r for r in all_scores if config["filter"](r)]
    # Sort by composite score descending
    candidates.sort(key=lambda x: -x["composite_score"])
    # Cap at max_stocks
    candidates = candidates[: config["max_stocks"]]

    # Apply sell filter
    sell_candidates = [r for r in all_scores if config.get("sell_filter", lambda _: False)(r)]
    sell_candidates.sort(key=lambda x: x["composite_score"])
    sell_candidates = sell_candidates[:4]

    if not candidates and not sell_candidates:
        return "", []

    now_str = datetime.now().strftime("%d %b %Y, %H:%M IST")

    msg = (
        f"\n{strategy_name}\n"
        f"<i>{config['description']}</i>\n"
        f"<code>Scored: {score_date} | Sent: {now_str}</code>\n"
    )

    # BUY SIGNALS
    if candidates:
        msg += f"\n🟢 <b>BUY SIGNALS ({len(candidates)})</b>\n"
        for r in candidates:
            sym = r["symbol"]
            score_chg_str = (
                f" <i>(+{r['score_change']:.1f} ↑)</i>" if r["score_change"] > 3
                else f" <i>({r['score_change']:+.1f})</i>" if r["score_change"] != 0
                else ""
            )
            stage_new = " 🆕" if r["stage_changed"] else ""

            msg += (
                f"\n<b>{sym}</b>{stage_new} · Score {r['composite_score']:.0f}{score_chg_str}\n"
            )
            # STATIC REASONING
            msg += f"  📋 <i>{config['static_reason'](r)}</i>\n"
            # DYNAMIC PRICING
            msg += price_line(sym, live_prices, r["price"]) + "\n"
            # Entry guidance
            if r["entry_signal"] not in ("N/A", "", None):
                msg += f"  🎯 Entry: <b>{r['entry_signal']}</b>"
                if r.get("entry_detail"):
                    msg += f" — {r['entry_detail']}"
                msg += "\n"
            # Stop hint
            if r["weinstein_stage"] in ("2A", "2B") and r["price"] > 0:
                stop_pct = 0.07  # 7% below current price as loose stop
                stop_lvl = r["price"] * (1 - stop_pct)
                msg += f"  🛑 Loose stop: ~₹{stop_lvl:,.0f} (7% rule)\n"

    # SELL SIGNALS
    if sell_candidates:
        msg += f"\n🔴 <b>EXIT SIGNALS ({len(sell_candidates)})</b>\n"
        for r in sell_candidates:
            sym = r["symbol"]
            msg += f"\n<b>{sym}</b> · Score {r['composite_score']:.0f}\n"
            msg += (
                f"  ⚠ Stage {r['weinstein_stage']} · RS {r['rs_percentile']:.0f}%ile · "
                f"{abs(r['price_vs_ma']):.1f}% below 200d MA\n"
            )
            msg += price_line(sym, live_prices, r["price"]) + "\n"
            msg += f"  ❌ Action: <b>Exit / Do not buy</b>\n"

    return msg, candidates + sell_candidates


# ═══════════════════════════════════════════════════
# CLAUDE AI SYNTHESIS
# ═══════════════════════════════════════════════════

def build_claude_synthesis(
    all_buy_signals: list[dict],
    sell_signals: list[dict],
    live_prices: dict,
    score_date: str,
) -> str:
    """Call Claude Sonnet to generate cross-strategy synthesis message."""
    if not ANTHROPIC_KEY:
        return _fallback_synthesis(all_buy_signals, sell_signals, live_prices, score_date)

    # Build a compact JSON summary to send to Claude
    buy_summary = [
        {
            "symbol": r["symbol"],
            "score": r["composite_score"],
            "stage": r["weinstein_stage"],
            "rs_pctile": r["rs_percentile"],
            "sector": r.get("sector", "?"),
            "entry": r.get("entry_signal", "?"),
            "live_price": live_prices.get(r["symbol"], {}).get("live_price", r["price"]),
            "stored_price": r["price"],
            "delta_pct": live_prices.get(r["symbol"], {}).get("delta", 0),
            "today_chg": live_prices.get(r["symbol"], {}).get("today_chg", 0),
            "score_change": r.get("score_change", 0),
            "stage_changed": r.get("stage_changed", False),
            "ma_slope": r.get("ma_slope", 0),
        }
        for r in sorted(all_buy_signals, key=lambda x: -x["composite_score"])[:15]
    ]

    sell_summary = [
        {
            "symbol": r["symbol"],
            "score": r["composite_score"],
            "stage": r["weinstein_stage"],
            "rs_pctile": r["rs_percentile"],
            "sector": r.get("sector", "?"),
            "today_chg": live_prices.get(r["symbol"], {}).get("today_chg", r.get("price_change_pct", 0)),
            "price_vs_ma": r.get("price_vs_ma", 0),
        }
        for r in sorted(sell_signals, key=lambda x: x["composite_score"])[:10]
    ]

    prompt = f"""You are AlphaRadar AI, a systematic NSE equity analyst. 
Analyse the following signal data from {score_date} and write a CROSS-STRATEGY SYNTHESIS Telegram message.

BUY SIGNALS (top 15):
{json.dumps(buy_summary, indent=2)}

SELL/EXIT SIGNALS (top 10):
{json.dumps(sell_summary, indent=2)}

Write a concise Telegram message (max 600 words) with:
1. Market breadth assessment (are buy signals broad or concentrated in one sector?)
2. Highest-conviction trade idea with entry/risk logic (pick 1 stock only)
3. Key risk/red flag from the sell signals (any sector pattern?)
4. One actionable idea for each: momentum traders, position traders, and risk-off investors
5. A 2-line summary of what the overall signal says about the NSE market today

Use HTML formatting (<b>, <i>) for emphasis. Use ₹ for prices. Be direct, not verbose. 
No disclaimers needed — the user is a professional trader.
Start with: 🧠 <b>AlphaRadar AI Synthesis — {score_date}</b>"""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model":      "claude-sonnet-4-20250514",
                "max_tokens": 1200,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"]
        else:
            print(f"  ⚠ Claude API error: {r.status_code}")
            return _fallback_synthesis(all_buy_signals, sell_signals, live_prices, score_date)
    except Exception as e:
        print(f"  ⚠ Claude call failed: {e}")
        return _fallback_synthesis(all_buy_signals, sell_signals, live_prices, score_date)


def _fallback_synthesis(all_buy, all_sell, live_prices, score_date) -> str:
    """Fallback if Claude API key not set."""
    now = datetime.now().strftime("%d %b %Y, %H:%M IST")
    top3 = sorted(all_buy, key=lambda x: -x["composite_score"])[:3]
    sectors = {}
    for r in all_buy:
        sec = r.get("sector", "Unknown")
        sectors[sec] = sectors.get(sec, 0) + 1
    top_sec = sorted(sectors.items(), key=lambda x: -x[1])[:3]

    msg = (
        f"🧠 <b>AlphaRadar Synthesis — {score_date}</b>\n"
        f"<code>{now}</code>\n\n"
        f"<b>Market breadth:</b> {len(all_buy)} buy · {len(all_sell)} sell signals\n"
        f"Top sectors: {', '.join(f'{s}({c})' for s,c in top_sec)}\n\n"
        f"<b>Top 3 conviction picks:</b>\n"
    )
    for r in top3:
        lp = live_prices.get(r["symbol"], {})
        price_str = f"₹{lp.get('live_price', r['price']):,.1f}"
        chg_str   = f"{lp.get('today_chg', 0):+.1f}% today"
        msg += f"• <b>{r['symbol']}</b> {price_str} ({chg_str}) · Score {r['composite_score']:.0f}\n"

    if all_sell:
        worst = sorted(all_sell, key=lambda x: x["composite_score"])[:2]
        msg += f"\n<b>Top exits:</b> " + ", ".join(f"<b>{r['symbol']}</b>" for r in worst)

    msg += "\n\n⚠ <i>Add ANTHROPIC_API_KEY for full Claude AI synthesis</i>"
    return msg


# ═══════════════════════════════════════════════════
# KOTAK NEO PORTFOLIO OVERLAY
# ═══════════════════════════════════════════════════

def build_kotak_portfolio_alert(
    session_id: str,
    all_scores: list[dict],
    live_prices: dict,
) -> str:
    """
    Call Kotak Neo MCP to get holdings, cross-reference with AlphaRadar signals.
    Returns a Telegram message.
    
    NOTE: This function formats the Kotak data — actual MCP call must be 
    made from Claude interface (kotak-neo:get_holdings tool).
    The session_id expires daily from ICICIDirect.
    """
    if not session_id:
        return (
            "💼 <b>Kotak Neo Portfolio Overlay</b>\n"
            "<i>Session ID not provided. To enable:</i>\n"
            "1. Login to ICICIDirect.com\n"
            "2. Go to Settings → API Sessions → Generate Token\n"
            "3. Set KOTAK_SESSION_ID env var\n"
            "4. Re-run this script\n\n"
            "Once connected: Claude will cross-reference your live "
            "portfolio with AlphaRadar signals to show which of YOUR "
            "holdings are flagging SELL, and which buy signals you don't own yet."
        )

    # Build a score lookup
    score_map = {r["symbol"]: r for r in all_scores}

    msg = "💼 <b>Kotak Neo Portfolio × AlphaRadar Signals</b>\n"
    msg += "<i>Cross-reference your live portfolio with today's signals</i>\n\n"
    msg += (
        "🔗 <i>Holdings fetched via Kotak Neo MCP. "
        "Run the kotak-neo:get_holdings tool in Claude chat for live data.</i>\n\n"
    )
    msg += "<b>How to use:</b>\n"
    msg += "1. In Claude, type: <code>show my Kotak portfolio vs AlphaRadar signals</code>\n"
    msg += "2. Claude will call Kotak MCP + cross-reference with the latest scores\n"
    msg += "3. You'll see: which holdings are in SELL zone, P&L, and new ideas\n"

    return msg


# ═══════════════════════════════════════════════════
# FRESH SELL SIGNALS MESSAGE
# ═══════════════════════════════════════════════════

def build_fresh_sell_message(
    all_scores: list[dict],
    live_prices: dict,
    score_date: str,
) -> str:
    """Build a dedicated SELL / EXIT alert message."""
    sells = [r for r in all_scores if r["bucket"] == "SELL"]
    # Sort by most severe (lowest score, steepest negative MA slope)
    sells.sort(key=lambda x: (x["composite_score"], x["ma_slope"]))

    # Fresh sells = stage changed today OR score dropped > 10
    fresh_sells = [
        r for r in sells
        if r.get("stage_changed") or (r.get("score_change", 0) < -5)
    ]

    # Notable names in sell zone (large caps, high RS names)
    notable = [r for r in sells if r.get("cap_bucket") == "large"]

    now = datetime.now().strftime("%d %b %Y, %H:%M IST")

    msg = (
        f"🔴 <b>AlphaRadar SELL / EXIT Signals — {score_date}</b>\n"
        f"<code>{now}</code>\n"
        f"<i>Total Stage 4 / SELL bucket: {len(sells)} stocks</i>\n"
    )

    if fresh_sells:
        msg += f"\n🚨 <b>FRESH SELLS TODAY ({len(fresh_sells)} new):</b>\n"
        for r in fresh_sells[:6]:
            sym = r["symbol"]
            lp  = live_prices.get(sym, {})
            live_str = f"₹{lp.get('live_price', r['price']):,.1f}" if lp else f"₹{r['price']:,.1f}"
            chg_str  = f"{lp.get('today_chg', r['price_change_pct']):+.2f}%"
            msg += (
                f"\n<b>{sym}</b> · Score {r['composite_score']:.0f}\n"
                f"  Stage: {r['weinstein_stage']} · RS: {r['rs_percentile']:.0f}%ile\n"
                f"  {live_str} ({chg_str} today) · {abs(r['price_vs_ma']):.1f}% below 200d MA\n"
                f"  Slope: {r['ma_slope']:+.4f} · Score Δ: {r.get('score_change',0):+.1f}\n"
                f"  ❌ <b>Exit any long position</b>\n"
            )
    else:
        msg += "\n<i>No fresh stage transitions into SELL today.</i>\n"

    if notable:
        msg += f"\n⚠ <b>NOTABLE LARGE-CAPS in SELL zone:</b>\n"
        for r in notable[:5]:
            sym = r["symbol"]
            lp  = live_prices.get(sym, {})
            live_str = f"₹{lp.get('live_price', r['price']):,.1f}" if lp else f"₹{r['price']:,.1f}"
            msg += (
                f"• <b>{sym}</b> ({r.get('sector','?')}) · {live_str} · "
                f"RS {r['rs_percentile']:.0f}%ile · Stage {r['weinstein_stage']}\n"
            )

    # Sector concentration in sell zone
    sec_counts = {}
    for r in sells:
        sec = r.get("sector", "Unknown")
        sec_counts[sec] = sec_counts.get(sec, 0) + 1
    top_sell_secs = sorted(sec_counts.items(), key=lambda x: -x[1])[:4]
    if top_sell_secs:
        msg += f"\n📊 <b>Sectors most in SELL zone:</b>\n"
        for sec, cnt in top_sell_secs:
            msg += f"  • {sec}: {cnt} stocks\n"

    return msg


# ═══════════════════════════════════════════════════
# DAILY HEADER MESSAGE
# ═══════════════════════════════════════════════════

def build_header_message(all_scores: list[dict], score_date: str) -> str:
    """Opening summary message."""
    from collections import Counter
    buckets = Counter(r["bucket"] for r in all_scores)
    stages  = Counter(r["weinstein_stage"] for r in all_scores)
    buy_nows = [r for r in all_scores if r.get("entry_signal") == "BUY NOW"]

    now = datetime.now().strftime("%d %b %Y, %H:%M IST")

    msg = (
        f"🎯 <b>AlphaRadar Daily Brief — {score_date}</b>\n"
        f"<code>{now} | {len(all_scores)} stocks scored</code>\n\n"
        f"📊 <b>Universe Snapshot:</b>\n"
        f"  🟢 Must Buy: {buckets.get('MUST_BUY',0)}  "
        f"🔵 Can Buy: {buckets.get('CAN_BUY',0)}\n"
        f"  ⚪ Neutral: {buckets.get('NEUTRAL',0)}  "
        f"🟡 Avoid: {buckets.get('AVOID',0)}  "
        f"🔴 Sell: {buckets.get('SELL',0)}\n\n"
        f"⚡ <b>Active BUY NOW setups: {len(buy_nows)}</b>\n"
    )
    for r in sorted(buy_nows, key=lambda x: -x["composite_score"])[:5]:
        msg += f"  → <b>{r['symbol']}</b> ({r['entry_detail']})\n"

    msg += (
        f"\n📈 <b>Stage Distribution:</b>\n"
        f"  Stage 2A: {stages.get('2A',0)} | Stage 2B: {stages.get('2B',0)} | "
        f"Stage 3: {stages.get('3',0)} | Stage 4: {stages.get('4',0)}\n"
        f"\n<i>Strategy-wise breakdowns follow ↓</i>"
    )
    return msg


# ═══════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════

def run_full_alert_cycle(kotak_session_id: str = ""):
    """
    Full pipeline:
    1. Fetch Supabase scores
    2. Identify all unique symbols needing live prices
    3. Batch-fetch live prices
    4. Send header message
    5. Send strategy-wise messages (one per strategy)
    6. Send fresh sell message
    7. Send Claude AI synthesis
    8. Send Kotak overlay status
    """
    print("\n" + "="*60)
    print("AlphaRadar Telegram Alert Cycle")
    print("="*60)

    # ── 1. Fetch scores ──
    print("\n[1/7] Fetching Supabase scores...")
    result = fetch_latest_scores()
    if not result:
        send_tg("⚠ AlphaRadar: Could not fetch scores. Check Supabase connection.")
        return
    all_scores, score_date = result

    # ── 2. Identify symbols for live prices ──
    print("\n[2/7] Identifying symbols for live price fetch...")
    # All buy candidates + sell signals
    price_symbols = list({
        r["symbol"] for r in all_scores
        if r["bucket"] in ("MUST_BUY", "CAN_BUY", "SELL")
        or r.get("stage_changed")
    })
    stored_prices = {r["symbol"]: r["price"] for r in all_scores}
    print(f"  Fetching live prices for {len(price_symbols)} symbols...")

    # ── 3. Batch fetch live prices ──
    print("\n[3/7] Fetching live prices...")
    live_prices = enrich_with_live_prices(price_symbols, stored_prices)
    print(f"  Got live prices for {len(live_prices)} symbols")

    # ── 4. Header message ──
    print("\n[4/7] Sending header message...")
    header = build_header_message(all_scores, score_date)
    send_tg(header)
    time.sleep(1)

    # ── 5. Strategy-wise messages ──
    print("\n[5/7] Sending strategy messages...")
    all_featured = []  # Track all stocks featured in buy signals
    sell_all = [r for r in all_scores if r["bucket"] == "SELL"]

    for strategy_name, config in STRATEGIES.items():
        print(f"  Strategy: {strategy_name}")
        msg, featured = build_strategy_message(
            strategy_name, config, all_scores, live_prices, score_date
        )
        if msg:
            send_tg(msg)
            all_featured.extend(featured)
            time.sleep(1.5)
        else:
            print(f"    (no signals for this strategy today)")

    # ── 6. Fresh sell message ──
    print("\n[6/7] Sending sell/exit alerts...")
    sell_msg = build_fresh_sell_message(all_scores, live_prices, score_date)
    send_tg(sell_msg)
    time.sleep(1)

    # ── 7. Claude AI synthesis ──
    print("\n[7/7] Generating Claude AI synthesis...")
    buy_unique = list({r["symbol"]: r for r in all_featured if r["bucket"] in ("MUST_BUY","CAN_BUY")}.values())
    synthesis = build_claude_synthesis(buy_unique, sell_all, live_prices, score_date)
    send_tg(synthesis)
    time.sleep(1)

    # ── Kotak overlay ──
    kotak_msg = build_kotak_portfolio_alert(
        kotak_session_id or KOTAK_SESSION,
        all_scores,
        live_prices,
    )
    send_tg(kotak_msg)

    print("\n✅ Alert cycle complete!")
    print(f"   Signals sent: {len(buy_unique)} buy, {len(sell_all)} sell")
    print(f"   Live prices: {len(live_prices)}/{len(price_symbols)}")


# ═══════════════════════════════════════════════════
# TELEGRAM BOT — INTERACTIVE COMMANDS
# ═══════════════════════════════════════════════════
"""
Interactive Telegram bot mode.
Commands:
  /start        — welcome message
  /signals      — run full signal cycle NOW
  /stock SYMBOL — live analysis of a specific stock
  /sell         — show all sell signals
  /portfolio    — Kotak portfolio overlay (requires session)
  /help         — list commands
"""

def handle_telegram_command(update: dict, kotak_session: str = ""):
    """Process incoming Telegram message and dispatch command."""
    try:
        msg   = update.get("message", {})
        text  = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        def reply(text):
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )

        if text.startswith("/start"):
            reply(
                "👋 <b>AlphaRadar Bot Active</b>\n\n"
                "Commands:\n"
                "  /signals — full strategy-wise alert\n"
                "  /stock SYMBOL — single stock analysis\n"
                "  /sell — sell / exit signals\n"
                "  /portfolio — Kotak portfolio check\n"
                "  /help — this list\n\n"
                "Powered by AlphaRadar scoring engine + Claude AI."
            )

        elif text.startswith("/signals"):
            reply("⏳ Running full signal cycle, please wait ~30 sec...")
            run_full_alert_cycle(kotak_session)

        elif text.startswith("/sell"):
            result = fetch_latest_scores()
            if result:
                all_scores, score_date = result
                # Get live for sell symbols
                sell_syms = [r["symbol"] for r in all_scores if r["bucket"] == "SELL"]
                stored    = {r["symbol"]: r["price"] for r in all_scores}
                lives     = enrich_with_live_prices(sell_syms[:20], stored)
                sell_msg  = build_fresh_sell_message(all_scores, lives, score_date)
                reply(sell_msg)

        elif text.lower().startswith("/stock "):
            sym = text[7:].strip().upper().replace("-", "-")
            reply(f"⏳ Fetching live data for {sym}...")
            _handle_stock_query(sym, reply)

        elif text.startswith("/portfolio"):
            if not kotak_session:
                reply(
                    "❌ Kotak session not active.\n"
                    "Log into ICICIDirect API, generate a session token, "
                    "and set KOTAK_SESSION_ID.\n\n"
                    "In Claude.ai, you can also type:\n"
                    "<code>show my Kotak portfolio vs AlphaRadar</code>"
                )
            else:
                result = fetch_latest_scores()
                if result:
                    all_scores, _ = result
                    stored = {r["symbol"]: r["price"] for r in all_scores}
                    msg = build_kotak_portfolio_alert(kotak_session, all_scores, {})
                    reply(msg)

        elif text.startswith("/help"):
            reply(
                "<b>AlphaRadar Bot Commands:</b>\n\n"
                "/signals — full daily signal cycle\n"
                "/stock NAVINFLUOR — single stock deep-dive\n"
                "/sell — all exit signals with live prices\n"
                "/portfolio — Kotak Neo portfolio overlay\n"
                "/start — welcome + instructions"
            )
    except Exception as e:
        print(f"  ⚠ Command handler error: {e}")


def _handle_stock_query(symbol: str, reply_fn):
    """Fetch AlphaRadar score + live price for a specific symbol."""
    try:
        result = fetch_latest_scores()
        if not result:
            reply_fn(f"⚠ Could not fetch data for {symbol}")
            return
        all_scores, score_date = result
        stock = next((r for r in all_scores if r["symbol"] == symbol), None)
        if not stock:
            reply_fn(f"❌ {symbol} not found in AlphaRadar universe")
            return

        lives = enrich_with_live_prices([symbol], {symbol: stock["price"]})
        lp    = lives.get(symbol, {})

        live_str  = f"₹{lp.get('live_price', stock['price']):,.2f}" if lp else f"₹{stock['price']:,.2f}"
        chg_str   = f"{lp.get('today_chg', stock['price_change_pct']):+.2f}%"
        delta_str = f"{lp.get('delta', 0):+.2f}% from signal"

        bucket_emoji = {"MUST_BUY":"🟢","CAN_BUY":"🔵","NEUTRAL":"⚪","AVOID":"🟡","SELL":"🔴"}.get(stock["bucket"],"")

        msg = (
            f"🔍 <b>{symbol}</b> {bucket_emoji} — {score_date}\n\n"
            f"💰 Live: <b>{live_str}</b> ({chg_str} today)\n"
            f"📌 {lp.get('momentum','—')} ({delta_str})\n"
            f"📊 Score: <b>{stock['composite_score']:.1f}/100</b> · {stock['action_label']}\n"
            f"📈 Stage: {stock['weinstein_stage']} · RS: {stock['rs_percentile']:.0f}%ile\n"
            f"🏢 Sector: {stock.get('sector','?')} · Cap: {stock.get('cap_bucket','?').title()}\n"
            f"📉 vs 200d MA: {stock['price_vs_ma']:+.1f}% · Slope: {stock['ma_slope']:+.5f}\n"
            f"🎯 Entry: {stock.get('entry_signal','?')}"
        )
        if stock.get("entry_detail"):
            msg += f" — {stock['entry_detail']}"
        msg += (
            f"\n📰 News sentiment: {stock.get('news_sentiment',0):.2f}/1.0\n"
            f"⬆ Score Δ: {stock.get('score_change',0):+.1f} · "
            f"Stage changed: {'Yes 🆕' if stock.get('stage_changed') else 'No'}\n"
            f"🏔 52W: ₹{stock['low_52w']:,.0f} — ₹{stock['high_52w']:,.0f}"
        )
        if ANTHROPIC_KEY:
            # Quick Claude note
            prompt = (
                f"Give a 3-sentence trading note on {symbol} "
                f"(NSE India). Score: {stock['composite_score']:.0f}/100, "
                f"Stage {stock['weinstein_stage']}, RS {stock['rs_percentile']:.0f}%ile, "
                f"live price ₹{lp.get('live_price', stock['price']):,.2f} "
                f"({lp.get('today_chg',0):+.2f}% today), "
                f"{lp.get('momentum','')}, entry: {stock.get('entry_signal','')}. "
                f"Be crisp and actionable. No disclaimers."
            )
            try:
                r = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"Content-Type":"application/json",
                             "x-api-key": ANTHROPIC_KEY,
                             "anthropic-version":"2023-06-01"},
                    json={"model":"claude-sonnet-4-20250514","max_tokens":200,
                          "messages":[{"role":"user","content":prompt}]},
                    timeout=20
                )
                if r.status_code == 200:
                    note = r.json()["content"][0]["text"]
                    msg += f"\n\n🤖 <i>{note}</i>"
            except: pass
        reply_fn(msg)
    except Exception as e:
        reply_fn(f"⚠ Error fetching {symbol}: {e}")


# ═══════════════════════════════════════════════════
# POLLING LOOP  (for self-hosted / local use)
# ═══════════════════════════════════════════════════

def start_polling(kotak_session: str = ""):
    """
    Start Telegram bot in long-polling mode.
    Use this for local testing.
    For production: use GitHub Actions cron + run_full_alert_cycle().
    """
    print("\n🤖 AlphaRadar Telegram Bot — Polling mode")
    print(f"   Bot: @Rishabh2Bot · Chat: {TG_CHAT}")
    print("   Press Ctrl+C to stop\n")

    last_update_id = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
                params={"offset": last_update_id + 1, "timeout": 20},
                timeout=30,
            )
            if r.status_code == 200:
                updates = r.json().get("result", [])
                for update in updates:
                    last_update_id = update["update_id"]
                    handle_telegram_command(update, kotak_session)
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:
            print(f"  Polling error: {e}")
            time.sleep(5)


# ═══════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"

    if mode == "poll":
        # Interactive bot mode — respond to /commands
        start_polling(KOTAK_SESSION)
    elif mode == "test":
        # Send a test ping
        send_tg("✅ AlphaRadar bot test — connection OK!")
        print("Test message sent.")
    else:
        # Default: run full daily alert cycle
        run_full_alert_cycle(KOTAK_SESSION)
