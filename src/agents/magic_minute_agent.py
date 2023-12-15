from langchain.schema import SystemMessage

from src import agents
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI


class MagicMinuteAgent(agents.Agent):
    name = 'magic_minute_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None):
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]

    def act(self) -> bool:
        system_prompt = self._configure_system_prompt()
            
        prev_conv_hist = self.state.conv_hist[agents.FollowupAgent.name].copy()
        self.llm.stream_callback.on_llm_new_token("<div class='tx-plan'>")
        response = self.llm(prev_conv_hist + [SystemMessage(content=system_prompt)])
        self.llm.stream_callback.on_llm_new_token("</div>")

        # Adding line breaks after magic minute.
        custom_message = "\n\n\n"
        self.llm.stream_callback.on_llm_new_token(custom_message)
        response.content += custom_message
        
        self.conv_hist.append(response)
        self.state.next_agent()
        return False
        
    def _configure_system_prompt(self):
        system_prompt = f"""
You are a doctor. Your name is Cody.
In the previous stage, you have been conversing with a patient, about their symptoms.
You have already asked a set of questions and the patient has answered them.
Now, use the conversation history and try to list out the key points from the conversation. 
The key points should be addressed in the second-person perspective (using pronouns like "you", "your", etc.).
{self.state.patient_name} had reached out to you regarding their {self.state.chief_complaint}. So, your first point should be something like "You have come to me regarding your {self.state.chief_complaint}".
Do not call any tool in this stage.

Example output:
{self.state.patient_name}, here's what I've understood so far:
<h1>Summary of our conversation</h1>
<ul>
<li>You have come to me regarding your {self.state.chief_complaint}.</li>
<li>[other key bullet points from the conversation history, but in brief.]</li>
</ul>

Do not add anything after the bullet points. Your task is to list out key points. Do not provide any explanation or advise.
"""
        return system_prompt