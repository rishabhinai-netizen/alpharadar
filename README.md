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

## Deployment

Deployed on Streamlit Cloud with Supabase backend.

## Accuracy

100% accuracy on 15 validation stocks with known chart patterns.
