from typing import Type

from langchain.schema import SystemMessage, AIMessage, HumanMessage
from langchain.tools.base import BaseTool
from langchain.tools.render import format_tool_to_openai_function
from pydantic import BaseModel, Field

from src import agents
from src.agents.utils import check_function_call
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI


class ToolCheck(BaseModel):
    feedback: int = Field(
        ..., description='A value between 1 and 5, representing the user feedback on the conversation')


class CaptureFeedbackTool(BaseTool):
    name = 'capture_feedback_tool'
    description = ('Saves the feedback for the conversation.')
    args_schema: Type[BaseModel] = ToolCheck

    def _run(self, feedback) -> str:
        return 'Feedback captured'


class QuestionAgent(agents.Agent):
    name = 'question_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None) -> None:
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]
        self.tools = [
            CaptureFeedbackTool()
        ]

    def act(self) -> bool:
        if len(self.conv_hist) == 0:
            content = "Sure. "
            self.conv_hist.append(AIMessage(content=content))
            self.llm.stream_callback.on_llm_new_token(content)
        else:
            self.conv_hist.append(HumanMessage(content=self.state.last_human_input))

        # check if the user wants to see the options
        if self.state.last_human_input.strip().lower() in ['options', 'option']:
            self.state.next_agent(
                name=agents.NavigationAgent.name, reset_hist=True)
            return False

        # Adding a check for the number of messages in the conversation history
        if len(self.conv_hist) >= 25:
            overuse_message = """I'm afraid we have reached our conversation limit for this session. Why dont you create a new conversation, and we can talk there? Thank you!"""
            self.llm.stream_callback.on_llm_new_token(overuse_message)
            return True

        response = self.llm(
            [SystemMessage(content=self._configure_system_prompt(
            ))] + self.state.conv_hist[agents.NavigationAgent.name][-5:-1] # Preventing function call msgs from Nav agent to enter llm conv
                + self.conv_hist[-10:],
            functions=[format_tool_to_openai_function(tool) for tool in self.tools])
        self.conv_hist.append(response)

        # Checking if a function call was made
        function_response, arguments = check_function_call(
            response, self.tools)
        if function_response is None:
            self.llm.stream_callback.on_llm_new_token('\n\n\nContinue our conversation or enter “Options”.')
            return True
        else:
            feedback = arguments['feedback']
            self.state.question_agent_feedback = feedback
            content = "Thank you for your feedback! If you have any more questions, feel free to ask. If you have another health issue to discuss, please start a new conversation."
            self.conv_hist.append(AIMessage(content=content))
            self.llm.stream_callback.on_llm_new_token(content)
            return True

    def _configure_system_prompt(self) -> str:
        return f"""
You are Cody, an AI doctor.
Your job is to converse with the patient and answer any questions they may have.
DO not entertain any other questions, except those related to health.
If the user wants to end the conversation or talk about a symptom/diagnosis, ask them to start a new conversation.

Politely remind them to provide a number between 1 and 5 to rate the conversation at the end.
Once you have a feedback, use the {CaptureFeedbackTool().name} tool.

Make sure your responses are short, (within a paragraph) but informative.
"""
