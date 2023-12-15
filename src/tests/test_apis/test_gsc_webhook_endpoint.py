from src.tests.test_apis.utils import app_client
from src.utils import MongoDBClient


def test_webhook_endpoint_success_response(app_client):
    response = app_client.post('/gsc/webhook',
                               headers={'User-Agent': 'Getsitecontrol WebHook',
                                        'Content-Type': 'application/x-www-form-urlencoded'},
                               data={'convo_id': 'convo_id_1', 'user_email': 'test_user_id_1',
                                     'cc_code': 'NO',
                                     'cc_city': 'Oslo',
                                     'nps': '10',
                                     'environment': 'production'})

    assert response.status_code == 200
    assert response.json['message'] == 'success'

    record = MongoDBClient.get_convo_analytics().find_one({'convo_id': 'convo_id_1'})

    assert record['convo_id'] == 'convo_id_1'
    assert record['user_email'] == 'test_user_id_1'
    assert record['gsc_cc_code'] == 'NO'
    assert record['gsc_city'] == 'Oslo'
    assert record['nps'] == '10'


def test_webhook_endpoint_401_response(app_client):
    response = app_client.post('/gsc/webhook',
                               headers={'Content-Type': 'application/x-www-form-urlencoded'},
                               data={'convo_id': 'convo_id_1', 'user_email': 'test_user_id_1',
                                     'cc_code': 'NO',
                                     'cc_city': 'Oslo',
                                     'nps': '10',
                                     'environment': 'production'})

    assert response.status_code == 401

    record = MongoDBClient.get_convo_analytics().find_one({'convo_id': 'convo_id_1'})

    assert record is None


def test_webhook_endpoint_success_response_no_entry_non_prod(app_client):
    response = app_client.post('/gsc/webhook',
                               headers={'User-Agent': 'Getsitecontrol WebHook',
                                        'Content-Type': 'application/x-www-form-urlencoded'},
                               data={'convo_id': 'convo_id_1', 'user_email': 'test_user_id_1',
                                     'cc_code': 'NO',
                                     'cc_city': 'Oslo',
                                     'nps': '10',
                                     'environment': 'staging'})

    assert response.status_code == 200
    assert response.json['message'] == 'success'

    record = MongoDBClient.get_convo_analytics().find_one({'convo_id': 'convo_id_1'})

    assert record is None
