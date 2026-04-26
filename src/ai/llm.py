from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic


class _LLMRegistry:

    def __init__(self):
        self._store = {}

    def init(self):
        self._store = {
            'reasoner': ChatOpenAI(model='gpt-4o', temperature=0),
            'writer': ChatOpenAI(model='gpt-4o', temperature=0.9),
            'fast': ChatOpenAI(model='gpt-4o', temperature=0),
            'claude': ChatAnthropic(model='claude-sonnet-4-5'),
        }

    def get(self, name):
        if not self._store:
            raise RuntimeError('LLMRegistry has not been initialized')
        if name not in self._store:
            raise KeyError(f'llm [{name}] not registered, available: {list(self._store.keys())}')
        return self._store[name]

    # registry['reasoner']
    def __getitem__(self, name):
        return self.get(name)


llm_registry = _LLMRegistry()
