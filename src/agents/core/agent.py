"""Agent 基类"""

from abc import ABC, abstractmethod

from src.core.config import settings
from src.agents.core.message import Message
from src.agents.core.llm import AgentsLLM


class Agent(ABC):

    def __init__(self, name, llm, system_prompt=None, config=None):
        self.name = name  # str
        self.llm = llm  # LLM 实例
        self.system_prompt = system_prompt  # 系统提示词 str
        self.config = config or settings
        self._history = []  # 消息 历史记录

    # 运行 Agent
    @abstractmethod
    def run(self, input_text: str, **kwargs) -> str:
        pass

    # 添加 消息到 历史记录
    def add_message(self, message: Message):
        self._history.append(message)

    # 清空 历史记录
    def clear_history(self):
        self._history.clear()

    # 获取 历史记录
    def get_history(self):
        return self._history.copy()
