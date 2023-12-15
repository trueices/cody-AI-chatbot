from typing import Type

from langchain.tools.base import BaseTool
from pydantic import BaseModel, Field


class ToolCheck(BaseModel):
    next_agent: str = Field(..., description='The name of the next agent to be called')
    pass
class NextAgentTool(BaseTool):
    name = 'next_agent_tool'
    description = 'Used to end the current agent and start the next agent'
    args_schema: Type[BaseModel] = ToolCheck
    def _run(self, next_agent) -> str:
        return 'Next agent started'