# 投资理财 Agent 工具清单

> 工具是 Agent 的手脚。这份文档定义所有工具的名称、用途、参数。
> 工具 docstring 是写给大模型看的，决定大模型知不知道该用这个工具。

---

## 一、工具设计原则

### 1.1 工具分类

| 类别 | 特征 | 例子 |
|------|------|------|
| **查询类** | 只读，无副作用 | 查净值、查风险等级 |
| **计算类** | 纯计算，无副作用 | 计算风险指标 |
| **合规类** | 强制串行执行，结果影响流程走向 | 适当性检查 |
| **RAG 类** | 向量搜索，只读 | 搜索产品说明书 |

### 1.2 docstring 写法规范

大模型靠 docstring 决定是否调用某个工具，以及每个参数是什么含义：

```
好的 docstring：
"查询客户的风险承受能力等级。
必须在生成任何投资建议之前调用此工具。
client_id: 客户唯一标识，从当前会话上下文获取。
返回 risk_level（C1-C5等级名称）、score（评分0-100）、valid_date（评测有效期）。"

坏的 docstring（大模型不知道什么时候用）：
"获取客户信息"
```

---

## 二、完整工具清单

### 分类 A：产品信息查询

#### A1. `query_product_info` — 查产品基本信息

```python
from langchain_core.tools import tool

@tool
def query_product_info(product_code, product_type="all"):
    """
    查询金融产品基本信息：产品名称、风险等级（R1-R5）、产品类型、
    成立日期、基金经理、管理费率、最低申购金额。

    product_code: 产品代码，如基金代码 '000001'，债券代码 '019521'。
    product_type: 类型过滤，'fund'（基金）、'bond'（债券）、'all'（全部），默认 all。

    适用于：用户询问某具体产品详情，或推荐前核实产品信息。
    注意：不包含实时净值或价格，净值请用 query_fund_nav。
    """
    # 实现：查 MySQL products 表或调外部数据 API
    return {
        "code": product_code,
        "name": "示例基金",
        "risk_level": "R3",         # R1保本 ~ R5激进
        "type": "混合型基金",
        "min_purchase": 1000.0,     # 最低申购金额（元）
        "manager": "张三",
        "management_fee": 0.015,    # 年管理费率 1.5%
        "established_date": "2018-06-01",
    }
```

#### A2. `query_fund_nav` — 查基金净值

```python
@tool
def query_fund_nav(fund_code, date=None):
    """
    查询基金单位净值（NAV）和累计净值。
    fund_code: 基金代码。
    date: 查询日期 YYYY-MM-DD，不填返回最新净值。

    适用于：用户询问基金当前价格，或计算持仓市值。
    """
    return {
        "fund_code": fund_code,
        "nav": 1.2345,
        "cumulative_nav": 2.3456,
        "date": "2026-04-03",
        "change_rate": 0.0023,      # 今日涨跌幅
    }
```

#### A3. `query_market_data` — 查市场行情

```python
@tool
def query_market_data(index_codes, period="1d"):
    """
    查询市场指数行情数据：涨跌幅、成交量、历史走势。
    index_codes: 指数代码列表，如 ['000001'（上证）, '399001'（深证）]。
    period: 时间周期，'1d'日、'1w'周、'1m'月、'3m'季、'1y'年。

    适用于：分析当前市场环境，判断是否适合推荐某类产品，
    或回答用户关于市场表现的问题。
    注意：返回市场整体数据，不是个股或基金数据。
    """
    return {
        "000001": {
            "name": "上证指数",
            "current": 3200.5,
            "change_rate": 0.012,
            "period_return": {"1d": 0.012, "1m": -0.025, "1y": 0.08},
        },
        "as_of": "2026-04-03 15:00:00",
    }
```

---

### 分类 B：客户信息查询

#### B1. `query_client_risk_profile` — 查客户风险等级（最重要）

```python
@tool
def query_client_risk_profile(client_id):
    """
    查询客户风险承受能力等级，这是生成任何投资建议的前提条件。
    必须在推荐任何产品之前调用此工具。
    client_id: 客户唯一标识。

    风险等级对应关系（客户等级 → 可购买产品最高风险等级）：
    C1 保守型   → 只能买 R1
    C2 稳健型   → 可买 R1-R2
    C3 平衡型   → 可买 R1-R3
    C4 成长型   → 可买 R1-R4
    C5 激进型   → 可买 R1-R5

    若返回 is_expired=True，说明风险评测已过期（超过1年），
    此时不得推荐 R3 以上产品，需提示客户重新评测。
    """
    return {
        "client_id": client_id,
        "risk_level": "C3",
        "risk_label": "平衡型",
        "score": 65,
        "valid_until": "2027-01-15",
        "is_expired": False,
    }
```

#### B2. `query_client_holdings` — 查客户当前持仓

```python
@tool
def query_client_holdings(client_id):
    """
    查询客户当前投资持仓：持仓产品、数量、成本、当前市值、收益率。
    client_id: 客户唯一标识。

    适用于：分析客户当前资产配置，在推荐新产品时避免过度集中风险。
    在生成再平衡建议时必须先调用此工具。
    """
    return {
        "client_id": client_id,
        "holdings": [
            {
                "product_code": "000001",
                "product_name": "某某基金",
                "shares": 10000.0,
                "cost_nav": 1.1,
                "current_nav": 1.2345,
                "market_value": 12345.0,
                "return_rate": 0.1223,
            }
        ],
        "total_market_value": 12345.0,
        "total_return_rate": 0.0823,
    }
```

#### B3. `query_client_trade_history` — 查客户交易历史

```python
@tool
def query_client_trade_history(client_id, days=90):
    """
    查询客户最近的申购、赎回交易记录。
    client_id: 客户唯一标识。
    days: 最近多少天的记录，默认90天，最大365天。

    适用于：了解客户投资习惯，判断是否有频繁交易风险，
    或回答客户关于历史交易的问题。
    """
    return {"client_id": client_id, "trades": [], "total_count": 0}
```

---

### 分类 C：合规检查工具（最关键）

**这类工具的结果会直接决定 Agent 流程走向，合规节点必须串行执行。**

#### C1. `check_product_suitability` — 适当性检查

```python
@tool
def check_product_suitability(client_id, product_code):
    """
    执行产品适当性检查（合规强制要求）：验证产品风险等级是否匹配客户承受能力。
    根据《证券期货投资者适当性管理办法》，向投资者推荐产品前必须执行此检查。
    client_id: 客户唯一标识。
    product_code: 待推荐产品代码。

    若返回 is_suitable=False，则不得向该客户推荐此产品，
    必须改为推荐更低风险等级产品，或向客户说明原因。
    此工具的检查结果会被记录到合规审计系统。
    """
    # 实现：查客户风险等级，查产品风险等级，按规则比对
    return {
        "is_suitable": True,
        "client_risk_level": "C3",
        "product_risk_level": "R3",
        "reason": "产品风险等级与客户承受能力匹配",
        "alternative_products": [],
        "check_id": "CHK_20260403_001",     # 审计追踪用
    }
```

#### C2. `check_position_limit` — 仓位限制检查

```python
@tool
def check_position_limit(client_id, product_code, purchase_amount):
    """
    检查购买金额是否超出单一产品仓位限制（单一资产不超过总资产30%）。
    在确认任何申购建议之前必须调用此工具。
    client_id: 客户唯一标识。
    product_code: 拟申购产品代码。
    purchase_amount: 拟申购金额（元）。
    """
    return {
        "is_within_limit": True,
        "current_ratio": 0.15,          # 当前该产品占总资产比例
        "limit": 0.30,
        "after_purchase_ratio": 0.22,
        "message": "购买后仓位比例为22%，符合要求",
    }
```

#### C3. `check_special_restrictions` — 特殊限制检查

```python
@tool
def check_special_restrictions(client_id, product_code):
    """
    检查是否存在特殊监管限制：
    - 产品是否处于封闭期（无法申购/赎回）
    - 客户是否被监管限制交易
    - 产品是否有特殊销售限制（仅限机构、仅限高净值客户等）
    - 是否存在内部控制限制（内部人员禁止交易相关产品）
    client_id: 客户唯一标识。
    product_code: 产品代码。
    此检查覆盖普通适当性检查未覆盖的场景，必须与适当性检查配合使用。
    """
    return {
        "has_restrictions": False,
        "restrictions": [],
    }
```

---

### 分类 D：分析计算工具

#### D1. `calculate_portfolio_risk` — 计算组合风险

```python
@tool
def calculate_portfolio_risk(holdings, time_horizon_days=250):
    """
    计算投资组合风险指标：年化波动率、VaR（在险价值）、夏普比率、最大回撤。
    holdings: 持仓列表，每项为 {"product_code": "xxx", "weight": 0.4}，weight 为权重（0-1）。
    time_horizon_days: 风险计算时间窗口（交易日数），默认250（约1年）。

    适用于：向客户展示组合风险，或比较不同组合方案的风险收益特征。
    注意：输入的 holdings 是拟投资的组合，不是当前持仓。
    """
    return {
        "volatility_annual": 0.12,      # 年化波动率12%
        "var_95_1day": 0.018,           # 95%置信度1日VaR
        "sharpe_ratio": 0.85,
        "max_drawdown": 0.15,
        "risk_level_estimated": "中风险",
    }
```

#### D2. `generate_asset_allocation` — 生成资产配置方案

```python
@tool
def generate_asset_allocation(client_risk_level, investment_amount, investment_horizon_months):
    """
    基于客户风险等级和投资目标，生成标准资产配置方案（股/债/货币比例）。
    client_risk_level: 从 query_client_risk_profile 获取的风险等级（C1-C5）。
    investment_amount: 投资金额（元）。
    investment_horizon_months: 投资期限（月）。

    注意：此工具只给出配置框架（各类资产比例），不是具体产品推荐。
    具体产品推荐还需经过 check_product_suitability 检查。
    """
    templates = {
        "C1": {"bond": 0.70, "money_market": 0.30, "equity": 0.00},
        "C2": {"bond": 0.60, "money_market": 0.20, "equity": 0.20},
        "C3": {"bond": 0.40, "money_market": 0.10, "equity": 0.50},
        "C4": {"bond": 0.20, "money_market": 0.05, "equity": 0.75},
        "C5": {"bond": 0.10, "money_market": 0.00, "equity": 0.90},
    }
    allocation = templates.get(client_risk_level, templates["C3"])
    return {
        "allocation": allocation,
        "rationale": f"基于{client_risk_level}风险等级和{investment_horizon_months}个月投资期限",
        "rebalance_frequency": "季度",
    }
```

---

### 分类 E：RAG 知识库查询

#### E1. `search_product_prospectus` — 搜索产品说明书

```python
@tool
def search_product_prospectus(query, product_code=None):
    """
    在产品说明书、基金合同等文件库中搜索相关信息。
    query: 查询问题，如"赎回费是多少"、"分红政策"。
    product_code: 指定产品代码（可选），不填则全库搜索。

    适用于：回答客户关于产品细节的问题（费率条款、赎回规则、分红政策等）。
    重要：对于涉及具体数字（费率、期限、收益率）的问题，必须用此工具查文档，
    不要凭记忆回答，避免给出错误信息。
    """
    # 实现：向量相似度搜索 + 返回相关文档片段
    return [
        {
            "source": "000001_基金合同_2024.pdf",
            "page": 15,
            "content": "赎回费：持有7天以内1.5%；持有7-30天0.5%；持有30天以上0%",
            "score": 0.92,
        }
    ]
```

#### E2. `search_investment_knowledge` — 搜索投资教育内容

```python
@tool
def search_investment_knowledge(query):
    """
    在投资者教育知识库中搜索相关内容。
    query: 查询问题，如"什么是ETF"、"可转债有什么风险"。

    适用于：解释金融概念，或回答投资常识问题。
    对于监管要求必须告知客户的风险提示，也从此知识库中获取标准措辞。
    """
    return []
```

---

### 分类 F：风险提示生成

#### F1. `generate_risk_warning` — 生成合规风险提示

```python
@tool
def generate_risk_warning(product_risk_level):
    """
    生成符合监管要求的标准风险提示语。
    product_risk_level: 产品风险等级，R1/R2/R3/R4/R5。

    在向客户推荐任何产品时，必须附上此工具生成的风险提示，
    不得省略，不得自行改写措辞（合规部门已审批）。
    """
    templates = {
        "R1": "本产品为保本型低风险产品，收益率可能低于通货膨胀率，请充分了解产品特征后再投资。",
        "R2": "本产品存在一定投资风险，历史业绩不代表未来表现，投资须谨慎。",
        "R3": "本产品风险适中，市值可能波动，请根据自身风险承受能力审慎投资。投资有风险，入市需谨慎。",
        "R4": "本产品为较高风险产品，可能发生较大亏损，仅适合具有相应风险承受能力的投资者。",
        "R5": "本产品为高风险产品，可能发生重大亏损甚至损失全部本金，请充分评估自身风险承受能力。",
    }
    return templates.get(product_risk_level, templates["R3"])
```

---

## 三、工具注册汇总

```python
# src/domains/agent/tools/__init__.py

from .product import query_product_info, query_fund_nav, query_market_data
from .client import query_client_risk_profile, query_client_holdings, query_client_trade_history
from .compliance import check_product_suitability, check_position_limit, check_special_restrictions
from .analysis import calculate_portfolio_risk, generate_asset_allocation
from .rag import search_product_prospectus, search_investment_knowledge
from .output import generate_risk_warning

ALL_TOOLS = [
    query_product_info,
    query_fund_nav,
    query_market_data,
    query_client_risk_profile,
    query_client_holdings,
    query_client_trade_history,
    check_product_suitability,
    check_position_limit,
    check_special_restrictions,
    calculate_portfolio_risk,
    generate_asset_allocation,
    search_product_prospectus,
    search_investment_knowledge,
    generate_risk_warning,
]
```

---

## 四、目录结构

```
src/domains/agent/tools/
├── __init__.py       ← 注册所有工具
├── product.py        ← A 类：产品查询
├── client.py         ← B 类：客户查询
├── compliance.py     ← C 类：合规检查（最重要）
├── analysis.py       ← D 类：分析计算
├── rag.py            ← E 类：知识库搜索
└── output.py         ← F 类：输出生成
```

---

## 五、关键设计提醒

1. **合规工具的 docstring 要有强制性语气**：写"必须在推荐前调用"，大模型会认真遵守。

2. **不要让大模型猜参数**：在 docstring 里说清楚参数从哪里来（如"从当前会话上下文获取"）。

3. **工具出错不要抛异常**：用 try/except 捕获，返回带 `error` 字段的 dict，让大模型知道发生了什么，而不是让整个 Agent 崩掉。

4. **合规检查结果要包含 check_id**：每次合规检查生成唯一 ID，用于事后的监管报告查询。
