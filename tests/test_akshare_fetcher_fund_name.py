# -*- coding: utf-8 -*-
"""Offline tests for AkshareFetcher.get_stock_name (F-prefixed fund codes).

These tests use mocked akshare entry points to avoid network calls and exercise
only the resolution logic added for 场外基金 (off-exchange funds) whose codes
arrive as ``Fxxxxxx``.

The contract under test:
- ``AkshareFetcher.get_stock_name`` returns a Chinese short name for F-prefixed
  off-exchange fund codes.
- Primary path: ``ak.fund_name_em()`` cached full-fund list.
- Fallback path: ``ak.fund_individual_basic_info_xq(symbol=code)``.
- Non-F codes are intentionally left to other fetchers (returns ``None``).
- All upstream akshare errors degrade to ``None`` rather than raising.
"""

import unittest
from unittest.mock import patch

import pandas as pd

from data_provider.akshare_fetcher import AkshareFetcher


def _make_full_list(rows):
    """Build a DataFrame matching the shape returned by ak.fund_name_em()."""
    return pd.DataFrame(
        {
            "基金代码": [r[0] for r in rows],
            "拼音缩写": ["MOCK"] * len(rows),
            "基金简称": [r[1] for r in rows],
            "基金类型": ["联接基金"] * len(rows),
            "拼音全称": ["MOCKQUANPIN"] * len(rows),
        }
    )


def _make_xq_detail(short_name):
    """Build a DataFrame matching ak.fund_individual_basic_info_xq() output."""
    return pd.DataFrame(
        {
            "item": ["基金代码", "基金简称", "基金全称", "成立时间"],
            "value": ["002611", short_name, short_name + "(全称)", "2020-01-01"],
        }
    )


class TestAkshareFetcherGetStockNameFund(unittest.TestCase):
    def setUp(self):
        # Disable rate-limiting sleeps so tests run instantly.
        self.fetcher = AkshareFetcher(sleep_min=0.0, sleep_max=0.0)
        # Reset class-level cache so each test is independent.
        AkshareFetcher._fund_name_em_cache = None

    # --- Red: method does not exist yet, these should fail at AttributeError ---

    def test_resolves_f_code_via_cached_full_list(self):
        cached = _make_full_list([("002611", "博时黄金ETF联接C")])
        with patch("akshare.fund_name_em", return_value=cached) as mock_list, \
                patch("akshare.fund_individual_basic_info_xq") as mock_xq:
            result = self.fetcher.get_stock_name("F002611")
        self.assertEqual(result, "博时黄金ETF联接C")
        mock_list.assert_called_once()
        # Cache hit — fallback must NOT be called.
        mock_xq.assert_not_called()

    def test_lowercase_f_prefix_is_stripped(self):
        cached = _make_full_list([("002611", "博时黄金ETF联接C")])
        with patch("akshare.fund_name_em", return_value=cached), \
                patch("akshare.fund_individual_basic_info_xq") as mock_xq:
            result = self.fetcher.get_stock_name("f002611")
        self.assertEqual(result, "博时黄金ETF联接C")
        mock_xq.assert_not_called()

    def test_falls_back_to_xueqiu_when_cached_list_misses(self):
        cached = _make_full_list([("999999", "其他基金")])
        xq = _make_xq_detail("易方达中证半导体材料设备主题ETF联接发起式C")
        with patch("akshare.fund_name_em", return_value=cached), \
                patch("akshare.fund_individual_basic_info_xq", return_value=xq) as mock_xq:
            result = self.fetcher.get_stock_name("F021894")
        self.assertEqual(result, "易方达中证半导体材料设备主题ETF联接发起式C")
        mock_xq.assert_called_once()
        # The fallback must be called with the BARE 6-digit code, not F-prefixed.
        args, kwargs = mock_xq.call_args
        sent = kwargs.get("symbol") or args[0]
        self.assertEqual(str(sent).lstrip("Ff"), "021894")
        self.assertFalse(str(sent).upper().startswith("F"))

    def test_reuses_cached_full_list_across_calls(self):
        cached = _make_full_list([("002611", "博时黄金ETF联接C")])
        with patch("akshare.fund_name_em", return_value=cached) as mock_list, \
                patch("akshare.fund_individual_basic_info_xq") as mock_xq:
            self.fetcher.get_stock_name("F002611")
            self.fetcher.get_stock_name("F002611")
            self.fetcher.get_stock_name("F002611")
        # Only the first call should hit the network; later ones reuse the cache.
        self.assertEqual(mock_list.call_count, 1)
        self.assertEqual(mock_xq.call_count, 0)

    def test_returns_none_when_both_sources_fail(self):
        cached = _make_full_list([])  # empty
        with patch("akshare.fund_name_em", return_value=cached), \
                patch(
                    "akshare.fund_individual_basic_info_xq",
                    side_effect=Exception("network down"),
                ):
            result = self.fetcher.get_stock_name("F002611")
        self.assertIsNone(result)

    def test_returns_none_for_non_f_codes(self):
        # A-share / ETF / HK / US codes are not the responsibility of this
        # method; they should fall through to other fetchers in the manager.
        with patch("akshare.fund_name_em") as mock_list, \
                patch("akshare.fund_individual_basic_info_xq") as mock_xq:
            self.assertIsNone(self.fetcher.get_stock_name("600519"))
            self.assertIsNone(self.fetcher.get_stock_name("161725"))
            self.assertIsNone(self.fetcher.get_stock_name("HK00700"))
        mock_list.assert_not_called()
        mock_xq.assert_not_called()


if __name__ == "__main__":
    unittest.main()
