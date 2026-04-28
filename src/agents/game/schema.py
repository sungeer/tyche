from typing import Literal

from pydantic import BaseModel
from langgraph.graph import MessagesState


class GameState(MessagesState):
    next: str


# 结构化输出
class RouterOutput(BaseModel):
    next: Literal['agent_a', 'agent_b', 'agent_c']
