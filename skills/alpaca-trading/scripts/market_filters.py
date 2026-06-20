"""
Market filters — pre-entry checks that block trades when conditions are unfavorable.

Filters applied before any buy order:
  1. Earnings proximity — skip if earnings within N days
  2. News sentiment    — skip if recent news is strongly negative
  3. News summary      — return recent headlines for the dashboard
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db


# ── Earnings Filter ────────────────────────────────────────────────────────────

def get_earnings_date(symbol: str) -> datetime | None:
    """
    Return next earnings date for a symbol using yfinance.
    Returns None if unavailable or yfinance not installed.
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is None:
            return None

        # yfinance returns a dict or DataFrame depending on version
        if hasattr(cal, 'get'):
            # dict form
            earnings_date = cal.get("Earnings Date")
            if earnings_date and len(earnings_date) > 0:
                ed = earnings_date[0]
                if hasattr(ed, 'to_pydatetime'):
                    return ed.to_pydatetime().replace(tzinfo=None)
                return pd_to_dt(ed)
        elif hasattr(cal, 'loc'):
            # DataFrame form (older yfinance)
            try:
                ed = cal.loc["Earnings Date"].iloc[0]
                return pd_to_dt(ed)
            except Exception:
                pass
    except ImportError:
        pass  # yfinance not installed — skip earnings check
    except Exception:
        pass
    return None


def pd_to_dt(val) -> datetime | None:
    """Convert a pandas Timestamp to Python datetime."""
    try:
        if hasattr(val, 'to_pydatetime'):
            return val.to_pydatetime().replace(tzinfo=None)
        return datetime.fromisoformat(str(val)[:19])
    except Exception:
        return None


def check_earnings_proximity(symbol: str, days_ahead: int = 2) -> tuple[bool, str]:
    """
    Returns (safe_to_trade, reason).
    safe_to_trade=False means earnings are too close — skip this entry.
    """
    earnings_dt = get_earnings_date(symbol)
    if earnings_dt is None:
        return True, "No earnings date found (proceeding)"

    now = datetime.now()
    days_until = (earnings_dt - now).days

    if 0 <= days_until <= days_ahead:
        return False, f"Earnings in {days_until}d ({earnings_dt.strftime('%Y-%m-%d')}) — skipping to avoid volatility"

    if days_until < 0:
        return True, f"Last earnings was {abs(days_until)}d ago"

    return True, f"Next earnings in {days_until}d ({earnings_dt.strftime('%Y-%m-%d')}) — safe"


# ── News Sentiment Filter ──────────────────────────────────────────────────────

def get_recent_news(account_name: str, symbols: list[str], hours: int = 24) -> dict[str, list[dict]]:
    """
    Fetch recent news for a list of symbols via Alpaca News API.
    Returns dict: {symbol: [{"headline": ..., "summary": ..., "sentiment": ..., "url": ..., "published_at": ...}]}
    """
    try:
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest
    except ImportError:
        return {s: [] for s in symbols}

    acct = db.get_account(account_name)
    if not acct:
        return {s: [] for s in symbols}

    try:
        client = NewsClient(
            api_key=acct["api_key"],
            secret_key=acct["api_secret"]
        )
        start = datetime.now(timezone.utc) - timedelta(hours=hours)
        req = NewsRequest(
            symbols=symbols,
            start=start,
            limit=50,
            include_content=False,
            exclude_contentless=True,
        )
        news = client.get_news(req)
        articles = news.news if hasattr(news, 'news') else []
    except Exception as e:
        print(f"  Warning: News API error: {e}")
        return {s: [] for s in symbols}

    result = {s: [] for s in symbols}
    for article in articles:
        sentiment = _score_sentiment(article.headline or "", article.summary or "")
        entry = {
            "headline":     article.headline or "",
            "summary":      (article.summary or "")[:200],
            "sentiment":    sentiment,
            "url":          article.url or "",
            "published_at": str(article.created_at)[:16] if article.created_at else "",
            "author":       article.author or "",
            "source":       article.source or "",
        }
        syms = article.symbols or []
        for sym in syms:
            if sym in result:
                result[sym].append(entry)

    return result


def _score_sentiment(headline: str, summary: str) -> str:
    """
    Simple keyword-based sentiment scoring.
    Returns: 'positive', 'negative', or 'neutral'
    """
    text = (headline + " " + summary).lower()

    negative_words = [
        "downgrade", "miss", "missed", "beats expectations" , "below expectations",
        "loss", "losses", "decline", "fell", "drops", "plunges", "plunge",
        "recall", "investigation", "lawsuit", "bankrupt", "layoffs", "cuts",
        "warning", "disappoints", "disappointing", "lowered guidance", "cut guidance",
        "sell rating", "underperform", "underweight", "bearish", "short",
        "fraud", "sec", "fine", "penalty", "probe", "subpoena",
    ]
    positive_words = [
        "upgrade", "beat", "beats", "exceeds", "above expectations",
        "record", "growth", "strong", "raises guidance", "raised guidance",
        "buy rating", "outperform", "overweight", "bullish",
        "partnership", "deal", "acquisition", "dividend", "buyback",
        "profit", "revenue up", "surge", "rallies", "breakout",
    ]

    neg_score = sum(1 for w in negative_words if w in text)
    pos_score = sum(1 for w in positive_words if w in text)

    if neg_score > pos_score:
        return "negative"
    elif pos_score > neg_score:
        return "positive"
    return "neutral"


def check_news_sentiment(account_name: str, symbol: str,
                         hours: int = 24, negative_threshold: int = 2) -> tuple[bool, str, list[dict]]:
    """
    Returns (safe_to_trade, reason, articles).
    safe_to_trade=False if too many negative articles found.
    """
    news = get_recent_news(account_name, [symbol], hours=hours)
    articles = news.get(symbol, [])

    if not articles:
        return True, "No recent news (proceeding)", []

    neg_count = sum(1 for a in articles if a["sentiment"] == "negative")
    pos_count = sum(1 for a in articles if a["sentiment"] == "positive")
    total     = len(articles)

    if neg_count >= negative_threshold and neg_count > pos_count:
        headlines = "; ".join(a["headline"][:60] for a in articles[:2] if a["sentiment"] == "negative")
        return False, f"Negative news ({neg_count}/{total} articles negative): {headlines}", articles

    return True, f"News sentiment OK ({pos_count} pos / {neg_count} neg / {total - pos_count - neg_count} neutral)", articles


# ── Combined Pre-Entry Gate ────────────────────────────────────────────────────

def pre_entry_check(account_name: str, symbol: str,
                    earnings_days: int = 2,
                    news_hours: int = 24,
                    news_neg_threshold: int = 2) -> tuple[bool, str, list[dict]]:
    """
    Run all pre-entry filters. Returns (ok_to_enter, reason, news_articles).
    If ok_to_enter is False, skip the buy signal for this symbol.
    """
    # 1. Earnings proximity
    earnings_ok, earnings_reason = check_earnings_proximity(symbol, days_ahead=earnings_days)
    if not earnings_ok:
        return False, f"[EARNINGS] {earnings_reason}", []

    # 2. News sentiment
    news_ok, news_reason, articles = check_news_sentiment(
        account_name, symbol, hours=news_hours, negative_threshold=news_neg_threshold
    )
    if not news_ok:
        return False, f"[NEWS] {news_reason}", articles

    return True, f"Filters passed — {earnings_reason} | {news_reason}", articles


if __name__ == "__main__":
    # Quick test
    import json
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    accounts = db.get_accounts()
    if not accounts:
        print("No accounts configured.")
        sys.exit(1)
    acct_name = accounts[0]["name"]

    print(f"\nPre-entry check for {symbol} (account: {acct_name})\n")
    ok, reason, articles = pre_entry_check(acct_name, symbol)
    print(f"  Result:  {'✓ OK to enter' if ok else '✗ BLOCKED'}")
    print(f"  Reason:  {reason}")
    if articles:
        print(f"\n  Recent news ({len(articles)} articles):")
        for a in articles[:5]:
            icon = "📈" if a["sentiment"] == "positive" else "📉" if a["sentiment"] == "negative" else "📰"
            print(f"  {icon} [{a['sentiment']:8s}] {a['headline'][:70]}")
