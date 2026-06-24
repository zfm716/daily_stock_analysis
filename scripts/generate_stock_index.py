#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock Index Generation Script

Generate stock index file for frontend autocomplete functionality
Output to apps/dsa-web/public/stocks.index.json

Two-phase strategy:
1. MVP: Use existing STOCK_NAME_MAP
2. Future: Combine with AkShare for complete list

Usage:
    python3 scripts/generate_stock_index.py
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple, Optional

# Add the project root to sys.path.
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_provider.akshare_fetcher import AkshareFetcher

try:
    from pypinyin import lazy_pinyin
    PYPINYIN_AVAILABLE = True
except ImportError:
    PYPINYIN_AVAILABLE = False
    print("[Warning] pypinyin not available, pinyin fields will be empty")
    print("[Info] Install with: pip install pypinyin")


def normalize_name_for_pinyin(name: str) -> str:
    """
    Normalize stock name to avoid special prefixes and full-width characters polluting pinyin index

    Args:
        name: Original stock name

    Returns:
        Normalized name for pinyin generation
    """
    normalized = unicodedata.normalize('NFKC', name).strip()

    # Strip common A-share prefixes while preserving the core name.
    normalized = re.sub(r'^(?:\*?ST|N)+', '', normalized, flags=re.IGNORECASE)

    return normalized.strip() or unicodedata.normalize('NFKC', name).strip()


def generate_stock_index_from_map() -> List[Dict[str, Any]]:
    """
    Generate index from STOCK_NAME_MAP (MVP)

    Returns:
        List of stock index
    """
    from src.data.stock_mapping import STOCK_NAME_MAP

    index = []

    for code, name in STOCK_NAME_MAP.items():
        # Generate pinyin fields.
        pinyin_full = None
        pinyin_abbr = None
        if PYPINYIN_AVAILABLE:
            try:
                normalized_name = normalize_name_for_pinyin(name)
                py = lazy_pinyin(normalized_name)
                pinyin_full = ''.join(py)
                pinyin_abbr = ''.join([p[0] for p in py])
            except Exception:
                pass

        # Determine market and asset type.
        market, asset_type = determine_market_and_type(code)

        # Generate short aliases.
        aliases = generate_aliases(name)

        index.append({
            "canonicalCode": build_canonical_code(code, market),
            "displayCode": code,
            "nameZh": name,
            "pinyinFull": pinyin_full,
            "pinyinAbbr": pinyin_abbr,
            "aliases": aliases,
            "market": market,
            "assetType": asset_type,
            "active": True,
            "popularity": 100,  # Default popularity
        })

    return index


def determine_market_and_type(code: str) -> Tuple[str, str]:
    """
    Determine market and asset type based on stock code

    Args:
        code: Stock code

    Returns:
        Tuple of (market, asset_type)
    """
    raw = (code or "").strip().upper()

    # F 开头场外基金 (F + 5-6 digits)
    if raw.startswith('F') and len(raw) > 1 and raw[1:].isdigit() and len(raw) - 1 in (5, 6):
        return 'CN', 'fund'

    # 6 位场内 ETF 前缀
    if len(raw) == 6 and raw.startswith(('51', '52', '56', '58', '15', '16', '18')):
        return 'ETF', 'fund'

    if raw.isdigit():
        if len(raw) == 5:
            # Five digits: likely HK stock or legacy B-share.
            if raw.startswith('0') or raw.startswith('2'):
                return 'HK', 'stock'
            return 'CN', 'stock'
        elif len(raw) == 6:
            # Six digits: A-share universe.
            if raw.startswith('6'):
                return 'CN', 'stock'  # Shanghai
            elif raw.startswith(('0', '2', '3')):
                return 'CN', 'stock'  # Shenzhen
            elif raw.startswith('8'):
                return 'BSE', 'stock'  # Beijing Stock Exchange
            return 'CN', 'stock'
        elif len(raw) == 4:
            # Four digits: likely a US symbol or special market code.
            return 'US', 'stock'

    # 字母代码，美股或其他
    return 'US', 'stock'


def build_fund_index(fetcher: AkshareFetcher) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """Fetch full fund list (off-exchange + ETF)."""
    print("正在获取基金列表...")
    df = fetcher.fetch_fund_list()
    if df.empty:
        print("[Warning] 基金列表为空")
        return [], set()

    fund_codes_reserved: Set[str] = set()
    rows: List[Dict[str, Any]] = []

    # Columns: 基金代码, 基金简称, 基金类型, ...
    code_col = df.columns[0]
    name_col = "基金简称" if "基金简称" in df.columns else df.columns[2]
    type_col = "基金类型" if "基金类型" in df.columns else None

    for _, r in df.iterrows():
        code6 = str(r[code_col]).zfill(6)
        fund_type = str(r.get(type_col, '')) if type_col else ''
        name = str(r[name_col]).strip()

        # 场外基金分类 (Off-exchange)
        is_off_exchange = fund_type in {
            '联接基金', 'LOF', 'FOF', 'QDII', 'OFC', '货币型', '理财型',
            '债券型', '债券指数', '混合型', '股票型', '被动指数型',
            '增强指数型', '定开债', '封闭债', '其他', '固收+',
        }
        # 场内 ETF 分类
        is_etf = fund_type == 'ETF' or code6.startswith(('51', '52', '56', '58', '15', '16', '18'))

        if is_etf and not is_off_exchange:
            market, asset_type = 'ETF', 'fund'
            display_code = code6
        elif is_off_exchange:
            market, asset_type = 'CN', 'fund'
            display_code = 'F' + code6
        else:
            # Skip other types if not explicitly categorized as fund/etf
            continue

        pinyin_full, pinyin_abbr = generate_pinyin_fields(name)
        aliases = generate_aliases(name)

        rows.append({
            "canonicalCode": build_canonical_code(display_code, market),
            "displayCode": display_code,
            "nameZh": name,
            "pinyinFull": pinyin_full,
            "pinyinAbbr": pinyin_abbr,
            "aliases": aliases,
            "market": market,
            "assetType": asset_type,
            "active": True,
            "popularity": 80,  # Funds slightly lower default popularity than main stocks
        })
        fund_codes_reserved.add(code6)

    print(f"完成基金索引构建: {len(rows)} 条")
    return rows, fund_codes_reserved


def build_stock_index(fetcher: AkshareFetcher, skip_codes: Set[str] = None) -> List[Dict[str, Any]]:
    """Fetch full A-share stock list."""
    print("正在获取股票列表...")
    df = fetcher.fetch_stock_list()
    if df.empty:
        print("[Warning] 股票列表为空，回退到 STOCK_NAME_MAP")
        return generate_stock_index_from_map()

    skip_codes = skip_codes or set()
    rows: List[Dict[str, Any]] = []

    # Eastmoney spot columns: 代码, 名称, ...
    for _, r in df.iterrows():
        code = str(r['代码']).strip()
        name = str(r['名称']).strip()

        if code in skip_codes:
            continue

        market, asset_type = determine_market_and_type(code)
        pinyin_full, pinyin_abbr = generate_pinyin_fields(name)
        aliases = generate_aliases(name)

        rows.append({
            "canonicalCode": build_canonical_code(code, market),
            "displayCode": code,
            "nameZh": name,
            "pinyinFull": pinyin_full,
            "pinyinAbbr": pinyin_abbr,
            "aliases": aliases,
            "market": market,
            "assetType": asset_type,
            "active": True,
            "popularity": 100,
        })

    print(f"完成股票索引构建: {len(rows)} 条")
    return rows


def generate_pinyin_fields(name: str) -> Tuple[Optional[str], Optional[str]]:
    """Generate pinyin full and abbreviation for a name."""
    pinyin_full = None
    pinyin_abbr = None
    if PYPINYIN_AVAILABLE:
        try:
            normalized_name = normalize_name_for_pinyin(name)
            py = lazy_pinyin(normalized_name)
            pinyin_full = ''.join(py)
            pinyin_abbr = ''.join([p[0] for p in py])
        except Exception:
            pass
    return pinyin_full, pinyin_abbr


def market_to_suffix(market: str) -> str:
    """
    Convert market code to suffix

    Args:
        market: Market code

    Returns:
        Market suffix
    """
    suffix_map = {
        'CN': 'SH',  # 简化处理，默认上海
        'HK': 'HK',
        'US': 'US',
        'INDEX': 'SH',
        'ETF': 'SH',
        'BSE': 'BJ',
    }
    return suffix_map.get(market, 'SH')


def build_canonical_code(code: str, market: str) -> str:
    """
    Generate canonical stock code based on code and market.

    A-shares need to distinguish between SH/SZ/BJ, cannot rely solely on the general CN -> SH mapping.
    """
    if market == 'CN' and code.isdigit() and len(code) == 6:
        # Shanghai Stock Exchange (SH)
        # 60xxxx: Main board, 688xxx: STAR market, 900xxx: B-shares
        if code.startswith(('6', '900')):
            return f"{code}.SH"

        # Shenzhen Stock Exchange (SZ)
        # 00xxxx: Main board, 30xxxx: ChiNext, 20xxxx: B-shares
        if code.startswith(('0', '2', '3')):
            return f"{code}.SZ"

        # Beijing Stock Exchange (BJ)
        # 920xxx: New codes and migrated stock codes after April 2024
        # 43xxxx, 83xxxx, 87xxxx, 88xxxx: Historical/Temporary codes
        # 81xxxx, 82xxxx: Convertible bonds/Preferred stocks
        if code.startswith(('920', '43', '83', '87', '88', '81', '82')):
            return f"{code}.BJ"

    if market == 'BSE' and code.isdigit() and len(code) == 6:
        return f"{code}.BJ"

    return f"{code}.{market_to_suffix(market)}"


def generate_aliases(name: str) -> List[str]:
    """
    Generate stock aliases (abbreviations)

    Args:
        name: Full stock name

    Returns:
        List of aliases
    """
    aliases = []

    # 常见简称映射
    alias_map = {
        '贵州茅台': ['茅台'],
        '中国平安': ['平安'],
        '平安银行': ['平银'],
        '招商银行': ['招行'],
        '五粮液': ['五粮'],
        '宁德时代': ['宁德'],
        '比亚迪': ['比亚'],
        '工商银行': ['工行'],
        '建设银行': ['建行'],
        '农业银行': ['农行'],
        '中国银行': ['中行'],
        '交通银行': ['交行'],
        '兴业银行': ['兴业'],
        '浦发银行': ['浦发'],
        '民生银行': ['民生'],
        '中信证券': ['中信'],
        '东方财富': ['东财'],
        '海康威视': ['海康'],
        '隆基绿能': ['隆基'],
        '中国神华': ['神华'],
        '长江电力': ['长电'],
        '中国石化': ['石化'],
        '中国石油': ['石油'],
    }

    if name in alias_map:
        aliases.extend(alias_map[name])

    return aliases


def compress_index(index: List[Dict[str, Any]]) -> List[List]:
    """
    Compress index to array format to reduce file size

    Args:
        index: Original index

    Returns:
        Compressed index
    """
    compressed = []
    for item in index:
        compressed.append([
            item["canonicalCode"],
            item["displayCode"],
            item["nameZh"],
            item.get("pinyinFull"),
            item.get("pinyinAbbr"),
            item.get("aliases", []),
            item["market"],
            item["assetType"],
            item["active"],
            item.get("popularity", 0),
        ])
    return compressed


def save_index_to_file(index: List[Dict[str, Any]], filename: str, test_mode: bool = False):
    """Save index to a JSON file (compressed format)."""
    compressed = compress_index(index)
    
    if test_mode:
        print(f"\n[测试模式] 预计 {filename} 文件大小：{len(json.dumps(compressed, ensure_ascii=False, separators=(',', ':'))) / 1024:.2f} KB")
        return

    output_path = Path(__file__).parent.parent / "apps" / "dsa-web" / "public" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('[\n')
        for i, item in enumerate(compressed):
            json.dump(item, f, ensure_ascii=False, separators=(',', ':'))
            if i < len(compressed) - 1:
                f.write(',\n')
            else:
                f.write('\n')
        f.write(']\n')

    file_size = output_path.stat().st_size
    print(f"索引已生成：{output_path} ({file_size / 1024:.2f} KB)")


def main():
    """Main function"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='生成股票/基金自动补全索引文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 scripts/generate_stock_index.py              # 默认：生成索引文件
  python3 scripts/generate_stock_index.py --test       # 测试模式：只读取不写入
  python3 scripts/generate_stock_index.py --test -v    # 测试模式 + 显示详细数据
        """
    )
    parser.add_argument(
        '--test', '-t',
        action='store_true',
        help='测试模式：只读取和验证数据，不写入文件'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='详细模式：显示预览数据'
    )
    args = parser.parse_args()

    print("开始生成索引数据...")

    fetcher = AkshareFetcher()

    # 1. 基金索引 (场内 ETF + 场外基金)
    fund_rows, fund_codes_reserved = build_fund_index(fetcher)

    # 2. 股票索引 (A股，跳过已在基金列表中的代码)
    stock_rows = build_stock_index(fetcher, skip_codes=fund_codes_reserved)

    # 3. 指数/其他 (目前仍从 STOCK_NAME_MAP 补充一些关键指数)
    existing_display_codes = {r['displayCode'] for r in fund_rows + stock_rows}
    legacy_index = generate_stock_index_from_map()
    extra_rows = [r for r in legacy_index if r['displayCode'] not in existing_display_codes]

    # 合并股票和其他非基金数据到 stocks.index.json
    stock_index = stock_rows + extra_rows
    fund_index = fund_rows

    print(f"统计数据：股票索引 {len(stock_index)} 条，基金索引 {len(fund_index)} 条")

    # 保存文件
    save_index_to_file(stock_index, "stocks.index.json", args.test)
    save_index_to_file(fund_index, "funds.index.json", args.test)

    if args.test and args.verbose:
        if fund_index:
            print("\n基金数据预览 (前5条):")
            for i, item in enumerate(fund_index[:5]):
                print(f"  {i + 1}. {item['canonicalCode']} - {item['nameZh']} ({item['displayCode']})")
        
        if stock_index:
            print("\n股票数据预览 (前5条):")
            for i, item in enumerate(stock_index[:5]):
                print(f"  {i + 1}. {item['canonicalCode']} - {item['nameZh']} ({item['displayCode']})")

    print("\n✓ 索引生成完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
