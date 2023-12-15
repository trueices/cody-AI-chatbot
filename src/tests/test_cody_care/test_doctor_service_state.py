from datetime import datetime

import pytest
import requests_mock

from src.agents.cody_care_questionnaires import get_questionaire
from src.rx.doctor_service import DoctorService
from src.rx.doctor_service_state import DoctorServiceOfferEvent
from src.tests.utils import load_mogo_records
from src.utils import MongoDBClient


@pytest.fixture
def client():
    MongoDBClient.create_new_mock_instance()
    yield MongoDBClient.get_doctor_service_offer()


def test_doctor_service_event_capture(client):
    DoctorService.capture('test_offer_id', 'test_convo_id', 'test_user_id',
                          DoctorServiceOfferEvent.QUESTIONNAIRE_DONE_OFFER_INITIATED, {})

    data = MongoDBClient.get_doctor_service_offer().find_one(
        {'convo_id': 'test_convo_id'})

    assert data['offer_id'] == 'test_offer_id'
    assert data['user_id'] == 'test_user_id'
    assert data['event'] == 'questionnaire_done_offer_initiated'
    assert data['convo_id'] == 'test_convo_id'
    assert data['created'] is not None
    assert data['updated'] is not None


def test_doctor_service_event_capture_fail_unknown_field(client):
    with pytest.raises(Exception) as e:
        DoctorService.capture('test_offer_id', 'test_convo_id', 'test_user_id',
                              DoctorServiceOfferEvent.QUESTIONNAIRE_DONE_OFFER_INITIATED,
                              {'test_key': 'test_value'})

    assert str(
        e.value) == '"DoctorServiceOfferState" object has no field "test_key"'
    data = MongoDBClient.get_doctor_service_offer().find_one(
        {'convo_id': 'test_convo_id'})

    assert data is None


def test_latest_event(client):
    MongoDBClient.get_doctor_service_offer().insert_one({'convo_id': 'test_convo_id',
                                                         'user_id': 'test_user_id',
                                                         'offer_id': 'test_offer_id',
                                                         'event': 'questionnaire_done_offer_initiated',
                                                         'created': '2021-08-20T00:00:00',
                                                         'updated': '2021-08-20T00:00:00'})

    MongoDBClient.get_doctor_service_offer().insert_one({'convo_id': 'test_convo_id',
                                                         'user_id': 'test_user_id',
                                                         'offer_id': 'test_offer_id',
                                                         'event': 'offer_accepted',
                                                         'created': '2021-08-21T00:00:00',
                                                         'updated': '2021-08-21T00:00:00'})

    data = DoctorService.latest_event('test_convo_id')

    assert data.offer_id == 'test_offer_id'
    assert data.user_id == 'test_user_id'
    assert data.event == DoctorServiceOfferEvent.OFFER_ACCEPTED
    assert data.convo_id == 'test_convo_id'


def test_event_of_type(client):
    MongoDBClient.get_doctor_service_offer().insert_one({'convo_id': 'test_convo_id',
                                                         'user_id': 'test_user_id',
                                                         'offer_id': 'test_offer_id',
                                                         'event': 'questionnaire_done_offer_initiated',
                                                         'created': '2021-08-20T00:00:00',
                                                         'updated': '2021-08-20T00:00:00'})

    MongoDBClient.get_doctor_service_offer().insert_one({'convo_id': 'test_convo_id',
                                                         'user_id': 'test_user_id',
                                                         'offer_id': 'test_offer_id',
                                                         'event': 'offer_accepted',
                                                         'created': '2021-08-21T00:00:00',
                                                         'updated': '2021-08-21T00:00:00'})

    data = DoctorService.event_of_type(
        'test_offer_id', DoctorServiceOfferEvent.QUESTIONNAIRE_DONE_OFFER_INITIATED)

    assert data.offer_id == 'test_offer_id'
    assert data.user_id == 'test_user_id'
    assert data.event == DoctorServiceOfferEvent.QUESTIONNAIRE_DONE_OFFER_INITIATED
    assert data.convo_id == 'test_convo_id'


def test_update_event_details(client):
    time_now = datetime.strptime('2021-08-20T00:00:00', '%Y-%m-%dT%H:%M:%S')
    MongoDBClient.get_doctor_service_offer().insert_one({'convo_id': 'test_convo_id',
                                                         'user_id': 'test_user_id',
                                                         'offer_id': 'test_offer_id',
                                                         'event': DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE.inventory_name,
                                                         'created': time_now,
                                                         'updated': time_now})

    DoctorService.update_event_details('test_offer_id', DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE, {
        'questionnaire': {'What is your name?': 'test_name'}
    })

    data = MongoDBClient.get_doctor_service_offer().find_one(
        {'offer_id': 'test_offer_id'}, sort=[('created', -1)])

    assert data['offer_id'] == 'test_offer_id'
    assert data['user_id'] == 'test_user_id'
    assert data['event'] == DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE.inventory_name
    assert data['convo_id'] == 'test_convo_id'
    assert data['created'] is not None
    assert data['updated'] > time_now
    assert data['questionnaire'] == {'What is your name?': 'test_name'}


def test_update_event_details_fails_unknown_field(client):
    time_now = datetime.strptime('2021-08-20T00:00:00', '%Y-%m-%dT%H:%M:%S')
    MongoDBClient.get_doctor_service_offer().insert_one({'convo_id': 'test_convo_id',
                                                         'user_id': 'test_user_id',
                                                         'offer_id': 'test_offer_id',
                                                         'event': DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE.inventory_name,
                                                         'created': time_now,
                                                         'updated': time_now})

    with pytest.raises(ValueError) as e:
        DoctorService.update_event_details('test_offer_id', DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE, {
            'new_field': 'test_name'
        })

    assert str(
        e.value) == '"DoctorServiceOfferState" object has no field "new_field"'


def test_update_event_fail_if_updating_past_event(client):
    time_now = datetime.strptime('2021-08-20T00:00:00', '%Y-%m-%dT%H:%M:%S')
    time_now_plus_1 = datetime.strptime(
        '2021-08-21T00:00:00', '%Y-%m-%dT%H:%M:%S')

    MongoDBClient.get_doctor_service_offer().insert_one({'convo_id': 'test_convo_id',
                                                         'user_id': 'test_user_id',
                                                         'offer_id': 'test_offer_id',
                                                         'event': DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE.inventory_name,
                                                         'created': time_now,
                                                         'updated': time_now})

    MongoDBClient.get_doctor_service_offer().insert_one({'convo_id': 'test_convo_id',
                                                         'user_id': 'test_user_id',
                                                         'offer_id': 'test_offer_id',
                                                         'event': DoctorServiceOfferEvent.QUESTIONNAIRE_DONE_OFFER_INITIATED.inventory_name,
                                                         'created': time_now_plus_1,
                                                         'updated': time_now_plus_1})

    with pytest.raises(Exception) as e:
        DoctorService.update_event_details('test_offer_id', DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE, {
            'questionnaire': {'What is your name?': 'test_name'}
        })

    assert str(
        e.value) == ('Cannot update event details for ro_questionnaire_capture as latest event is '
                     'questionnaire_done_offer_initiated. Only latest event can be updated.')


def test_send_to_ehr(client, monkeypatch):
    monkeypatch.setenv('AKUTE_API_KEY', 'test_key')
    monkeypatch.setenv('AKUTE_BASE_URL', 'https://api.staging.akutehealth.com')
    monkeypatch.setenv('MOCK_EMAIL', 'true')

    time_now = datetime.strptime('2021-08-20T00:00:00', '%Y-%m-%dT%H:%M:%S')

    _capture_onboarding_event(time_now)

    MongoDBClient.get_doctor_service_offer().insert_one(
        {'convo_id': 'FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
         'user_id': 'test_user_id',
         'offer_id': 'test_offer_id',
         'event': DoctorServiceOfferEvent.SEND_TO_EHR.inventory_name,
         'created': time_now,
         'updated': time_now})

    MongoDBClient.get_doctor_service_offer().insert_one(
        {'convo_id': 'FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
         'user_id': 'test_user_id',
         'offer_id': 'test_offer_id',
         'event': DoctorServiceOfferEvent.HCP_MATCH.inventory_name,
         'created': time_now,
         'updated': time_now,
         'hcp': {
             'id': 'test_hcp_id',
             'name': 'test_hcp_name',
             'email': 'test_hcp_email',
         }
         })

    MongoDBClient.get_doctor_service_offer().insert_one(
        {'convo_id': 'FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
         'user_id': 'test_user_id',
         'offer_id': 'test_offer_id',
         'event': DoctorServiceOfferEvent.CAPTURE_STATE.inventory_name,
         'created': time_now,
         'updated': time_now,
         'state': 'oregon'
         })

    MongoDBClient.get_users().insert_one({'email': 'test_user_id',
                                          'firstName': {'value': 'test'},
                                          'lastName': {'value': 'user'}})

    load_mogo_records("test_cody_care/test_data/convo/collection.json")

    with requests_mock.Mocker() as req:
        req.post('https://api.staging.akutehealth.com/v1/patients', status_code=201, json={
            'statusCode': 201,
            'data': {'id': 'test_ehr_id'}
        })

        req.post('https://api.staging.akutehealth.com/v1/tasks', status_code=201, json={
            'statusCode': 201,
            'data': {'id': 'test_task_id'}
        })

        DoctorService.process_for_ehr('test_offer_id')

    data = MongoDBClient.get_doctor_service_offer().find_one(
        {'offer_id': 'test_offer_id'}, sort=[('created', -1)])

    assert data['event'] == DoctorServiceOfferEvent.EHR_SENT.inventory_name
    assert data['ehr_task_id'] == 'test_task_id'

    user_data = MongoDBClient.get_users().find_one({'email': 'test_user_id'})

    assert user_data['ehr_id'] == 'test_ehr_id'

    history = req.request_history

    assert history[0].url == 'https://api.staging.akutehealth.com/v1/patients'
    assert history[0].text == ('first_name=test&last_name=user&email=test_user_id&sex=male&primary_phone_number'
                               '=1234567890&primary_phone_type=mobile&date_of_birth=1988-11-17&appointment_state'
                               '=OR&address_line_1=NA&address_city=NA&address_state=OR&address_zipcode=99999&status'
                               '=active')

    assert history[1].url == 'https://api.staging.akutehealth.com/v1/tasks'

    assert history[1].json().keys() == {
        'patient_id', 'task', 'priority', 'status', 'owner_id', 'description'}

    assert history[1].json()['patient_id'] == 'test_ehr_id'
    assert history[1].json()['task'] == 'Pending Visit: fever'
    assert history[1].json()['priority'] == 'p2'
    assert history[1].json()['status'] == 'not-started'
    assert history[1].json()['owner_id'] == 'test_hcp_id'

    description_fields = ['Conversation ID', 'Chief Complaint', 'DOB', 'Gender', 'Medications', 'Allergies',
                          'Medical History', 'Pharmacy']

    assert all(field in history[1].json()['description']
               for field in description_fields)


def test_send_to_ehr_patient_ehr_already_present(client, monkeypatch):
    monkeypatch.setenv('AKUTE_API_KEY', 'test_key')
    monkeypatch.setenv('AKUTE_BASE_URL', 'https://api.staging.akutehealth.com')
    monkeypatch.setenv('MOCK_EMAIL', 'true')

    time_now = datetime.strptime('2021-08-20T00:00:00', '%Y-%m-%dT%H:%M:%S')

    MongoDBClient.get_doctor_service_offer().insert_one(
        {'convo_id': 'FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
         'user_id': 'test_user_id',
         'offer_id': 'test_offer_id',
         'event': DoctorServiceOfferEvent.SEND_TO_EHR.inventory_name,
         'created': time_now,
         'updated': time_now})

    MongoDBClient.get_doctor_service_offer().insert_one(
        {'convo_id': 'FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
         'user_id': 'test_user_id',
         'offer_id': 'test_offer_id',
         'event': DoctorServiceOfferEvent.HCP_MATCH.inventory_name,
         'created': time_now,
         'updated': time_now,
         'hcp': {
             'id': 'test_hcp_id',
             'name': 'test_hcp_name',
             'email': 'test_hcp_email',
         }
         })

    MongoDBClient.get_users().insert_one({'email': 'test_user_id',
                                          'ehr_id': 'test_ehr_id',
                                          'firstName': {'value': 'test'},
                                          'lastName': {'value': 'user'}},
                                         )
    _capture_onboarding_event(time_now)

    load_mogo_records("test_cody_care/test_data/convo/collection.json")

    with requests_mock.Mocker() as req:
        req.post('https://api.staging.akutehealth.com/v1/tasks', status_code=201, json={
            'statusCode': 201,
            'data': {'id': 'test_task_id'}
        })

        DoctorService.process_for_ehr('test_offer_id')

    data = MongoDBClient.get_doctor_service_offer().find_one(
        {'offer_id': 'test_offer_id'}, sort=[('created', -1)])

    assert data['event'] == DoctorServiceOfferEvent.EHR_SENT.inventory_name
    assert data['ehr_task_id'] == 'test_task_id'

    history = req.request_history

    assert history[0].url == 'https://api.staging.akutehealth.com/v1/tasks'


def test_send_to_ehr_failed(client, monkeypatch):
    monkeypatch.setenv('AKUTE_API_KEY', 'test_key')
    monkeypatch.setenv('AKUTE_BASE_URL', 'https://api.staging.akutehealth.com')

    time_now = datetime.strptime('2021-08-20T00:00:00', '%Y-%m-%dT%H:%M:%S')

    MongoDBClient.get_doctor_service_offer().insert_one(
        {'convo_id': 'FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
         'user_id': 'test_user_id',
         'offer_id': 'test_offer_id',
         'event': DoctorServiceOfferEvent.SEND_TO_EHR.inventory_name,
         'created': time_now,
         'updated': time_now})

    MongoDBClient.get_users().insert_one({'email': 'test_user_id',
                                          'ehr_id': 'test_ehr_id',
                                          'firstName': {'value': 'test'},
                                          'lastName': {'value': 'user'}},
                                         )

    _capture_onboarding_event(time_now)

    load_mogo_records("test_cody_care/test_data/convo/collection.json")

    with requests_mock.Mocker() as req:
        req.post('https://api.staging.akutehealth.com/v1/tasks', status_code=500, json={
            'statusCode': 500,
            'error': 'Internal Server Error'
        })

        with pytest.raises(Exception) as e:
            DoctorService.process_for_ehr('test_offer_id')

        assert str(
            e.value) == 'Failed to create task in EHR, response: {\'statusCode\': 500, \'error\': \'Internal Server Error\'}'

    data = MongoDBClient.get_doctor_service_offer().find_one(
        {'offer_id': 'test_offer_id'}, sort=[('created', -1)])

    assert data['event'] == DoctorServiceOfferEvent.SEND_TO_EHR.inventory_name


def test_create_patient_failed(client, monkeypatch):
    monkeypatch.setenv('AKUTE_API_KEY', 'test_key')
    monkeypatch.setenv('AKUTE_BASE_URL', 'https://api.staging.akutehealth.com')

    time_now = datetime.strptime('2021-08-20T00:00:00', '%Y-%m-%dT%H:%M:%S')

    MongoDBClient.get_doctor_service_offer().insert_one(
        {'convo_id': 'FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
         'user_id': 'test_user_id',
         'offer_id': 'test_offer_id',
         'event': DoctorServiceOfferEvent.SEND_TO_EHR.inventory_name,
         'created': time_now,
         'updated': time_now})

    _capture_onboarding_event(time_now)

    MongoDBClient.get_users().insert_one({'email': 'test_user_id',
                                          'firstName': {'value': 'test'},
                                          'lastName': {'value': 'user'}})

    load_mogo_records("test_cody_care/test_data/convo/collection.json")

    with requests_mock.Mocker() as req:
        req.post('https://api.staging.akutehealth.com/v1/patients', status_code=500, json={
            'statusCode': 500,
            'error': 'Internal Server Error'
        })

        with pytest.raises(Exception) as e:
            DoctorService.process_for_ehr('test_offer_id')

        assert str(
            e.value) == 'Failed to create patient in EHR, response: {\'statusCode\': 500, \'error\': \'Internal Server Error\'}'

    data = MongoDBClient.get_doctor_service_offer().find_one(
        {'offer_id': 'test_offer_id'}, sort=[('created', -1)])

    assert data['event'] == DoctorServiceOfferEvent.SEND_TO_EHR.inventory_name

    user_data = MongoDBClient.get_users().find_one({'email': 'test_user_id'})

    assert user_data.get('ehr_id') is None

    history = req.request_history

    assert len(history) == 1
    assert history[0].url == 'https://api.staging.akutehealth.com/v1/patients'
    assert history[0].text == ('first_name=test&last_name=user&email=test_user_id&sex=male&primary_phone_number'
                               '=1234567890&primary_phone_type=mobile&date_of_birth=1988-11-17&status=active')


def _capture_onboarding_event(time_now):
    questionnaire = get_questionaire('onboarding')
    for question in questionnaire:
        if question['id'] == 'DOB':
            question['response'] = 'Nov 17, 1988'
            question['llm_response'] = '11/17/1988'
        elif question['id'] == 'PHONE':
            question['formatted_response'] = '1234567890'
        elif question['id'] == 'SEX_AT_BIRTH':
            question['response'] = 'male'
            question['llm_response'] = 2
        else:
            question['response'] = 'test_response'
            question['llm_response'] = 'test_llm_response'
    MongoDBClient.get_doctor_service_offer().insert_one(
        {'convo_id': 'FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
         'user_id': 'test_user_id',
         'offer_id': 'test_offer_id',
         'event': DoctorServiceOfferEvent.ONBOARDING_QUESTIONNAIRE_CAPTURE.inventory_name,
         'created': time_now,
         'updated': time_now,
         'questionnaire': questionnaire
         })


def test_event_for_task_id(client):
    time_now = datetime.strptime('2021-08-20T00:00:00', '%Y-%m-%dT%H:%M:%S')

    MongoDBClient.get_doctor_service_offer().insert_many([
        {'convo_id': 'convo_id_1',
         'user_id': 'user_id_1',
         'offer_id': 'offer_id_1',
         'event': DoctorServiceOfferEvent.EHR_SENT.inventory_name,
         'created': time_now,
         'updated': time_now,
         'ehr_task_id': 'task_id_1'
         },
        {'convo_id': 'convo_id_2',
         'user_id': 'user_id_2',
         'offer_id': 'offer_id_2',
         'event': DoctorServiceOfferEvent.EHR_SENT.inventory_name,
         'created': time_now,
         'updated': time_now,
         'ehr_task_id': 'task_id_2'
         }
    ])

    data = DoctorService.get_event_for_task_id('task_id_1')
    assert data.offer_id == 'offer_id_1'
    assert data.user_id == 'user_id_1'
    assert data.ehr_task_id == 'task_id_1'

    data = DoctorService.get_event_for_task_id('non_existent_task_id')
    assert data is None


def test_process_for_certified_plan(client, monkeypatch):
    import os
    import json
    MongoDBClient.get_doctor_service_offer().insert_one(
        {'convo_id': 'convo_id',
         'user_id': 'user_id',
         'offer_id': 'offer_id',
         'event': DoctorServiceOfferEvent.EHR_TASK_DONE.inventory_name,
         'created': '2021-08-20T00:00:00',
         'updated': '2021-08-20T00:00:00',
         'ehr_task_id': 'task_id_1',
         'ehr_task': {
             'patient_id': 'patient_id_1',
             'last_updated': '2021-08-20T00:00:00',
             'date_created': '2021-08-20T00:00:00',
         }
         }
    )

    # Mock notes data
    monkeypatch.setenv('AKUTE_API', 'test_key')
    monkeypatch.setenv('AKUTE_BASE_URL', 'https://api.staging.akutehealth.com')
    # Mock email sender
    monkeypatch.setenv('MOCK_EMAIL', 'true')

    notes = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/akute/notes.json'))
    with open(notes, 'r', encoding='utf-8') as file:
        notes_data = file.read()

    with requests_mock.Mocker() as req:
        req.get('https://api.staging.akutehealth.com/v1/notes',
                json=json.loads(notes_data))

        DoctorService.process_for_certified_plan('offer_id')

    assert req.request_history[0].url == 'https://api.staging.akutehealth.com/v1/notes?patient_id=patient_id_1&limit=10&service_date_start=2021-08-20&status=final'

    # Verfiy if EHR_PLAN_READY event is captured
    data = MongoDBClient.get_doctor_service_offer().find_one(
        {'offer_id': 'offer_id', 'event': DoctorServiceOfferEvent.EHR_PLAN_READY.inventory_name})
    assert data is not None
    assert data['questionnaire'][0]['id'] == 'PLAN_ACKNOWLEDGEMENT'
    assert data['questionnaire'][0]['presented'] == True

    # Verify conversation history is updated.
    data = MongoDBClient.get_botstate().find_one({'username': 'convo_id'})
    assert data['current_agent_name'] == 'cody_care_agent'
    data = MongoDBClient.get_full_conv_hist().find_one(
        {'conversation_id': "convo_id"})
    assert data['full_conv_hist'][-1]['role'] == 'assistant'
    assert '\n\n\nPLAN 2: Here is your Certified Plan' in data['full_conv_hist'][-1]['content']
