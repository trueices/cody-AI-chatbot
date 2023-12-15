import json

from src import agents
from src.agents.utils import load_priority_fields
from src.bot import Bot
from src.bot_state import BotState
from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup
from src.tests.utils import ask, compare_state_dicts, setup
from src.utils import fake_llm

all_priority_fields = list(load_priority_fields(
    Specialist.Neurologist, SubSpecialtyDxGroup.Generalist)[0])

"""
Sub specialists:
"""


def test_sub_speciality_end_to_end(setup):
    bot = Bot(username='test')

    bot.state.subSpecialty = SubSpecialtyDxGroup.ParkinsonsDisease
    bot.state.next_agent(name=agents.FollowupAgent.name)
    assert bot.state.current_agent_name == agents.FollowupAgent.name

    # First message requires just the initial question call
    fake_llm.responses += [
        json.dumps({
            'thought': '_',
            'fields_answered': [],
            'next_field': 'Diagnosed with Parkinson\'s Disease',
            'question': 'que 1',
        })]
    bot = ask(bot)
    assert 'que 1' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Field filled for the first question
    fake_llm.responses += [
        json.dumps({
            'thought': '_',
            'fields_answered': ['Diagnosed with Parkinson\'s Disease'],
            'next_field': 'Diagnosed with other Neurologic Conditions',
            'question': 'que 2',
        }),
        'formatted que 2'
    ]
    bot = ask(bot)
    assert bot.state.priority_fields_asked == [
        'diagnosed with parkinson\'s disease']
    assert 'formatted que 2' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Field not filled for the second question
    fake_llm.responses += [
        json.dumps({
            'thought': '_',
            'fields_answered': [],
            'next_field': 'Diagnosed with other Neurologic Conditions',
            'question': 'que 3',
        }),
        'formatted que 3'
    ]
    bot = ask(bot)
    # only the first priority field should be present here.
    assert bot.state.priority_fields_asked == [
        'diagnosed with parkinson\'s disease']
    assert 'formatted que 3' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # A lot of the priority fields are filled
    fake_llm.responses += [
        json.dumps({
            'thought': '_',
            'fields_answered': ['Diagnosed with Parkinson\'s Disease',
                                'Diagnosed with other Neurologic Conditions',
                                'Tremor',
                                'Year of birth',
                                'Sex',
                                'Slowness of movement',
                                'Muscle Rigidity',
                                'Change in Balance',
                                'Changes in how you walk',
                                'Handwriting Changes',
                                'Facial Expression changes',
                                'Voice Changes',
                                'Muscle Aches',
                                'Difficulty sleeping',
                                'Light headed',
                                'Mood changes',
                                'Thinking changes'],
            'next_field': 'Low blood pressure',
            'question': 'que 4',
        }),
        # Adding confidence score, after min score threshold is reached
        json.dumps({
            'diagnosis': '_',
            'confidence_score': 10,
            'thought': '_',
        }),
        'formatted que 4',
    ]
    bot = ask(bot)
    assert len(bot.state.priority_fields_asked) == 17
    assert 'formatted que 4' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # All fields asked
    fake_llm.responses += [
        json.dumps({
            'thought': '_',
            'fields_answered': ['Low blood pressure'],
            'next_field': '',
            'question': '',
        }),
        'magic minute output',
        'diagnosis output',
    ]
    bot = ask(bot)
    assert len(bot.state.priority_fields_asked) == 18
    assert bot.state.current_agent_name == agents.ConciergeAgent.name

    # Making sure that nothing is broken in the conv_hist
    for conv in bot.full_conv_hist.full_conv_hist:
        assert 'Sorry' not in conv['content']


def test_timeout_sub_speciality(setup):
    bot = Bot(username='test')

    bot.state.subSpecialty = SubSpecialtyDxGroup.ParkinsonsDisease
    bot.state.next_agent(name=agents.FollowupAgent.name)
    assert bot.state.current_agent_name == agents.FollowupAgent.name

    # First message requires just the initial question call
    fake_llm.responses += [
        json.dumps({
            'thought': '_',
            'fields_answered': [],
            'next_field': 'Diagnosed with Parkinson\'s Disease',
            'question': 'que 1',
        })
    ]
    bot = ask(bot)
    assert len(bot.state.conv_hist[agents.FollowupAgent.name]) == 1
    assert 'que 1' in bot.full_conv_hist.full_conv_hist[-1]['content']
    # Creating the initial state to compare with timeout state
    initial_bot_state = bot.state.dict().copy()

    # Test 1: Timeout on first API call
    fake_llm.responses += [
        'Timeout',
    ]
    bot = ask(bot)
    compare_state_dicts(initial_bot_state, bot.state.dict())
    assert 'Sorry, that took too long to process for us.' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Test 2: First API call passes, but conversation agent call fails
    fake_llm.responses += [
        json.dumps({
            'thought': '_',
            'fields_answered': ['Diagnosed with Parkinson\'s Disease'],
            'next_field': 'Diagnosed with other Neurologic Conditions',
            'question': 'que 2',
        }),
        'Timeout',
    ]
    bot = ask(bot)
    compare_state_dicts(initial_bot_state, bot.state.dict())
    assert 'Sorry, that took too long to process for us.' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Test 3: Confidence score API call fails
    fake_llm.responses += [
        json.dumps({
            'thought': '_',
            'fields_answered': ['Diagnosed with Parkinson\'s Disease',
                                'Diagnosed with other Neurologic Conditions',
                                'Tremor',
                                'Year of birth',
                                'Sex',
                                'Slowness of movement',
                                'Muscle Rigidity',
                                'Change in Balance',
                                'Changes in how you walk',
                                'Handwriting Changes',
                                'Facial Expression changes',
                                'Voice Changes',
                                'Muscle Aches',
                                'Difficulty sleeping',
                                'Light headed',
                                'Mood changes',
                                'Thinking changes'],
            'next_field': 'Low blood pressure',
            'question': 'que 4',
        }),
        'Timeout',
    ]
    bot = ask(bot)
    compare_state_dicts(initial_bot_state, bot.state.dict())
    assert 'Sorry, that took too long to process for us.' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Test 4: All API calls pass
    fake_llm.responses += [
        json.dumps({
            'thought': '_',
            'fields_answered': ['Diagnosed with Parkinson\'s Disease',
                                'Diagnosed with other Neurologic Conditions',
                                'Tremor',
                                'Year of birth',
                                'Sex',
                                'Slowness of movement',
                                'Muscle Rigidity',
                                'Change in Balance',
                                'Changes in how you walk',
                                'Handwriting Changes',
                                'Facial Expression changes',
                                'Voice Changes',
                                'Muscle Aches',
                                'Difficulty sleeping',
                                'Light headed',
                                'Mood changes',
                                'Thinking changes'],
            'next_field': 'Low blood pressure',
            'question': 'que 4',
        }),
        # Adding confidence score, after min score threshold is reached
        json.dumps({
            'diagnosis': '_',
            'confidence_score': 95,
            'thought': '_',
        }),
        'formatted que 4',
    ]
    bot = ask(bot)
    assert 'Sorry, that took too long to process for us.' not in bot.full_conv_hist.full_conv_hist[-1]['content']


def test_key_error_handling_sub_specialist(setup):
    bot = Bot(username='test')
    bot.state.subSpecialty = SubSpecialtyDxGroup.ParkinsonsDisease
    bot.state.next_agent(name=agents.FollowupAgent.name)
    assert bot.state.current_agent_name == agents.FollowupAgent.name

    # First message without the "priority_fields_asked" field
    fake_llm.responses += [
        json.dumps({})]
    bot = ask(bot)
    assert bot.full_conv_hist.full_conv_hist[-1]['content'].split('\n\n\n')[-1] == '', \
        'Should have asked the question without any errors.'


def test_early_exit(setup):
    bot = Bot(username='test')

    bot.state.subSpecialty = SubSpecialtyDxGroup.ParkinsonsDisease
    bot.state.next_agent(name=agents.FollowupAgent.name)
    assert bot.state.current_agent_name == agents.FollowupAgent.name

    # First message requires just the initial question call
    fake_llm.responses += [
        json.dumps({
            'thought': '_',
            'fields_answered': [],
            'next_field': 'Diagnosed with Parkinson\'s Disease',
            'question': 'que 1',
        })]
    bot = ask(bot)
    assert 'que 1' in bot.full_conv_hist.full_conv_hist[-1]['content']
    assert bot.state.current_agent_name == agents.FollowupAgent.name

    # Early exit
    fake_llm.responses += [
        'magic minute output',
        'diagnosis output',
    ]
    bot = ask(bot, message='go')
    assert bot.state.current_agent_name == agents.ConciergeAgent.name


def test_too_many_conversations(setup):
    bot = Bot(username='test')

    bot.state.subSpecialty = SubSpecialtyDxGroup.ParkinsonsDisease
    bot.state.next_agent(name=agents.FollowupAgent.name)
    assert bot.state.current_agent_name == agents.FollowupAgent.name

    # First message requires just the initial question call
    fake_llm.responses += [
        json.dumps({
            'thought': '_',
            'fields_answered': [],
            'next_field': 'Diagnosed with Parkinson\'s Disease',
            'question': 'que 1',
        })]
    bot = ask(bot)
    assert 'que 1' in bot.full_conv_hist.full_conv_hist[-1]['content']
    assert bot.state.current_agent_name == agents.FollowupAgent.name

    # Multiple conversations
    for _ in range(100):
        assert bot.state.current_agent_name == agents.FollowupAgent.name
        fake_llm.responses += [
            json.dumps({
                'thought': '_',
                'fields_answered': [],
                'next_field': 'Diagnosed with Parkinson\'s Disease',
                'question': 'que 1',
            }),
            'formatted que 1']
        bot = ask(bot)
        if bot.state.current_agent_name != agents.FollowupAgent.name:
            break
    assert len(bot.state.conv_hist[agents.FollowupAgent.name]) == 40


"""
Specialists:
"""


def test_convo_training(setup):
    from unittest.mock import patch
    from langchain.schema import AIMessage

    bot = Bot(username='test')
    bot.state.next_agent(name=agents.FollowupAgent.name)
    assert bot.state.current_agent_name == agents.FollowupAgent.name
    followup_agent: agents.FollowupAgent = bot.agents[bot.state.current_agent_index]

    with patch('random.random') as mock_random:
        mock_random.return_value = 0  # Triggering the training

        # First message
        followup_agent.convo_training()
        assert len(bot.state.conv_train_msgs) == 1
        assert bot.full_conv_hist.full_conv_hist[-1]['content'].endswith(
            f'{bot.state.conv_train_msgs[0]}\n\n\n')

        # Second message
        followup_agent.conv_hist[:] = [AIMessage(content='q1')]
        followup_agent.convo_training()
        assert len(bot.state.conv_train_msgs) == 2
        assert bot.full_conv_hist.full_conv_hist[-1]['content'].endswith(
            f'{bot.state.conv_train_msgs[1]}\n\n\n')
        assert bot.state.conv_train_msgs[0] != bot.state.conv_train_msgs[1], "Training messages should be different"

        # No more training messages
        followup_agent.conv_hist[:] = [AIMessage(content='q1')]*3
        followup_agent.convo_training()
        assert len(bot.state.conv_train_msgs) == 2

    with patch('random.random') as mock_random:
        mock_random.return_value = 1  # Not triggering training
        followup_agent.convo_training()
        assert len(bot.state.conv_train_msgs) == 2
