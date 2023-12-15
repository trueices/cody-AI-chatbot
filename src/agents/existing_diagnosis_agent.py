import json

from langchain.schema import AIMessage, SystemMessage

from src import agents
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI, CustomChatOpenAI
from langchain.schema import AIMessage, SystemMessage, HumanMessage
import json
from src.agents.utils import process_nav_input
from src.agents.utils import check_function_call


class ExistingDiagnosisAgent(agents.Agent):
    name = 'existing_diagnosis_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None) -> None:
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]

    def act(self) -> bool:
        self._extract_disease_name()

        OPTIONS = f"""1. We could prepare a treatment plan for your {self.state.existing_dx}.
2. I could help you find the best doctors near you for your {self.state.existing_dx}.
3. We could chat about your {self.state.existing_dx}."""

        MSG = f"""Here's how I can help you with your {self.state.existing_dx}.

{OPTIONS}


Continue our conversation or enter “Options”."""

        if len(self.conv_hist) == 0:
            self.conv_hist.append(AIMessage(content=MSG))
            self.llm.stream_callback.on_llm_new_token(MSG)
            return True

        # check if the user wants to see the options
        if self.state.last_human_input.strip().lower() in ['options', 'option']:
            self.state.next_agent(
                name=agents.NavigationAgent.name, reset_hist=True)
            return False

        number = process_nav_input(human_input=self.state.last_human_input,
                                   options=OPTIONS,
                                   state=self.state)
        if number == 1:
            self.state.next_agent(name=agents.TreatmentAgent.name, reset_hist=True)
            self.state.next_agent_name = agents.ExistingDiagnosisAgent.name
            return False
        elif number == 2:
            self.state.next_agent(name=agents.FindCareAgent.name, reset_hist=True)
            self.state.next_agent_name = agents.ExistingDiagnosisAgent.name
            return False
        elif number == 3:
            self.state.next_agent(name=agents.DxConversationAgent.name, reset_hist=True)
            self.state.next_agent_name = agents.ExistingDiagnosisAgent.name
            return False
        else:
            self.llm.stream_callback.on_llm_new_token(
                "I'm sorry, I didn't understand that. Could you please type a valid option.")
            return True

    def _extract_disease_name(self):
        if self.state.existing_dx == '':
            conv_hist = '\n'.join(
                [f'{msg.type}: {msg.content}' for msg in self.state.conv_hist[agents.NavigationAgent.name]])
            system_prompt = f"""
From a given conversation history, determine the disease that the user is suffering from/suspecting.

Your output should be a JSON with the following keys: (all keys are required)
- disease_name: str (The disease of the user)

Example conversation:
Human: I have diabetes
AI: Have you been diagnosed with diabetes?
Human: Yes
OUTPUT: {{"disease_name": "diabetes"}}
End of example conversation.

NOW, PLEASE IDENTIFY THE DISEASE NAME FROM THE GIVEN CONVERSATION HISTORY.
CONVERSATION HISTORY:
{conv_hist}
"""
            response = CustomChatOpenAI(state=self.state)([SystemMessage(
                content=system_prompt)], response_format={"type": "json_object"}).content
            response: dict = json.loads(response)
            self.state.existing_dx = response.get('disease_name', '')


