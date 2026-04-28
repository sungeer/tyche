from langchain_core.tools import tool


@tool
def search_web(query: str) -> str:
    """在互联网上搜索最新资讯、新闻、实时数据"""
    # TODO: 接入真实搜索 API，如 Tavily / Bing Search
    return f"[搜索结果] 关键词「{query}」的相关内容：..."


@tool
def calculate(expression: str) -> str:
    """安全地计算数学表达式，支持四则运算"""
    try:
        # 生产环境建议使用 numexpr 替代 eval
        result = eval(expression, {"__builtins__": {}})
        return f"[计算结果] {expression} = {result}"
    except Exception as e:
        return f"[计算错误] {e}"


@tool
def query_database(sql: str) -> str:
    """查询业务数据库，获取订单、用户、库存等结构化数据"""
    # TODO: 接入真实业务数据库
    return f"[数据库查询] SQL: {sql} → 返回结果：..."
