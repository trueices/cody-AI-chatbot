import json

import requests_mock
from langchain.schema import AIMessage

from src import agents
from src.agents.cody_care_questionnaires import get_questionaire
from src.bot import Bot
from src.rx.doctor_service import DoctorService
from src.rx.doctor_service_state import DoctorServiceOfferEvent
from src.rx.ehr_service import EhrService
from src.tests.utils import ask, setup
from src.utils import MongoDBClient
from src.utils import fake_llm


def test_force_login(setup):
    bot = Bot(username='test_convo_id')
    bot.state.next_agent(name=agents.CodyCareAgent.name)
    assert bot.state.current_agent_name == agents.CodyCareAgent.name

    bot = ask(bot)
    assert 'Please <a class="text-blue underline app-link" href="/sign-in">login' in \
           bot.full_conv_hist.full_conv_hist[-1][
               'content']

    # Let's simulate the user logging in
    profile = {'email': 'test_user_id'}
    # Stimulate the init call first by initializing the bot with the profile.
    bot = Bot(username='test_convo_id', profile=profile)
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert last_msg.startswith('What state in the U.S. are you in right now?')


def init():
    profile = {
        "email": "test_user_id",
        "isLoggedIn": True
    }
    bot = Bot(username='test_convo_id', profile=profile)
    bot.state.next_agent(name=agents.CodyCareAgent.name)
    assert bot.state.current_agent_name == agents.CodyCareAgent.name

    # Ensure that this is not the first time user is entering cody care.
    bot.state.conv_hist[agents.CodyCareAgent.name][:] = [
        AIMessage(content='Initial message')]
    return bot, profile


def test_state_capture_valid(setup, monkeypatch):
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

    # Confirm the state this time.
    bot = ask(bot, profile=profile, message='1')
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    state_event = DoctorService.event_of_type(
        'test_offer_id', DoctorServiceOfferEvent.CAPTURE_STATE)
    assert state_event.state == 'California'
    assert 'Good News! We have Doctors ready to care for you in California' in last_msg
    assert 'Are you experiencing any of the following today?' in last_msg
    latest_event = DoctorService.latest_event('test_convo_id')
    assert latest_event.event == DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE


def test_ro_questionnaire(setup):
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
    bot = ask(bot, profile=profile, message='2')

    # answer the second question, I am the patient
    assert 'Who is the patient?' in bot.full_conv_hist.full_conv_hist[-1]['content']
    bot = ask(bot, profile=profile, message='1')

    # answer the third question, I am 18
    # Now, we should be done with the questionnaire
    assert 'Please confirm that you are at least 18 years of age' in bot.full_conv_hist.full_conv_hist[-1]['content']
    bot = ask(bot, profile=profile, message='1')
    assert "Ok, we're all set" in bot.full_conv_hist.full_conv_hist[-1]['content']
    assert "The Doctor Service is just $39" in bot.full_conv_hist.full_conv_hist[-1]['content']
    prev_event = DoctorService.event_of_type(
        'test_offer_id', DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE)
    assert prev_event.questionnaire[0]['llm_response'] == 2
    assert prev_event.questionnaire[1]['llm_response'] == 1
    assert prev_event.questionnaire[2]['llm_response'] == 1
    latest_event = DoctorService.latest_event('test_convo_id')
    assert latest_event.event == DoctorServiceOfferEvent.QUESTIONNAIRE_DONE_OFFER_INITIATED


def test_offer_consent(setup):
    bot, profile = init()

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.QUESTIONNAIRE_DONE_OFFER_INITIATED.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
        'questionnaire': get_questionaire('offer_consent'),
    })

    # Initialize
    bot = ask(bot, profile=profile)
    assert 'The Doctor Service is just $39' in bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'Would you like to order the Cody Doctor Service?' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Accept the offer
    bot = ask(bot, profile=profile, message='1')
    assert 'Great! Let’s get your payment information.' in bot.full_conv_hist.full_conv_hist[-1]['content']
    latest_event = DoctorService.latest_event('test_convo_id')
    assert latest_event.event == DoctorServiceOfferEvent.OFFER_ACCEPTED


def test_offer_initiated(setup):
    bot, profile = init()

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.QUESTIONNAIRE_DONE_OFFER_INITIATED.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
        'questionnaire': get_questionaire('offer_consent'),
    })
    # Initialize
    bot = ask(bot, profile=profile)
    assert '1. Yes, I want The Doctor Service.' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Let's accept the offer
    bot = ask(bot, profile=profile, message='1')
    assert 'Great! Let’s get your payment information.' in bot.full_conv_hist.full_conv_hist[-1]['content']
    latest_event = DoctorService.latest_event('test_convo_id')
    assert latest_event.event == DoctorServiceOfferEvent.OFFER_ACCEPTED


def test_offer_accepted(setup, monkeypatch):
    bot, profile = init()

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.OFFER_ACCEPTED.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
    })

    # First, let's try to enter something and proceed without actually making a payment.
    bot = ask(bot, profile=profile, message='please proceed')
    assert 'Looks like we have not received your payment yet. Please enter your payment details.' in \
           bot.full_conv_hist.full_conv_hist[
               -1]['content']

    # Now, let's start mocking the payment process.
    import stripe
    from unittest.mock import MagicMock

    # Mock the charge_.data[0] object
    mock_charge_data_0 = MagicMock()
    mock_charge_data_0.status = 'succeeded'
    mock_charge_data_0.payment_intent = 'pi_1234'
    mock_charge_data_0.receipt_url = 'https://example.com/receipt'

    # Mock the charge_ object
    mock_charge_ = MagicMock()
    mock_charge_.data = [mock_charge_data_0]

    # Let's simulate the user accepting the offer
    # First, let's mock stripe.Charge.search
    monkeypatch.setattr(stripe.Charge, 'search', lambda query: mock_charge_)
    profile['checkoutStatus'] = 'complete'
    bot = ask(bot, profile=profile)
    assert 'Next the Doctor and your Pharmacy require us to verify your identity.' in bot.full_conv_hist.full_conv_hist[
        -1]['content']
    offer_payment_done_event = DoctorService.event_of_type(
        'test_offer_id', DoctorServiceOfferEvent.OFFER_PAYMENT_DONE)
    assert offer_payment_done_event.event is not None, 'Offer payment done event not found'
    assert offer_payment_done_event.payment['id'] == 'pi_1234'
    assert offer_payment_done_event.payment['receipt_url'] == 'https://example.com/receipt'
    verify_user_event = DoctorService.event_of_type(
        'test_offer_id', DoctorServiceOfferEvent.VERIFY_USER)
    assert verify_user_event.event is not None, 'Verify user event not found'


def test_offer_payment_done_verified(setup):
    # Add verified user.
    MongoDBClient.get_users().insert_one({
        'email': 'test_user_id',
        'verified': {'value': True}
    })

    bot, profile = init()
    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.OFFER_PAYMENT_DONE.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
    })

    bot = ask(bot, profile=profile)
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'Please review our policies and approve to continue.' in last_msg
    assert '1. I approve' in last_msg


def test_verify_user_yes(setup):
    bot, profile = init()
    profile['verified'] = True

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.VERIFY_USER.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
    })

    bot = ask(bot, profile=profile)
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'Please review our policies and approve to continue.' in last_msg
    assert '1. I approve' in last_msg


def test_verify_user_no(setup):
    bot, profile = init()
    profile['verified'] = False

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.VERIFY_USER.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
    })

    bot = ask(bot, profile=profile)
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'Looks like you are not verified yet. We will need to verify your account first.' in last_msg


def test_user_verified_and_policy_consent(setup):
    bot, profile = init()

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.USER_VERIFIED.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
    })

    bot = ask(bot, profile=profile)
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'Please review our policies and approve to continue.' in last_msg
    assert '1. I approve' in last_msg
    last_event = DoctorService.latest_event('test_convo_id')
    assert last_event.event == DoctorServiceOfferEvent.POLICY_CONSENT

    bot = ask(bot, profile=profile, message='1')
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert "Yay! You are all set up.\n\n\nYou’re now being matched to your Doctor." in last_msg
    assert 'What is your phone number?' in last_msg


def test_user_verification_failed(setup):
    bot, profile = init()

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.USER_VERIFICATION_FAILED.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
    })

    bot = ask(bot, profile=profile)
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'Looks like your previous verification attempt failed.' in last_msg


def test_onboarding_questionnaire(setup, monkeypatch):
    bot, profile = init()

    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.ONBOARDING_QUESTIONNAIRE_CAPTURE.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
        'questionnaire': get_questionaire('onboarding'),
    })

    # Start with the phone number question
    bot = ask(bot, profile=profile)
    assert 'What is your phone number?' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Enter a 11 character phoen number.
    bot = ask(bot, profile=profile, message='98765432101')
    assert 'phone number looks invalid' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Enter a 10 digit number with hyphens
    bot = ask(bot, profile=profile, message='987-654-3210')
    assert 'What is your date of birth?' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Enter an invalid date
    fake_llm.responses += [json.dumps({'value': 'invalid'})]
    bot = ask(bot, profile=profile, message='13/13/1990')
    assert 'I am sorry, date of birth looks invalid.' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Enter a valid date
    fake_llm.responses += [json.dumps({'value': '11/16/2000'})]
    bot = ask(bot, profile=profile, message='11/16/2000')
    assert 'What is your sex assigned at birth?\n\n1. Female\n2. Male' in bot.full_conv_hist.full_conv_hist[
        -1]['content']

    # Enter male
    bot = ask(bot, profile=profile, message='2')
    assert 'What is your gender?' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Enter male
    bot = ask(bot, profile=profile, message='2')
    assert 'What prescription and nonprescription medications are you currently taking?' in \
           bot.full_conv_hist.full_conv_hist[-1]['content']

    # Enter a prescription
    fake_llm.responses += [json.dumps({'value': 'Ibuprofen'})]
    bot = ask(bot, profile=profile, message='Ibuprofen')
    assert 'Please list all your medication allergies.' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Enter an allergy
    fake_llm.responses += [json.dumps({'value': 'Penicillin'})]
    bot = ask(bot, profile=profile, message='Penicillin')
    assert 'What are your current medical conditions?' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Enter a medical condition
    fake_llm.responses += [json.dumps({'value': 'Diabetes'})]
    bot = ask(bot, profile=profile, message='Diabetes')
    assert 'What is your preferred pharmacy?' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Enter a pharmacy, after which the doctor is matched and info is sent to EHR.
    fake_llm.responses += [json.dumps({'value': 'Walgreens'})]
    # Mocking state captured as California
    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.CAPTURE_STATE.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
        'state': 'California'
    })
    # Adding user as a registered patient in .
    MongoDBClient.get_users().insert_one({
        'email': 'test_user_id',
        'ehr_id': 'test_ehr_id',
    })
    # Mocking doctor match.
    import os
    prescribers = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '../test_cody_care/test_data/akute/prescribers.json'))
    with open(prescribers, 'r', encoding='utf-8') as file:
        prescribers_data = file.read()

        monkeypatch.setattr(EhrService, 'match_prescriber',
                            lambda self, search_params: json.loads(prescribers_data)[0])
        monkeypatch.setenv('AKUTE_API_KEY', 'test_key')
        monkeypatch.setenv(
            'AKUTE_BASE_URL', 'https://api.staging.akutehealth.com')
        monkeypatch.setenv('MOCK_EMAIL', 'true')
        bot.state.conv_hist[agents.MagicMinuteAgent.name][:] = [
            AIMessage(content='Magic minute Summary')]
        with requests_mock.Mocker() as req:
            req.post('https://api.staging.akutehealth.com/v1/tasks', status_code=201, json={
                'statusCode': 201,
                'data': {'id': 'test_task_id'}
            })

            bot = ask(bot, profile=profile, message='Walgreens')
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'You’ve been matched to your Doctor.\n\nbio' in last_msg, \
        "Should contain the doctor's bio"


def test_ehr_send(setup):
    bot, profile = init()
    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.EHR_SENT.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
    })

    bot = ask(bot, profile=profile)
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'If you have a moment, please check out your My Story' in last_msg
    assert bot.state.current_agent_name == agents.FeedbackAgent.name
    assert 'Please tell us about how your experience has been so far.' in last_msg

    # Add a feedback
    bot = ask(bot, profile=profile, message='5')
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'Thank you for the valuable feedback!' in last_msg
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert 'What should we do next?' in last_msg


def test_ehr_plan_ready(setup):
    questionnaire = get_questionaire('plan_acknowledgement')
    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.EHR_PLAN_READY.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
        'questionnaire': questionnaire,
    })

    bot, profile = init()
    # Initialize
    bot = ask(bot, profile=profile)
    assert '1. I approve of my Certified Plan.' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Let's approve the plan
    bot = ask(bot, profile=profile, message='1')
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'Excellent. You are on your way to feeling better.' in last_msg
    assert bot.state.current_agent_name == agents.CodyCareAgent.name
    assert DoctorService.latest_event(
        'test_convo_id').event == DoctorServiceOfferEvent.EHR_PLAN_ACKNOWLEDGED

    bot = ask(bot, profile=profile, message='options')
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert 'What should we do next?' in last_msg
    assert DoctorService.latest_event(
        'test_convo_id').event == DoctorServiceOfferEvent.EHR_PLAN_ACKNOWLEDGED


def test_ehr_plan_ready_not_approve(setup):
    questionnaire = get_questionaire('plan_acknowledgement')
    MongoDBClient.get_doctor_service_offer().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'offer_id': 'test_offer_id',
        'event': DoctorServiceOfferEvent.EHR_PLAN_READY.inventory_name,
        'created': '2021-08-20T00:00:00',
        'updated': '2021-08-20T00:00:00',
        'questionnaire': questionnaire,
    })

    bot, profile = init()
    # Initialize
    bot = ask(bot, profile=profile)
    assert '1. I approve of my Certified Plan.' in bot.full_conv_hist.full_conv_hist[-1]['content']

    # Let's approve the plan
    bot = ask(bot, profile=profile, message='2')
    last_msg: str = bot.full_conv_hist.full_conv_hist[-1]['content']
    assert 'Please send an email to' in last_msg
    assert bot.state.current_agent_name == agents.ConciergeAgent.name
    assert 'What should we do next?' in last_msg
    assert DoctorService.latest_event(
        'test_convo_id').event == DoctorServiceOfferEvent.EHR_PLAN_NOT_ACKNOWLEDGED
