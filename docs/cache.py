import sys
import io

# 设置 UTF-8 编码，避免 Windows 终端中文乱码
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import os
from typing import TypedDict, Annotated, Literal, Any
from dotenv import load_dotenv
# LangChain 核心组件：消息类型、工具装饰器
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
# Ollama 本地模型接入
from langchain_ollama import ChatOllama
# LangGraph 图构建核心：状态图、起点终点、消息累加器
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
# Command API：用于节点间动态路由
from langgraph.types import Command
# Pydantic：定义结构化输出模型
from pydantic import BaseModel, Field

# 加载 .env 环境变量（OLLAMA_MODEL、OLLAMA_BASE_URL 等）
load_dotenv()
# ============================================================
# 配置
# ============================================================
# 从环境变量读取模型配置，默认使用 qwen3:4b
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen3:4b")
# Ollama 服务地址，默认本地 11434 端口
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# 创建基础 LLM 实例（Supervisor 用，不绑定工具）
llm = ChatOllama(model=MODEL_NAME, base_url=OLLAMA_BASE_URL, temperature=0)


# ============================================================
# 一、State 定义
# ============================================================
class AgentState(TypedDict):
    """
    Supervisor 多 Agent 共享状态
    messages:     消息历史（Annotated + add_messages 自动合并，避免并发覆盖）
    next:         Supervisor 决策的下一个执行节点名
    task_results: 各 Worker 的输出结果 {worker_name: result_text}
    """
    # Annotated 标记：使用 add_messages 函数自动合并消息列表
    messages: Annotated[list, add_messages]
    # 下一个要执行的 Worker 名称
    next: str
    # 存储各 Worker 的执行结果，用于 Worker 间信息共享
    task_results: dict


# ============================================================
# 二、Supervisor 路由输出结构（结构化输出）
# ============================================================
# 定义可用的 Worker 列表
WORKERS = ["researcher", "coder", "reviewer"]


class RouterDecision(BaseModel):
    """
    Supervisor 的路由决策
    LLM 以结构化格式输出，避免解析错误
    """
    # Literal 限制输出只能是这几个值之一
    next: Literal["researcher", "coder", "reviewer", "FINISH"] = Field(
        description="下一个要执行的 Worker 名称，或 FINISH 表示任务完成"
    )
    # 决策理由，用于调试和可解释性
    reasoning: str = Field(
        description="选择该 Worker 的理由（调试用）"
    )


# 给 LLM 绑定结构化输出格式，Supervisor 调用时会返回 RouterDecision 对象
llm_router = llm.with_structured_output(RouterDecision)


# ============================================================
# 三、Tools（各 Worker 的工具集）
# ============================================================
@tool("search_knowledge_base")
def search_knowledge_base(query: str) -> str:
    """
    搜索知识库，返回相关文档片段
    参数：query - 搜索关键词或问题
    """
    # 模拟知识库检索（生产环境替换为 Chroma / BM25 混合检索）
    knowledge = {
        "python": "Python 是一种解释型高级编程语言，由 Guido van Rossum 于 1991 年创建。",
        "排序": "常用排序算法：冒泡排序 O(n²)、快速排序 O(n log n)、归并排序 O(n log n)。",
        "异步": "Python 异步编程使用 asyncio 库，async/await 语法，适用于 I/O 密集型任务。",
        "agent": "Agent 是一种能够感知环境、做出决策并执行行动的 AI 系统。",
        "langgraph": "LangGraph 是 LangChain 团队开发的 Agent 编排框架，基于 StateGraph。",
        "default": f"未找到 '{query}' 的直接匹配，建议补充相关文档。"
    }
    # 简单的关键词匹配
    for keyword, content in knowledge.items():
        if keyword.lower() in query.lower():
            return f"[知识库检索结果] {content}"
    return knowledge["default"]


@tool("execute_code")
def execute_code(code: str) -> str:
    """
    执行 Python 代码片段，返回执行结果
    参数：code - Python 代码字符串
    """
    # 安全沙箱（生产环境需要更严格的隔离，如 Docker）
    import io as _io
    import traceback
    # 捕获标准输出
    stdout_capture = _io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_capture
    result = ""
    try:
        # 创建独立的执行环境，避免污染全局命名空间
        exec_globals: dict[str, Any] = {}
        exec(code, exec_globals)
        result = stdout_capture.getvalue() or "[代码执行成功，无输出]"
    except Exception:
        result = f"[执行错误]\n{traceback.format_exc()}"
    finally:
        # 恢复标准输出
        sys.stdout = old_stdout
    return result


@tool("review_content")
def review_content(content: str) -> str:
    """
    审查内容质量，返回审查意见
    参数：content - 需要审查的代码或文档
    """
    # 模拟审查逻辑，检查常见问题
    issues = []
    if "TODO" in content or "pass" in content.lower():
        issues.append("存在未完成的 TODO 或空实现")
    if len(content) < 50:
        issues.append("内容过于简短，建议补充细节")
    if not issues:
        return "[审查结果] PASS：内容质量良好，逻辑清晰，无明显问题。"
    return f"[审查结果] 发现 {len(issues)} 个问题：\n" + "\n".join(f"  - {i}" for i in issues)


# ============================================================
# 四、Worker 节点（Sub Agents）
# ============================================================
def _make_worker_llm(tools: list) -> ChatOllama:
    """创建绑定工具的 Worker LLM"""
    return ChatOllama(
        model=MODEL_NAME,
        base_url=OLLAMA_BASE_URL,
        temperature=0
    ).bind_tools(tools)  # 绑定工具，让 LLM 可以调用


def researcher_node(state: AgentState) -> dict:
    """
    Researcher Worker
    职责：搜索知识库，返回相关信息
    """
    print("\n[Researcher] 开始工作...")
    # 创建绑定 search_knowledge_base 工具的 LLM
    worker_llm = _make_worker_llm([search_knowledge_base])
    # 从消息历史中提取最后一条用户输入（HumanMessage）
    last_human = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "请检索相关知识"
    )
    # 系统提示词：定义 Worker 的角色和职责
    system_prompt = (
        "你是一个专业的知识检索员（Researcher）。"
        "你的工作是使用 search_knowledge_base 工具搜索相关信息，"
        "并整理成清晰的摘要返回给团队。"
    )
    # 调用 LLM，传入系统提示和用户任务
    response = worker_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"请检索以下任务所需的知识：{last_human}")
    ])
    # 如果模型调用了工具，执行工具并收集结果
    tool_results = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tc in response.tool_calls:
            if tc['name'] == 'search_knowledge_base':
                # 调用实际工具函数
                result = search_knowledge_base.invoke(tc['args'])
                tool_results.append(result)
                print(f"  [Tool] search_knowledge_base({tc['args']}) -> {result[:60]}...")
    # 优先使用工具结果，否则使用 LLM 的文本回复
    result_text = "\n".join(tool_results) if tool_results else response.content
    print(f"  [Result] {result_text[:100]}...")
    # 返回更新：添加 AI 消息到历史，保存到 task_results
    return {
        "messages": [AIMessage(content=f"[Researcher 输出]\n{result_text}")],
        "task_results": {**state.get("task_results", {}), "researcher": result_text},
    }


def coder_node(state: AgentState) -> dict:
    """
    Coder Worker
    职责：生成代码，并可执行验证
    """
    print("\n[Coder] 开始工作...")
    # 绑定代码执行工具
    worker_llm = _make_worker_llm([execute_code])
    # 提取用户原始任务
    last_human = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "请生成代码"
    )
    system_prompt = (
        "你是一个专业的 Python 开发者（Coder）。"
        "你的工作是根据需求编写高质量的 Python 代码，"
        "必要时使用 execute_code 工具验证代码逻辑。"
        "只输出代码和简短说明，不要废话。"
    )
    response = worker_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"请完成以下编程任务：{last_human}")
    ])
    # 执行工具调用（代码验证）
    tool_results = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tc in response.tool_calls:
            if tc['name'] == 'execute_code':
                result = execute_code.invoke(tc['args'])
                tool_results.append(result)
                print(f"  [Tool] execute_code -> {result[:60]}...")
    # 合并代码输出和执行结果
    result_text = response.content
    if tool_results:
        result_text += "\n[执行验证]\n" + "\n".join(tool_results)
    print(f"  [Result] {result_text[:100]}...")
    return {
        "messages": [AIMessage(content=f"[Coder 输出]\n{result_text}")],
        "task_results": {**state.get("task_results", {}), "coder": result_text},
    }


def reviewer_node(state: AgentState) -> dict:
    """
    Reviewer Worker
    职责：审查代码和输出质量
    """
    print("\n[Reviewer] 开始工作...")
    # 绑定审查工具
    worker_llm = _make_worker_llm([review_content])
    # 收集所有 Worker 的输出作为审查内容
    task_results = state.get("task_results", {})
    content_to_review = "\n\n".join(
        f"=== {k.upper()} 输出 ===\n{v}"
        for k, v in task_results.items()
    ) or "（暂无其他 Worker 的输出，请审查整体任务完成情况）"
    system_prompt = (
        "你是一个严格的代码和内容审查员（Reviewer）。"
        "使用 review_content 工具对以下内容进行质量审查，"
        "指出问题并给出改进建议。"
    )
    response = worker_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"请审查以下内容：\n\n{content_to_review}")
    ])
    # 执行审查工具
    tool_results = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tc in response.tool_calls:
            if tc['name'] == 'review_content':
                result = review_content.invoke(tc['args'])
                tool_results.append(result)
                print(f"  [Tool] review_content -> {result[:60]}...")
    result_text = response.content
    if tool_results:
        result_text += "\n" + "\n".join(tool_results)
    print(f"  [Result] {result_text[:100]}...")
    return {
        "messages": [AIMessage(content=f"[Reviewer 输出]\n{result_text}")],
        "task_results": {**state.get("task_results", {}), "reviewer": result_text},
    }


# ============================================================
# 五、Supervisor 节点（路由决策）
# ============================================================
SUPERVISOR_SYSTEM_PROMPT = """你是一个任务调度 Supervisor。
你手下有三个专业 Worker：
- researcher：负责搜索知识库，获取背景信息
- coder：负责编写和执行 Python 代码
- reviewer：负责审查代码和输出的质量
你的工作流程：
1. 接收用户任务
2. 判断需要哪个 Worker 来处理下一步
3. 当所有必要的工作都完成后，返回 FINISH
决策原则：
- 如果任务需要背景知识 → 先派 researcher
- 如果任务需要代码实现 → 派 coder
- 如果已有代码或内容需要审查 → 派 reviewer
- 如果任务已完整完成 → 返回 FINISH
已完成的工作会在消息历史中体现，避免重复派遣同一个 Worker（除非有充分理由）。
"""


def supervisor_node(state: AgentState) -> Command[Literal["researcher", "coder", "reviewer", "__end__"]]:
    """
    Supervisor 路由决策节点
    - 读取完整消息历史
    - LLM 判断下一步派哪个 Worker
    - 用 Command API 路由
    """
    print(f"\n[Supervisor] 分析任务，已完成: {list(state.get('task_results', {}).keys())}")
    # 组装消息：系统提示 + 历史消息
    messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)] + list(state["messages"])
    # 调用结构化输出 LLM，避免 LLM 输出格式不稳定
    try:
        decision: RouterDecision = llm_router.invoke(messages)
        next_worker = decision.next
        reasoning = decision.reasoning
    except Exception as e:
        print(f"  [WARN] 结构化输出失败，默认 FINISH: {e}")
        next_worker = "FINISH"
        reasoning = "解析异常，安全退出"
    print(f"  [Decision] -> {next_worker}（理由：{reasoning[:60]}）")
    # 路由目标转换：FINISH → __end__（LangGraph 的结束节点标识）
    goto = "__end__" if next_worker == "FINISH" else next_worker
    # Command API：指定下一个跳转节点，并更新状态
    return Command(
        goto=goto,
        update={"next": next_worker}
    )


# ============================================================
# 六、构建 StateGraph
# ============================================================
def build_supervisor_graph(max_iterations: int = 10) -> Any:
    """
    构建 Supervisor 多 Agent 图
    结构：
      START → supervisor
      supervisor → [researcher | coder | reviewer | END]（Command 路由）
      researcher → supervisor（执行完返回 Supervisor）
      coder → supervisor（执行完返回 Supervisor）
      reviewer → supervisor（执行完返回 Supervisor）
    """
    # 创建状态图，状态类型为 AgentState
    graph = StateGraph(AgentState)
    # 添加所有节点：Supervisor + 3 个 Worker
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("coder", coder_node)
    graph.add_node("reviewer", reviewer_node)
    # 设置入口边：从 START 到 supervisor
    graph.add_edge(START, "supervisor")
    # Worker 执行完 → 返回 Supervisor（形成循环）
    graph.add_edge("researcher", "supervisor")
    graph.add_edge("coder", "supervisor")
    graph.add_edge("reviewer", "supervisor")
    # Supervisor 的路由由 Command.goto 动态控制（不需要 add_conditional_edges）
    # 编译图，生成可执行对象
    return graph.compile()


# ============================================================
# 七、演示
# ============================================================
def demo():
    """运行 Supervisor 多 Agent 演示"""
    print("=" * 70)
    print("[Day11-01] LangGraph Multi-Agent Supervisor 演示")
    print("=" * 70)
    # 构建编译后的图
    graph = build_supervisor_graph()
    # 演示任务列表
    tasks = [
        "用 Python 写一个快速排序函数，并做代码审查",
        "查找 Python 异步编程的最佳实践，并给出示例代码",
    ]
    # 遍历执行每个任务
    for i, task in enumerate(tasks, 1):
        print(f"\n{'=' * 70}")
        print(f"[Task {i}] {task}")
        print("=" * 70)
        # 初始化状态：用户消息、空的 next、空的 task_results
        initial_state: AgentState = {
            "messages": [HumanMessage(content=task)],
            "next": "",
            "task_results": {},
        }
        try:
            # 执行图，传入初始状态和递归限制（防止无限循环）
            final_state = graph.invoke(
                initial_state,
                config={"recursion_limit": 5}
            )
            print(f"\n[RESULT] 任务完成！")
            # 显示执行链路（Worker 执行顺序）
            print(f"执行链路: {' -> '.join(final_state.get('task_results', {}).keys())}")
            print("\n各 Worker 输出摘要：")
            # 显示每个 Worker 的输出前 120 字符
            for worker, result in final_state.get("task_results", {}).items():
                print(f"  [{worker.upper()}] {result[:120]}...")
        except Exception as e:
            print(f"\n[ERROR] 任务执行失败: {e}")
            import traceback
            traceback.print_exc()
    print("\n" + "=" * 70)
    print("[DONE] Day11-01 演示完成")
    print("=" * 70)


# 程序入口：直接运行本文件时执行 demo()
if __name__ == "__main__":
    demo()
