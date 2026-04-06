# 第一课：LLM 和工具调用的本质

> 一切 Agent 技术的地基。不理解这个，后面所有东西都是魔法。

---

## 你已经知道的：HTTP 请求/响应

你每天写 Starlette，对这个流程闭着眼睛都会：

```
客户端                        你的 Starlette 服务
   │                                 │
   │ ── POST /api/login ──────────► │
   │    {"username": "tom",          │  view 函数处理
   │     "password": "123"}         │
   │                                 │
   │ ◄── 200 OK ─────────────────── │
   │    {"token": "eyJ..."}         │
```

**LLM 的调用和这个几乎一模一样。** 它也是一个 HTTP 服务，你发请求，它返回响应。

---

## LLM API 调用：也是 HTTP 请求

```python
import httpx

# 你平时调外部 API
response = httpx.post(
    "https://api.anthropic.com/v1/messages",
    headers={"x-api-key": "sk-ant-..."},
    json={
        "model": "claude-3-5-sonnet-20241022",
        "messages": [
            {"role": "user", "content": "帮我查一下基金000001的净值"}
        ]
    }
)

print(response.json()["content"][0]["text"])
# 输出：好的，基金000001... （纯文字，它没真的查过）
```

这和你调一个天气 API 没有任何本质区别。只不过返回的是文字，不是结构化数据。

**问题来了：返回的是文字，它没法真正去查数据库。**

---

## 工具调用：给 LLM 加一个"特殊能力"

工具调用（Tool Call / Function Call）的核心想法是：

> 告诉 LLM："你有这些工具可以用。如果你需要查数据，不要自己编造，
> 告诉我你要调用哪个工具、传什么参数，我来执行，再把结果给你。"

### 实际发生了什么（底层）

**第一次请求：你发工具定义给 LLM**

```python
response = httpx.post(
    "https://api.anthropic.com/v1/messages",
    headers={"x-api-key": "sk-ant-..."},
    json={
        "model": "claude-3-5-sonnet-20241022",
        "messages": [
            {"role": "user", "content": "帮我查一下基金000001的净值"}
        ],
        # 重点：把工具的"说明书"发过去
        "tools": [
            {
                "name": "query_fund_nav",
                "description": "查询基金当前净值。fund_code: 基金代码",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "fund_code": {"type": "string"}
                    },
                    "required": ["fund_code"]
                }
            }
        ]
    }
)
```

**LLM 的回复不再是文字，而是：**

```json
{
  "stop_reason": "tool_use",
  "content": [
    {
      "type": "tool_use",
      "id": "toolu_01abc",
      "name": "query_fund_nav",
      "input": {"fund_code": "000001"}
    }
  ]
}
```

LLM 说："我不自己编，我要调用 `query_fund_nav`，参数是 `{'fund_code': '000001'}`"。

**你的代码收到这个，真正去执行这个函数：**

```python
def query_fund_nav(fund_code):
    # 真正查数据库
    return {"nav": 1.2345, "date": "2026-04-03"}

result = query_fund_nav("000001")
```

**第二次请求：把执行结果发回给 LLM**

```python
response2 = httpx.post(
    "https://api.anthropic.com/v1/messages",
    json={
        "model": "claude-3-5-sonnet-20241022",
        "messages": [
            {"role": "user", "content": "帮我查一下基金000001的净值"},
            # 第一次 LLM 的回复（它说要调用工具）
            {"role": "assistant", "content": [{"type": "tool_use", "id": "toulu_01abc", "name": "query_fund_nav", "input": {"fund_code": "000001"}}]},
            # 工具的执行结果
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_01abc", "content": '{"nav": 1.2345, "date": "2026-04-03"}'}]}
        ]
    }
)

print(response2.json()["content"][0]["text"])
# 输出：基金000001的当前净值为 1.2345，数据日期是2026年4月3日。
```

---

## 类比总结：LLM 工具调用 ≈ 你调外部 API

| 你熟悉的 | LLM 工具调用 |
|---------|------------|
| `httpx.post(url, json=data)` | LLM API 调用 |
| 请求体里的 JSON 数据 | 发给 LLM 的消息列表 |
| API 返回 `{"action": "redirect", "url": "..."}` | LLM 返回 `{"type": "tool_use", "name": "...", "input": {...}}` |
| 你解析返回值，决定下一步 | 你解析 tool_use，执行对应函数 |
| 把执行结果再发出去 | 把 tool_result 再发给 LLM |

**LLM 本质上是一个协议解析器：** 它读消息历史，输出"下一步该做什么"——要么是文字回复，要么是工具调用。你负责执行它说的工具，再把结果塞回消息历史。

---

## LangChain 帮你做了什么

上面的手工操作很繁琐。LangChain 的 `@tool` + `bind_tools` 帮你把这些封装掉了：

```python
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic

# LangChain 自动把函数转成 JSON Schema 告诉 LLM
@tool
def query_fund_nav(fund_code):
    """查询基金当前净值。fund_code: 基金代码。"""
    return {"nav": 1.2345, "date": "2026-04-03"}

llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")
llm_with_tools = llm.bind_tools([query_fund_nav])

# 一次调用，LangChain 帮你搞定 JSON Schema 序列化
response = llm_with_tools.invoke([HumanMessage(content="查一下000001的净值")])

# 如果 LLM 要调工具，response.tool_calls 里有
print(response.tool_calls)
# [{"name": "query_fund_nav", "args": {"fund_code": "000001"}, "id": "toulu_01abc"}]
```

你只需要写 Python 函数 + docstring，LangChain 负责把它翻译成 LLM 能理解的 JSON 格式。

---

## 一个关键细节：LLM 怎么"决定"调哪个工具

LLM 没有什么神奇的决策能力。它做的事是：

1. 读取你发过来的所有工具的 `description` 和 `input_schema`
2. 根据用户的问题，判断哪个工具最匹配
3. 输出一个 JSON 格式的"调用指令"

**所以 docstring 写得好不好，直接决定 LLM 知不知道该用这个工具。**

```python
# 坏的 docstring：LLM 不知道什么时候用
@tool
def get_info(code):
    """获取信息。"""
    ...

# 好的 docstring：LLM 清楚地知道什么时候用、参数是什么
@tool
def query_fund_nav(fund_code):
    """
    查询基金的当前单位净值（NAV）。
    在推荐基金产品前必须先用此工具确认当前价格。
    fund_code: 基金代码，如 '000001'、'110011'。
    """
    ...
```

---

## 小结

```
你发给 LLM：
  - 用户消息
  - 工具的"说明书"（name + description + input_schema）

LLM 返回：
  - 文字回复（stop_reason = end_turn）
  - 或：工具调用指令（stop_reason = tool_use）

你执行工具，把结果塞回消息历史，再问 LLM 下一步

这就是 Agent 的全部秘密。
```

下一课：[02 - AgentLoop：这个过程怎么循环起来](./02-agent-loop.md)
