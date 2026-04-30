import asyncio
import json
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel

client = AsyncOpenAI()  # 默认读取环境变量 OPENAI_API_KEY


# ============================================================
# Schema
# ============================================================

class RouterOutput(BaseModel):
    next: Literal["agent_a", "agent_b", "agent_c"]


# ============================================================
# Tool 定义（OpenAI function calling 格式）
# ============================================================

SEARCH_WEB = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "搜索互联网获取信息",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["query"],
        },
    },
}

CALCULATE = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "执行数学计算",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "合法的数学表达式"}
            },
            "required": ["expression"],
        },
    },
}

QUERY_DATABASE = {
    "type": "function",
    "function": {
        "name": "query_database",
        "description": "查询数据库",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SQL 查询语句"}
            },
            "required": ["sql"],
        },
    },
}


# ============================================================
# Tool 实现（替换成你的真实逻辑）
# ============================================================

async def search_web(query: str) -> str:
    return f"[search_web] '{query}' 的搜索结果：..."


async def calculate(expression: str) -> str:
    try:
        return str(eval(expression))  # 生产环境换成安全的计算库
    except Exception as e:
        return f"计算错误: {e}"


async def query_database(sql: str) -> str:
    return f"[query_database] 执行 '{sql}' 返回若干行..."


TOOL_EXECUTORS = {
    "search_web": search_web,
    "calculate": calculate,
    "query_database": query_database,
}

# ============================================================
# Prompts & Agent 配置
# ============================================================

SUPERVISOR_PROMPT = """\
你是调度 Agent，根据对话内容决定由哪个子 Agent 处理：
- agent_a：网络搜索 + 数学计算
- agent_b：数学计算 + 数据库查询
- agent_c：网络搜索 + 数据库查询
"""

AGENT_CONFIGS = {
    "agent_a": {
        "system": "你是 Agent A，擅长网络搜索和数学计算。",
        "tools": [SEARCH_WEB, CALCULATE],
    },
    "agent_b": {
        "system": "你是 Agent B，擅长数学计算和数据库查询。",
        "tools": [CALCULATE, QUERY_DATABASE],
    },
    "agent_c": {
        "system": "你是 Agent C，擅长网络搜索和数据库查询。",
        "tools": [SEARCH_WEB, QUERY_DATABASE],
    },
}


# ============================================================
# Supervisor：结构化输出做路由
# ============================================================

async def run_supervisor(messages: list[dict]) -> str:
    recent = messages[-6:]
    response = await client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SUPERVISOR_PROMPT},
            *recent,
        ],
        response_format=RouterOutput,
    )
    result: RouterOutput = response.choices[0].message.parsed
    return result.next


# ============================================================
# 子 Agent：标准 ReAct 工具循环
# ============================================================

async def run_agent(agent_name: str, messages: list[dict]) -> list[dict]:
    config = AGENT_CONFIGS[agent_name]

    while True:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": config["system"]}, *messages],
            tools=config["tools"],
            tool_choice="auto",
        )

        assistant_msg = response.choices[0].message

        # 统一转成 dict 追加到 messages（保持消息列表干净）
        msg_dict: dict = {"role": "assistant", "content": assistant_msg.content or ""}
        if assistant_msg.tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_msg.tool_calls
            ]
        messages.append(msg_dict)

        # 没有工具调用 → 本轮结束
        if not assistant_msg.tool_calls:
            break

        # 并发执行所有 tool_calls
        async def exec_one(tc) -> dict:
            name = tc.function.name
            args = json.loads(tc.function.arguments)
            print(f"  [tool] {name}({args})")
            result = await TOOL_EXECUTORS[name](**args)
            return {"role": "tool", "tool_call_id": tc.id, "content": result}

        tool_results = await asyncio.gather(
            *[exec_one(tc) for tc in assistant_msg.tool_calls]
        )
        messages.extend(tool_results)
        # 继续循环，让 LLM 消化工具结果

    return messages


# ============================================================
# 主入口
# ============================================================

async def run_game_graph(user_input: str) -> list[dict]:
    messages = [{"role": "user", "content": user_input}]

    # Step 1：Supervisor 路由
    next_agent = await run_supervisor(messages)
    print(f"[Supervisor] → {next_agent}")

    # Step 2：子 Agent ReAct 循环
    messages = await run_agent(next_agent, messages)

    return messages


# ============================================================
# 运行示例
# ============================================================

async def main():
    result = await run_game_graph("帮我查一下最新的 GPU 价格，再算一下 3090 和 4090 的价格差")
    print("\n=== 对话记录 ===")
    for msg in result:
        role = msg["role"]
        content = msg.get("content", "")
        if content:
            print(f"[{role}]: {content}")


if __name__ == "__main__":
    asyncio.run(main())
