from abc import ABC, abstractmethod


class Agent(ABC):
    name: str

    @abstractmethod
    def __init__(self, state, llm, profile: dict = None):
        pass

    @abstractmethod
    def act(self) -> bool:
        pass
