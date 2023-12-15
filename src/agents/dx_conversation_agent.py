from langchain.schema import HumanMessage, SystemMessage, AIMessage

from src import agents
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI


class DxConversationAgent(agents.Agent):
    """
    This agent may have two different modes of operation:
    1. Linear funnel for a list of dx, coming from ConciergeAgent.
    2. Specialized funnel for a single dx, coming from ExistingDiagnosisAgent.

    The decision is made based on the value of `next_agent_name` in the state.
    """
    name = 'dx_conversation_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None):
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]

    def act(self) -> bool:
        if len(self.conv_hist) == 0:
            if self.state.next_agent_name == agents.ExistingDiagnosisAgent.name:
                content = f"""<div class='tx-plan'>Sure, here are some things we could discuss.
<ul>
<li>What is {self.state.existing_dx}.</li>
<li>What causes {self.state.existing_dx}.</li>
<li>How to confirm {self.state.existing_dx}.</li>
</ul>
Continue our conversation or enter “Options”.</div>"""
            else:
                content = """<div class='tx-plan'>Sure, here are some things we could discuss about your diagnosis list.
<ul>
<li>Chat about a specific condition from the List.</li>
<li>How to confirm a condition from the List.</li>
</ul>
Continue our conversation or enter “Options”.</div>"""
            self.conv_hist.append(AIMessage(content=content))
            self.llm.stream_callback.on_llm_new_token(content)
            return True

        if self.state.next_agent_name == agents.ExistingDiagnosisAgent.name:
            return self.handle_conversation_single_dx()
        else:
            return self.handle_conversation(self)

    def _configure_system_prompt(self) -> str:
        if self.state.next_agent_name == agents.ExistingDiagnosisAgent.name:
            patient_name = '' if self.state.patient_name is None else f"The name of the patient is {self.state.patient_name}.\n"
            return f"""
You are Cody, an AI doctor. A patient has come to you with an existing diagnosis of {self.state.existing_dx}.
{patient_name}
Your job is to converse with the patient and answer any questions they may have about the diagnosis.
DO not entertain any other questions, except those related to the diagnosis.
Make sure your responses are short, but informative.
"""
        else:
            return f"""
You are Cody, an AI doctor. A patient has come to you with a chief complaint of {self.state.chief_complaint}.
The name of the patient is {self.state.patient_name}.
Below is the summary of the patient's history:
{self.state.conv_hist[agents.MagicMinuteAgent.name][0].content}
The patient has been provided a differential diagnosis of {', '.join([dx.title() for dx in self.state.diagnosis_list])}.
Your job is to converse with the patient and answer any questions they may have about the diagnosis.
DO not entertain any other questions, except those related to the diagnosis
Make sure your responses are short, but informative.
"""

    @staticmethod
    def handle_conversation(self) -> bool:
        # To avoid circular import
        self: agents.DxConversationAgent | agents.TxConversationAgent = self

        # check if the user wants to see the options
        if self.state.last_human_input.strip().lower() in ['options', 'option']:
            if isinstance(self, agents.DxConversationAgent):
                self.state.concierge_option = 'detailed'
            else:
                self.state.concierge_option = 'find_care'
            self.state.next_agent(
                name=agents.ConciergeAgent.name, reset_hist=True)
            return False

        # human input appended in history
        self.conv_hist.append(HumanMessage(
            content=self.state.last_human_input))

        # Adding a check for the number of messages in the conversation history
        if len(self.conv_hist) >= 25:
            overuse_message = """I'm afraid we have reached our conversation limit for this session. Why dont you create a new conversation, and we can talk there? Thank you!

    In the meantime, let me take you back to your treatment options.\n\n\n"""
            self.llm.stream_callback.on_llm_new_token(overuse_message)
            self.state.concierge_option = 'detailed'
            self.state.next_agent(
                name=agents.ConciergeAgent.name, reset_hist=True)
            return False

        response = self.llm(
            [SystemMessage(content=self._configure_system_prompt())] + self.conv_hist[-10:])
        self.conv_hist.append(response)
        self.llm.stream_callback.on_llm_new_token(
            "\n\n\nContinue our conversation or enter “Options”")
        return True

    def handle_conversation_single_dx(self) -> bool:
        # check if the user wants to see the options
        if self.state.last_human_input.strip().lower() in ['options', 'option']:
            self.state.next_agent(
                name=agents.ExistingDiagnosisAgent.name, reset_hist=True)
            return False

        # human input appended in history
        self.conv_hist.append(HumanMessage(
            content=self.state.last_human_input))

        # Adding a check for the number of messages in the conversation history
        if len(self.conv_hist) >= 25:
            overuse_message = """I'm afraid we have reached our conversation limit for this session. Why dont you create a new conversation, and we can talk there? Thank you!

In the meantime, let's start over.\n\n\n"""
            self.llm.stream_callback.on_llm_new_token(overuse_message)
            self.state.next_agent(
                name=agents.ExistingDiagnosisAgent.name, reset_hist=True)
            return False

        response = self.llm(
            [SystemMessage(content=self._configure_system_prompt())] + self.conv_hist[-10:])
        self.conv_hist.append(response)
        self.llm.stream_callback.on_llm_new_token(
            "\n\n\nContinue our conversation or enter “Options”")
        return True