import textwrap

from langchain.schema import HumanMessage, SystemMessage, AIMessage
from src import agents
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI, CustomChatOpenAI

class NameEnquiryAgent(agents.Agent):
    name = 'name_enquiry_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None):
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]

    def act(self) -> bool:
        # check if patient name is already captured, then just greet patient and call next agent
        if self.state.patient_name is not None:
            self._greet_patient(True)
            self.state.next_agent()
            return False

        if len(self.conv_hist) == 0:
            self.conv_hist.append(AIMessage(
                content="Thanks for confirming! Before I ask you a few questions, what should I call you?"))
            last_message = self.conv_hist[-1].content
            self.llm.stream_callback.on_llm_new_token(last_message)
            return True
        else:
            system_prompt = f"""
Your job is to capture the name of the patient from the conversation.
Output should be a JSON with the following keys:
- name: The name of the patient with the first letter of each word capitalized.
If the patient's name is not provided, return use "N/A" as the name.

EXAMPLE: 
CONV HIST:
AI: Thanks for confirming! Before I ask you a few questions, what should I call you?
HUMAN: Ghana
OUTPUT: {{"name": "Ghana"}}
"""
            # append the last human input to the conversation history
            self.conv_hist.append(HumanMessage(content=self.state.last_human_input))

            llm = CustomChatOpenAI(state=self.state)
            conv_hist = [SystemMessage(content=system_prompt)] + self.conv_hist[-2:]
            response = llm(conv_hist, response_format={"type": "json_object"})
            import json
            response:dict = json.loads(response.content)
            name = response.get('name', 'N/A')
            
            if name != 'N/A':
                self.state.patient_name = name
                self.state.next_agent()
                self._greet_patient()
                return False
            elif len(self.conv_hist) > 4:
                # If name isnt captured after asking twice, move to the next agent.
                self.state.patient_name = ' '
                self.state.next_agent()
                self._greet_patient()
                return False
            else:
                content = "I'm sorry, but I didn't get your name. Can you please provide it again?"
                self.conv_hist.append(AIMessage(content=content))
                self.llm.stream_callback.on_llm_new_token(content)
                return True

    def _greet_patient(self, is_profile=False) -> None:
        if is_profile:
            content = f"{self.state.patient_name}, my goal is to provide you with an accurate assessment and plan. Lets talk about your concerns regarding {self.state.chief_complaint}."
        else:
            content = f"Good to meet you, {self.state.patient_name}! My goal is to provide you with an accurate assessment and plan. Lets talk about your concerns regarding {self.state.chief_complaint}."
        self.llm.stream_callback.on_llm_new_token(content + '\n\n\n')
        self.conv_hist.append(AIMessage(content=content))
        return None
