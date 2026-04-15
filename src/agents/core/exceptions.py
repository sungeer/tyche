"""异常体系"""


class AgentsError(Exception):
    """Agents 基础异常类"""
    pass


class LLMError(AgentsError):
    """LLM 相关异常"""
    pass


class AgentError(AgentsError):
    """Agent 相关异常"""
    pass


class ConfigError(AgentsError):
    """配置相关异常"""
    pass


class ToolError(AgentsError):
    """工具相关异常"""
    pass
