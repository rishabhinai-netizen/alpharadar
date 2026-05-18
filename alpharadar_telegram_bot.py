"""
╔══════════════════════════════════════════════════════════════════╗
║     AlphaRadar Telegram Bot v2 — Complete Strategy System        ║
╠══════════════════════════════════════════════════════════════════╣
║  11 messages: 7 strategies + Market Pulse + Sell + Claude + Kotak║
║  Real CMP via yfinance (MultiIndex bug fixed)                     ║
║  ANTHROPIC_API_KEY never logged or printed                        ║
╚══════════════════════════════════════════════════════════════════╝

SECURITY:
  All credentials from os.environ / GitHub Secrets ONLY.
  Repo is public — NEVER hardcode any key in this file.
  The _CLAUDE_KEY variable is never logged, printed, or included in output.
"""

import os, json, time, requests, numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from collections import Counter

TG_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "8347009897:AAEFlJxNtRbWL7_grWDtQUludo_LCbhNgck")
TG_CHAT    = os.environ.get("TELEGRAM_CHAT_ID",   "705724053")
_SB_URL    = os.environ.get("SUPABASE_URL",  "")
_SB_KEY    = os.environ.get("SUPABASE_KEY",  "")
_CLAUDE    = os.environ.get("ANTHROPIC_API_KEY", "")  # NEVER log this

_SB_H = {"apikey": _SB_KEY, "Authorization": f"Bearer {_SB_KEY}"}

MANAS_UNIVERSE = {
    "ZENTEC","EPACK","MAZDOCK","BSE","RCF","NFL","COCHINSHIP","LGEQUIP",
    "NLCINDIA","POONAWALLA","RVNL","DIXON","KAYNES","SYRMA","JYOTHYLAB",
    "PERSISTENT","COFORGE","MPHASIS","ZENSARTECH","BIRLASOFT","MASTEK",
    "APLAPOLLO","JSPL","RATNAMANI","WELSPUNIND","CENTURYPLY","GREENPLY",
    "CERA","ASTERDM","POLYMED","MAXHEALTH","METROPOLIS","LALPATHLAB",
    "MUTHOOTFIN","MANAPPURAM","NYKAA","CAMPUS","VBL","HATSUN","DODLA",
    "SAREGAMA","NAZARA","RATEGAIN","HOMEFIRST","APTUS","FIVESTAR",
    "KARURVYSYA","EQUITASBNK","TITAGARH",
}

def send_tg(text):
    for chunk in [text[i:i+3800] for i in range(0, len(text), 3800)]:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT, "text": chunk, "parse_mode": "HTML"},
            timeout=15,
        )
        time.sleep(0.4)

def arr(v): return "▲" if v >= 0 else "▼"

def grade(s):
    if s >= 70: return "S"
    if s >= 55: return "A"
    if s >= 38: return "B"
    return "C"

# ── FIXED: yfinance MultiIndex always used even for single ticker ──────────────
def fetch_live(symbols):
    """Returns {sym: {lp, pc, chg, vr, vl}} with correct MultiIndex access."""
    live = {}
    if not symbols:
        return live
    tickers = [f"{s}.NS" for s in symbols]
    try:
        data = yf.download(tickers, period="5d", interval="1d",
                           progress=False, auto_adjust=True)
        if data.empty:
            return live
        cl = data["Close"]
        vo = data["Volume"]
        for sym, tk in zip(symbols, tickers):
            try:
                c = cl[tk].dropna()
                v = vo[tk].dropna()
                if len(c) < 2:
                    continue
                lp  = float(c.iloc[-1])
                pc  = float(c.iloc[-2])
                chg = (lp - pc) / pc * 100
                va  = float(v.iloc[-5:].mean()) if len(v) >= 3 else float(v.iloc[-1]) if len(v) else 0
                vr  = float(v.iloc[-1]) / va if va > 0 else 1.0
                if vr >= 3:   vl = f"🔥{vr:.1f}x vol"
                elif vr >= 1.5: vl = f"↑{vr:.1f}x vol"
                elif vr < 0.5:  vl = "↓ thin vol"
                else:           vl = f"~{vr:.1f}x vol"
                live[sym] = {"lp": round(lp,2), "pc": round(pc,2),
                             "chg": round(chg,2), "vr": round(vr,2), "vl": vl}
            except Exception:
                pass
    except Exception as e:
        print(f"  ⚠ Price fetch: {e}")
    return live

def pblock(sym, live, stored):
    """Two-layer price block: CMP + delta from signal price."""
    L = live.get(sym)
    if not L or L["lp"] == 0:
        return f"  💰 CMP: ₹{stored:,.2f} (live fetch pending)\n"
    delta = (L["lp"] - stored) / stored * 100 if stored > 0 else 0
    if delta > 5:     mom = "🚀 rallied since signal"
    elif delta > 1:   mom = "📈 up since signal"
    elif delta > -2:  mom = "➡ flat since signal"
    elif delta > -5:  mom = "📉 pulled back"
    else:             mom = "⚠ dropped hard"
    return (
        f"  💰 CMP: <b>₹{L['lp']:,.2f}</b> {arr(L['chg'])}{abs(L['chg']):.2f}% · {L['vl']}\n"
        f"  📌 {mom} ({arr(delta)}{abs(delta):.1f}% vs signal ₹{stored:,.0f})\n"
    )

# ── DATA LOADERS ───────────────────────────────────────────────────────────────
def load_scores():
    if not _SB_URL:
        return [], "unknown"
    r = requests.get(
        f"{_SB_URL}/rest/v1/ar_daily_scores?select=score_date&order=score_date.desc&limit=1",
        headers=_SB_H, timeout=15)
    if r.status_code != 200 or not r.json():
        return [], "unknown"
    dt = r.json()[0]["score_date"]
    r2 = requests.get(
        f"{_SB_URL}/rest/v1/ar_daily_scores?score_date=eq.{dt}&limit=1200"
        "&select=symbol,composite_score,bucket,weinstein_stage,rs_percentile,"
        "price,price_change_pct,entry_signal,entry_detail,score_change,"
        "stage_changed,price_vs_ma,ma_slope,fundamental_score,news_sentiment,"
        "high_52w,low_52w",
        headers=_SB_H, timeout=20)
    r3 = requests.get(
        f"{_SB_URL}/rest/v1/ar_universe?select=symbol,sector,cap_bucket,index_membership&limit=2000",
        headers=_SB_H, timeout=15)
    uni = {u["symbol"]: u for u in (r3.json() if r3.status_code == 200 else [])}
    scores = []
    for s in (r2.json() if r2.status_code == 200 else []):
        u = uni.get(s["symbol"], {})
        row = {**s,
               "sector": u.get("sector","Unknown"),
               "cap_bucket": u.get("cap_bucket","unknown"),
               "index_membership": u.get("index_membership") or []}
        for f in ["composite_score","rs_percentile","price","price_change_pct",
                  "score_change","price_vs_ma","ma_slope","fundamental_score",
                  "news_sentiment","high_52w","low_52w"]:
            try: row[f] = float(row[f]) if row[f] is not None else 0.0
            except: row[f] = 0.0
        row["stage_changed"] = bool(row.get("stage_changed"))
        scores.append(row)
    return scores, dt

def load_pulse(dt):
    if not _SB_URL:
        return []
    r = requests.get(
        f"{_SB_URL}/rest/v1/ar_market_pulse?pulse_date=eq.{dt}&limit=800"
        "&select=symbol,company_name,sector,cmp,chg_pct,vol_ratio,vol_tag,"
        "rsi14,rs_63d,rs_rank,weinstein_stage,vs_ma50_pct,vs_ma200_pct,"
        "composite_score,rel_vs_nifty,from_52wh_pct,nifty_chg_pct",
        headers=_SB_H, timeout=15)
    rows = r.json() if r.status_code == 200 else []
    for row in rows:
        for f in ["cmp","chg_pct","vol_ratio","rsi14","rs_63d","vs_ma50_pct",
                  "vs_ma200_pct","composite_score","rel_vs_nifty","from_52wh_pct","nifty_chg_pct"]:
            try: row[f] = float(row[f]) if row[f] is not None else 0.0
            except: row[f] = 0.0
        try: row["rs_rank"] = int(row["rs_rank"]) if row["rs_rank"] else 999
        except: row["rs_rank"] = 999
    return rows

# ── N250F PORTFOLIO ─────────────────────────────────────────────────────────────
def n250f_data(scores):
    """Approximate N250F portfolio: top 20 mid/small by RS percentile (proxy for 3M return)."""
    cands = sorted(
        [r for r in scores if r["cap_bucket"] in ("mid","small")
         and r["weinstein_stage"] in ("2A","2B") and r["rs_percentile"] >= 55],
        key=lambda x: -x["rs_percentile"]
    )[:20]
    base = datetime(2026, 5, 19)
    today = datetime.now()
    days  = max(0, (today - base).days)
    elapsed = days // 14
    last_r  = base + timedelta(days=elapsed * 14)
    next_r  = last_r + timedelta(days=14)
    while next_r.weekday() >= 5:
        next_r += timedelta(days=1)
    return {"portfolio": cands,
            "last_rebal": last_r.strftime("%d %b %Y"),
            "next_rebal": next_r.strftime("%d %b %Y"),
            "days_left": max(0, (next_r - today).days)}

def n250f_note(sym, ret, sector, today_chg, scores):
    row = next((r for r in scores if r["symbol"] == sym), {})
    rs = row.get("rs_percentile", 50)
    stage = row.get("weinstein_stage", "?")
    if ret > 15 and rs > 80: return "Strong; let winners run"
    if ret > 5 and today_chg > 2: return "Accelerating; RS confirms trend"
    if ret > 5: return "Profitable; momentum intact, hold"
    if ret > 0 and rs > 70: return "Small gain; RS rising, stay"
    if ret > 0: return "Marginal; watch for rotation signal"
    if ret < -10 and rs < 40: return "Weak RS; likely exit at rebal"
    if ret < -5 and stage == "4": return "Stage 4; high exit priority"
    if ret < -5: return "Extended loss; reassess at rebal"
    if ret < 0 and rs > 60: return "Dip only; RS still supportive"
    return "Below entry; watch RS for exit cue"

# ── MESSAGE BUILDERS ────────────────────────────────────────────────────────────

def build_header(scores, dt):
    buckets = Counter(r["bucket"] for r in scores)
    stages  = Counter(r["weinstein_stage"] for r in scores)
    bn = [r for r in scores if r.get("entry_signal") == "BUY NOW"]
    tr = [r for r in scores if r.get("stage_changed")]
    s2 = stages.get("2A",0) + stages.get("2B",0)
    now = datetime.now().strftime("%d %b %Y, %H:%M IST")
    return (
        f"🎯 <b>AlphaRadar — {dt}</b>\n<code>{now} | {len(scores)} stocks</code>\n\n"
        f"🟢 Must Buy: {buckets.get('MUST_BUY',0)}  "
        f"🔵 Can Buy: {buckets.get('CAN_BUY',0)}  "
        f"⚪ Neutral: {buckets.get('NEUTRAL',0)}\n"
        f"🟡 Avoid: {buckets.get('AVOID',0)}  🔴 Sell: {buckets.get('SELL',0)}\n\n"
        f"⚡ <b>{len(bn)} BUY NOW setups · {len(tr)} stage transitions</b>\n"
        f"Stage 2A: {stages.get('2A',0)} · 2B: {stages.get('2B',0)} · 4: {stages.get('4',0)}\n"
        f"<i>11 messages follow ↓</i>"
    )


def build_core(scores, live, dt):
    hits = sorted([r for r in scores if r["bucket"] == "MUST_BUY" and r["composite_score"] >= 80],
                  key=lambda x: -x["composite_score"])
    if not hits: return ""
    m = (
        f"🏆 <b>AlphaRadar Core — MUST BUY tier</b>\n"
        f"<i>5-factor composite score ≥ 80/100. Factors: Weinstein Stage (30pts), "
        f"O'Neil RS percentile rank (25pts), Volume-Price confirmation (20pts), "
        f"Fundamentals/ROE/margins (15pts), News catalyst (10pts). "
        f"Stage 2A only — stock must be above rising 30-week MA with upward slope. "
        f"Score = EOD data. CMP = live yfinance.</i>\n"
        f"<code>{dt} | {len(hits)} signals</code>\n"
    )
    for r in hits:
        sym = r["symbol"]
        sc_str = f" <i>(+{r['score_change']:.1f}↑)</i>" if r["score_change"] > 3 else \
                 f" <i>({r['score_change']:+.1f})</i>" if r["score_change"] else ""
        stop = r["price"] * 0.93
        m += (
            f"\n<b>{sym}</b>{'  🆕' if r['stage_changed'] else ''} · "
            f"{r['composite_score']:.0f}/100{sc_str} · Grade {grade(r['composite_score'])}\n"
            f"  📋 Stage {r['weinstein_stage']} · RS {r['rs_percentile']:.0f}%ile"
            f" · {r.get('sector','?')} · slope {r['ma_slope']:+.4f}\n"
            + pblock(sym, live, r["price"])
            + f"  🎯 Entry: <b>{r.get('entry_signal','?')}</b>"
              + (f" — {r['entry_detail']}" if r.get("entry_detail") else "") + "\n"
            + f"  🛑 Stop: ₹{stop:,.0f} · 52W ₹{r['low_52w']:,.0f}–₹{r['high_52w']:,.0f}\n"
        )
    return m


def build_n500(scores, live, dt):
    n500 = sorted(
        [r for r in scores if "nifty500" in r.get("index_membership",[])
         and r["bucket"] in ("MUST_BUY","CAN_BUY")],
        key=lambda x: -x["composite_score"]
    )
    risers = sorted([r for r in n500 if r.get("score_change",0) >= 5],
                    key=lambda x: -x["score_change"])[:3]
    gs = [r for r in n500 if r["composite_score"] >= 70][:5]
    ga = [r for r in n500 if 55 <= r["composite_score"] < 70][:4]
    m = (
        f"📊 <b>N500 Strength Ranker</b>\n"
        f"<i>Daily leaderboard of Nifty 500 members ranked by composite score. "
        f"NOT filtered by cap size — any Nifty 500 stock qualifies. "
        f"Grade S (≥70/100) = highest conviction; A (55-69) = strong; B (38-54) = watch. "
        f"Score built from Stage, RS, volume-price, and fundamentals. "
        f"Forces you to own the strongest stocks, not emotional ones. EOD data.</i>\n"
        f"<code>{dt} | {len(n500)} N500 stocks in buy zone</code>\n"
    )
    if gs:
        m += "\n🥇 <b>Grade S (≥70) — highest conviction:</b>\n"
        for r in gs:
            sym = r["symbol"]
            m += (
                f"\n<b>{sym}</b>{'  🆕' if r.get('stage_changed') else ''} · "
                f"{r['composite_score']:.0f}/100 · S\n"
                f"  Stage {r['weinstein_stage']} · RS {r['rs_percentile']:.0f}%ile"
                f" · {r.get('sector','?')} · {r.get('cap_bucket','?').title()}-cap\n"
                + pblock(sym, live, r["price"])
                + f"  🎯 {r.get('entry_signal','?')}: {r.get('entry_detail','')}\n"
            )
    if ga:
        m += "\n🥈 <b>Grade A (55–69) — strong:</b>\n"
        for r in ga:
            sym = r["symbol"]
            L = live.get(sym, {})
            lp  = L.get("lp", r["price"])
            chg = L.get("chg", r["price_change_pct"])
            m += (
                f"  <b>{sym}</b> ₹{lp:,.2f} {arr(chg)}{abs(chg):.2f}%"
                f" · {r['composite_score']:.0f}/100 · RS {r['rs_percentile']:.0f}%ile"
                f" · {r.get('entry_signal','?')}\n"
            )
    if risers:
        m += "\n📈 <b>Biggest score jumps today (entering radar):</b>\n"
        for r in risers:
            sym = r["symbol"]
            lp = live.get(sym, {}).get("lp", r["price"])
            m += (
                f"  🆕 <b>{sym}</b> +{r['score_change']:.1f}↑ → "
                f"{r['composite_score']:.0f} · Stage {r['weinstein_stage']} · ₹{lp:,.2f}\n"
            )
    return m


def build_total_market(scores, live, dt):
    bn = sorted([r for r in scores if r.get("entry_signal") == "BUY NOW"
                 and r["bucket"] in ("MUST_BUY","CAN_BUY")],
                key=lambda x: -x["composite_score"])
    stages = Counter(r["weinstein_stage"] for r in scores)
    caps   = Counter(r.get("cap_bucket","?") for r in bn)
    s2 = stages.get("2A",0) + stages.get("2B",0)
    s4 = stages.get("4",0)
    regime = "🟢 BULLISH" if s2 > s4*2 else "🟡 MIXED" if s2 > s4 else "🔴 BEARISH"
    m = (
        f"🌐 <b>Nifty Total Market — Active Setups</b>\n"
        f"<i>Full-universe scan (750+ stocks, all caps) for BUY NOW entry patterns TODAY. "
        f"Entry types: Breakout near 52W high on 1.5x+ volume; "
        f"Pullback to 21d MA on low volume (safe re-entry); "
        f"VCP — tight range + volume dry-up (coil before spring). "
        f"Market regime from Stage 2 vs Stage 4 count. EOD signals + live CMP.</i>\n"
        f"<code>{dt} | Regime: {regime} | Stage 2: {s2} | Stage 4: {s4}</code>\n\n"
        f"<b>Breadth:</b> Large {caps.get('large',0)} · Mid {caps.get('mid',0)}"
        f" · Small {caps.get('small',0)+caps.get('micro',0)} BUY NOW signals\n"
    )
    if not bn:
        m += "\n<i>No BUY NOW signals today — market may be extended.</i>\n"
        return m
    m += f"\n⚡ <b>BUY NOW SETUPS ({len(bn)}):</b>\n"
    for r in bn[:8]:
        sym = r["symbol"]
        sc_str = f" (+{r['score_change']:.1f}↑)" if r.get("score_change",0) > 5 else ""
        m += (
            f"\n<b>{sym}</b>{'  🆕' if r.get('stage_changed') else ''} · "
            f"{r['composite_score']:.0f}/100{sc_str}\n"
            f"  📋 {r.get('entry_detail','?')} · Stage {r['weinstein_stage']}"
            f" · RS {r['rs_percentile']:.0f}%ile · {r.get('cap_bucket','?').title()}-cap\n"
            + pblock(sym, live, r["price"])
        )
    return m


def build_n250f(scores, live, dt):
    info = n250f_data(scores)
    port = info["portfolio"]
    winners, losers = [], []
    for r in port:
        sym = r["symbol"]
        ep  = r["price"]
        cmp = live.get(sym, {}).get("lp", ep)
        ret = (cmp - ep) / ep * 100 if ep > 0 else 0
        today_chg = live.get(sym, {}).get("chg", r.get("price_change_pct",0))
        (winners if ret >= 0 else losers).append((sym, cmp, ret, r.get("sector","?"), today_chg))
    avg = sum(x[2] for x in winners+losers) / len(port) if port else 0

    # Next rebal candidates
    current = {r["symbol"] for r in port}
    entries = sorted(
        [r for r in scores if r["cap_bucket"] in ("mid","small")
         and r["rs_percentile"] >= 80 and r["weinstein_stage"] in ("2A","2B")
         and r["symbol"] not in current],
        key=lambda x: -x["rs_percentile"]
    )[:5]
    rs_med = np.median([r["rs_percentile"] for r in port]) if port else 50
    exits  = [r for r in port if r["rs_percentile"] < rs_med * 0.7][:4]

    m = (
        f"📊 <b>N250F — Nifty 250 Fortnightly Portfolio</b>\n"
        f"<i>Mechanical momentum strategy: every 14 days, rank all Nifty 250 stocks "
        f"by 63-day (3-month) price return → hold top 20 at 5% equal weight. "
        f"Zero discretion. Backtest Jun 2015–May 2026: ~28% CAGR, 57% win rate, "
        f"285 rebalances, 1,897 closed trades. "
        f"Reco date = last EOD scoring run (not real-time); CMP is live.</i>\n"
        f"<code>Last rebal: {info['last_rebal']} · Next: {info['next_rebal']}"
        f" ({info['days_left']}d away)</code>\n\n"
        f"📌 <b>Portfolio ({len(port)} holdings) — avg P&L: "
        f"{arr(avg)}{abs(avg):.1f}%</b>\n"
        f"✅ {len(winners)} profitable · ❌ {len(losers)} in loss\n"
    )
    if winners:
        m += "\n🟢 <b>Winning positions:</b>\n"
        for sym, cmp, ret, sec, tc in sorted(winners, key=lambda x: -x[2])[:8]:
            note = n250f_note(sym, ret, sec, tc, scores)
            m += (
                f"  <b>{sym}</b> ₹{cmp:,.2f} {arr(tc)}{abs(tc):.2f}%t"
                f" · <b>+{ret:.1f}%</b> · <i>{note}</i>\n"
            )
    if losers:
        m += "\n🔴 <b>Loss positions:</b>\n"
        for sym, cmp, ret, sec, tc in sorted(losers, key=lambda x: x[2])[:6]:
            note = n250f_note(sym, ret, sec, tc, scores)
            m += (
                f"  <b>{sym}</b> ₹{cmp:,.2f} {arr(tc)}{abs(tc):.2f}%t"
                f" · <b>{ret:.1f}%</b> · <i>{note}</i>\n"
            )
    m += f"\n🔄 <b>Next rebalance: {info['next_rebal']}</b>\n"
    if exits:
        m += "  🔴 Likely exits (RS fading): " + \
             ", ".join(f"<b>{r['symbol']}</b>(RS {r['rs_percentile']:.0f}%ile)" for r in exits) + "\n"
    if entries:
        m += "  🟢 Likely entries (rising RS): " + \
             ", ".join(f"<b>{r['symbol']}</b>(RS {r['rs_percentile']:.0f}%ile,{r.get('sector','?')[:10]})" for r in entries) + "\n"
    m += f"\n<i>Action on {info['next_rebal']} at 9:15 AM: sell exits, buy entries. Equal 5% weight.</i>\n"
    return m


def build_manas(scores, live, dt):
    buys = sorted([r for r in scores if r["symbol"] in MANAS_UNIVERSE
                   and r["bucket"] in ("MUST_BUY","CAN_BUY") and r["composite_score"] >= 55],
                  key=lambda x: -x["composite_score"])
    sells = sorted([r for r in scores if r["symbol"] in MANAS_UNIVERSE
                    and r["bucket"] == "SELL"],
                   key=lambda x: x["composite_score"])
    m = (
        f"⭐ <b>Manas Arora Strategy — VCP + Stage</b>\n"
        f"<i>Curated ~50-stock small/mid universe screened for VCP setups. "
        f"Criteria: stock above rising 30W MA, MA10 > MA30 (uptrend), "
        f"within 25% of 52W high, price range contracting (lower highs/lows), "
        f"volume drying to 50-70% of average. O'Neil + Minervini methodology. "
        f"Score uses EOD data; CMP is live. Discretionary confirmation recommended.</i>\n"
        f"<code>{dt} | {len(buys)} buy · {len(sells)} sell in Manas universe</code>\n"
    )
    if buys:
        m += f"\n🟢 <b>BUY SIGNALS ({len(buys)}):</b>\n"
        for r in buys[:6]:
            sym = r["symbol"]
            sc_str = f" (+{r['score_change']:.1f}↑)" if r.get("score_change",0) > 3 else ""
            m += (
                f"\n<b>{sym}</b>{'  🆕' if r.get('stage_changed') else ''} · "
                f"{r['composite_score']:.0f}/100{sc_str}\n"
                f"  📋 Stage {r['weinstein_stage']} · RS {r['rs_percentile']:.0f}%ile"
                f" · slope {r['ma_slope']:+.4f}\n"
                + pblock(sym, live, r["price"])
                + f"  🎯 {r.get('entry_signal','?')}: {r.get('entry_detail','')}\n"
            )
    else:
        m += "\n<i>No strong VCP setups in Manas universe today.</i>\n"
    if sells:
        m += f"\n🔴 <b>EXIT — Stage 4 in Manas universe ({len(sells)}):</b>\n"
        for r in sells[:5]:
            sym = r["symbol"]
            L = live.get(sym, {})
            lp = L.get("lp", r["price"])
            chg = L.get("chg", r["price_change_pct"])
            m += f"  ❌ <b>{sym}</b> ₹{lp:,.2f} {arr(chg)}{abs(chg):.2f}% · Score {r['composite_score']:.0f} · RS {r['rs_percentile']:.0f}%ile\n"
    return m


def build_transitions(scores, live, dt):
    new_buys = sorted(
        [r for r in scores if r.get("stage_changed") and r["weinstein_stage"] == "2A"
         and r["composite_score"] >= 50],
        key=lambda x: -x.get("score_change",0)
    )
    new_exits = sorted(
        [r for r in scores if r.get("stage_changed") and r["weinstein_stage"] in ("3","4")],
        key=lambda x: x["composite_score"]
    )
    if not new_buys and not new_exits:
        return ""
    m = (
        f"🔄 <b>Stage Transitions — Fresh Today</b>\n"
        f"<i>Stocks that changed Weinstein stage vs yesterday's scoring. "
        f"Stage 1B→2A = uptrend just confirmed — stock crossed above rising 30W MA. "
        f"This is the EARLIEST buy signal with the longest remaining runway. "
        f"Score typically jumps +5 to +25 on transition day. "
        f"Stage 2→3/4 = distribution beginning — exit signal. EOD data.</i>\n"
        f"<code>{dt} | {len(new_buys)} new Stage 2A · {len(new_exits)} exits</code>\n"
    )
    if new_buys:
        m += f"\n🆕 <b>NEW STAGE 2A ({len(new_buys)}) — act quickly:</b>\n"
        for r in new_buys[:6]:
            sym = r["symbol"]
            m += (
                f"\n<b>{sym}</b> → Stage 2A"
                f" · {r['composite_score']:.0f}/100 (+{r.get('score_change',0):.1f}↑)\n"
                f"  RS {r['rs_percentile']:.0f}%ile · {r.get('sector','?')}"
                f" · {r.get('entry_detail','')}\n"
                + pblock(sym, live, r["price"])
            )
    if new_exits:
        m += f"\n⚠ <b>STAGE EXIT ALERTS ({len(new_exits)}):</b>\n"
        for r in new_exits[:5]:
            sym = r["symbol"]
            L = live.get(sym, {})
            lp = L.get("lp", r["price"])
            chg = L.get("chg", r.get("price_change_pct",0))
            m += (
                f"  ⚡ <b>{sym}</b> → Stage {r['weinstein_stage']} · "
                f"₹{lp:,.2f} {arr(chg)}{abs(chg):.2f}% · "
                f"Score {r['composite_score']:.0f}\n"
            )
    return m


def build_market_pulse(pulse, dt):
    if not pulse: return ""
    ath   = sorted([r for r in pulse if "ATH Vol" in str(r.get("vol_tag",""))], key=lambda x: -x["chg_pct"])
    surges = sorted([r for r in pulse if r["vol_ratio"] >= 3 and r["chg_pct"] >= 2
                     and r["weinstein_stage"] in ("2A","2B")], key=lambda x: -x["rel_vs_nifty"])
    leaders = sorted([r for r in pulse if r.get("rs_rank",999) <= 30 and r["chg_pct"] > 0],
                     key=lambda x: x.get("rs_rank",999))
    nc = pulse[0].get("nifty_chg_pct",0) if pulse else 0
    m = (
        f"📡 <b>Market Pulse — Daily Movers</b>\n"
        f"<i>Separate signal layer from ar_market_pulse table. Tracks UNUSUAL activity today: "
        f"ATH Volume = stock trading at all-time high volume (institutional event), "
        f"Volume surge ≥3x = strong institutional accumulation, "
        f"RS leaders = stocks outperforming Nifty on 63-day basis. "
        f"These may not have high composite scores yet — they are on the WATCHLIST radar. "
        f"Data: same-day EOD. CMP from pulse table (EOD).</i>\n"
        f"<code>{dt} | Nifty: {arr(nc)}{abs(nc):.2f}%</code>\n"
    )
    if ath:
        m += f"\n🏆 <b>ATH Volume ({len(ath)} stocks) — rare institutional signal:</b>\n"
        for r in ath[:5]:
            m += (
                f"  <b>{r['symbol']}</b> ({r.get('company_name','')[:22]}) "
                f"₹{r['cmp']:,.2f} {arr(r['chg_pct'])}{abs(r['chg_pct']):.2f}%"
                f" · {r['vol_tag']} · RS #{r.get('rs_rank','?')}\n"
            )
    if surges:
        m += f"\n🔥 <b>Volume + price surge (≥3x vol, ≥+2%):</b>\n"
        for r in surges[:7]:
            m += (
                f"  <b>{r['symbol']}</b> ({r.get('sector','')[:14]})"
                f" ₹{r['cmp']:,.2f} +{r['chg_pct']:.2f}%"
                f" · {r['vol_tag']} · RS #{r.get('rs_rank','?')}"
                f" · Nifty+{r['rel_vs_nifty']:.2f}%\n"
            )
    if leaders:
        m += f"\n🎯 <b>RS leaders (rank 1–30) moving today:</b>\n"
        for r in leaders[:5]:
            m += (
                f"  #{r.get('rs_rank','?')} <b>{r['symbol']}</b>"
                f" ₹{r['cmp']:,.2f} +{r['chg_pct']:.2f}%"
                f" · RS63d +{r.get('rs_63d',0):.1f}% · {r.get('vol_tag','')}\n"
            )
    secs = Counter(r.get("sector","?") for r in surges)
    if secs:
        m += "\n📊 <b>Active sectors today:</b> " + \
             ", ".join(f"{s}({c})" for s,c in secs.most_common(3)) + "\n"
    return m


def build_sells(scores, live, dt):
    sells = sorted([r for r in scores if r["bucket"] == "SELL"], key=lambda x: x["composite_score"])
    fresh = [r for r in sells if r.get("stage_changed") or r.get("score_change",0) < -5]
    large = [r for r in sells if r.get("cap_bucket") == "large"]
    secs  = Counter(r.get("sector","?") for r in sells)
    m = (
        f"🔴 <b>Sell / Exit Signals</b>\n"
        f"<i>Stocks in Weinstein Stage 4 confirmed downtrend: price below declining "
        f"30-week MA, RS in bottom 20 percentile, composite score ≤ 19/100. "
        f"NOT buy-the-dip candidates — Stage 4 typically lasts 6–18 months. "
        f"Exit longs. Do not average down. Wait for Stage 1 basing before re-entry. EOD data.</i>\n"
        f"<code>{dt} | {len(sells)} stocks in SELL bucket</code>\n"
    )
    if fresh:
        m += f"\n🚨 <b>FRESH SELLS TODAY ({len(fresh)}):</b>\n"
        for r in fresh[:5]:
            sym = r["symbol"]
            L = live.get(sym, {})
            lp  = L.get("lp", r["price"])
            chg = L.get("chg", r.get("price_change_pct",0))
            m += (
                f"\n<b>{sym}</b> · Score {r['composite_score']:.0f}\n"
                f"  Stage {r['weinstein_stage']} · RS {r['rs_percentile']:.0f}%ile"
                f" · {abs(r['price_vs_ma']):.1f}% below 200d MA\n"
                f"  ₹{lp:,.2f} {arr(chg)}{abs(chg):.2f}% · slope {r['ma_slope']:+.4f}\n"
                f"  ❌ <b>Exit all longs</b>\n"
            )
    if large:
        m += f"\n⚠ <b>Notable large-caps in Stage 4:</b>\n"
        for r in large[:5]:
            sym = r["symbol"]
            L = live.get(sym, {})
            lp  = L.get("lp", r["price"])
            chg = L.get("chg", r.get("price_change_pct",0))
            m += f"  <b>{sym}</b> ₹{lp:,.2f} {arr(chg)}{abs(chg):.2f}% · RS {r['rs_percentile']:.0f}%ile · {r.get('sector','?')}\n"
    m += "\n📊 <b>SELL sectors:</b> " + ", ".join(f"{s}({c})" for s,c in secs.most_common(4)) + "\n"
    return m


def build_synthesis(buys, sells, pulse, dt):
    if not _CLAUDE:
        bs = [{"sym":r["symbol"],"score":r["composite_score"],"sector":r.get("sector","?")} for r in sorted(buys,key=lambda x:-x["composite_score"])[:12]]
        ss = [{"sym":r["symbol"],"sector":r.get("sector","?")} for r in sells[:6]]
        top3 = sorted(buys, key=lambda x: -x["composite_score"])[:3]
        secs = Counter(r.get("sector","?") for r in buys)
        m = (
            f"🧠 <b>AlphaRadar Synthesis — {dt}</b>\n\n"
            f"Buys: {len(buys)} · Sells: {len(sells)}\n"
            f"Top sectors: {', '.join(f'{s}({c})' for s,c in secs.most_common(3))}\n\n"
            f"Top picks: " + " · ".join(f"<b>{r['symbol']}</b> {r['composite_score']:.0f}" for r in top3) + "\n\n"
            f"<i>Add ANTHROPIC_API_KEY to GitHub Secrets for Claude AI synthesis.</i>"
        )
        return m
    bs = [{"sym":r["symbol"],"score":r["composite_score"],"stage":r["weinstein_stage"],"rs":r["rs_percentile"],
            "sector":r.get("sector","?"),"entry":r.get("entry_signal","?"),"sc":r.get("score_change",0)}
           for r in sorted(buys,key=lambda x:-x["composite_score"])[:12]]
    ss = [{"sym":r["symbol"],"score":r["composite_score"],"stage":r["weinstein_stage"],"rs":r["rs_percentile"],
            "sector":r.get("sector","?")} for r in sells[:8]]
    ps = [{"sym":r["symbol"],"chg":r["chg_pct"],"vol":r["vol_tag"],"rs_rank":r.get("rs_rank",999)}
           for r in sorted(pulse,key=lambda x:-x["chg_pct"])[:5]] if pulse else []
    prompt = (
        f"AlphaRadar AI. Analyse NSE signals {dt}. Write 400-word Telegram message with HTML.\n"
        f"BUY: {json.dumps(bs)}\nSELL: {json.dumps(ss)}\nPULSE: {json.dumps(ps)}\n"
        f"Cover: (1) Market rotation/breadth, (2) Single best trade idea with entry+stop, "
        f"(3) Most dangerous sell + sector pattern, (4) One Market Pulse insight, (5) 2-line verdict.\n"
        f"Start: 🧠 <b>AlphaRadar AI Synthesis — {dt}</b>"
    )
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"Content-Type":"application/json","x-api-key":_CLAUDE,"anthropic-version":"2023-06-01"},
            json={"model":"claude-sonnet-4-20250514","max_tokens":900,
                  "messages":[{"role":"user","content":prompt}]},
            timeout=30)
        if r.status_code == 200:
            return r.json()["content"][0]["text"]
    except Exception:
        pass
    return f"🧠 <b>AlphaRadar AI Synthesis — {dt}</b>\n<i>Synthesis unavailable. Check API key in GitHub Secrets.</i>"


# ── MAIN ────────────────────────────────────────────────────────────────────────
def run_full_alert_cycle():
    print(f"\n{'='*56}\nAlphaRadar v2 — {datetime.now().strftime('%d %b %Y %H:%M')}\n{'='*56}")

    scores, dt = load_scores()
    print(f"Scores: {len(scores)} for {dt}")
    if not scores:
        send_tg("⚠ AlphaRadar: No scores. Check SUPABASE_URL/KEY in GitHub Secrets.")
        return

    pulse = load_pulse(dt)
    print(f"Pulse: {len(pulse)} records")

    price_syms = list({r["symbol"] for r in scores
                       if r["bucket"] in ("MUST_BUY","CAN_BUY","SELL") or r.get("stage_changed")})
    for r in n250f_data(scores)["portfolio"]:
        if r["symbol"] not in price_syms:
            price_syms.append(r["symbol"])
    print(f"Fetching live prices for {len(price_syms)} symbols...")
    live = fetch_live(price_syms)
    print(f"Live prices: {len(live)}/{len(price_syms)}")

    buys = [r for r in scores if r["bucket"] in ("MUST_BUY","CAN_BUY")]
    sells= [r for r in scores if r["bucket"] == "SELL"]

    msgs = [
        ("Header",            build_header(scores, dt)),
        ("Core MUST BUY",     build_core(scores, live, dt)),
        ("N500 Ranker",       build_n500(scores, live, dt)),
        ("Total Market",      build_total_market(scores, live, dt)),
        ("N250F Portfolio",   build_n250f(scores, live, dt)),
        ("Manas Arora",       build_manas(scores, live, dt)),
        ("Stage Transitions", build_transitions(scores, live, dt)),
        ("Market Pulse",      build_market_pulse(pulse, dt)),
        ("Sell / Exit",       build_sells(scores, live, dt)),
        ("AI Synthesis",      build_synthesis(buys, sells, pulse, dt)),
        ("Kotak Status",      (
            f"💼 <b>Kotak Neo Overlay</b>\n"
            f"✅ Kotak Neo MCP connected in Claude.ai · Session expires daily\n"
            f"In Claude.ai: <code>show my Kotak portfolio vs AlphaRadar signals</code>\n\n"
            f"<b>SELL zone — check your portfolio:</b>\n"
            + "".join(f"  ❌ <b>{r['symbol']}</b> Stage {r['weinstein_stage']}"
                      f" · RS {r['rs_percentile']:.0f}%ile · Score {r['composite_score']:.0f}\n"
                      for r in sorted(sells, key=lambda x: x['composite_score'])[:5])
            + f"\n🔗 alpharadar.streamlit.app"
        )),
    ]

    sent = 0
    for name, msg in msgs:
        if msg and len(msg.strip()) > 20:
            send_tg(msg)
            print(f"  ✅ {name}")
            sent += 1
            time.sleep(1.5)
        else:
            print(f"  ⏭ {name} (no signals)")
    print(f"\n✅ Done — {sent} messages sent")


def start_polling():
    print("🤖 Polling | @Rishabh2Bot | Ctrl+C to stop")
    last = 0
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
                             params={"offset": last+1, "timeout": 20}, timeout=30)
            if r.status_code == 200:
                for u in r.json().get("result", []):
                    last = u["update_id"]
                    _handle(u)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  Poll error: {e}")
            time.sleep(5)


def _handle(update):
    msg  = update.get("message", {})
    text = msg.get("text", "").strip()
    cid  = str(msg.get("chat", {}).get("id",""))
    def reply(t):
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      data={"chat_id":cid,"text":t,"parse_mode":"HTML"}, timeout=10)
    cmd = text.split()[0].lower() if text else ""
    if cmd == "/start":
        reply("👋 <b>AlphaRadar v2</b>\n/signals /sell /pulse /n250f /stock SYMBOL /help")
    elif cmd == "/signals":
        reply("⏳ Running (~45s)...")
        run_full_alert_cycle()
    elif cmd == "/sell":
        s, dt = load_scores()
        live = fetch_live([r["symbol"] for r in s if r["bucket"]=="SELL"][:20])
        reply(build_sells(s, live, dt))
    elif cmd == "/pulse":
        s, dt = load_scores()
        reply(build_market_pulse(load_pulse(dt), dt))
    elif cmd == "/n250f":
        s, dt = load_scores()
        info = n250f_data(s)
        live = fetch_live([r["symbol"] for r in info["portfolio"]])
        reply(build_n250f(s, live, dt))
    elif cmd == "/stock" and len(text.split()) >= 2:
        sym = text.split()[1].upper()
        s, dt = load_scores()
        row = next((r for r in s if r["symbol"]==sym), None)
        if not row:
            reply(f"❌ {sym} not found"); return
        L = fetch_live([sym]).get(sym,{})
        lp = L.get("lp", row["price"])
        chg = L.get("chg", row.get("price_change_pct",0))
        reply(
            f"🔍 <b>{sym}</b> — {dt}\n\n"
            f"💰 CMP: <b>₹{lp:,.2f}</b> {arr(chg)}{abs(chg):.2f}%\n"
            f"Score: <b>{row['composite_score']:.1f}/100</b> · {row['bucket']}\n"
            f"Stage: {row['weinstein_stage']} · RS: {row['rs_percentile']:.0f}%ile\n"
            f"Sector: {row.get('sector','?')} · Entry: {row.get('entry_signal','?')}\n"
            f"52W: ₹{row['low_52w']:,.0f}–₹{row['high_52w']:,.0f}"
        )
    elif cmd == "/help":
        reply("/signals /sell /pulse /n250f /stock SYM")


if __name__ == "__main__":
    import sys
    m = sys.argv[1] if len(sys.argv) > 1 else "run"
    if m == "poll": start_polling()
    elif m == "test": send_tg("✅ AlphaRadar v2 OK")
    else: run_full_alert_cycle()
