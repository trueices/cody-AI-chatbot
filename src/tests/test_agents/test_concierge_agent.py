from langchain.schema import AIMessage

from src import agents
from src.bot import Bot
from src.tests.utils import ask, setup
from src.utils import fake_llm

"""
First level options.
"""


def init(profile: dict = None):
    if profile is None:
        profile = {'isLoggedIn': False}

    bot = Bot(username='test', profile=profile)
    bot.state.patient_name = 'test'
    bot.state.diagnosis_list = ['disease 1', 'disease 2', 'disease 3']
    bot.state.conv_hist[agents.MagicMinuteAgent.name][:] = [
        AIMessage(content='SUMMARY')]

    bot.state.next_agent(name=agents.ConciergeAgent.name)
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'detailed'

    bot = ask(bot, profile=profile)
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert """1. 💊 Get Treatment Now From a Licensed Doctor.
2. Let’s discuss your Top 3 Condition List.
3. Let’s take a look at Treatments.
4. Start a new conversation.""" in last_msg

    if profile is None or not profile.get('isLoggedIn', False):
        assert f"""Save our conversation.""" in last_msg, \
            "Save option should be logged out state."
    else:
        assert f"""Save our conversation.""" not in last_msg, \
            "Save option should not be logged in state."
    return bot


def test_options_logged_out(setup):
    bot = init()

    # Save conversation
    bot = ask(bot, '5')
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'detailed'
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert f"""To save our conversation, please <a class="text-blue underline app-link" href="/register">Create account</a>""" in last_msg

    # Discuss another health problem
    bot = ask(bot, '4')
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'detailed'
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert f"""To discuss another health problem, please <a class="text-blue underline app-link" href="/register">Create account</a> with us.""" in last_msg

    # Selecting invalid option
    bot = ask(bot, '6')
    assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'Please enter a valid option number.'
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'detailed'

    # Selecting gibberish
    fake_llm.responses += ['{"option": 0}']
    bot = ask(bot, 'asdasd')
    assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'Please type a valid option.'
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'detailed'

    # connect to a doctor
    bot = ask(bot, '1')

    assert (('Please <a class="text-blue underline app-link" href="/sign-in">login</a> or <a class="text-blue underline '
            'app-link" href="/register">create an account</a> to get treatment now.') in
            bot.full_conv_hist.full_conv_hist[-1]['content'])
    assert bot.state.current_agent_name == agents.CodyCareAgent.name
    assert bot.state.concierge_option == 'detailed'


def test_options_logged_in(setup):
    profile = {'isLoggedIn': True}
    bot = init(profile=profile)

    # Trying to save conversation should lead to invalid option
    bot = ask(bot, '5', profile=profile)
    assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'Please enter a valid option number.'
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'detailed'


def test_options_treatment(setup):
    bot = init()

    # Show me treatment plans
    bot = ask(bot, '3')
    assert bot.state.current_agent_name == agents.TreatmentAgent.name


def test_options_conv(setup):
    bot = init()

    # Let's chat about your diagnosis list
    bot = ask(bot, '2')
    assert bot.state.current_agent_name == agents.DxConversationAgent.name


def test_options_invalid_llm(setup):
    bot = init()

    # Llm not able to figure out the option
    fake_llm.responses += ['invalid json']
    bot = ask(bot, 'asdasd')
    assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'Please type a valid option.'
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'detailed'

    # Llm not able to figure out the option
    fake_llm.responses += ['{"option": "string"}']
    bot = ask(bot, 'asdasd')
    assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'Please type a valid option.'
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'detailed'


def test_options_via_llm(setup):
    bot = init()

    # Selecting gibberish
    fake_llm.responses += ['{"option_number": 3}']
    bot = ask(bot, 'show treatment plans')
    assert 'Ok, to view a treatment plan enter the number of the diagnosis' in bot.full_conv_hist.full_conv_hist[-1][
        'content']
    assert bot.state.current_agent_name == agents.TreatmentAgent.name
    assert bot.state.concierge_option == 'detailed'


"""
find care options
"""


def init_fc_options(profile: dict = None):
    bot = init()
    bot = ask(bot, '3', profile=profile)
    assert bot.state.current_agent_name == agents.TreatmentAgent.name

    # Selecting first diagnosis
    fake_llm.responses += ['Treatment plan for disease 1.']
    bot = ask(bot, '1', profile=profile)  # Selecting first diagnosis
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'find_care'
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert "1. Let’s chat about my treatment plan" in last_msg
    assert "2. Show me the best doctors near me for Disease 1" in last_msg
    assert "3. Show me treatment plans for other conditions" in last_msg
    assert "4. Other options." in last_msg
    return bot


def test_fc_options_treatment(setup):
    bot = init_fc_options()

    # Show me treatment plans
    bot = ask(bot, '3')
    assert bot.state.current_agent_name == agents.TreatmentAgent.name


def test_fc_options_other_options(setup):
    bot = init_fc_options()

    # Other options
    bot = ask(bot, '4')
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'detailed'
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert "Let’s take a look at Treatments." in last_msg, \
        "Should show the options."


def test_fc_options_invalid(setup):
    bot = init_fc_options()

    # Selecting invalid option
    bot = ask(bot, '6')
    assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'Please enter a valid option number.'
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'find_care'

    fake_llm.responses += ['{"option": 0}']
    # Selecting gibberish
    bot = ask(bot, 'asdasd')
    assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'Please type a valid option.'
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'find_care'


def test_fc_options_free_text_valid(setup):
    profile = {'isLoggedIn': True}
    bot = init_fc_options(profile=profile)

    # Selecting invalid option
    bot = ask(bot, '6', profile=profile)
    assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'Please enter a valid option number.'
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'find_care'

    fake_llm.responses += ['{"option_number": 2}']
    fake_llm.responses += ['May I know your location?']

    bot = ask(bot, 'best doctors near me', profile=profile)
    # Show me doctors.
    assert bot.state.current_agent_name == agents.FindCareAgent.name
    assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'May I know your location?'


def test_fc_options_tx_conv(setup):
    bot = init_fc_options()

    # Let's chat about your treatment plan
    bot = ask(bot, '1')
    assert bot.state.current_agent_name == agents.TxConversationAgent.name
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith(
        "<div class='tx-plan'>Great. Here are some treatment topics we can discuss.")
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].endswith("</div>")

    # Asking a question
    fake_llm.responses += ['LLM response']
    bot = ask(bot, '_')
    assert bot.state.current_agent_name == agents.TxConversationAgent.name
    assert bot.full_conv_hist.full_conv_hist[-1][
        'content'] == 'LLM response\n\n\nContinue our conversation or enter “Options”'

    # Let's enter options
    bot = ask(bot, 'Options')
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'find_care'
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert "1. Let’s chat about my treatment plan" in last_msg
    assert "2. Show me the best doctors near me for Disease 1" in last_msg


def test_fc_logged_out(setup):
    profile = {'isLoggedIn': False}
    bot = init_fc_options(profile=profile)

    # Show me doctors.
    bot = ask(bot, '2', profile=profile)
    assert 'Please <a class="text-blue underline app-link" href="/sign-in">login</a> or <a class="text-blue underline app-link" href="/register">create an account</a> to view the best doctors near you.' \
           in bot.full_conv_hist.full_conv_hist[-1]['content']
    assert bot.state.current_agent_name == agents.FindCareAgent.name
    assert bot.state.concierge_option == 'detailed'


def test_fc_logged_in(setup):
    profile = {'isLoggedIn': True}
    bot = init_fc_options(profile=profile)

    # Show me doctors.
    fake_llm.responses += ['May I know your location?']
    bot = ask(bot, '2', profile=profile)
    assert bot.state.current_agent_name == agents.FindCareAgent.name
    assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'May I know your location?'
