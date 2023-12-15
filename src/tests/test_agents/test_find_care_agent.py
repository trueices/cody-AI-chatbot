import json
from unittest.mock import Mock

from langchain.schema import AIMessage, HumanMessage

from src import agents
from src.agents import FindCareAgent, ConciergeAgent
from src.bot import Bot
from src.care.google_place_care_provider import GooglePlaceCareProvider
from src.tests.utils import ask, setup
from src.utils import fake_llm


def init_find_care_agent(profile: dict = None) -> Bot:
    if profile is None:
        profile = {'isLoggedIn': True}

    bot = Bot(username='test', profile=profile)
    bot.state.next_agent(name=agents.FindCareAgent.name)
    assert bot.state.current_agent_name == agents.FindCareAgent.name

    agent: FindCareAgent = bot.agents[bot.state.current_agent_index]
    agent.care_provider_renderer = Mock()
    agent.care_provider_renderer.render.return_value = 'Care Providers'
    bot.state.patient_name = 'Dave'
    bot.state.treatment_plans_seen = ['1']
    bot.state.diagnosis_list = ['Disease 1', 'Disease 2', 'Disease 3']
    bot.state.concierge_option = 'detailed'
    bot.state.treatment_plans = {'1': '<html><body><p>Disease 1</p></body></html>'}
    return bot


def test_find_care_via_bot_state_end_to_end(setup):
    profile = {'isLoggedIn': True}
    bot = init_find_care_agent(profile=profile)
    fake_llm.responses += ['May I know your location?']

    # Ask the bot to find care
    bot = ask(bot, profile=profile)
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert last_msg == 'May I know your location?'
    assert bot.state.current_agent_name == agents.FindCareAgent.name

    # Provide address
    fake_llm.responses += ['Do you want to proceed with Oslo, Norway?']
    bot = ask(bot, 'Oslo, Norway', profile=profile)
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert last_msg == 'Do you want to proceed with Oslo, Norway?'
    assert bot.state.current_agent_name == agents.FindCareAgent.name

    # Confirm address
    fake_llm.responses += ['']
    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'find_care_address_tool',
        'arguments': json.dumps({'address': 'Oslo, Norway'})
    }})
    agents.FindCareAgent.care_provider_renderer = Mock()
    agents.FindCareAgent.care_provider_renderer.render.return_value = 'Care Providers'
    bot = ask(bot, 'Yes', profile=profile)
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert last_msg.startswith('Care Providers\n\n\n')
    assert bot.state.current_agent_name == agents.FindCareAgent.name

    # Collecting feedback
    bot = ask(bot, '5')
    assert bot.state.care_feedback_rating == 5, \
        "Should collect feedback rating"
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert bot.state.conv_hist[FindCareAgent.name][-2] == HumanMessage(content='5')
    assert last_msg.startswith('Thank you for the valuable feedback!')
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert "3. Let’s take a look at Treatments." in last_msg, \
        "Should present concierge options"


def test_find_care_with_feedback_already_received(setup):
    bot = init_find_care_agent()

    bot.state.care_feedback_rating = 5  # Already received feedback
    fake_llm.responses += ['']
    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'find_care_address_tool',
        'arguments': json.dumps({'address': 'Oslo, Norway'})
    }})
    # Ask the bot to find care
    bot = ask(bot)
    assert bot.state.current_agent_name == agents.ConciergeAgent.name, \
        "Should skip feedback and go to concierge agent"
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert last_msg.startswith('Care Providers\n\n\n\n\n\nWhat should we do next?')


def test_find_care_feedback_with_no_results(setup):
    bot = init_find_care_agent()

    # Change find care to return no results
    agents.FindCareAgent.care_provider_renderer.render.return_value = ''
    fake_llm.responses += ['']
    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'find_care_address_tool',
        'arguments': json.dumps({'address': 'Oslo, Norway'})
    }})

    # Ask the bot to find care
    bot = ask(bot)
    assert bot.state.current_agent_name == agents.FindCareAgent.name, \
        "Should skip feedback and go to concierge agent"
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert last_msg.startswith('Sorry, I couldn\'t find any care options for you. ')


def test_find_care_agent_enabled():
    bot_state = Mock()
    care_provider_renderer = Mock()
    care_provider_renderer.render.return_value = 'Care Providers'

    bot_state.patient_name = 'Dave'
    bot_state.conv_hist = {
        "find_care_agent": []
    }

    bot_state.errors_care = []
    bot_state.diagnosis_list = ['Disease 1', 'Disease 2', 'Disease 3']
    bot_state.treatment_plans_seen = ['1']
    bot_state.treatment_plans = {'1': '<html><body><p>Disease 1</p></body></html>'}

    bot_state.specialist.inventory_name = 'Generalist'
    bot_state.ip_address = '8.8.8.8'
    bot_state.address = None

    llm = Mock()
    llm.return_value = AIMessage(content='', additional_kwargs={"function_call": {
        'name': 'find_care_address_tool',
        'arguments': json.dumps({'address': 'Oslo, Norway'})
    }})

    find_care_agent = FindCareAgent(bot_state, llm, profile={'isLoggedIn': True})
    FindCareAgent.care_provider_renderer = care_provider_renderer

    find_care_agent.act()

    bot_state.next_agent.assert_called_once_with(name=ConciergeAgent.name, reset_hist=True)
    assert len(bot_state.conv_hist['find_care_agent']) == 3
    care_provider_renderer.render.assert_called_once()
    assert care_provider_renderer.render.call_args[0][0].search_terms == ['generalist', 'disease 1', 'near Oslo, Norway']
    assert bot_state.errors_care == []


def test_find_care_agent_with_abbreviated_dx():
    bot_state = Mock()
    care_provider_renderer = Mock()
    care_provider_renderer.render.return_value = 'Care Providers'

    bot_state.patient_name = 'Dave'
    bot_state.conv_hist = {
        "find_care_agent": []
    }

    bot_state.errors_care = []
    bot_state.diagnosis_list = ['ATTENTION DEFICIT HYPERACTIVITY DISORDER (ADHD)', 'MAJOR DEPRESSIVE DISORDER (MDD)',
                                'GENERALIZED ANXIETY DISORDER (GAD)']
    bot_state.treatment_plans_seen = ['1']
    bot_state.specialist.inventory_name = 'Generalist'
    bot_state.treatment_plans = {'1': '<html><body><p>Disease 1</p></body></html>'}
    bot_state.address = None
    llm = Mock()
    llm.return_value = AIMessage(content='', additional_kwargs={"function_call": {
        'name': 'find_care_address_tool',
        'arguments': json.dumps({'address': 'Oslo, Norway'})
    }})

    find_care_agent = FindCareAgent(bot_state, llm, profile={'isLoggedIn': True})
    FindCareAgent.care_provider_renderer = care_provider_renderer

    find_care_agent.act()

    bot_state.next_agent.assert_called_once_with(name=ConciergeAgent.name, reset_hist=True)
    assert len(bot_state.conv_hist['find_care_agent']) == 3
    care_provider_renderer.render.assert_called_once()
    assert care_provider_renderer.render.call_args[0][0].search_terms == ['generalist',
                                                                          'attention deficit hyperactivity disorder', 'near Oslo, Norway']


def test_find_care_agent_failed():
    bot_state = Mock()
    care_provider_renderer = Mock()
    care_provider_renderer.render.side_effect = GooglePlaceCareProvider.GoogleFindCareException("test", 500)

    bot_state.patient_name = 'Dave'
    bot_state.username = 'test'
    bot_state.conv_hist = {
        "find_care_agent": []
    }

    bot_state.errors_care = []
    bot_state.diagnosis_list = ['Disease 1', 'Disease 2', 'Disease 3']
    bot_state.treatment_plans_seen = ['1']
    bot_state.specialist.inventory_name = 'Generalist'
    bot_state.address = None
    bot_state.treatment_plans = {'1': '<html><body><p>Disease 1</p></body></html>'}

    llm = Mock()
    llm.return_value = AIMessage(content='', additional_kwargs={"function_call": {
        'name': 'find_care_address_tool',
        'arguments': json.dumps({'address': 'Oslo, Norway'})
    }})
    find_care_agent = FindCareAgent(bot_state, llm, profile={'isLoggedIn': True})
    FindCareAgent.care_provider_renderer = care_provider_renderer

    find_care_agent.act()

    bot_state.next_agent.assert_called_once_with(name=FindCareAgent.name, reset_hist=False)
    assert bot_state.conv_hist['find_care_agent'][2] == AIMessage(content="Sorry, I couldn't find any care options for you. Please try again by providing another address.\n\n\n")
    care_provider_renderer.render.assert_called_once()
    assert bot_state.errors_care == ['GoogleFindCareException']


def test_find_care_agent_search_on_specialty_result():
    bot_state = Mock()
    care_provider_renderer = Mock()
    care_provider_renderer.render.side_effect = ['Care Providers']

    bot_state.patient_name = 'Dave'
    bot_state.conv_hist = {
        "find_care_agent": []
    }

    bot_state.errors_care = []
    bot_state.diagnosis_list = ['ATTENTION DEFICIT HYPERACTIVITY DISORDER (ADHD)', 'MAJOR DEPRESSIVE DISORDER (MDD)',
                                'GENERALIZED ANXIETY DISORDER (GAD)']
    bot_state.treatment_plans_seen = ['1']
    bot_state.specialist.inventory_name = 'Generalist'
    bot_state.treatment_plans = {'1': '<div><h2>Health Professional Referrals</h2><ul><li><b>Neurologist</b></li><li'
                                      '><b>Primary Care</b></li></ul><h2>Tests to Confirm '
                                      'Diagnosis</h2><ul><li><b>Laboratory Tests:</b></li></ul></div>'}
    bot_state.address = None

    llm = Mock()
    llm.return_value = AIMessage(content='', additional_kwargs={"function_call": {
        'name': 'find_care_address_tool',
        'arguments': json.dumps({'address': 'Oslo, Norway'})
    }})

    find_care_agent = FindCareAgent(bot_state, llm, profile={'isLoggedIn': True})
    FindCareAgent.care_provider_renderer = care_provider_renderer

    find_care_agent.act()

    care_provider_renderer.render.assert_called_once()
    assert care_provider_renderer.render.call_args[0][0].search_terms == ['neurologist',
                                                                          'attention deficit hyperactivity disorder',
                                                                          'near Oslo, Norway']
    assert bot_state.conv_hist['find_care_agent'][2] == AIMessage(content='Care Providers\n\n\n')


def test_find_care_agent_search_on_specialty_no_result_fallback_primary_care():
    bot_state = Mock()
    care_provider_renderer = Mock()
    care_provider_renderer.render.side_effect = ['', 'Care Providers']

    bot_state.patient_name = 'Dave'
    bot_state.conv_hist = {
        "find_care_agent": []
    }

    bot_state.errors_care = []
    bot_state.diagnosis_list = ['ATTENTION DEFICIT HYPERACTIVITY DISORDER (ADHD)', 'MAJOR DEPRESSIVE DISORDER (MDD)',
                                'GENERALIZED ANXIETY DISORDER (GAD)']
    bot_state.treatment_plans_seen = ['1']
    bot_state.specialist.inventory_name = 'Generalist'
    bot_state.treatment_plans = {'1': '<div><h2>Health Professional Referrals</h2><ul><li><b>Neurologist</b></li><li'
                                      '><b>Primary Care</b></li></ul><h2>Tests to Confirm '
                                      'Diagnosis</h2><ul><li><b>Laboratory Tests:</b></li></ul></div>'}
    bot_state.address = None

    llm = Mock()
    llm.return_value = AIMessage(content='', additional_kwargs={"function_call": {
        'name': 'find_care_address_tool',
        'arguments': json.dumps({'address': 'Oslo, Norway'})
    }})

    find_care_agent = FindCareAgent(bot_state, llm, profile={'isLoggedIn': True})
    FindCareAgent.care_provider_renderer = care_provider_renderer

    find_care_agent.act()

    assert care_provider_renderer.render.call_count == 2
    [call1, call2] = care_provider_renderer.render.call_args_list
    assert call1[0][0].search_terms == ['neurologist', 'attention deficit hyperactivity disorder', 'near Oslo, Norway']
    assert call2[0][0].search_terms == ['attention deficit hyperactivity disorder', 'doctor', 'near Oslo, Norway']
    assert bot_state.conv_hist['find_care_agent'][2] == AIMessage(content='Care Providers\n\n\n')


def test_find_care_agent_search_on_specialty_no_result_fallback_primary_care_no_result():
    bot_state = Mock()
    care_provider_renderer = Mock()
    care_provider_renderer.render.side_effect = ['', '']

    bot_state.patient_name = 'Dave'
    bot_state.conv_hist = {
        "find_care_agent": []
    }

    bot_state.errors_care = []
    bot_state.diagnosis_list = ['ATTENTION DEFICIT HYPERACTIVITY DISORDER (ADHD)', 'MAJOR DEPRESSIVE DISORDER (MDD)',
                                'GENERALIZED ANXIETY DISORDER (GAD)']
    bot_state.treatment_plans_seen = ['1']
    bot_state.specialist.inventory_name = 'Generalist'
    bot_state.treatment_plans = {'1': '<div><h2>Health Professional Referrals</h2><ul><li><b>Neurologist</b></li><li'
                                      '><b>Primary Care</b></li></ul><h2>Tests to Confirm '
                                      'Diagnosis</h2><ul><li><b>Laboratory Tests:</b></li></ul></div>'}
    bot_state.address = None
    llm = Mock()
    llm.return_value = AIMessage(content='', additional_kwargs={"function_call": {
        'name': 'find_care_address_tool',
        'arguments': json.dumps({'address': 'Oslo, Norway'})
    }})

    find_care_agent = FindCareAgent(bot_state, llm, profile={'isLoggedIn': True})
    FindCareAgent.care_provider_renderer = care_provider_renderer

    find_care_agent.act()

    assert care_provider_renderer.render.call_count == 2
    [call1, call2] = care_provider_renderer.render.call_args_list
    assert call1[0][0].search_terms == ['neurologist', 'attention deficit hyperactivity disorder', 'near Oslo, Norway']
    assert call2[0][0].search_terms == ['attention deficit hyperactivity disorder', 'doctor', 'near Oslo, Norway']
    assert bot_state.conv_hist['find_care_agent'][2] == AIMessage(content="Sorry, I couldn't find any care options for you. Please try again by providing another address.\n\n\n")


def test_find_care_agent_search_if_tx_care_is_not_bold():
    bot_state = Mock()
    care_provider_renderer = Mock()
    care_provider_renderer.render.side_effect = ['Care Providers']

    bot_state.patient_name = 'Dave'
    bot_state.conv_hist = {
        "find_care_agent": []
    }

    bot_state.errors_care = []
    bot_state.diagnosis_list = ['ATTENTION DEFICIT HYPERACTIVITY DISORDER (ADHD)', 'MAJOR DEPRESSIVE DISORDER (MDD)',
                                'GENERALIZED ANXIETY DISORDER (GAD)']
    bot_state.treatment_plans_seen = ['1']
    bot_state.specialist.inventory_name = 'Generalist'
    bot_state.treatment_plans = {'1': '<div><h2>Health Professional Referrals</h2><ul><li><b>Neurologist</b></li><li'
                                      '><b>Primary Care</b></li>'
                                      '<li>Rheuatologist</li>'
                                      '</ul>'
                                      '<h2>Tests to Confirm '
                                      'Diagnosis</h2><ul><li><b>Laboratory Tests:</b></li></ul></div>'}
    bot_state.address = None

    llm = Mock()
    llm.return_value = AIMessage(content='', additional_kwargs={"function_call": {
        'name': 'find_care_address_tool',
        'arguments': json.dumps({'address': 'Oslo, Norway'})
    }})

    find_care_agent = FindCareAgent(bot_state, llm, profile={'isLoggedIn': True})
    FindCareAgent.care_provider_renderer = care_provider_renderer

    find_care_agent.act()

    care_provider_renderer.render.assert_called_once()
    [call1] = care_provider_renderer.render.call_args_list
    assert call1[0][0].search_terms == ['neurologist', 'rheuatologist', 'attention deficit hyperactivity disorder', 'near Oslo, Norway']
    assert bot_state.conv_hist['find_care_agent'][2] == AIMessage(content='Care Providers\n\n\n')
