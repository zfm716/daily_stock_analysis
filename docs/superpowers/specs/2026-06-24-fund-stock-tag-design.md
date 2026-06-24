# 区分基金 / 股票：StockAutocomplete tag 筛选

> 状态：设计中 / 待用户审查
> 日期：2026-06-24
> 范围：StockAutocomplete 组件 + stocks.index.json 数据生成 + 周边测试

## 1. 目标与背景

用户希望在 Web 前端的股票/代码输入框（`StockAutocomplete`）里，能按"基金 / 股票"两类 tag 查阅候选代码，而不是看到 A 股、ETF、场外联接基金混杂在一起。

实际痛点：
- `F002611` 是场外基金"博时黄金ETF联接C"，但 6 位数字 `002611` 本身也是 A 股"东方精工"。用户期望输入 `F002611` 一定命中"博时黄金ETF联接C"而不是被同名股票污染。
- 场内 ETF（`51/52/56/58/15/16/18` 开头）属于基金范畴但 `market` 字段当前叫 `ETF`，跟用户的"基金"心智模型一致，应当折进"基金"。

不在本次范围：
- 选股池 / 主页 / 历史记录 / 报告页的基金股票拆分（用户明确选择"只 StockAutocomplete 筛选"）。
- `monitoring` / `alerts` 列表的 type 字段变更。
- 数据层新增独立的"基金池"持久化（仍复用现有 `stocks.index.json`）。

## 2. 分类决策表

| 输入 code 形态 | market | asset_type | 来源 | 在 stocks.index.json 的 display code |
| --- | --- | --- | --- | --- |
| `F` + 5–6 位数字（场外） | `CN` | `fund` | `ak.fund_name_em()` 中 `基金类型 ∈ {联接基金, LOF, FOF, QDII, OFC, 货币型, …}` | 原 6 位数字 + `F` 前缀（如 `F002611`） |
| `51/52/56/58/15/16/18` 开头 6 位（场内 ETF） | `ETF` | `fund` | `ak.fund_name_em()` 中 `基金类型 = ETF` 或现有 `determine_market_and_type('ETF')` 路径 | 原 6 位数字（如 `510050`） |
| `0/2/3/4/6/9` 开头 6 位（A 股） | `CN` | `stock` | `ak.stock_zh_a_spot_em()` | 原 6 位数字 + 交易所后缀 |
| `8` 开头 6 位 | `BSE` | `stock` | 北交所接口 | 原 6 位数字 |
| 5 位 | `HK` | `stock` | 港股接口 | 5 位数字 |
| 指数代码 | `INDEX` | `index` | 指数接口 | 指数代码 |
| 美股 / 日股 / 韩股 ticker | 各原值 | `stock` | 已有接口 | 原 ticker |

**关键约束**：场外基金不收录裸 6 位形式，只收录 `F` + 6 位。避免与 A 股同名代码（`002611` → 东方精工）冲突。

## 3. 数据层：`scripts/generate_stock_index.py` 改造

### 3.1 `determine_market_and_type` 扩展

在现有 5/6 位判定之前新增 F 前缀分支：

```python
def determine_market_and_type(code: str) -> tuple[str, str]:
    raw = (code or "").strip().upper()
    # F 开头场外基金
    if raw.startswith('F') and len(raw) > 1 and raw[1:].isdigit() and len(raw) - 1 in (5, 6):
        return 'CN', 'fund'
    # 6 位场内 ETF 前缀
    if len(raw) == 6 and raw.startswith(('51', '52', '56', '58', '15', '16', '18')):
        return 'ETF', 'fund'   # 原来是 ('ETF', 'etf')
    # 其余分支保持原样
    ...
```

### 3.2 新增 `build_fund_index()`

独立函数，先于 `build_stock_index()` 跑、收集到的 6 位 fund code 集合传给股票构建以避免重复：

```python
def build_fund_index(fetcher) -> list[dict]:
    """从 ak.fund_name_em() 拉取场外 + 场内 ETF 全量。"""
    df = fetcher.fetch_fund_list()  # 等价于 ak.fund_name_em()
    fund_codes_reserved: set[str] = set()
    rows: list[dict] = []
    for _, r in df.iterrows():
        code6 = str(r['基金代码']).zfill(6)
        fund_type = str(r.get('基金类型', ''))
        is_off_exchange = fund_type in {
            '联接基金', 'LOF', 'FOF', 'QDII', 'OFC', '货币型', '理财型',
            '债券型', '债券指数', '混合型', '股票型', '被动指数型',
            '增强指数型', '定开债', '封闭债', '其他', '固收+',
        }
        is_etf = fund_type == 'ETF' or code6.startswith(('51', '52', '56', '58', '15', '16', '18'))
        if is_etf and not is_off_exchange:
            market, asset_type = 'ETF', 'fund'
            display_code = code6
        elif is_off_exchange:
            market, asset_type = 'CN', 'fund'
            display_code = 'F' + code6
        else:
            continue
        # 跳过与 A 股重叠的场内 ETF
        rows.append({...})
        fund_codes_reserved.add(code6)
    return rows, fund_codes_reserved
```

主流程合并：

```python
fund_rows, fund_codes_reserved = build_fund_index(fetcher)
stock_rows = build_stock_index(fetcher, skip_codes=fund_codes_reserved)  # 51/52/... 6 位不重复
index = fund_rows + stock_rows + index_rows + ...
```

### 3.3 索引输出格式

沿用现有 10 元 tuple，不动 schema（`market` 字段值新增 `'CN' (fund)` / `'ETF' (fund)`，前端按 `assetType` 字段区分）：

```
[display_code, code, name, pinyin, short, aliases, market, asset_type, active, sort_weight]
```

## 4. 前端类型 & 徽章

### 4.1 [apps/dsa-web/src/types/stockIndex.ts](file:///d:/编程/Python/daily_stock_analysis/apps/dsa-web/src/types/stockIndex.ts)

```ts
export type AssetType = 'stock' | 'fund' | 'index';
// 'etf' 已被 'fund' 吸收；保留兼容分支仅在生成器输出里（不会写回索引）
```

迁移要求：所有用到 `AssetType` 的地方扫一遍 `'etf'` 字面量，迁到 `'fund'` 或显式兼容：

```ts
// 兼容写法（如有需要）
if ((item.assetType as string) === 'etf') item.assetType = 'fund';
```

### 4.2 [apps/dsa-web/src/components/StockAutocomplete/SuggestionsList.tsx](file:///d:/编程/Python/daily_stock_analysis/apps/dsa-web/src/components/StockAutocomplete/SuggestionsList.tsx)

新增 `ASSET_TYPE_BADGE_CONFIG`：

```ts
const ASSET_TYPE_BADGE_CONFIG = {
  fund: { label: '基金', className: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-500' },
};
```

渲染逻辑（伪代码）：

```tsx
const renderBadge = (item: StockSuggestion) => {
  if (item.assetType === 'fund') {
    return <Badge ...>{ASSET_TYPE_BADGE_CONFIG.fund.label}</Badge>;
  }
  return <MarketBadge market={item.market} />;  // 沿用 MARKET_BADGE_CONFIG
};
```

`MARKET_BADGE_CONFIG` 保留（INDEX / ETF / BSE 等仍然兜底，只是 fund 条目优先走 asset_type 徽章）。

## 5. UI：常驻 chip 过滤

### 5.1 [apps/dsa-web/src/components/StockAutocomplete/StockChipRow.tsx](file:///d:/编程/Python/daily_stock_analysis/apps/dsa-web/src/components/StockAutocomplete/StockChipRow.tsx)（新建）

Props：

```ts
interface StockChipRowProps {
  value: AssetFilter;
  onChange: (next: AssetFilter) => void;
}
type AssetFilter = 'all' | 'stock' | 'fund';
```

3 chip，水平排列，无图标。视觉：

- 选中：主色边框 + 浅主色背景
- 未选：默认边框 + 透明背景，hover 主色淡边框

文案走 i18n：在 `apps/dsa-web/src/locales/featureText.ts` 里追加

```ts
assetFilterAll: { zh: '全部', en: 'All' },
assetFilterStock: { zh: '股票', en: 'Stocks' },
assetFilterFund: { zh: '基金', en: 'Funds' },
```

### 5.2 [StockAutocomplete.tsx](file:///d:/编程/Python/daily_stock_analysis/apps/dsa-web/src/components/StockAutocomplete/StockAutocomplete.tsx) 集成

```tsx
const [assetFilter, setAssetFilter] = useState<AssetFilter>('all');
const { suggestions, /* ... */ } = useAutocomplete(index, { assetFilter });
return (
  <div className="flex flex-col gap-1">
    <input ... />
    <StockChipRow value={assetFilter} onChange={setAssetFilter} />
    {isOpen && <SuggestionsList items={suggestions} ... />}
  </div>
);
```

状态不持久化。组件卸载即清零（符合"最小范围 + 不引入全局偏好"）。

### 5.3 [useAutocomplete](file:///d:/编程/Python/daily_stock_analysis/apps/dsa-web/src/hooks/useAutocomplete.ts) 过滤逻辑

在 `useAutocomplete` 现有 query 过滤前，先按 `assetFilter` 截取 index：

```ts
const baseByFilter = useMemo(() => {
  if (assetFilter === 'all') return index;
  return index.filter((item) => item.assetType === assetFilter);
}, [index, assetFilter]);
```

随后 `suggestions` 计算从 `baseByFilter` 取（不直接用 `index`）。文字输入与 chip 是 **AND**。

## 6. 错误处理 & 边界

- 空索引 / 过滤后空集 → 沿用现有 `EmptyState` 组件；不专门区分"全部空"和"过滤后空"。
- `F` 前缀但 `F` 后不是 5/6 位数字 → 旧 `normalize_stock_code` 已经返回原样，本次不动；index 生成脚本里 `build_fund_index` 跳过非法 code。
- `ak.fund_name_em()` 失败 → 记录 warning，跳过 fund 注入，主流程继续生成 stock 索引；不阻塞脚本退出码 0。
- 同一 6 位既是 fund（场内 ETF）又走 A 股路径 → `fund_codes_reserved` 集合传给 stock 生成，A 股路径跳过这些 code。
- `'etf'` 旧数据 → 一次性迁移：`scripts/refresh_stock_index.py` 重跑后自动归一为 `'fund'`。

## 7. 测试矩阵

### 7.1 Python

`tests/test_generate_stock_index.py`（如不存在则新建）：

| 用例 | 输入 | 期望 |
| --- | --- | --- |
| 现有 A 股 6 位 | `002611` | `('CN', 'stock')` |
| F 开头场外 6 位 | `F002611` | `('CN', 'fund')` |
| 场内 ETF 沪 51 | `510050` | `('ETF', 'fund')` |
| 场内 ETF 深 16 | `159915` | `('ETF', 'fund')` |
| 港股 5 位 | `00700` | `('HK', 'stock')` |
| 北交所 8 | `830xxx` | `('BSE', 'stock')` |
| 指数 | `000300` | `('INDEX', 'index')` |
| 防重复 | fund + stock 合并 | `510050` 出现 1 次且 `asset_type='fund'` |
| F 后 5 位 | `F12345` | `('CN', 'fund')`（与 `normalize_stock_code` 对齐） |
| F 后非数字 | `Fabc12` | 走原 `is_etf_code` / `else` 分支，不被识别为 fund |

### 7.2 前端

[StockAutocomplete.test.tsx](file:///d:/编程/Python/daily_stock_analysis/apps/dsa-web/src/components/StockAutocomplete/__tests__/StockAutocomplete.test.tsx)：

- 渲染 3 个 chip
- 默认 `all`
- 点 "基金" → suggestions 只剩 `assetType === 'fund'`
- 点 "股票" → 反之
- 点 "全部" → 恢复
- chip + 文字 AND 关系

[StockChipRow.test.tsx](file:///d:/编程/Python/daily_stock_analysis/apps/dsa-web/src/components/StockAutocomplete/__tests__/StockChipRow.test.tsx)（新建）：

- 3 chip 渲染
- 点击回调
- i18n 文案切换
- 选中态 className

## 8. 文档

- [docs/CHANGELOG.md](file:///d:/编程/Python/daily_stock_analysis/docs/CHANGELOG.md) `[Unreleased]` 加：
  - `[新功能] stocks.index.json 区分 fund / stock / index 资产类型，场外基金以 F 前缀形式收录避免与 A 股同名代码冲突`
  - `[新功能] StockAutocomplete 输入框下加 [全部] [股票] [基金] chip 过滤`
- [docs/market-support.md](file:///d:/编程/Python/daily_stock_analysis/docs/market-support.md) 在 "市场支持" 小节追加"场外基金"条目，说明 F 前缀约定。
- [README.md](file:///d:/编程/Python/daily_stock_analysis/README.md) **不更新**（AGENTS.md：README 只放首页级信息，这种细节放 docs）。

## 9. 风险点

1. `ak.fund_name_em()` 字段结构变更（akshare 升级可能调整列名）→ 需在 `build_fund_index` 中按列名 fallback，参考 §3.2 的 `'基金简称'` / `'基金代码'` 多分支写法。
2. `'etf'` → `'fund'` 兼容：现有 watchlist / history 持久化里如果有 `asset_type='etf'` 旧值，需要做读取时的兼容回退。
3. 重跑 `scripts/generate_stock_index.py` 会覆盖 `apps/dsa-web/public/stocks.index.json`，文件大小从 ~100KB（A 股 ~5000 条）涨到 ~2-3MB（27k fund + 5k stock + others），CDN / 浏览器加载时间需要关注；后续如果成为瓶颈可以再加分片或压缩。
4. fund 名称变化（基金清盘 / 转型）需要 `scripts/refresh_stock_index.py` 周期性重跑；不在本次范围但要列入后续 TODO。

## 10. 实施步骤（高层，落到 writing-plans 阶段细化）

1. 修改 `scripts/generate_stock_index.py`：`determine_market_and_type` 扩展 + `build_fund_index` 新增 + 主流程合并
2. 新增 `tests/test_generate_stock_index.py`
3. 修改 `apps/dsa-web/src/types/stockIndex.ts`：`AssetType` 扩展
4. 修改 `apps/dsa-web/src/components/StockAutocomplete/SuggestionsList.tsx`：新增 `ASSET_TYPE_BADGE_CONFIG` + 渲染分支
5. 新建 `apps/dsa-web/src/components/StockAutocomplete/StockChipRow.tsx` + 测试
6. 修改 `StockAutocomplete.tsx` 集成 chip
7. 修改 `useAutocomplete.ts` 接收 `assetFilter` 参数
8. 修改 `apps/dsa-web/src/locales/featureText.ts` 加 3 个 i18n key
9. 新增 `StockChipRow.test.tsx` + 扩展 `StockAutocomplete.test.tsx`
10. 重新生成 `apps/dsa-web/public/stocks.index.json`
11. 文档：`docs/CHANGELOG.md` + `docs/market-support.md`
12. 验证：`./scripts/ci_gate.sh` + `cd apps/dsa-web && npm run lint && npm run build`
