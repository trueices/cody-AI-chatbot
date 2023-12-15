import json
from langchain.schema import SystemMessage
from src import agents
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI, CustomChatOpenAI


class ChiefComplaintAgent(agents.Agent):
    name = 'chief_complaint_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None):
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]

    def act(self) -> bool:
        self._identify_chief_complaint_from_nav_agent()
        self.state.next_agent()
        return False

    def _identify_chief_complaint_from_nav_agent(self):
        conv_hist = '\n'.join(
            [f'{msg.type}: {msg.content}' for msg in self.state.conv_hist[agents.NavigationAgent.name]])
        system_prompt = f"""
From a given conversation history, determine the chief complaint of the user.

Your output should be a JSON with the following keys: (all keys are required)
- chief_complaint: str (The chief complaint of the user)

Example conversation:
Human: I have a back pain
AI: So you want to focus on your back pain today, is that correct?
Human: Yes
OUPUT: {{"chief_complaint": "back pain"}}
End of example conversation.

NOW, PLEASE IDENTIFY THE CHIEF COMPLAINT FROM THE GIVEN CONVERSATION HISTORY.
CONVERSATION HISTORY:
{conv_hist}
"""
        response = CustomChatOpenAI(state=self.state)([SystemMessage(content=system_prompt)], response_format={"type": "json_object"}).content
        response:dict = json.loads(response)
        self.state.chief_complaint = response.get('chief_complaint', '')