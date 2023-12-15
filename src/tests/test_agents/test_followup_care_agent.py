import json
from datetime import datetime

from langchain.schema import AIMessage

from src import agents
from src.bot import Bot
from src.followup.followup_care_state import FollowUpCareState, FollowupState
from src.tests.utils import ask, setup
from src.utils import fake_llm, MongoDBClient


def init_followup_care():
    bot = Bot(username='test')

    bot.state.next_agent(name=agents.FollowupCareAgent.name)
    bot.state.patient_name = 'John Doe'
    bot.state.chief_complaint = 'Toothache'
    bot.state.conv_hist[agents.MagicMinuteAgent.name] = [
        AIMessage(
            content='- You have come to me regarding your toothache.\n- And other stuff...')
    ]

    MongoDBClient.get_followup_care().insert_one({
        'name': 'John Doe',
        'chief_complaint': 'Toothache',
        'convo_id': bot.state.username,
        'user_id': 'test_user_id_1',
        'state': 'new',
        'is_locked': False,
        'next_followup_date': datetime(2024, 2, 13),
    })

    # Asking 4 question
    for i in range(4):
        fake_llm.responses += [f'Mock response {i}']
        bot = ask(bot)

        if i == 0:
            assert '<b><u>CodyMD Check-In' in bot.full_conv_hist.full_conv_hist[-1]['content'], \
                "Should add the header to the response"
        assert f'Mock response {i}' in bot.full_conv_hist.full_conv_hist[-1]['content']
        assert f'Mock response {i}' in bot.state.conv_hist[agents.FollowupCareAgent.name][-1].content, \
            "Should save the response in the conversation history"
        assert len(bot.state.conv_hist[agents.FollowupCareAgent.name]) == (i + 1) * 2
    return bot


def test_followup_care_status_all_better(setup):
    bot = init_followup_care()

    # Faking the user's response  
    fake_llm.responses += [json.dumps({
        'guidance': 'specific guidance',
        'status_of_problem': 'all_better'
    })]
    bot = ask(bot)
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith('specific guidance')
    assert bot.state.current_agent_name == agents.ConciergeAgent.name

    state = FollowUpCareState(convo_id=bot.state.username)

    assert state.is_locked is False
    assert state.state == FollowupState.RESOLVED
    assert state.next_followup_date is None
    assert state.last_followup_outcome == 'all_better'


def test_followup_care_status_healing_as_expected(setup):
    bot = init_followup_care()

    # Faking the user's response  
    fake_llm.responses += [json.dumps({
        'guidance': 'specific guidance',
        'status_of_problem': 'healing_as_expected'
    })]
    bot = ask(bot)
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith('specific guidance')
    assert bot.state.current_agent_name == agents.ConciergeAgent.name

    state = FollowUpCareState(convo_id=bot.state.username)

    assert state.is_locked is False
    assert state.state == FollowupState.NEW
    assert state.next_followup_date == datetime(2024, 2, 13, 0, 0)
    assert state.last_followup_outcome == 'healing_as_expected'


def test_followup_care_status_not_healing_as_expected(setup):
    bot = init_followup_care()

    # Faking the user's response  
    fake_llm.responses += [json.dumps({
        'guidance': 'specific guidance',
        'status_of_problem': 'not_healing_as_expected'
    })]
    bot = ask(bot)
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith('specific guidance')
    assert bot.state.current_agent_name == agents.ConciergeAgent.name

    state = FollowUpCareState(convo_id=bot.state.username)

    assert state.is_locked is False
    assert state.state == FollowupState.NEW
    assert state.next_followup_date == datetime(2024, 2, 13, 0, 0)
    assert state.last_followup_outcome == 'not_healing_as_expected'


def test_followup_care_json_empty(setup):
    bot = init_followup_care()

    # Faking the user's response  
    fake_llm.responses += [json.dumps({})]
    bot = ask(bot)
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].startswith('I hope you feel better soon.')
    assert bot.state.current_agent_name == agents.ConciergeAgent.name

    state = FollowUpCareState(convo_id=bot.state.username)

    assert state.is_locked is False
    assert state.state == FollowupState.NEW
    assert state.next_followup_date == datetime(2024, 2, 13, 0, 0)
    assert state.last_followup_outcome == 'not_healing_as_expected'
