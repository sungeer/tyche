# 第二课：AgentLoop — 让 LLM 反复思考直到完成任务

> 上一课你看到了一次 LLM 调用 + 一次工具执行。
> 但现实中一个任务往往需要多步骤。这节课讲怎么把它循环起来。

---

## 你已经知道的：Starlette 中间件链

你的 Starlette 请求进来，经过一层层处理：

```
请求进来
   │
   ▼
CORS 中间件（检查来源）
   │
   ▼
JWT 认证中间件（验证 token）
   │
   ▼
路由 → view 函数（真正的业务逻辑）
   │
   ▼
返回响应
```

每一层要么"放行"，要么"拦截"，直到最终完成。

**AgentLoop 和这个类似，只不过每一轮循环都是"LLM 思考一步 → 执行一步 → 再思考"。**

---

## AgentLoop 是什么

最简单的说法：

```python
while True:
    response = llm.invoke(messages)    # LLM 思考
    
    if response.stop_reason == "end_turn":
        break                           # 任务完成，退出
    
    # LLM 说要调工具，执行工具
    tool_result = execute_tool(response.tool_calls[0])
    messages.append(tool_result)        # 把结果加回消息历史
    # 继续循环，再问 LLM 下一步
```

这就是 ReAct 模式（**Re**asoning + **Act**ing）的全部秘密。
LLM 每次要么"行动"（调工具），要么"结束"（任务完成）。

---

## 手写一个完整的 AgentLoop

假设你要查一支基金的净值，顺便检查一下合规性：

```python
import httpx
import json

API_KEY = "sk-ant-..."
BASE_URL = "https://api.anthropic.com/v1/messages"

# 模拟工具函数（真实环境里你会查数据库）
def query_fund_nav(fund_code):
    return {"nav": 1.2345, "date": "2026-04-03"}

def check_product_suitability(client_id, product_code):
    return {"is_suitable": True, "reason": "产品风险等级与客户匹配"}

# 工具清单（告诉 LLM 有哪些工具可以用）
TOOLS = [
    {
        "name": "query_fund_nav",
        "description": "查询基金当前单位净值",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码"}
            },
            "required": ["fund_code"]
        }
    },
    {
        "name": "check_product_suitability",
        "description": "检查产品是否适合客户风险等级",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "product_code": {"type": "string"}
            },
            "required": ["client_id", "product_code"]
        }
    }
]

# 工具名 → 函数 的映射
TOOL_MAP = {
    "query_fund_nav": query_fund_nav,
    "check_product_suitability": check_product_suitability,
}


def agent_loop(user_message):
    """
    完整的 AgentLoop：
    1. 带着工具定义问 LLM
    2. LLM 说要调哪个工具，我们执行
    3. 把结果塞回消息，继续问 LLM
    4. 直到 LLM 说任务完成
    """
    messages = [{"role": "user", "content": user_message}]
    
    max_rounds = 5  # 防止无限循环（LLM 出 bug 时的保险）
    
    for round_num in range(max_rounds):
        print(f"\n── 第 {round_num + 1} 轮 ──")
        
        # 问 LLM
        response = httpx.post(
            BASE_URL,
            headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01"},
            json={
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 1024,
                "tools": TOOLS,
                "messages": messages,
            }
        ).json()
        
        stop_reason = response["stop_reason"]
        print(f"stop_reason: {stop_reason}")
        
        # 把 LLM 的回复加入消息历史
        messages.append({"role": "assistant", "content": response["content"]})
        
        # 任务完成
        if stop_reason == "end_turn":
            # 从 content 里找文字内容
            for block in response["content"]:
                if block["type"] == "text":
                    return block["text"]
            return "完成"
        
        # LLM 要调工具
        if stop_reason == "tool_use":
            tool_results = []
            
            for block in response["content"]:
                if block["type"] == "tool_use":
                    tool_name = block["name"]
                    tool_args = block["input"]
                    tool_use_id = block["id"]
                    
                    print(f"执行工具: {tool_name}({tool_args})")
                    
                    # 找到对应的函数并执行
                    fn = TOOL_MAP.get(tool_name)
                    if fn:
                        result = fn(**tool_args)
                    else:
                        result = {"error": f"工具 {tool_name} 不存在"}
                    
                    print(f"工具结果: {result}")
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(result, ensure_ascii=False)
                    })
            
            # 把工具执行结果塞回消息历史
            messages.append({"role": "user", "content": tool_results})
            # 继续下一轮循环，再问 LLM
    
    return "达到最大轮次，任务未完成"


# 运行
result = agent_loop("帮我查一下基金000001的净值，并检查客户C001是否可以购买")
print(f"\n最终回答：{result}")
```

**运行后会打印：**

```
── 第 1 轮 ──
stop_reason: tool_use
执行工具: query_fund_nav({'fund_code': '000001'})
工具结果: {'nav': 1.2345, 'date': '2026-04-03'}

── 第 2 轮 ──
stop_reason: tool_use
执行工具: check_product_suitability({'client_id': 'C001', 'product_code': '000001'})
工具结果: {'is_suitable': True, 'reason': '产品风险等级与客户匹配'}

── 第 3 轮 ──
stop_reason: end_turn

最终回答：基金000001的当前净值为1.2345（截至2026年4月3日）。
经合规检查，该产品适合客户C001购买，风险等级匹配。
```

---

## 类比：AgentLoop ≈ Starlette 请求处理链

| Starlette | AgentLoop |
|-----------|-----------|
| 请求进来，开始处理 | 用户消息进来，开始循环 |
| 中间件逐层放行 | LLM 逐步决定下一个工具 |
| `await call_next(request)` 传递给下一层 | 工具结果塞进 `messages` 传给下一轮 |
| 最后 view 函数返回响应 | `end_turn` 时返回最终文字 |
| `max_retries` 防死循环 | `max_rounds = 5` 防死循环 |

**核心共同点：都是"逐步处理，完成才结束"的流程控制。**

---

## LangChain 帮你把这个循环封装了

上面那个手写循环，LangChain 和 LangGraph 会帮你做掉。

### LangChain AgentExecutor（旧方式，理解原理用）

```python
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, ToolMessage

@tool
def query_fund_nav(fund_code):
    """查询基金当前单位净值。fund_code: 基金代码。"""
    return {"nav": 1.2345, "date": "2026-04-03"}

@tool
def check_product_suitability(client_id, product_code):
    """检查产品是否适合客户。client_id: 客户ID。product_code: 产品代码。"""
    return {"is_suitable": True}

llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)
llm_with_tools = llm.bind_tools([query_fund_nav, check_product_suitability])

# 手动实现 AgentLoop（LangGraph 会帮你做这个）
messages = [HumanMessage(content="查000001净值并检查客户C001能否购买")]

while True:
    response = llm_with_tools.invoke(messages)
    messages.append(response)
    
    if not response.tool_calls:
        print(response.content)
        break
    
    for tc in response.tool_calls:
        fn_map = {
            "query_fund_nav": query_fund_nav,
            "check_product_suitability": check_product_suitability,
        }
        result = fn_map[tc["name"]].invoke(tc["args"])
        messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
```

这和上面的手写版本逻辑完全一样，只是用了 LangChain 的 `@tool` 和 `bind_tools` 封装了 JSON Schema 那部分。

---

## 关键问题：最大轮次为什么重要

不加限制的 `while True` 很危险。考虑这种情况：

```
用户："帮我查基金000001"

第1轮：LLM 调 query_fund_nav("000001")
第2轮：LLM 说要再调一次 query_fund_nav("000001")（它可能陷入"确认"循环）
第3轮：...
第N轮：你的钱包空了，API 费用耗尽
```

所以 **必须加 `max_rounds`**，通常 5-10 步足够一个合理任务。

```python
for round_num in range(10):   # 最多 10 轮
    ...
    if stop_reason == "end_turn":
        break
else:
    # for 循环正常结束（没有 break），说明超出轮次
    raise RuntimeError("Agent 超出最大步数，可能陷入循环")
```

---

## 小结

```
AgentLoop 本质是一个 while 循环：

while True:
    response = 问 LLM（带工具定义）
    
    if LLM 说完了（end_turn）:
        return 最终回答
    
    if LLM 要调工具（tool_use）:
        result = 执行工具函数
        把 result 追加到 messages
        继续循环
```

**消息历史（messages）是 AgentLoop 的"短期记忆"。**
每一轮，LLM 都能看到所有历史，知道自己做了什么，还差什么。

下一课：[03 - LangGraph State：用图来控制这个循环](./03-langgraph-state.md)
