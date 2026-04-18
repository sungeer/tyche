"""工具链管理器
Agents 工具链式调用支持
"""

from typing import List, Dict, Any, Optional

from src.agents.tools.registry import ToolRegistry


# 工具链 支持多个工具的顺序执行
class ToolChain:

    def __init__(self, name, description):
        self.name = name  # str
        self.description = description  # str
        self.steps = []

    # 添加 工具执行 步骤
    def add_step(self, tool_name, input_template, output_key=None):
        """
        Args:
            tool_name: 工具名称 str
            input_template: 输入模板，支持变量替换，如 '{input}' 或 '{search_result}'
            output_key: 输出结果的键名，用于后续步骤引用 str
        """
        step = {
            'tool_name': tool_name,
            'input_template': input_template,
            'output_key': output_key or f'step_{len(self.steps)}_result'
        }
        self.steps.append(step)
        print(f'工具链 [{self.name}] 添加步骤: {tool_name}')

    # 执行 工具链
    def execute(self, registry, input_data, context=None):
        """
        Args:
            registry: 工具注册表 ToolRegistry
            input_data: 初始输入数据 str
            context: 执行上下文，用于变量替换 dict

        Returns:
            最终执行结果 str
        """
        if not self.steps:
            return '工具链为空，无法执行'

        print(f'开始执行工具链 [{self.name}]')

        # 初始化 上下文
        if context is None:
            context = {}
        context['input'] = input_data

        for i, step in enumerate(self.steps, 1):
            tool_name = step['tool_name']
            input_template = step['input_template']
            output_key = step['output_key']

            print(f'执行步骤 {i}/{len(self.steps)}: {tool_name}')

            # 替换 模板中的变量
            try:
                actual_input = input_template.format(**context)
            except KeyError as e:
                return f'模板变量替换失败: {e}'

            # 执行工具
            try:
                result = registry.execute_tool(tool_name, actual_input)
                context[output_key] = result
                print(f'步骤 {i} 完成')
            except Exception as e:
                return f'工具 [{tool_name}] 执行失败: {e}'

        # 返回 最后一步 的结果
        final_result = context[self.steps[-1]['output_key']]
        print(f'工具链 [{self.name}] 执行完成')
        return final_result


# 工具链 管理器
class ToolChainManager:

    def __init__(self, registry):
        self.registry = registry  # ToolRegistry
        self.chains = {}  # ToolChain

    # 注册 工具链
    def register_chain(self, chain):
        self.chains[chain.name] = chain  # ToolChain
        print(f'工具链 [{chain.name}] 已注册')

    # 执行 指定的 工具链
    def execute_chain(self, chain_name, input_data, context=None):
        if chain_name not in self.chains:
            return f'工具链 [{chain_name}] 不存在'
        chain = self.chains[chain_name]
        return chain.execute(self.registry, input_data, context)  # str

    # 列出 所有 已注册的工具链
    def list_chains(self):
        return list(self.chains.keys())

    # 获取 工具链信息
    def get_chain_info(self, chain_name):
        if chain_name not in self.chains:
            return None
        chain = self.chains[chain_name]
        return {
            'name': chain.name,
            'description': chain.description,
            'steps': len(chain.steps),
            'step_details': [
                {
                    'tool_name': step['tool_name'],
                    'input_template': step['input_template'],
                    'output_key': step['output_key']
                }
                for step in chain.steps
            ]
        }


# 便捷函数
def create_research_chain():
    """创建一个研究工具链：搜索 -> 计算 -> 总结"""
    chain = ToolChain(
        name='research_and_calculate',
        description='搜索信息并进行相关计算'
    )

    # 步骤1：搜索信息
    chain.add_step(
        tool_name='search',
        input_template='{input}',
        output_key='search_result'
    )

    # 步骤2：基于搜索结果进行计算
    chain.add_step(
        tool_name='my_calculator',
        input_template='2 + 2',  # 简单的计算示例
        output_key='calc_result'
    )

    return chain  # ToolChain


def create_simple_chain() -> ToolChain:
    """创建一个简单的工具链示例"""
    chain = ToolChain(
        name='simple_demo',
        description='简单的工具链演示'
    )

    # 只包含一个计算步骤
    chain.add_step(
        tool_name='my_calculator',
        input_template='{input}',
        output_key='result'
    )

    return chain
