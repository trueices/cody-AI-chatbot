import json
import os

from src.rx.doctor_service import DoctorService
from src.rx.doctor_service_state import DoctorServiceOfferEvent
from src.tests.test_apis.utils import app_client
from src.utils import MongoDBClient


def test_webhook_endpoint_success_response(app_client, monkeypatch):
    monkeypatch.setenv('VERIFF_WEBHOOK_KEY', 'test_VERIFF_WEBHOOK_KEY')

    absolute_file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/cody_care_agent/veriff_webhook.json'))

    with open(absolute_file_path, 'r', encoding='utf-8') as file:
        file_data = file.read()

    MongoDBClient.get_users().insert_one({'_id': 'test_user_id_1', 'email': 'test_user_id_1'})

    DoctorService.capture('YDQI58M2JK2RCLU2H8N21W8L1F6EDJIZB8J1OHFOTY6E60VSWS', 'convo_id_1', 'test_user_id_1',
                          DoctorServiceOfferEvent.VERIFY_USER, {})

    response = app_client.post('/veriff-webhook',
                               json=json.loads(file_data))

    assert response.status_code == 401

    response = app_client.post('/veriff-webhook',
                               headers={'x-auth-client': 'test_VERIFF_WEBHOOK_KEY'},
                               json=json.loads(file_data))

    assert response.status_code == 200
    assert response.json['message'] == 'success'

    record = MongoDBClient.get_doctor_service_offer().find_one(
        {'offer_id': 'YDQI58M2JK2RCLU2H8N21W8L1F6EDJIZB8J1OHFOTY6E60VSWS', 'event': 'user_verified'},)

    assert record['convo_id'] == 'convo_id_1'
    assert record['event'] == DoctorServiceOfferEvent.USER_VERIFIED.inventory_name
    assert record['verification'] is not None

    user_ = MongoDBClient.get_users().find_one({'email': 'test_user_id_1'})

    assert user_['verified']['value'] is True


def test_webhook_endpoint_success_response_user_not_verified(app_client, monkeypatch):
    monkeypatch.setenv('VERIFF_WEBHOOK_KEY', 'test_VERIFF_WEBHOOK_KEY')

    DoctorService.capture('YDQI58M2JK2RCLU2H8N21W8L1F6EDJIZB8J1OHFOTY6E60VSWS', 'convo_id_1', 'test_user_id_1',
                          DoctorServiceOfferEvent.VERIFY_USER, {})

    absolute_file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/cody_care_agent/veriff_webhook.json'))

    with open(absolute_file_path, 'r', encoding='utf-8') as file:
        file_data = file.read()

    json_response = json.loads(file_data)

    json_response['data']['verification']['decision'] = 'declined'

    MongoDBClient.get_users().insert_one({'_id': 'test_user_id_1', 'email': 'test_user_id_1'})

    response = app_client.post('/veriff-webhook',
                               headers={'x-auth-client': 'test_VERIFF_WEBHOOK_KEY'},
                               json=json_response)

    assert response.status_code == 200
    assert response.json['message'] == 'success'

    record = MongoDBClient.get_doctor_service_offer().find_one(
        {'offer_id': 'YDQI58M2JK2RCLU2H8N21W8L1F6EDJIZB8J1OHFOTY6E60VSWS', 'event': 'user_verification_failed'}, sort=[('created', -1)])

    assert record['convo_id'] == 'convo_id_1'
    assert record['event'] == DoctorServiceOfferEvent.USER_VERIFICATION_FAILED.inventory_name
    assert record['verification'] is not None

    user_ = MongoDBClient.get_users().find_one({'email': 'test_user_id_1'})

    assert user_.keys() == {'_id', 'email'}


def test_webhook_endpoint_success_response_invalid_event_from_before(app_client, monkeypatch):
    monkeypatch.setenv('VERIFF_WEBHOOK_KEY', 'test_VERIFF_WEBHOOK_KEY')

    absolute_file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/cody_care_agent/veriff_webhook.json'))

    with open(absolute_file_path, 'r', encoding='utf-8') as file:
        file_data = file.read()

    json_response = json.loads(file_data)

    json_response['data']['verification']['decision'] = 'approved'

    MongoDBClient.get_users().insert_one({'_id': 'test_user_id_1', 'email': 'test_user_id_1'})

    DoctorService.capture('YDQI58M2JK2RCLU2H8N21W8L1F6EDJIZB8J1OHFOTY6E60VSWS', 'convo_id_1', 'test_user_id_1',
                          DoctorServiceOfferEvent.USER_VERIFIED, {})

    response = app_client.post('/veriff-webhook',
                               headers={'x-auth-client': 'test_VERIFF_WEBHOOK_KEY'},
                               json=json_response)

    assert response.status_code == 200
    assert response.json['error'] == 'Invalid service event'

    record = MongoDBClient.get_doctor_service_offer().find_one(
        {'offer_id': 'YDQI58M2JK2RCLU2H8N21W8L1F6EDJIZB8J1OHFOTY6E60VSWS'}, sort=[('created', -1)])

    assert record['event'] == DoctorServiceOfferEvent.USER_VERIFIED.inventory_name

    user_ = MongoDBClient.get_users().find_one({'email': 'test_user_id_1'})

    assert user_.keys() == {'_id', 'email'}
