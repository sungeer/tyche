from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from src.agents.tools import get_weather, calculator, search_database


class _AgentHolder:

    def __init__(self):
        self._checkpointer = None
        self._map = {}

    def init(self, llm_registry):
        self._checkpointer = MemorySaver()

        self._map = {
            'chat': create_react_agent(
                model=llm_registry['fast'],
                tools=[],
                checkpointer=self._checkpointer,
                state_modifier='You are a helpful assistant.',
            ),
            'weather': create_react_agent(
                model=llm_registry['reasoner'],
                tools=[get_weather, calculator],
                checkpointer=self._checkpointer,
                state_modifier='You are a weather assistant.',
            ),
            'data': create_react_agent(
                model=llm_registry['claude'],
                tools=[search_database],
                checkpointer=self._checkpointer,
                state_modifier='You are a data analyst assistant.',
            ),
        }

    def get(self, name):
        if name not in self._map:
            raise KeyError(f'Agent [{name}] not found, available: {list(self._map.keys())}')
        return self._map[name]

    # agents['weather']
    def __getitem__(self, name):
        return self.get(name)


agents = _AgentHolder()
