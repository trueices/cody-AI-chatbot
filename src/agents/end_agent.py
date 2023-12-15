from langchain.schema import AIMessage
from src import agents
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI
from src.utils import base_url


class EndAgent(agents.Agent):
    name = 'end_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None) -> None:
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]

    def act(self) -> bool:
        if len(self.conv_hist) == 0:
            self.conv_hist.append(AIMessage(content=(
                f"""\n\n\n{self.state.patient_name},

It's been an honor to be your AI Doctor. 

To get the maximum benefits of my services, please create an account if you havent already.

Bookmark <a class="text-blue underline" href="{base_url()}" target="_blank">{base_url()}</a> and return for 
all your AI Doctor needs.

I improve every time a person uses me so please share Cody.MD with your friends and family.

Sincerely,

Cody.MD
An AI Doctor for Every Human""")
            ))
            self.llm.stream_callback.on_llm_new_token(self.conv_hist[-1].content)
            return True
        else:
            LAST_MSG = "We've reached the end of our conversation. Thanks for using Cody! You can close this window now."
            self.llm.stream_callback.on_llm_new_token(LAST_MSG)
            return True
