import json

from src import agents
from src.bot import Bot
from src.tests.utils import ask, setup
from src.utils import fake_llm


def init():
    bot = Bot(username='test')
    bot.state.mode = 'existing_dx'
    bot.state.next_agent(name=agents.ExistingDiagnosisAgent.name)

    # Test capture of dx
    fake_llm.responses += [json.dumps({
        "disease_name": "diabetes"
    })]
    bot = ask(bot)
    assert bot.state.existing_dx == 'diabetes', \
        "Should have captured the disease name in the bot state"
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith("Here's how I can help you with your diabetes."), \
        "Should have shown the default message for the user"

    return bot


def test_tx_plan(setup):
    bot = init()

    # Test tx plan
    fake_llm.responses += ["You should take insulin."]
    bot = ask(bot, '1')
    assert 'You should take insulin.' in bot.state.existing_dx_tx, \
        "Should have captured the tx plan in the bot state"
    assert 'You should take insulin.' in bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have shown the tx plan to the user"
    assert bot.state.current_agent_name == agents.ExistingDiagnosisAgent.name, \
        "Should have stayed in ExistingDiagnosisAgent"
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].endswith("Continue our conversation or enter “Options”."), \
        "Should have shown the options to the user"

    # Test tx plan already captured (this time it shouldnt use the llm)
    bot = ask(bot, '1')
    assert 'You should take insulin.' in bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have shown the tx plan to the user"
    assert bot.state.current_agent_name == agents.ExistingDiagnosisAgent.name, \
        "Should have stayed in ExistingDiagnosisAgent"
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].endswith("Continue our conversation or enter “Options”."), \
        "Should have shown the options to the user"


def test_options(setup):
    bot = init()

    # Test options
    bot = ask(bot, "options")
    assert bot.state.current_agent_name == agents.NavigationAgent.name, \
        "Should have moved to NavigationAgent"
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith("We can work on a pressing problem."), \
        "Should have shown the options to the user"


def test_invalid_option(setup):
    bot = init()

    # Test invalid option
    bot = ask(bot, "4")
    assert bot.state.current_agent_name == agents.ExistingDiagnosisAgent.name, \
        "Should have stayed in ExistingDiagnosisAgent"
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith("I'm sorry, I didn't understand that."), \
        "Should have shown the invalid option message to the user"


def test_conv_agent(setup):
    bot = init()

    # Test conv agent
    bot = ask(bot, "3")
    assert bot.state.current_agent_name == agents.DxConversationAgent.name, \
        "Should have moved to DxConversationAgent"
    assert "What causes diabetes." in bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have shown option to chat about the diagnosis to the user"

    # Ask a question
    fake_llm.responses += ["Diabetes is ..."]
    bot = ask(bot, "What is diabetes?")
    assert bot.state.current_agent_name == agents.DxConversationAgent.name, \
        "Should have stayed in DxConversationAgent"
    assert "Diabetes is ..." in bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have shown the answer to the user"

    # Test options
    bot = ask(bot, "options")
    assert bot.state.current_agent_name == agents.ExistingDiagnosisAgent.name, \
        "Should have moved to ExistingDiagnosisAgent"
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith("Here's how I can help you with your diabetes."), \
        "Should have shown the options to the user"


def test_conv_agent_limit(setup):
    bot = init()

    # Enter conv agent
    bot = ask(bot, "3")
    assert bot.state.current_agent_name == agents.DxConversationAgent.name, \
        "Should have moved to DxConversationAgent"

    from langchain.schema import AIMessage
    # Test conv agent limit
    bot.state.conv_hist[agents.DxConversationAgent.name].extend(
        [AIMessage(content="Diabetes is ...")]*30)

    # Ask a question
    bot = ask(bot, "What is diabetes?")
    bot.full_conv_hist.full_conv_hist[-1]['content'].startswith("I'm afraid we have reached our conversation limit"), \
        "Should have shown the limit message to the user"
    assert bot.state.current_agent_name == agents.ExistingDiagnosisAgent.name, \
        "Should have moved to ExistingDiagnosisAgent"


def test_find_care(setup):
    bot = init()

    # Test find care
    fake_llm.responses += ["May I know the address?"]
    bot = ask(bot, "2")
    assert bot.state.current_agent_name == agents.FindCareAgent.name, \
        "Should have moved to FindCareAgent"
    assert "May I know the address?" in bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have asked for the address to the user"

    # Confirm address
    fake_llm.responses += ['']
    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'find_care_address_tool',
        'arguments': json.dumps({'address': 'jamshedpur'})
    }})
    from unittest.mock import Mock
    agents.FindCareAgent.care_provider_renderer = Mock()
    agents.FindCareAgent.care_provider_renderer.render.return_value = 'Care Providers'
    bot = ask(bot, 'jamshedpur')
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert last_msg.startswith('Care Providers\n\n\n')
    assert bot.state.current_agent_name == agents.ExistingDiagnosisAgent.name
    assert "Here's how I can help you with your diabetes." in last_msg, \
        "Should have shown the options to the user"
