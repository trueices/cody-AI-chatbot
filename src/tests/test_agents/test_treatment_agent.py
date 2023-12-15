import os

import requests_mock

from src import agents
from src.bot import Bot
from src.tests.utils import ask, setup
from src.utils import fake_llm


def init():
    bot = Bot(username='test')
    bot.state.patient_name = 'test'
    bot.state.diagnosis_list = ['disease 1', 'disease 2', 'disease 3']

    bot.state.next_agent(name=agents.TreatmentAgent.name)
    assert bot.state.current_agent_name == agents.TreatmentAgent.name

    bot = ask(bot)
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert last_msg.startswith(
        "Ok, to view a treatment plan enter the number of the diagnosis.")
    assert "1. Disease 1" in last_msg
    assert "2. Disease 2" in last_msg
    assert "3. Disease 3" in last_msg
    return bot


def test_treatment_agent_options_basic(setup):
    bot = init()

    with requests_mock.Mocker() as req_mock:
        req_mock.post('https://google.serper.dev/search', json={})

        # Selecting invalid disease number
        bot = ask(bot, '4')
        assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'Please select a valid disease number.'
        assert bot.state.current_agent_name == agents.TreatmentAgent.name

        # Entering gibberish
        fake_llm.responses += ['{"option": 0}']
        bot = ask(bot, 'gibberish')
        assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'Please type a valid option to view a treatment plan.'
        assert bot.state.current_agent_name == agents.TreatmentAgent.name

        # Selecting the 2nd disease
        fake_llm.responses += ['Treatment for disease 2']
        bot = ask(bot, '2')
        assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith(
            "<div class='tx-plan'>Treatment for disease 2</div>"), 'Treatment plan not generated correctly'
        assert bot.state.treatment_plans_seen == [2]
        assert bot.state.treatment_plans['2'] == "<div class='tx-plan'>Treatment for disease 2</div>"
        assert bot.state.concierge_option == 'find_care'
        assert bot.state.current_agent_name == agents.ConciergeAgent.name

        # Now, selecting the 2nd disease again
        bot = ask(bot, '3')  # Going into the treatment agent
        assert bot.state.current_agent_name == agents.TreatmentAgent.name
        bot = ask(bot, '2')  # Selecting the 2nd disease
        assert bot.state.current_agent_name == agents.ConciergeAgent.name
        last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
        assert last_msg.startswith("<div class='tx-plan'>Treatment for disease 2</div>")
        assert bot.state.treatment_plans_seen == [2]
        bot = ask(bot, '3')  # Going into the treatment agent
        # Now, lets see all treatment plans, and check the bot response.
        fake_llm.responses += ['Treatment for disease 1']
        bot = ask(bot, '1')  # Selecting the 1st disease
        assert "3. Show me treatment plans for other conditions" in \
            bot.full_conv_hist.full_conv_hist[-1]['content']
        # selecting option to show treatment plans for other diseases
        bot = ask(bot, '3')
        assert bot.state.current_agent_name == agents.TreatmentAgent.name
        fake_llm.responses += ['Treatment for disease 3']
        bot = ask(bot, '3')  # Selecting the 3rd disease
        assert "3. Show me treatment plans for other conditions" in \
            bot.full_conv_hist.full_conv_hist[-1]['content']
        # selecting option to show treatment plans for other diseases
        bot = ask(bot, '3')
        bot = ask(bot, '3')  # Selecting the 3rd disease
        last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
        assert last_msg.startswith(
            "<div class='tx-plan'>Treatment for disease 3</div>")
        assert bot.state.concierge_option == 'find_care'


def test_treatment_agent_options_basic_via_llm(setup):
    bot = init()

    with requests_mock.Mocker() as req_mock:
        req_mock.post('https://google.serper.dev/search', json={})

        fake_llm.responses += ['{"option_number": "string"}']
        bot = ask(bot, 'confusing llm')
        assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'Please type a valid option to view a treatment plan.'
        assert bot.state.current_agent_name == agents.TreatmentAgent.name

        fake_llm.responses += ['non json response']
        bot = ask(bot, 'confusing llm non json')
        assert bot.full_conv_hist.full_conv_hist[-1]['content'] == 'Please type a valid option to view a treatment plan.'
        assert bot.state.current_agent_name == agents.TreatmentAgent.name

        fake_llm.responses += ['{"option_number": 1}']
        fake_llm.responses += ['Treatment for disease 1']
        bot = ask(bot, 'show first tx plan')
        assert "3. Show me treatment plans for other conditions" in \
            bot.full_conv_hist.full_conv_hist[-1]['content']
        assert "Treatment for disease 1" in bot.full_conv_hist.full_conv_hist[-1]['content']

        assert bot.state.current_agent_name == agents.ConciergeAgent.name


def test_treatment_agent_options_options(setup):
    bot = init()

    # entering options
    bot = ask(bot, 'options')
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert bot.state.concierge_option == 'detailed'
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert "What should we do next?" in last_msg
    assert f"""<a class="text-blue underline app-link" href="/register">Save our conversation.</a>""" in last_msg


def test_treatment_agent_for_references(setup):
    os.environ['SERPER_API_KEY'] = 'test'
    bot = init()

    # Selecting the 2nd disease
    fake_llm.responses += ['Treatment for disease 2']
    with requests_mock.Mocker() as req_mock:
        post = req_mock.post('https://google.serper.dev/search', json={'organic': [
            {'title': 'title 1', 'snippet': 'snippet 1',
             'link': 'https://www.mayoclinic.org/diseases-conditions/migraine-headache/diagnosis-treatment/drc-20360207',
             'date': 'Jul 7, 2023'}, {'title': 'title 2', 'snippet': 'snippet 2',
                                      'link': 'https://www.aafp.org/pubs/afp/issues/2018/0215/p243.html'}]})
        bot = ask(bot, '2')

    content_ = bot.full_conv_hist.full_conv_hist[-1]['content']

    assert content_.startswith(
        "<div class='tx-plan'>Treatment for disease 2"), 'Treatment plan not generated correctly'

    assert "<h2>Best disease 2 treatment references for you:</h2>" in content_
    assert "<p>\nJul 7, 2023\n<br>\nwww.mayoclinic.org\n<br>\nsnippet 1\n</p>" in content_
    assert "<p>\nwww.aafp.org\n<br>\nsnippet 2\n</p>" in content_

    assert post.call_count == 1
    assert post.last_request.query == "q=disease+2+treatment+for+patients&gl=us&hl=en&num=10"


def test_treatment_agent_for__no_references(setup):
    os.environ['SERPER_API_KEY'] = 'test'
    bot = init()

    # Selecting the 2nd disease
    fake_llm.responses += ['Treatment for disease 2']
    with requests_mock.Mocker() as req_mock:
        req_mock.post('https://google.serper.dev/search',
                      json={'organic': []})

        bot = ask(bot, '2')

    content_ = bot.full_conv_hist.full_conv_hist[-1]['content']

    assert content_.startswith(
        "<div class='tx-plan'>Treatment for disease 2</div>"), 'Treatment plan not generated correctly'

    assert "<h2>Best disease 2 treatment references for you:</h2>" not in content_


def test_treatment_agent_for_error_calling_serper(setup):
    os.environ['SERPER_API_KEY'] = 'test'
    bot = init()

    # Selecting the 2nd disease
    fake_llm.responses += ['Treatment for disease 2']
    with requests_mock.Mocker() as req_mock:
        req_mock.post('https://google.serper.dev/search', status_code=500)

        bot = ask(bot, '2')

    content_ = bot.full_conv_hist.full_conv_hist[-1]['content']

    assert content_.startswith(
        "<div class='tx-plan'>Treatment for disease 2</div>"), 'Treatment plan not generated correctly'

    assert "<h2>Best disease 2 treatment references for you:</h2>" not in content_
