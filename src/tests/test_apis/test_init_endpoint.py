from datetime import datetime, timedelta

import requests_mock

from src import agents
from src.bot_state import BotState
from src.followup.followup_care import FollowupCare
from src.followup.followup_care_state import FollowUpCareState
from src.tests.test_apis.utils import get_credentials, app_client
from src.tests.utils import load_mogo_records
from src.utils import MongoDBClient
from src.utils import fake_llm


def test_init_endpoint_initialization(app_client):
    response = app_client.get(
        '/new_token', headers={'Authorization': f'Basic {get_credentials()}'})
    assert response.status_code == 200

    token_ = response.json['access_token']

    init_ = app_client.get(
        '/init', headers={'Authorization': f'Bearer {token_}'})
    assert len(init_.json['conv_hist']
               ) == 1, "Should only contain the greeting message"

    assert "Hello नमस्ते Hola Kamust 你好 Bonjour\n\n\nI'm Cody" in init_.json['conv_hist'][0][
        'content']
    assert init_.status_code == 200
    assert init_.json['current_user'] is not None

    assert len(init_.json['conv_hist']) == 1


def test_init_endpoint_diagnosis_with_full_convo_history(app_client):
    response = app_client.get('/new_token?session_id=mgvg2skD9ecihUlx8CHA4SorKdHv9xcZ7YqLbsUjf1TRZkCiPS',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    load_mogo_records('test_apis/test_data/diagnosis/collection.json',
                      'test_apis/test_data/diagnosis/full_convo_history.json')

    init_ = app_client.get(
        '/init', headers={'Authorization': f'Bearer {token_}'})
    assert init_.status_code == 200
    assert init_.json['current_user'] is not None
    assert init_.json['chief_complaint'] == 'faint line on pregnancy test'

    assert len(init_.json['conv_hist']) == 22


def test_init_endpoint_treatment_no_full_convo(app_client):
    response = app_client.get('/new_token?session_id=ngAXz2uCWSE5h7gKFdjaFmJrqW6ykQsszhxZf0ke1Y99yra0jb',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    load_mogo_records('test_apis/test_data/treatment_agent/collection.json')

    init_ = app_client.get(
        '/init', headers={'Authorization': f'Bearer {token_}'})

    assert init_.status_code == 200
    assert init_.json['current_user'] is not None
    assert init_.json['chief_complaint'] == 'baby constipation'

    assert len(init_.json['conv_hist']) == 31


def test_init_endpoint_character(app_client):
    response = app_client.get('/new_token?session_id=fake_character',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    init_ = app_client.get('/init?character=parkinsons',
                           headers={'Authorization': f'Bearer {token_}'})

    assert len(init_.json['conv_hist']
               ) == 1, "Should only contain the greeting message"
    assert init_.json['conv_hist'][0]['content'].startswith(
        "Hello नमस्ते Hola Kamust 你好 Bonjour\n\n\nI\'m Cody, your AI Doctor, specializing in Neurology.")

    assert init_.status_code == 200

    assert init_.json['specialist'] == 'neurologist'
    assert init_.json['subSpecialty'] == 'ParkinsonsDisease'


def test_init_endpoint_character_with_patient_name(app_client):
    response = app_client.get('/new_token?session_id=fake_character',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    init_ = app_client.get('/init?character=migraine&name=Harry%20Potter',
                           headers={'Authorization': f'Bearer {token_}'})

    assert len(init_.json['conv_hist']
               ) == 1, "Should only contain the greeting message"
    assert init_.json['conv_hist'][0]['content'].startswith(
        "Hello Harry Potter!\n\n\nI'm Cody, your AI Doctor, specializing in Neurology.")

    assert init_.status_code == 200

    assert init_.json['specialist'] == 'neurologist'
    assert init_.json['subSpecialty'] == 'Migraine'


def test_init_endpoint_with_followup(app_client):
    response = app_client.get('/new_token?session_id=mgvg2skD9ecihUlx8CHA4SorKdHv9xcZ7YqLbsUjf1TRZkCiPS',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    MongoDBClient.get_followup_care().insert_one({
        'name': 'John Doe',
        'chief_complaint': 'some complaint',
        'convo_id': 'mgvg2skD9ecihUlx8CHA4SorKdHv9xcZ7YqLbsUjf1TRZkCiPS',
        'user_id': 'test_user_id_1',
        'state': 'new',
        'is_locked': False,
        'next_followup_date': datetime(2024, 2, 13),
        'created': datetime(2024, 2, 13),
        'updated': datetime(2024, 2, 13)
    })
    fake_llm.responses = ['Greetings from followup']

    load_mogo_records('test_apis/test_data/diagnosis/collection.json',
                      'test_apis/test_data/diagnosis/full_convo_history.json')

    init_ = app_client.get('/init?followup=true',
                           headers={'Authorization': f'Bearer {token_}'})
    assert init_.status_code == 200

    assert init_.json['conv_hist'][-1]['content'].endswith(
        'Greetings from followup')

    # Adding ask endpoint test, to make sure the followup agent is working as expected
    fake_llm.responses += ['followup response']
    ask_ = app_client.post('/ask', headers={'Authorization': f'Bearer {token_}'},
                           json={'input': '_'})
    assert ask_.status_code == 200
    events = ask_.get_data(as_text=True)
    state_ = MongoDBClient.get_botstate().find_one(
        {'username': 'mgvg2skD9ecihUlx8CHA4SorKdHv9xcZ7YqLbsUjf1TRZkCiPS'})
    assert state_['current_agent_name'] == 'followup_care_agent'
    assert events == 'followup response'

    # Now, let's test to ensure that an init call with followup=true doesnt trigger the followup agent again
    init_ = app_client.get('/init?followup=true',
                           headers={'Authorization': f'Bearer {token_}'})
    assert init_.status_code == 200
    assert init_.json['conv_hist'][-1]['content'] == 'followup response', \
        "The followup agent should not be triggered again"

    # However, if the user arrives via a new followup state, the followup agent should be triggered
    followup_care_state = FollowUpCareState(
        'mgvg2skD9ecihUlx8CHA4SorKdHv9xcZ7YqLbsUjf1TRZkCiPS')
    FollowupCare.release_lock_update_state(
        followup_care_state)  # Moves to the next state
    fake_llm.responses += ['Next greetings from followup']
    init_ = app_client.get('/init?followup=true',
                           headers={'Authorization': f'Bearer {token_}'})
    assert init_.status_code == 200
    assert init_.json['conv_hist'][-1]['content'].endswith(
        'Next greetings from followup')
    # Also ensure that the conv_hist for new followup is cleared.
    state = BotState(
        username='mgvg2skD9ecihUlx8CHA4SorKdHv9xcZ7YqLbsUjf1TRZkCiPS')
    assert len(state.conv_hist[agents.FollowupCareAgent.name]) == 2


def test_init_with_followup_enabled_greeting(app_client):
    response = app_client.get('/new_token?session_id=new_conv_id',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    MongoDBClient.get_followup_care().insert_one({
        'name': 'John Doe',
        'chief_complaint': 'some complaint',
        'convo_id': 'prev_conv_id',
        'email_address': 'johndoe@awesome.com',
        'user_id': 'test_user_id_1',
        'state': 'follow_up_1',
        'is_locked': False,
        'next_followup_date': datetime(2024, 2, 13),
        'created': datetime(2024, 2, 13),
        'updated': datetime(2024, 2, 13)
    })

    init_ = app_client.get('/init?email=johndoe@awesome.com',
                           headers={'Authorization': f'Bearer {token_}'})
    assert init_.status_code == 200
    assert len(init_.json['conv_hist']) == 1
    assert "some complaint" in init_.json['conv_hist'][-1]['content']
    assert "John Doe" in init_.json['conv_hist'][-1]['content']
    assert "<a class=\"text-blue underline app-link\" href" in init_.json['conv_hist'][-1]['content'], \
        "The followup link should be contain proper class and href tag"
    assert "prev_conv_id" in init_.json['conv_hist'][-1]['content'], \
        "The followup link should contain the previous conversation id"
    assert "new_conv_id" not in init_.json['conv_hist'][-1]['content'], \
        "The followup link should not contain the current conversation id"

    # Let's also test a user id that does not exist
    init_ = app_client.get('/init?email=blahblah@awesome.com',
                           headers={'Authorization': f'Bearer {token_}'})
    assert init_.status_code == 200
    assert len(init_.json['conv_hist']) == 1
    assert "Hello" in init_.json['conv_hist'][-1]['content']
    assert "some complaint" not in init_.json['conv_hist'][-1]['content']
    assert "John Doe" not in init_.json['conv_hist'][-1]['content']


def test_init_without_followup_enabled_greeting_for_new_state(app_client):
    response = app_client.get('/new_token?session_id=new_conv_id',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    MongoDBClient.get_followup_care().insert_one({
        'name': 'John Doe',
        'chief_complaint': 'some complaint',
        'convo_id': 'prev_conv_id',
        'email_address': 'johndoe@awesome.com',
        'user_id': 'test_user_id_1',
        'state': 'new',
        'is_locked': False,
        'next_followup_date': datetime(2024, 2, 13),
        'created': datetime(2024, 2, 13),
        'updated': datetime(2024, 2, 13)
    })

    init_ = app_client.get('/init?email=johndoe@awesome.com',
                           headers={'Authorization': f'Bearer {token_}'})
    assert init_.status_code == 200
    assert len(init_.json['conv_hist']) == 1
    assert "some complaint" not in init_.json['conv_hist'][-1]['content']
    assert "<a class=\"text-blue underline app-link\" href" not in init_.json['conv_hist'][-1]['content'], \
        "The followup link should be contain proper class and href tag"
    assert "prev_conv_id" not in init_.json['conv_hist'][-1]['content'], \
        "The followup link should contain the previous conversation id"
    assert "new_conv_id" not in init_.json['conv_hist'][-1]['content'], \
        "The followup link should not contain the current conversation id"


def test_init_with_followup_enabled_greeting_followup_done_less_than_180_days(app_client):
    now = datetime.now()
    ten_days_ago = now - timedelta(days=10)

    response = app_client.get('/new_token?session_id=new_conv_id',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    MongoDBClient.get_followup_care().insert_one({
        'name': 'John Doe',
        'chief_complaint': 'some complaint',
        'convo_id': 'prev_conv_id',
        'email_address': 'johndoe@awesome.com',
        'user_id': 'test_user_id_1',
        'state': 'follow_up_done',
        'is_locked': False,
        'next_followup_date': ten_days_ago + timedelta(days=2),
        'created': ten_days_ago,
        'updated': ten_days_ago
    })

    init_ = app_client.get('/init?email=johndoe@awesome.com',
                           headers={'Authorization': f'Bearer {token_}'})

    assert init_.status_code == 200
    assert len(init_.json['conv_hist']) == 1

    assert f"""Hello, John Doe!

It looks like we last chatted around 10 days ago and you were dealing with some complaint.

I hope you are doing well.""" in init_.json['conv_hist'][-1]['content']


def test_init_with_followup_enabled_greeting_resolved_less_than_180_days(app_client):
    now = datetime.now()
    ten_days_ago = now - timedelta(days=10)

    response = app_client.get('/new_token?session_id=new_conv_id',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    MongoDBClient.get_followup_care().insert_one({
        'name': 'John Doe',
        'chief_complaint': 'resolved complaint',
        'convo_id': 'prev_conv_id',
        'email_address': 'johndoe@awesome.com',
        'user_id': 'test_user_id_1',
        'state': 'resolved',
        'is_locked': False,
        'next_followup_date': ten_days_ago + timedelta(days=2),
        'created': ten_days_ago,
        'updated': ten_days_ago
    })

    init_ = app_client.get('/init?email=johndoe@awesome.com',
                           headers={'Authorization': f'Bearer {token_}'})

    assert init_.status_code == 200
    assert len(init_.json['conv_hist']) == 1

    assert f"""Hello, John Doe!

It looks like we last chatted around 10 days ago and you were dealing with resolved complaint.

I hope you are doing well.""" in init_.json['conv_hist'][-1]['content']


def test_init_with_followup_enabled_greeting_followup_done_more_than_180_days(app_client):
    now = datetime.now()
    six_months_ago = now - timedelta(days=190)

    response = app_client.get('/new_token?session_id=new_conv_id',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    MongoDBClient.get_followup_care().insert_one({
        'name': 'John Doe',
        'chief_complaint': 'resolved complaint',
        'convo_id': 'prev_conv_id',
        'email_address': 'johndoe@awesome.com',
        'user_id': 'test_user_id_1',
        'state': 'resolved',
        'is_locked': False,
        'next_followup_date': six_months_ago + timedelta(days=2),
        'created': six_months_ago,
        'updated': six_months_ago
    })

    init_ = app_client.get('/init?email=johndoe@awesome.com',
                           headers={'Authorization': f'Bearer {token_}'})

    assert init_.status_code == 200
    assert len(init_.json['conv_hist']) == 1

    assert f"""Hello, John Doe!

It looks like we last chatted around 6 months ago.

I hope you are doing well.""" in init_.json['conv_hist'][-1]['content']


def test_init_endpoint_find_care_force_login_onload_display(app_client, monkeypatch):
    monkeypatch.setenv('GOOGLE_API_KEY', 'test')

    response = app_client.get('/new_token?session_id=kXnbtoAt2MhAiW7GoUokgueHobzi731YAAWJiNtKU0Ae6ZgdPB',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    load_mogo_records('test_apis/test_data/find_care/collection_no_login.json')

    with requests_mock.Mocker() as req:
        req.post('https://places.googleapis.com/v1/places:searchText', json={"places": [
            {"displayName": {"text": "test"}, "shortFormattedAddress": "test", "internationalPhoneNumber": "test",
             "websiteUri": "test", "rating": "5", "businessStatus": "OPERATIONAL"},
            {"displayName": {"text": "test2"}, "shortFormattedAddress": "test2", "internationalPhoneNumber": "test2",
             "websiteUri": "test2", "rating": "4", "businessStatus": "CLOSED_PERMANENTLY"},
            {"displayName": {"text": "test3"}, "shortFormattedAddress": "test3", "internationalPhoneNumber": "test3",
             "rating": "3", "businessStatus": "OPERATIONAL"}
        ]})

        init_ = app_client.get(
            '/init?email=johndoe@awesome.com', headers={'Authorization': f'Bearer {token_}'})

        assert init_.status_code == 200
        assert "Please let me know your address to find the best doctor nearest you." in init_.json['conv_hist'][-1][
            'content']

        state_ = MongoDBClient.get_botstate().find_one(
            {'username': 'kXnbtoAt2MhAiW7GoUokgueHobzi731YAAWJiNtKU0Ae6ZgdPB'})

        agent_ = state_['conv_hist']['find_care_agent']

        assert len(agent_) == 2
        assert "Please let me know your address to find the best doctor nearest you." in agent_[-1]['content']


def test_init_endpoint_find_care_force_no_login_no_onload_display(app_client, monkeypatch):
    response = app_client.get('/new_token?session_id=kXnbtoAt2MhAiW7GoUokgueHobzi731YAAWJiNtKU0Ae6ZgdPB',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    load_mogo_records('test_apis/test_data/find_care/collection_no_login.json')

    init_ = app_client.get(
        '/init', headers={'Authorization': f'Bearer {token_}'})

    assert init_.status_code == 200
    assert "Sure thing. I have found 2 care options" not in init_.json['conv_hist'][-1]['content']

    state_ = MongoDBClient.get_botstate().find_one(
        {'username': 'kXnbtoAt2MhAiW7GoUokgueHobzi731YAAWJiNtKU0Ae6ZgdPB'})

    agent_ = state_['conv_hist']['find_care_agent']

    assert len(agent_) == 1
    assert "Sure thing. I have found 2 care options" not in agent_[-1]['content']


def test_init_endpoint_find_care_force_login_no_onload_display_if_already_displayed(app_client, monkeypatch):
    response = app_client.get('/new_token?session_id=kXnbtoAt2MhAiW7GoUokgueHobzi731YAAWJiNtKU0Ae6ZgdPB',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    load_mogo_records('test_apis/test_data/find_care/collection_login_find_care_displayed.json')

    init_ = app_client.get(
        '/init?email=johndoe@awesome.com', headers={'Authorization': f'Bearer {token_}'})

    assert init_.status_code == 200
    assert "Thanks for logging in." in init_.json['conv_hist'][-1]['content']

    state_ = MongoDBClient.get_botstate().find_one(
        {'username': 'kXnbtoAt2MhAiW7GoUokgueHobzi731YAAWJiNtKU0Ae6ZgdPB'})

    agent_ = state_['conv_hist']['find_care_agent']

    assert len(agent_) == 2
    assert "Thanks for logging in." in agent_[-1]['content']
