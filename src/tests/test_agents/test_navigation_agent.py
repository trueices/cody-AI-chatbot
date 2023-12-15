import json

from langchain.schema import AIMessage

from src import agents
from src.bot import Bot
from src.tests.utils import ask, setup
from src.utils import fake_llm


def test_nav_health_problem(setup):
    bot = Bot(username='test')

    assert len(bot.get_conv_hist()) == 1, \
        "Conversation history should be initialized with the first message"

    fake_llm.responses += ['']
    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'capture_intent_tool',
        'arguments': json.dumps({'intent': 'symptom_or_suspected_condition'})
    }})

    fake_llm.responses += [json.dumps({
        "chief_complaint": "headache"
    })]
    fake_llm.responses += ['']
    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'categorize_chief_complaint',
        'arguments': json.dumps({'specialist': '_'})
    }})

    bot = ask(bot)

    assert bot.state.current_agent_name == agents.NameEnquiryAgent.name, \
        "Should have moved to NameEnquiryAgent"
    assert bot.state.chief_complaint == 'headache', \
        "Chief complaint should be set in the bot state"
    assert "Before I ask you a few questions, what should I call you?" in \
           bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have asked for the user's name"


def test_nav_existing_diagnosis(setup):
    bot = Bot(username='test')

    fake_llm.responses += ['']
    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'capture_intent_tool',
        'arguments': json.dumps({'intent': 'confirmed_condition'})
    }})
    fake_llm.responses += [json.dumps({
        "disease_name": "diabetes"
    })]
    bot = ask(bot)

    assert bot.state.existing_dx == 'diabetes', \
        "Should have captured the disease name in the bot state"
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith("Here's how I can help you with your diabetes."), \
        "Should have shown the default message for the user"
    assert bot.state.current_agent_name == agents.ExistingDiagnosisAgent.name, \
        "Should have moved to ExistingDiagnosisAgent"


def test_nav_question_agent(setup):
    bot = Bot(username='test')

    fake_llm.responses += ['', 'Answer to question.']
    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'capture_intent_tool',
        'arguments': json.dumps({'intent': 'health_related_question'})
    }})
    bot = ask(bot)
    assert bot.state.current_agent_name == agents.QuestionAgent.name, \
        "Should have moved to QuestionAgent"
    assert bot.full_conv_hist.full_conv_hist[-1][
               'content'] == 'Sure. Answer to question.\n\n\nContinue our conversation or enter “Options”.', \
        "Should have answered the question and have the keyword 'Sure' in the response"
    
    # test subsequent human response capture
    fake_llm.responses += ['']
    bot = ask(bot, message="my next question")
    assert bot.state.conv_hist[agents.QuestionAgent.name][-2].content == "my next question", \
        "Should have captured the user's response in the conversation history"


    # Test feedback capture
    fake_llm.responses += ['']
    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'capture_feedback_tool',
        'arguments': json.dumps({'feedback': 2})
    }})
    bot = ask(bot)
    assert bot.state.question_agent_feedback == 2, \
        "Feedback should be captured in the bot state"
    assert "Thank you" in bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have thanked the user for the feedback"

    # Test conversation limit
    bot.state.conv_hist[agents.QuestionAgent.name].extend([AIMessage(content='test')] * 24)
    bot = ask(bot)
    assert "I'm afraid we have reached our conversation limit for this session." in \
           bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have informed the user about the conversation limit"

    # Test exiting the conversation
    bot = ask(bot, message="options")
    assert bot.state.current_agent_name == agents.NavigationAgent.name, \
        "Should have moved to NavigationAgent"
    assert ("We can work on a pressing problem. Just tell me what’s wrong. You can say  “sinus pressure” or "
            "“I have a sore throat”.") in bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have shown the options"


def test_nav_too_long(setup):
    bot = Bot(username='test')

    assert len(bot.get_conv_hist()) == 1, \
        "Conversation history should be initialized with the first message"

    bot.state.conv_hist[agents.NavigationAgent.name].extend([AIMessage(content='test')] * 25)

    bot = ask(bot)
    assert "Unfortunately, I cant go any longer here." in bot.full_conv_hist.full_conv_hist[-1]['content']
    assert bot.state.current_agent_name == agents.NavigationAgent.name, \
        "Should have stayed in NavigationAgent"
