from src.utils import fake_llm
import json

from src.utils import MongoDBClient
from src.tests.test_apis.utils import get_credentials, app_client


# Meant to test ask endpoint end to end. So far it test upto name agent and follwup agent has just started.
def test_ask_endpoint(app_client):
    assert MongoDBClient().get_botstate().find_one(
        {'username': 'fake_ask'}) is None
    response = app_client.get('/new_token?session_id=fake_ask',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    fake_llm.responses = ['Do you suspect of fever or confirmed?']

    ask_events = app_client.post(
        '/ask', headers={'Authorization': f'Bearer {token_}', 'Content-Type': 'application/json'}, json={})

    assert ask_events.status_code == 400

    ask_events = app_client.post(
        '/ask', headers={'Authorization': f'Bearer {token_}'}, json={'input': 'Fever'})

    assert ask_events.status_code == 200
    events = ask_events.get_data(as_text=True)
    assert events == 'Do you suspect of fever or confirmed?'

    state_ = MongoDBClient.get_botstate().find_one({'username': 'fake_ask'})
    full_conv_hist_ = MongoDBClient.get_full_conv_hist().find_one(
        {'conversation_id': 'fake_ask'})

    assert state_['current_agent_name'] == 'navigation_agent'
    assert len(state_['conv_hist']['navigation_agent']) == 3
    assert len(full_conv_hist_['full_conv_hist']) == 3

    fake_llm.responses += ['', '{"chief_complaint": "Fever"}', '']
    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'capture_intent_tool',
        'arguments': json.dumps({'intent': 'symptom_or_suspected_condition'})
    }})

    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'categorize_chief_complaint',
        'arguments': json.dumps({'specialist': '_'})
    }})

    ask_events = app_client.post(
        '/ask', headers={'Authorization': f'Bearer {token_}'}, json={'input': 'confirmed'})

    assert state_['specialist'] == "generalist"
    assert state_['subSpecialty'] == "general"

    assert ask_events.status_code == 200
    events = ask_events.get_data(as_text=True)

    assert events == 'Thanks for confirming! Before I ask you a few questions, what should I call you?'

    state_ = MongoDBClient.get_botstate().find_one({'username': 'fake_ask'})

    full_conv_hist_ = MongoDBClient.get_full_conv_hist().find_one(
        {'conversation_id': 'fake_ask'})

    assert state_['current_agent_name'] == "name_enquiry_agent"

    assert len(state_['conv_hist']['name_enquiry_agent']) == 1
    assert len(full_conv_hist_['full_conv_hist']) == 5


def test_ask_endpoint_with_character(app_client):
    response = app_client.get('/new_token?session_id=fake_ask_character',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    fake_llm.responses = ['Do you suspect of fever or confirmed?']

    ask_events = app_client.post('/ask', headers={'Authorization': f'Bearer {token_}'}, json={
        'input': 'Fever',
        'profile': {
            'character': 'parkinsons'
        }
    })

    events = ask_events.get_data(as_text=True)
    assert events == 'Do you suspect of fever or confirmed?'

    state_ = MongoDBClient.get_botstate().find_one(
        {'username': 'fake_ask_character'})

    assert state_['current_agent_name'] == "navigation_agent"
    assert state_['specialist'] == "neurologist"
    assert state_['subSpecialty'] == "ParkinsonsDisease"


def test_ask_endpoint_with_not_supported_speciality_character(app_client):
    response = app_client.get('/new_token?session_id=fake_ask_character',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    fake_llm.responses = ["So you want to focus on X today, is that correct?"]

    ask_events = app_client.post('/ask', headers={'Authorization': f'Bearer {token_}'}, json={
        'input': 'Fever',
        'profile': {
            'character': 'blahblah'
        }
    })

    events = ask_events.get_data(as_text=True)
    assert events == 'So you want to focus on X today, is that correct?'

    state_ = MongoDBClient.get_botstate().find_one(
        {'username': 'fake_ask_character'})

    assert state_['current_agent_name'] == "navigation_agent"
    assert state_['specialist'] == "generalist"
    assert state_['subSpecialty'] == "general"


def test_ask_endpoint_with_pcos_gyno(app_client):
    response = app_client.get('/new_token?session_id=fake_ask_character',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    fake_llm.responses = ["So you want to focus on X today, is that correct?"]

    ask_events = app_client.post('/ask', headers={'Authorization': f'Bearer {token_}'}, json={
        'input': 'Fever',
        'profile': {
            'character': 'pcos'
        }
    })

    events = ask_events.get_data(as_text=True)
    assert events == 'So you want to focus on X today, is that correct?'

    state_ = MongoDBClient.get_botstate().find_one(
        {'username': 'fake_ask_character'})

    assert state_['specialist'] == "gynecologist"
    assert state_['subSpecialty'] == "PolycysticOvarySyndrome"


def test_ask_endpoint_with_psychiatry_anxiety(app_client):
    response = app_client.get('/new_token?session_id=fake_ask_character',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    fake_llm.responses = ["So you want to focus on X today, is that correct?"]

    ask_events = app_client.post('/ask', headers={'Authorization': f'Bearer {token_}'}, json={
        'input': 'Fever',
        'profile': {
            'character': 'anxiety'
        }
    })

    events = ask_events.get_data(as_text=True)
    assert events == 'So you want to focus on X today, is that correct?'

    state_ = MongoDBClient.get_botstate().find_one(
        {'username': 'fake_ask_character'})

    assert state_['specialist'] == "psychiatrist"
    assert state_['subSpecialty'] == "Anxiety"


def test_ask_endpoint_with_psychiatry(app_client):
    response = app_client.get('/new_token?session_id=fake_ask_character',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    fake_llm.responses = ["So you want to focus on X today, is that correct?"]

    ask_events = app_client.post('/ask', headers={'Authorization': f'Bearer {token_}'}, json={
        'input': 'Fever',
        'profile': {
            'character': 'psychiatry'
        }
    })

    events = ask_events.get_data(as_text=True)
    assert events == 'So you want to focus on X today, is that correct?'

    state_ = MongoDBClient.get_botstate().find_one(
        {'username': 'fake_ask_character'})

    assert state_['specialist'] == "psychiatrist"
    assert state_['subSpecialty'] == "general"


def test_ask_endpoint_with_not_supported_speciality_character_router_agent(app_client):
    response = app_client.get('/new_token?session_id=fake_ask_character',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    fake_llm.responses = ["So you want to focus on X today, is that correct?"]

    ask_events = app_client.post('/ask', headers={'Authorization': f'Bearer {token_}'}, json={
        'input': 'Stomach pain',
        'profile': {
            'character': 'StomachPain'
        }
    })

    events = ask_events.get_data(as_text=True)
    assert events == 'So you want to focus on X today, is that correct?'

    state_ = MongoDBClient.get_botstate().find_one(
        {'username': 'fake_ask_character'})

    assert state_['current_agent_name'] == "navigation_agent"
    assert state_['specialist'] == "generalist"
    assert state_['subSpecialty'] == "general"

    fake_llm.responses += ['', '{"chief_complaint": "stomach pain"}', '', '']

    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'capture_intent_tool',
        'arguments': json.dumps({'intent': 'symptom_or_suspected_condition'})
    }})
    fake_llm.additional_kwargs.put({})

    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'categorize_chief_complaint',
        'arguments': json.dumps({'specialist': 'dummy_specialist'})
    }})
    fake_llm.additional_kwargs.put({"function_call": {
        'name': 'categorize_chief_complaint',
        'arguments': json.dumps({'sub_speciality': 'dummy_subspecialist', 'is_disease_name': False})
    }})

    ask_events = app_client.post('/ask', headers={'Authorization': f'Bearer {token_}'}, json={
        'input': 'Yes',
        'profile': {
            'character': 'StomachPain'
        }
    })

    events = ask_events.get_data(as_text=True)

    assert events == 'Thanks for confirming! Before I ask you a few questions, what should I call you?'

    state_ = MongoDBClient.get_botstate().find_one(
        {'username': 'fake_ask_character'})

    assert state_['current_agent_name'] == "name_enquiry_agent"
    assert state_['specialist'] == "generalist"
    assert state_['subSpecialty'] == "general"


def test_exception_in_ask(app_client):
    response = app_client.get('/new_token?session_id=fake_ask',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    # No response added to fake_llm. This should raise an exception.

    ask_events = app_client.post(
        '/ask', headers={'Authorization': f'Bearer {token_}'}, json={'input': 'Fever'})

    # This is important. During an exception, the status code should be 200.
    # The server should not crash.
    assert ask_events.status_code == 200
    events = ask_events.get_data(as_text=True)
    assert 'Sorry, there was an issue on our end.' in events


def test_ask_endpoint_with_locations(app_client):
    response = app_client.get('/new_token?session_id=fake_ask',
                              headers={'Authorization': f'Basic {get_credentials()}'})
    token_ = response.json['access_token']

    fake_llm.responses = ["So you want to focus on X today, is that correct?"]

    ask_events = app_client.post('/ask', headers={'Authorization': f'Bearer {token_}'}, json={
        'input': 'Fever',
        'profile': {
            'longitude': 77.5946,
            'latitude': 12.9716
        }
    })

    events = ask_events.get_data(as_text=True)
    assert events == 'So you want to focus on X today, is that correct?'

    state_ = MongoDBClient.get_botstate().find_one(
        {'username': 'fake_ask'})

    assert state_['location']['coordinates'] == [77.5946, 12.9716]
    assert state_['location']['type'] == 'Point'


def test_ask_endpoint_with_empty_input_and_care_agent(app_client):
    response = app_client.get('/new_token?session_id=fake_ask',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    MongoDBClient().get_botstate().insert_one({
        'username': 'fake_ask',
        'current_agent_name': 'cody_care_agent',
        'conv_hist': {'care_agent': []}
    })

    fake_llm.responses = ['{"option_number": 1}']

    ask_events = app_client.post('/ask', headers={'Authorization': f'Bearer {token_}',
                                                  'Content-Type': 'application/json'
                                                  }, json={
        'profile': {
            'email': 'fake_ask',
            'isLoggedIn': True
        }
    })

    events = ask_events.get_data(as_text=True)
    assert events is not None

    state_ = MongoDBClient.get_doctor_service_offer().find_one(
        {'convo_id': 'fake_ask'})

    assert state_ is not None
    assert state_['convo_id'] == 'fake_ask'
    assert state_['user_id'] == 'fake_ask'
    assert state_['event'] == 'capture_state'

