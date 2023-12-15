from langchain.schema import HumanMessage, SystemMessage, AIMessage

from src import agents
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI


class TxConversationAgent(agents.Agent):
    name = 'tx_conversation_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None):
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]

    def act(self) -> bool:
        if len(self.conv_hist) == 0:
            content = f"""<div class='tx-plan'>Great. Here are some treatment topics we can discuss. Let me know what you’d like to discuss:
<ul>
<li>What to Expect With {self.state.get_last_diagnosis()}.</li>
<li>Medication Treatment Options</li>
<li>Self Care Options</li>
</ul>
Continue our conversation or enter “Options”.</div>"""
            self.conv_hist.append(AIMessage(content=content))
            self.llm.stream_callback.on_llm_new_token(content)
            return True
        
        # Since dx and tx are very similar right now, we can use the same function to handle the conversation.
        # Later, we can add more specific functionality to this function.
        return agents.DxConversationAgent.handle_conversation(self)

    def _configure_system_prompt(self) -> str:
        return f"""
You are Cody, an AI doctor. A patient has come to you with a chief complaint of {self.state.chief_complaint}.
The name of the patient is {self.state.patient_name}.
Below is the summary of the patient's history:
{self.state.conv_hist[agents.MagicMinuteAgent.name][0].content}
The patient has been provided a differential diagnosis of {', '.join([dx.title() for dx in self.state.diagnosis_list])}.
The patient may want to discuss treatment options for {self.state.get_last_diagnosis()}.
The treatment you have provided is: 
{self.state.get_last_treatment_plan()}
Your job is to converse with the patient and answer any questions they may have about the treatment.
DO not entertain any other questions, except those related to the treatment
Make sure your responses are short, but informative.
"""
