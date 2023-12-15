import json

from langchain.schema import AIMessage

from src import agents
from src.bot import Bot
from src.tests.utils import ask, setup
from src.utils import fake_llm


def init():
    bot = Bot(username='test')

    bot.state.next_agent(name=agents.NameEnquiryAgent.name)
    assert bot.state.current_agent_name == agents.NameEnquiryAgent.name, \
        "Should have moved to NameEnquiryAgent"

    # first message
    bot = ask(bot)
    assert bot.state.current_agent_name == agents.NameEnquiryAgent.name, \
        "Should have stayed in NameEnquiryAgent"
    assert "Before I ask you a few questions, what should I call you?" in \
           bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have asked for the user's name"

    return bot


def test_name_enquiry(setup):
    bot = init()

    # entering name not captured properly
    fake_llm.responses += [json.dumps({
        "name": "N/A"
    })]
    bot = ask(bot)
    assert bot.state.current_agent_name == agents.NameEnquiryAgent.name, \
        "Should have stayed in NameEnquiryAgent"
    assert "I'm sorry, but I didn't get your name. Can you please provide it again?" in \
        bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have asked for the user's name again"

    # entering name captured properly
    fake_llm.responses += [json.dumps({
        "name": "John"
    })]
    # Adding a mock for act method of FollowupAgent
    bot.agents[bot.state.agent_names.index(
        agents.FollowupAgent.name)].act = lambda: True
    bot = ask(bot, 'John')
    assert bot.state.patient_name == 'John', \
        "Name should be set in the bot state"
    assert bot.state.current_agent_name == agents.FollowupAgent.name, \
        "Should have moved to FollowupAgent"
    assert "Good to meet you, John! My goal" in \
        bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have thanked the user for sharing their name"
    
def test_name_capture_not_happening(setup):
    bot = init()

    # entering name not captured properly try 1
    fake_llm.responses += ['{}']
    bot = ask(bot)
    assert "I'm sorry" in \
        bot.full_conv_hist.full_conv_hist[-1]['content']
    
    # entering name not captured properly try 2
    fake_llm.responses += [json.dumps({
        'name': "N/A"
    })]
    bot = ask(bot)
    assert "I'm sorry" in \
        bot.full_conv_hist.full_conv_hist[-1]['content']
    
    # entering name not captured properly try 3
    fake_llm.responses += ['{}']
    # Adding a mock for act method of FollowupAgent
    bot.agents[bot.state.agent_names.index(
        agents.FollowupAgent.name)].act = lambda: True
    bot = ask(bot)
    assert bot.state.patient_name == ' '
    assert "Good to meet you,  !" in bot.full_conv_hist.full_conv_hist[-1]['content']
    assert bot.state.current_agent_name == agents.FollowupAgent.name, \
        "Should have moved to FollowupAgent"

def test_existing_user_greeting(setup):
    bot = Bot(username='test')
    bot.state.patient_name = 'John'
    bot.state.next_agent(name=agents.NameEnquiryAgent.name)
    assert bot.state.current_agent_name == agents.NameEnquiryAgent.name, \
        "Should have moved to NameEnquiryAgent"

    # first message
    # Adding a mock for act method of FollowupAgent
    bot.agents[bot.state.agent_names.index(
        agents.FollowupAgent.name)].act = lambda: True
    bot = ask(bot)
    assert "John, my goal" in bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should have greeted the user by name"
    assert bot.state.current_agent_name == agents.FollowupAgent.name, \
        "Should have moved to FollowupAgent"

