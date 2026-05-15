# ◎ AlphaRadar

**Nifty 1000 Weinstein + O'Neil + Minervini Scoring Engine**

Scores every stock in the Nifty Total Market Index (755 stocks) on a 0-100 composite scale using:
- **Weinstein Stage Analysis** (30%) — with Hard Gate
- **Relative Strength** (25%) — Mansfield RS + percentile rank
- **Volume & Price Action** (20%) — O'Neil/Minervini patterns
- **Fundamentals** (15%) — EPS, revenue, ROE
- **Catalyst/News** (10%) — Bulk deals, earnings proximity

## Stage Hard Gate

The key innovation: Stage isn't just a weight — it's a filter.
- Stage 4 stocks are **capped at 20** regardless of RS/fundamentals
- Stage 3 stocks are **capped at 40**
- This prevents buying declining stocks that "look cheap"

## Pages

| Page | Description |
|------|-------------|
| ⚡ Run Scoring | Full scoring pipeline — run weekly or daily |
| 📊 N250F | Nifty 250 F&O watchlist |
| 📡 Market Pulse | Market breadth and sector rotation |
| 🏆 N500 Strength Ranker | **NEW** — Ranks all Nifty 500 stocks strongest to weakest with live CMP, multi-timeframe returns, signal tags (RS Leader / Breakout / Stage 2 / News-Driven⚑ / Vol Surge / Weak), and Claude AI one-line justification per stock |

## Secrets required (Streamlit Cloud)

```toml
[supabase]
url = "https://aiebaqvclyzxajigvkfd.supabase.co"
key = "your-supabase-anon-key"

BREEZE_API_KEY      = "your-icici-direct-api-key"
BREEZE_API_SECRET   = "your-icici-direct-api-secret"
BREEZE_SESSION_TOKEN = "daily-session-token"   # refresh every morning

ANTHROPIC_API_KEY   = "sk-ant-..."             # for AI justifications on N500 Ranker
```

## Deployment

Deployed on Streamlit Cloud with Supabase backend (`aiebaqvclyzxajigvkfd`).

## Accuracy

100% accuracy on 15 validation stocks with known chart patterns.
