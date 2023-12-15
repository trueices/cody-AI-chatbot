from typing import Callable
from typing import List

from langchain.schema import HumanMessage, AIMessage

from src import agents
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI
from src.utils import demo_mode

OPTIONS_CALLABLE: dict[str, Callable[['agents.ConciergeAgent'], None]] = {
    'tx':
    lambda self: self.state.next_agent(
        name=agents.TreatmentAgent.name, reset_hist=True),
    'save':
    lambda self: self.llm.stream_callback.on_llm_new_token(
        f"""To save our conversation, please <a class="text-blue underline app-link" href="/register">Create account</a> or <a class="text-blue underline app-link" href="/sign-in">Login</a>.\nOnce logged in, you can easily view this conversation under the chat history bubble.\n\n\n""")
        or self.state.next_agent(
        name=agents.ConciergeAgent.name, reset_hist=True),
    'new_conv_log_in':
    lambda self: self.llm.stream_callback.on_llm_new_token(
        f"""To discuss another health problem, tap on New Chat under chat history bubble at top left of the screen.\n\n\n""") or self.state.next_agent(
        name=agents.ConciergeAgent.name, reset_hist=True),
    'new_conv_log_out':
        lambda self: self.llm.stream_callback.on_llm_new_token(
        f"""To discuss another health problem, please <a class="text-blue underline app-link" href="/register">Create account</a> with us.\n\n\n""") or self.state.next_agent(
        name=agents.ConciergeAgent.name, reset_hist=True),
    'conv': lambda self: self.state.next_agent(
        name=agents.DxConversationAgent.name, reset_hist=True),
    'cont_conv': lambda self: self.state.next_agent(
        name=agents.DxConversationAgent.name, reset_hist=True),
    'connect': lambda self: self.state.next_agent(agents.CodyCareAgent.name, reset_hist=True),
}

OPTIONS_STR = {
    'tx': 'Let’s take a look at Treatments.',
    'save': '<a class="text-blue underline app-link" href="/register">Save our conversation.</a>',
    'new_conv_log_in': 'Start a new conversation.',
    'new_conv_log_out': 'Start a new conversation.',
    'conv': 'Let’s discuss your Top 3 Condition List.',
    'cont_conv': 'Continue our conversation.',
    'connect': '💊 Get Treatment Now From a Licensed Doctor.',
}


class ConciergeAgent(agents.Agent):
    name = 'concierge_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict):
        self.state = state
        self.llm = llm
        self.profile = profile
        self.conv_hist = self.state.conv_hist[self.name]
        assert OPTIONS_CALLABLE.keys() == OPTIONS_STR.keys(), \
            "Please add the same keys in both OPTIONS_CALLABLE and OPTIONS_STR, in the same order"

    def act(self) -> bool:
        # Adding a check for the number of messages in the conversation history
        if len(self.conv_hist) >= 25:
            OVERUSE_MESSAGE = "Unfortunately, I cant go any longer here. Please start a new conversation."
            self.llm.stream_callback.on_llm_new_token(OVERUSE_MESSAGE)
            return True

        # Routing to concierge options
        if self.state.concierge_option == 'find_care':
            return self.find_care_options()
        else:
            return self.detailed_options()

    def find_care_options(self):
        # Finding which diagnosis to show care options for.
        diagnosis = self.state.get_last_diagnosis()

        # Presenting options upon landing on the concierge agent
        if len(self.conv_hist) == 0:
            options = self._find_care_options(diagnosis)

            custom_message = AIMessage(content=options)
            self.llm.stream_callback.on_llm_new_token(custom_message.content)
            self.conv_hist.append(custom_message)
            return True

        self.conv_hist.append(HumanMessage(
            content=self.state.last_human_input))
        response_number = self._process_concierge_input(
            self._find_care_options(diagnosis))
        if response_number != 0:
            return self._handle_find_care_options(response_number, diagnosis)
        else:
            return True

    def _find_care_options(self, diagnosis):
        options = f"""{self.state.patient_name}, what should we get after next? 

1. Let’s chat about my treatment plan.
2. Show me the best doctors near me for {diagnosis}. 
3. Show me treatment plans for other conditions
4. Other options.
"""
        # This is just to support sales demo for ADHD. Will be removed after the demo.
        demo_match = demo_mode(self.state.mode)
        if demo_match:
            options = f"""{self.state.patient_name}, I have found the best doctors near you for {diagnosis}.
Enter the number of your option.

1. Yes, show me the best doctors near me for {diagnosis}. 
2. Show me treatment plans for other conditions.
3. Other options.
4. Chat with Cody about {demo_match.group(1)} treatment.
"""
        return options

    def _handle_find_care_options(self, number, diagnosis) -> bool:
        if number == 1:
            self.state.next_agent(
                name=agents.TxConversationAgent.name, reset_hist=True)
        elif number == 2:
            self.state.concierge_option = 'detailed'
            self.state.next_agent(
                name=agents.FindCareAgent.name, reset_hist=True)
        elif number == 3:
            self.state.next_agent(
                name=agents.TreatmentAgent.name, reset_hist=True)
        elif number == 4:
            self.state.concierge_option = 'detailed'
            self.state.next_agent(
                name=agents.ConciergeAgent.name, reset_hist=True)
        else:
            # This is just to support sales demo for ADHD. Will be removed after the demo.
            demo_match = demo_mode(self.state.mode)
            if demo_match and demo_match.group(1) in diagnosis.lower() and number == 4:
                self.state.next_agent(
                    name=agents.AdDemoAgent.name, reset_hist=True)
            else:
                self.llm.stream_callback.on_llm_new_token(
                    "Please enter a valid option number.")
                return True
        return False

    def detailed_options(self):
        # Presenting options upon landing on the concierge agent
        if len(self.conv_hist) == 0:
            options, _ = self._detailed_options_text()
            custom_message = AIMessage(content=options)
            self.llm.stream_callback.on_llm_new_token(custom_message.content)
            self.conv_hist.append(custom_message)
            return True

        self.conv_hist.append(HumanMessage(
            content=self.state.last_human_input))
        options, options_list = self._detailed_options_text()
        response_number = self._process_concierge_input(options)
        if response_number != 0:
            return self._handle_detailed_options(response_number, options_list)
        else:
            return True

    def _handle_detailed_options(self, number: int, option_list: List[str]) -> bool:
        index = number - 1
        if index >= len(option_list):
            self.llm.stream_callback.on_llm_new_token(
                "Please enter a valid option number.")
            return True
        option_str = option_list[index]
        OPTIONS_CALLABLE[option_str](self)
        return False

    def _detailed_options_text(self):
        logged_in = self.profile and self.profile.get('isLoggedIn', False)
        if logged_in:
            options = ['connect', 'conv', 'tx', 'new_conv_log_in']
        else:
            options = ['connect', 'conv', 'tx', 'new_conv_log_out', 'save']
        if len(self.state.conv_hist[agents.DxConversationAgent.name]) > 0:
            options[0] = 'cont_conv'

        options_text = "\n".join(
            [f"{i + 1}. {OPTIONS_STR[option]}" for i, option in enumerate(options)])
        options_text = f"""\n\n\nWhat should we do next?\n\n{options_text}"""
        return options_text, options

    def _process_concierge_input(self, options):
        from src.agents.utils import process_nav_input
        number = process_nav_input(human_input=self.state.last_human_input,
                                   options=options,
                                   state=self.state)
        if number == 0:
            self.llm.stream_callback.on_llm_new_token(
                "Please type a valid option.")
        return number
