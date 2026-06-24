import logging
import pandas as pd
from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS, normalize_stock_code
from .sqlite_storage import upsert_etf_data, query_etf_data
import akshare as ak

logger = logging.getLogger(__name__)

class EtfFetcher(BaseFetcher):
    """Fetch daily net‑value data for China‑listed ETFs / 基金 using Akshare.

    The fetcher stores retrieved rows in a local SQLite cache (etf_cache.db) so
    subsequent calls for the same code and date range hit the cache, mirroring the
    stock caching strategy.
    """

    name = "EtfFetcher"
    priority = 2  # higher than Baostock, lower than possible premium sources

    def __init__(self):
        pass

    def _fetch_raw_data(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Use ``ak.fund_etf_hist_sina`` to pull daily net‑value.

        The function returns a DataFrame with ``date`` and ``close`` columns.
        """
        try:
            # Akshare expects the pure 6‑digit code (no prefix)
            pure_code = normalize_stock_code(code)
            df = ak.fund_etf_hist_sina(symbol=pure_code, start_date=start_date, end_date=end_date)
            if df.empty:
                raise DataFetchError(f"Akshare returned empty data for ETF {code}")
            # Ensure column names align with our standard columns
            df = df.rename(columns={"date": "date", "close": "close"})
            return df[["date", "close"]]
        except Exception as exc:
            raise DataFetchError(str(exc))

    def get_daily_data(self, code: str, start_date: str | None = None, end_date: str | None = None, days: int = 30) -> pd.DataFrame:
        """Public entry used by ``DataFetcherManager``.

        Parameters
        ----------
        code: str
            Fund code (may include ``F`` prefix).
        start_date, end_date: optional ISO strings. If omitted, ``days`` days
            up to today are fetched.
        days: fallback window when dates are not supplied.
        """
        # Resolve date range
        if not start_date or not end_date:
            # reuse BaseFetcher helper to compute range based on ``days``
            start_date, end_date = self._resolve_date_range(days)
        # Try cache first
        cached = query_etf_data(code, start_date, end_date)
        if not cached.empty and len(cached) >= days:
            logger.debug(f"ETF cache hit for {code} ({len(cached)} rows)")
            return cached
        # Cache miss – fetch from Akshare
        raw = self._fetch_raw_data(code, start_date, end_date)
        # Store into SQLite cache
        upsert_etf_data(raw, code)
        return raw

    # Helper to compute date range – similar to BaseFetcher logic
    def _resolve_date_range(self, days: int) -> tuple[str, str]:
        from datetime import datetime, timedelta
        end = datetime.today()
        start = end - timedelta(days=days)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
