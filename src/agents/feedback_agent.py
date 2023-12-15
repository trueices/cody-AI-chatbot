from langchain.schema import HumanMessage, AIMessage

from src import agents
from src.agents.utils import parse_feedback_rating
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI


class FeedbackAgent(agents.Agent):
    """
    This agent isnt used anymore, but is kept for legacy reasons.
    Also, if a user in a previous version of the bot wanted to give feedback, this agent would be called.
    """
    name = 'feedback_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None):
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]

    def act(self) -> bool:
        if len(self.conv_hist) == 0:
            if self.state.next_agent_name == agents.ConciergeAgent.name:
                self.conv_hist.append(AIMessage(content=(
                    "Please tell us about how your experience has been so far. Please rate it on a scale of 1 to 5 "
                    "where 1 is the worst medication prescription experience you’ve ever had to 5 being the best "
                    "you’ve ever had. Also, please feel free to share your suggestions on how to make Cody the "
                    "fastest, easiest, lowest cost way for you to get your meds."
                )))
            else:
                # First round of feedback
                self.conv_hist.append(AIMessage(content=(
                    "Can you please rate the accuracy of the Condition List "
                    "on a scale of 1 to 5 where 1 is not accurate and 5 is highly accurate?")))
            self.llm.stream_callback.on_llm_new_token(self.conv_hist[-1].content)
            return True
        elif len(self.conv_hist) == 1:
            # Second round of feedback
            self.conv_hist.append(HumanMessage(content=self.state.last_human_input))

            # parse the last human input to be a decimal number and round it to the nearest integer
            self.state.feedback_rating = parse_feedback_rating(self.state.last_human_input)

            self.conv_hist.append(AIMessage(content="Thank you for the valuable feedback!\n\n\n"))
            self.llm.stream_callback.on_llm_new_token(self.conv_hist[-1].content)
            self.state.next_agent(reset_hist=True)
            return False
        else:
            # Feedback is already filled. Skip to end agent.
            self.state.next_agent(reset_hist=True)
            return False