"""
This file contains tests for the denied (non-confirmation/unhappy) sideflows of the Cody Care agent.
"""

import json

from src import agents
from src.agents.cody_care_questionnaires import get_questionaire
from src.rx.doctor_service_state import DoctorServiceOfferEvent
from src.rx.ehr_service import EhrService
from src.tests.test_agents.test_cody_care_agent import init
from src.tests.utils import ask, setup
from src.utils import MongoDBClient
from src.utils import fake_llm


def test_state_capture_invalid(setup, monkeypatch):
    bot, profile = init()

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.CAPTURE_STATE.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
    })

    # Start with entering a non-US state.
    fake_llm.responses += [json.dumps({'state': 'not_captured'})]
    bot = ask(bot, profile=profile, message='Canada')
    assert 'Currently, we only support US states' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Now, lets enter a non supported US state.
    monkeypatch.setattr(EhrService, 'all_supported_state',
                        lambda x: {'california'})
    fake_llm.responses += [json.dumps({'state': 'New York'})]
    bot = ask(bot, profile=profile, message='New York')
    assert "do not support the state you entered" in bot.full_conv_hist.full_conv_hist[-1]['content']
    assert bot.state.current_agent_name == agents.ConciergeAgent.name


def test_state_capture_denied_confirm(setup, monkeypatch):
    bot, profile = init()

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.CAPTURE_STATE.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
    })

    # Start with entering a valid supported US state.
    monkeypatch.setattr(EhrService, 'all_supported_state',
                        lambda x: {'california'})
    fake_llm.responses += [json.dumps({'state': 'California'})]
    bot = ask(bot, profile=profile, message='California')
    assert 'To confirm, you are currently in California, U.S.' in bot.full_conv_hist.full_conv_hist[
        -1]['content']

    # Now, let's decline the state. (Just for testing)
    bot = ask(bot, profile=profile, message='2')
    assert 'What state in the U.S. are you in right now?' in bot.full_conv_hist.full_conv_hist[-1]['content'], \
        "Should ask for the state again"


def test_emergency_symptoms(setup):
    bot, profile = init()

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
        'questionnaire': get_questionaire('ro'),
    })
    # Initialize
    bot = ask(bot, profile=profile)

    # answer the first question, no symptoms
    assert 'Are you experiencing any of the following today?' in bot.full_conv_hist.full_conv_hist[-1]['content']
    bot = ask(bot, profile=profile, message='1')
    assert 'it’s important that you contact your primary care doctor,' in bot.full_conv_hist.full_conv_hist[
        -1]['content']
    assert bot.state.current_agent_name == agents.EndAgent.name, \
        "Should end the conversation if the user has emergency symptoms"


def test_not_a_patient(setup):
    bot, profile = init()
    questionaire = get_questionaire('ro')
    questionaire[0]['response'] = 'test'  # First question answered

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
        'questionnaire': questionaire,
    })
    # Initialize
    bot = ask(bot, profile=profile)

    # answer the second question, I am not the patient
    assert 'Who is the patient?' in bot.full_conv_hist.full_conv_hist[-1]['content']
    bot = ask(bot, profile=profile, message='2')
    last_msg = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'We’d love to care for you, but the Doctor must care for the patient directly.' in last_msg
    assert 'What should we do next?' in last_msg
    assert bot.state.current_agent_name == agents.ConciergeAgent.name, \
        "Should exit cody care agent"


def test_not_18_plus(setup):
    bot, profile = init()
    questionaire = get_questionaire('ro')
    questionaire[0]['response'] = 'test'  # First question answered
    questionaire[1]['response'] = 'test'  # Second question answered

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
        'questionnaire': questionaire,
    })
    # Initialize
    bot = ask(bot, profile=profile)

    # answer the third question, I am 18
    # Now, we should be done with the questionnaire
    assert 'Please confirm that you are at least 18 years of age' in bot.full_conv_hist.full_conv_hist[-1]['content']
    bot = ask(bot, profile=profile, message='2')
    last_msg = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'We’d love to care for you, but patients for the Doctor Service must be at least 18 years of age.' in last_msg
    assert 'What should we do next?' in last_msg
    assert bot.state.current_agent_name == agents.ConciergeAgent.name, \
        "Should exit cody care agent"


def test_policy_consent_denied(setup):
    bot, profile = init()

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.POLICY_CONSENT.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
        'questionnaire': get_questionaire('policy_consent'),
    })
    # Initialize
    bot = ask(bot, profile=profile)
    assert '2. I do NOT approve of these policies.' in bot.full_conv_hist.full_conv_hist[-1]['content']

    bot = ask(bot, profile=profile, message='2')
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert "Darn. We are unable to serve you if you do not approve our policies." in last_msg
    assert "What should we do next?" in last_msg
    assert bot.state.current_agent_name == agents.ConciergeAgent.name, \
        "Should exit cody care agent"
