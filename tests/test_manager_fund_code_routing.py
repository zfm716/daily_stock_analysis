# -*- coding: utf-8 -*-
"""Offline tests for ``DataFetcherManager.get_stock_name`` F-prefix routing.

Background
----------
The bare 6-digit form of an F-prefixed off-exchange fund code (e.g. ``002611``
for 博时黄金ETF联接C) usually ALSO identifies a regular A-share stock
(``002611`` 东方精工). If the manager:

  * normalizes the code too early (strips F before passing it to fetchers),
  * uses the normalized code as the cache key, and
  * lets the realtime quote path return a stock name for a fund code,

then ``get_stock_name("F002611")`` silently returns 东方精工 — wrong.

These tests pin down the contract that F codes must travel through a
dedicated path that preserves the F prefix as the cache key, skips the
realtime quote source, and only consults fetchers that declare they
handle the F convention.
"""

import unittest
from unittest.mock import MagicMock, patch

from data_provider.akshare_fetcher import AkshareFetcher
from data_provider.base import DataFetcherManager


def _make_manager_with_fetcher(fetcher: MagicMock) -> DataFetcherManager:
    """Build a minimal manager wired with a single injected fetcher.

    The real ``DataFetcherManager.__init__`` spins up the full default fetcher
    set and runs connectivity probes; we bypass that and inject our own so
    the test stays offline and deterministic.
    """
    mgr = DataFetcherManager.__new__(DataFetcherManager)
    # Initialize just enough state for the name-resolution path.
    mgr._ensure_concurrency_guards()
    mgr._fetchers = [fetcher]
    mgr._refresh_fetcher_indexes_locked()
    mgr._stock_name_cache = {}
    return mgr


class TestManagerFundCodeRouting(unittest.TestCase):
    def setUp(self):
        # A single mock fetcher that pretends to know both F and non-F codes.
        # We'll tighten its behaviour per test via direct attribute swaps.
        self.akshare_fetcher = MagicMock(spec=AkshareFetcher, name="AkshareFetcher")
        self.akshare_fetcher.name = "AkshareFetcher"
        self.akshare_fetcher.handles_fund_codes = True
        self.akshare_fetcher.is_available_for_request = MagicMock(return_value=True)

        self.akshare_fetcher.get_stock_name = MagicMock(
            side_effect=lambda code: (
                "博时黄金ETF联接C"
                if (code or "").upper() == "F002611"
                else ("东方精工" if code == "002611" else None)
            )
        )
        self.mgr = _make_manager_with_fetcher(self.akshare_fetcher)

    def test_f_code_returns_fund_name(self):
        result = self.mgr.get_stock_name("F002611")
        self.assertEqual(result, "博时黄金ETF联接C")

    def test_f_code_does_not_query_realtime(self):
        # Patch the class-level method so the manager can no longer call the
        # real implementation. If the F-code routing ever regresses and
        # falls back into the realtime path, the mock below will fire.
        with patch.object(
            DataFetcherManager, "get_realtime_quote", autospec=True
        ) as mock_realtime:
            self.mgr.get_stock_name("F002611")
        mock_realtime.assert_not_called()

    def test_f_code_passes_f_prefixed_code_to_fetcher(self):
        self.mgr.get_stock_name("F002611")
        # The fetcher must receive the F-prefixed form, not the normalized one.
        called_codes = [c.args[0] for c in self.akshare_fetcher.get_stock_name.call_args_list]
        self.assertIn("F002611", called_codes)
        self.assertNotIn("002611", called_codes)

    def test_f_code_uses_f_prefixed_code_as_cache_key(self):
        self.mgr.get_stock_name("F002611")
        # Cache must be keyed by the F-prefixed form so it never collides
        # with the actual A-share stock ``002611`` (东方精工).
        self.assertIn("F002611", self.mgr._stock_name_cache)
        self.assertEqual(self.mgr._stock_name_cache["F002611"], "博时黄金ETF联接C")
        self.assertNotIn("002611", self.mgr._stock_name_cache)

    def test_f_code_and_stock_002611_have_independent_caches(self):
        # First F002611 → fund name. Then 002611 → stock name. The two must
        # not pollute each other.
        self.mgr.get_stock_name("F002611")
        result = self.mgr.get_stock_name("002611")
        self.assertEqual(result, "东方精工")
        self.assertIn("F002611", self.mgr._stock_name_cache)
        self.assertEqual(self.mgr._stock_name_cache["F002611"], "博时黄金ETF联接C")
        self.assertIn("002611", self.mgr._stock_name_cache)
        self.assertEqual(self.mgr._stock_name_cache["002611"], "东方精工")

    def test_lowercase_f_prefix_is_routed_to_fund_path(self):
        result = self.mgr.get_stock_name("f002611")
        self.assertEqual(result, "博时黄金ETF联接C")
        # Cache must keep the user's original (lowercase) form consistent.
        self.assertEqual(self.mgr._stock_name_cache.get("f002611"), "博时黄金ETF联接C")


if __name__ == "__main__":
    unittest.main()
