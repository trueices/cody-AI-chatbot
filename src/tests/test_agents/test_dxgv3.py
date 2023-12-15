import json

from src import agents
from src.agents.utils import load_priority_fields
from src.bot import Bot
from src.bot_state import BotState
from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup
from src.tests.utils import ask, compare_state_dicts, setup
from src.utils import fake_llm


def test_pattern_matching_for_pfs():
    from src.agents.followup_agent_new import DXGv3
    # Example usage:
    actual = ["apple", "orange", "kiwi", "banana"]
    generated = {"banane": 3, "iwi ": 9, "appl": 6, }
    mapping = DXGv3.pattern_matching(generated, actual)
    assert mapping == {"apple": 6, "kiwi": 9, "banana": 3}


def test_dxgv3_relevance(setup):
    bot = Bot(username='test')
    fake_llm.responses += [json.dumps({
        'reasoning': '_',
        'relevant': False,
    })]
    fields = load_priority_fields(specialist=Specialist.Neurologist,
                                  dx_group=SubSpecialtyDxGroup.Generalist,
                                  chief_complaint='headache')[0]
    updated_fields = agents.DXGv3.remove_irrelevant_fields(bot.state, fields)
    assert len(updated_fields) == len(fields) - 1, \
        "Expected one field to be removed, but got more or less"


all_priority_fields = list(load_priority_fields(
    Specialist.Neurologist, SubSpecialtyDxGroup.Generalist, 'headache')[0])


def init():
    bot = Bot(username='test')
    bot.state.chief_complaint = 'headache'
    bot.state.specialist = Specialist.Neurologist
    bot.state.next_agent(name=agents.FollowupAgent.name)
    assert bot.state.current_agent_name == agents.FollowupAgent.name
    return bot


def test_dxgv3_end_to_end(setup):
    bot = init()

    # Step 1: First question
    fake_llm.responses += [json.dumps({
        'reasoning': '_',
        'relevant': True,
    })]  # Relevance check
    fake_llm.responses += ['convo summary']  # followup summary
    fake_llm.responses += [json.dumps({
        "question": "Que 1"
    })]  # question generation
    bot = ask(bot)
    assert bot.state.priority_fields_asked == []
    assert 'Que 1' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Step 2: Field filled for the first question, asking 2nd question
    fake_llm.responses += ['convo summary']  # followup summary
    fake_llm.responses += [json.dumps({
        "details of headache": "pain in the head",
        all_priority_fields[-1]: "N/A"  # This should be not marked as filled
    })]  # pf check
    fake_llm.responses += [json.dumps({
        "question": 'Que 2'})
    ]  # question generation
    fake_llm.responses += [json.dumps({
        "response": 'natural response'
    })]  # fact check
    bot = ask(bot)
    assert all_priority_fields[-1] not in bot.state.priority_fields_asked, \
        f"Field {all_priority_fields[-1]} should not be marked as filled"
    assert bot.state.priority_fields_asked == [all_priority_fields[0]], \
        f"Only the first priority field should be present here. Got {bot.state.priority_fields_asked}"
    assert 'natural response.\n\n\nQue 2' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Step 3: All but one priority field asked. Here, we test confidence check
    fake_llm.responses += ['convo summary']  # followup summary
    fake_llm.responses += [json.dumps({
        field: "filled" for field in all_priority_fields if field != all_priority_fields[-1]
    })]  # pf check
    fake_llm.responses += [json.dumps({
        "question": 'Que 3'})
    ]  # question generation
    fake_llm.responses += [
        # Adding confidence score, after min score threshold is reached
        json.dumps({
            'diagnosis': '_',
            'confidence_score': 90,
            'thought': '_',
        }),
    ]
    fake_llm.responses += [json.dumps({
        "response": 'natural response'
    })]  # fact check
    bot = ask(bot)
    assert len(bot.state.priority_fields_asked) == 9
    assert all_priority_fields[-1] not in bot.state.priority_fields_asked, \
        f"Field {all_priority_fields[-1]} should not be marked as filled"
    assert 'natural response.\n\n\nQue 3' in bot.full_conv_hist.full_conv_hist[-1]['content']
    assert f'Ah, I see. I am now 90% confident of your Top 3 Condition List.' in bot.full_conv_hist.full_conv_hist[
        -1]['content']

    # Step 4: All priority fields asked
    fake_llm.responses += ['convo summary']  # followup summary
    fake_llm.responses += [json.dumps({
        field: "filled" for field in all_priority_fields
    })]  # pf check
    # Adding a mock for act method of MagicMinuteAgent
    bot.agents[bot.state.agent_names.index(
        agents.MagicMinuteAgent.name)].act = lambda: True
    bot = ask(bot)
    assert len(bot.state.priority_fields_asked) == 10
    assert bot.state.current_agent_name == agents.MagicMinuteAgent.name

    # Making sure that nothing is broken in the conv_hist
    for conv in bot.full_conv_hist.full_conv_hist:
        assert 'Sorry' not in conv['content'], \
            f"Sorry should not be present in the conversation history. Got {conv['content']}"


def test_specialist_timeout(setup):
    bot = init()
    # let's have a validated first question, so that timeout can be checked on PF check.
    fake_llm.responses += [json.dumps({
        'reasoning': '_',
        'relevant': True,
    }),
        'convo summary',
        json.dumps({
            "question": "Que 1"
        })]  # question generation
    bot = ask(bot)
    assert 'Que 1' in bot.full_conv_hist.full_conv_hist[-1]['content']
    initial_bot_state = bot.state.dict().copy()

    # Test1: Timeout on summary API call
    fake_llm.responses += ['Timeout']
    bot = ask(bot)
    compare_state_dicts(initial_bot_state, bot.state.dict())
    assert 'Sorry, that took too long to process for us.' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Test2: Timeout on pf check API call
    fake_llm.responses += ['convo summary', 'Timeout']
    bot = ask(bot)
    compare_state_dicts(initial_bot_state, bot.state.dict())
    assert 'Sorry, that took too long to process for us.' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Test3: Timeout on question generation API call
    fake_llm.responses += ['convo summary',
                           json.dumps({"details of headache": "pain in the head"}),
                           'Timeout']
    bot = ask(bot)
    compare_state_dicts(initial_bot_state, bot.state.dict())
    assert 'Sorry, that took too long to process for us.' in bot.full_conv_hist.full_conv_hist[-1]['content']
    
    # Test4: Timeout on fact check API call
    fake_llm.responses += ['convo summary',
                           json.dumps({"details of headache": "pain in the head"}),
                           json.dumps({"question": 'Que 2'}),
                           'Timeout']
    bot = ask(bot)
    compare_state_dicts(initial_bot_state, bot.state.dict())
    assert 'Sorry, that took too long to process for us.' in bot.full_conv_hist.full_conv_hist[-1]['content']
