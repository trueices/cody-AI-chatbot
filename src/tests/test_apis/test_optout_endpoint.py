from src.tests.test_apis.utils import get_credentials, app_client
from src.utils import MongoDBClient


def test_opt_out_endpoint_success_response(app_client):
    response = app_client.get('/new_token?session_id=mgvg2skD9ecihUlx8CHA4SorKdHv9xcZ7YqLbsUjf1TRZkCiPS',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    MongoDBClient.get_followup_care().insert_one({'convo_id': 'mgvg2skD9ecihUlx8CHA4SorKdHv9xcZ7YqLbsUjf1TRZkCiPS',
                                                  'user_id': 'test_user_id_1',
                                                  'email_address': 'test_email_address',
                                                  'name': 'test_name_1',
                                                  'state': 'new',
                                                  'chief_complaint': 'test_chief_complaint',
                                                  'is_locked': False,
                                                  'next_followup_date': '2021-08-01T00:00:00.000Z'})

    meta_ = app_client.get('/care/optout', headers={'Authorization': f'Bearer {token_}'})
    assert meta_.status_code == 200
    assert meta_.json['message'] == 'Opted out successfully'


def test_opt_out_endpoint_400_response(app_client):
    response = app_client.get('/new_token?session_id=mgvg2skD9ecihUlx8CHA4SorKdHv9xcZ7YqLbsUjf1TRZkCiPS',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    MongoDBClient.get_followup_care().insert_one({'convo_id': 'different_convo_id',
                                                  'user_id': 'test_user_id_1',
                                                  'email_address': 'test_email_address',
                                                  'name': 'test_name_1',
                                                  'state': 'new',
                                                  'chief_complaint': 'test_chief_complaint',
                                                  'is_locked': False,
                                                  'next_followup_date': '2021-08-01T00:00:00.000Z'})

    meta_ = app_client.get('/care/optout', headers={'Authorization': f'Bearer {token_}'})
    assert meta_.status_code == 400
    assert meta_.json['error'] == 'Not eligible for opt out'
