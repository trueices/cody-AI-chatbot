import os
import re

from langchain.schema import SystemMessage, HumanMessage, AIMessage

from src import agents
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI
from src.utils import demo_mode


class AdDemoAgent(agents.Agent):
    name = 'ad_demo_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None) -> None:
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]

    def act(self) -> bool:
        if self.state.last_human_input.lower().strip() in ['concierge', 'options']:
            self.state.next_agent(name=agents.ConciergeAgent.name, reset_hist=True)
            return False

        demo_match = demo_mode(self.state.mode)

        if demo_match:
            if self.state.concierge_option == 'find_care':
                return self._cody_tx_demo(demo_match.group(1))
            else:
                return self._cody_ad_demo(demo_match.group(2))

    def _cody_ad_demo(self, provider: str) -> bool:
        if os.path.exists(f"{os.path.dirname(__file__)}/../demo/{self.state.mode}/ad_prompt.txt"):
            with open(f"{os.path.dirname(__file__)}/../demo/{self.state.mode}/ad_prompt.txt", 'r', encoding='utf-8') as file:
                system_prompt = file.read()
        else:
            system_prompt = f"""
            In the previous stage, you have been conversing with a patient and recommended three options for medical provider.
    
    You are an expert knowledge agent on Green Oak Therapists. DO NOT answer anything which is NOT related to
    ${provider}
    
    Example conversation:
    Human: Yes
    AI: Share our conversation with newpatient@greenoaktherapist.com. Create an account or log in. 
    View your “Conversations with Cody”. Highlight this current conversation. 
    Tap the “share” icon and enter Newpatient@{provider}.com. Tap “share” button.

    Then, tap this link meet.google.com/rgk-ygym-ymu  and your Health Coach will join within 10 minutes.
    
    Human: Great, Thank you
    AI: No problem! On behalf of {provider}, we are looking forward to meeting you.
    Human: Bye"""

        static_greeting_mode = (
            os.path.exists(f"{os.path.dirname(__file__)}/../demo/{self.state.mode}/ad_greeting.txt")
            and os.path.exists(f"{os.path.dirname(__file__)}/../demo/{self.state.mode}/ad_end.txt")
        )

        if static_greeting_mode and len(self.conv_hist) == 0:
            with open(f"{os.path.dirname(__file__)}/../demo/{self.state.mode}/ad_greeting.txt", 'r', encoding='utf-8') as file:
                self.conv_hist.append(AIMessage(content=file.read()))
            self.llm.stream_callback.on_llm_new_token(self.conv_hist[-1].content)
        elif static_greeting_mode and len(self.conv_hist) == 1 and self.state.last_human_input.lower().strip() == 'yes':
            with open(f"{os.path.dirname(__file__)}/../demo/{self.state.mode}/ad_end.txt", 'r', encoding='utf-8') as file:
                self.conv_hist.append(AIMessage(content=file.read()))
            self.llm.stream_callback.on_llm_new_token(self.conv_hist[-1].content)
        else:
            self.conv_hist.append(HumanMessage(content=self.state.last_human_input))
            response = self.llm([SystemMessage(content=system_prompt)] + self.conv_hist)
            self.conv_hist.append(response)

        return True

    def _cody_tx_demo(self, diag: str) -> bool:
        knowledge_base = ""

        if os.path.exists(f"{os.path.dirname(__file__)}/../demo/{self.state.mode}/knowledge.txt"):
            with open(f"{os.path.dirname(__file__)}/../demo/{self.state.mode}/knowledge.txt", 'r', encoding='utf-8') as file:
                knowledge_base = file.read()

        system_prompt = f""" You are an expert doctor on {diag}. You are an expert at discussing {diag} treatment 
        options. You discuss ONLY on one of the below topics:
    
    1. Setting Treatment Goals
    2. Medication Treatment Options
    3. Cognitive Therapy with a professional
    4. Self Care
    
    DONOT answer anything which is not related to {diag} treatment options. If user asks about anything else, 
    you need to humbly refuse to answer and ask the user to ask about ADHD treatment options. Keep your response 
    concise and not more than 10 sentences.
    
    Use knowledge below when answering questions:
    
    {knowledge_base}
    
    <EXAMPLE>
    Human: Medication Treatment Options
    AI: Medication is a common treatment for {diag}. There are many medications available to treat {diag}.
    Human: Thank you
    AI: You are welcome. You can ask me any question about {diag} treatment options.
    """

        if len(self.conv_hist) == 0:
            self.conv_hist.append(AIMessage(content=(f"""
Great. Here are some {diag} treatment topics we can discuss. Let me know what you’d like to discuss:

    - Setting Treatment Goals
    - Medication Treatment Options
    - Cognitive Therapy with a professional
    - Self Care
    
By the way, you can always enter “Options” to see what you can do next.
            """)))

            self.llm.stream_callback.on_llm_new_token(self.conv_hist[-1].content)
        else:
            self.conv_hist.append(HumanMessage(
                content=self.state.last_human_input))
            response = self.llm([SystemMessage(content=system_prompt)] + self.conv_hist[-1:])
            self.llm.stream_callback.on_llm_new_token(f'\n\n\nWhat {diag} Treatment topics would you like to discuss next?')
            response.content = response.content + f'\n\n\nWhat {diag} Treatment topics would you like to discuss next?'
            self.conv_hist.append(response)

        return True

