import json

from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup

from src.bot import Bot
from src import agents
from src.utils import fake_llm
from src.tests.utils import ask, setup

def test_router_agent(setup):
    bot = Bot(username='test')

    bot.state.next_agent(name=agents.RouterAgent.name)

    # Faking a speciality and sub-speciality
    fake_llm.responses += ['', '']
    fake_llm.additional_kwargs.put({'function_call': {
        'name': 'categorize_chief_complaint',
        'arguments': json.dumps({'specialist': 'Dentist'})
    }})
    fake_llm.additional_kwargs.put({'function_call': {
        'name': 'categorize_chief_complaint',
        'arguments': json.dumps({'sub_speciality': 'Toothache', 'is_disease_name': True})
    }})
    bot = ask(bot)

    assert bot.state.specialist == Specialist.Dentist
    assert bot.state.subSpecialty == SubSpecialtyDxGroup.Toothache
    assert bot.state.current_agent_name == agents.NameEnquiryAgent.name

    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith("Thanks for confirming!")

def test_router_agent_where_cc_is_not_a_disease(setup):
    bot = Bot(username='test')

    bot.state.next_agent(name=agents.RouterAgent.name)

    # Faking a speciality and sub-speciality
    fake_llm.responses += ['', '']
    fake_llm.additional_kwargs.put({'function_call': {
        'name': 'categorize_chief_complaint',
        'arguments': json.dumps({'specialist': 'Dentist'})
    }})
    fake_llm.additional_kwargs.put({'function_call': {
        'name': 'categorize_chief_complaint',
        'arguments': json.dumps({'sub_speciality': 'Toothache', 'is_disease_name': False})
    }})
    bot = ask(bot)

    assert bot.state.specialist == Specialist.Dentist
    assert bot.state.subSpecialty == SubSpecialtyDxGroup.Generalist
    assert bot.state.current_agent_name == agents.NameEnquiryAgent.name

    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith("Thanks for confirming!")

def test_router_agent_without_function_call(setup):
    bot = Bot(username='test')

    bot.state.next_agent(name=agents.RouterAgent.name)

    # Faking a speciality and sub-speciality
    fake_llm.responses += ['']
    bot = ask(bot)

    assert bot.state.specialist == Specialist.Generalist
    assert bot.state.subSpecialty == SubSpecialtyDxGroup.Generalist
    assert bot.state.current_agent_name == agents.NameEnquiryAgent.name

    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith("Thanks for confirming!")

def test_router_agent_no_routing_if_specialist_known(setup):
    bot = Bot(username='test', profile={'character': 'anxiety'})

    bot.state.next_agent(name=agents.RouterAgent.name)

    bot = ask(bot)

    assert bot.state.specialist == Specialist.Psychiatrist
    assert bot.state.subSpecialty == SubSpecialtyDxGroup.Anxiety
    assert bot.state.current_agent_name == agents.NameEnquiryAgent.name