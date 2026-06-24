# -*- coding: utf-8 -*-
"""Offline tests for TushareFetcher.get_stock_name F-prefix short-circuit.

Background
----------
Tushare's ``stock_basic`` endpoint is rate-limited to 1 call per minute. When
``DataFetcherManager.get_stock_name`` iterates fetchers, an F-prefixed
off-exchange fund code (e.g. ``F025506``) used to fall into the
``else stock_basic`` branch — wasting rate budget and producing the
"频率超限(1次/分钟)" warning.

Contract: F-prefixed codes are off-exchange funds, out of Tushare stock_basic
scope, and should be skipped so the manager can continue to fetchers that
actually support them (e.g. AkshareFetcher).
"""

import unittest
from unittest.mock import MagicMock

from data_provider.tushare_fetcher import TushareFetcher


class TestTushareFetcherFundShortCircuit(unittest.TestCase):
    def setUp(self):
        # Build a fetcher with a stub API so we can detect any accidental call.
        self.api = MagicMock(name="tushare_api")
        fetcher = TushareFetcher.__new__(TushareFetcher)
        fetcher._api = self.api
        fetcher._check_rate_limit = MagicMock(name="rate_limit")
        self.fetcher = fetcher

    def test_f_prefixed_code_returns_none_without_calling_api(self):
        # Both uppercase and lowercase F should be skipped.
        for code in ("F025506", "f025506"):
            self.api.reset_mock()
            self.fetcher._check_rate_limit.reset_mock()
            result = self.fetcher.get_stock_name(code)
            self.assertIsNone(
                result,
                f"Tushare should return None for F-prefixed code {code!r}",
            )
            # Critical: no API endpoint should be hit; no rate limit budget
            # should be consumed.
            self.assertEqual(
                self.api.stock_basic.call_count,
                0,
                f"stock_basic must not be called for {code!r}",
            )
            self.assertEqual(
                self.api.fund_basic.call_count,
                0,
                f"fund_basic must not be called for {code!r}",
            )
            self.assertEqual(
                self.api.hk_basic.call_count,
                0,
                f"hk_basic must not be called for {code!r}",
            )
            self.fetcher._check_rate_limit.assert_not_called()

    def test_f_prefixed_code_does_not_pollute_local_cache(self):
        self.fetcher.get_stock_name("F025506")
        cache = getattr(self.fetcher, "_stock_name_cache", {})
        self.assertNotIn("F025506", cache)
        self.assertNotIn("025506", cache)


if __name__ == "__main__":
    unittest.main()
