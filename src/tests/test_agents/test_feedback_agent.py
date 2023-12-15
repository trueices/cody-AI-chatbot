from src import agents
from src.agents.utils import parse_feedback_rating
from src.bot import Bot
from src.tests.utils import ask, setup


def test_various_conditions_for_parsing_feedback():
    assert parse_feedback_rating('1') == 1, \
        "Should parse a single digit string to an integer"
    assert parse_feedback_rating("I would say its somewhere between 1 and 2") is None, \
        "Should not parse a string with non-numeric characters to an integer"
    assert parse_feedback_rating('2.7') == 3, \
        "Should round a decimal number to the nearest integer"
    assert parse_feedback_rating('2.4') == 2, \
        "Should round a decimal number to the nearest integer"
    assert parse_feedback_rating('10.5') == 5, \
        "5 should be the maximum value for the feedback rating"

def test_feedback_reaching_via_concierge(setup):
    bot = Bot(username='test')
    bot.state.next_agent(name=agents.FeedbackAgent.name)
    
    # Asking for feedback
    bot = ask(bot)
    assert bot.state.current_agent_name == agents.FeedbackAgent.name
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith(
        'Can you please rate')

    # Giving a rating
    bot = ask(bot, '5')
    assert bot.state.feedback_rating == 5
    last_message: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert last_message.startswith('Thank you')
    assert bot.state.current_agent_name == agents.EndAgent.name
    assert bot.state.concierge_option == 'detailed'

    # Calling the agent again should skip the feedback agent
    bot.state.next_agent(name=agents.FeedbackAgent.name)
    assert bot.state.current_agent_name == agents.FeedbackAgent.name
    bot = ask(bot)
    assert bot.state.current_agent_name == agents.EndAgent.name

