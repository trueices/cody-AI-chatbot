from src.utils import MongoDBClient
from src.tests.test_apis.utils import get_credentials, app_client


def test_stats_endpoint_response(app_client):
    response = app_client.get('/new_token?session_id=mgvg2skD9ecihUlx8CHA4SorKdHv9xcZ7YqLbsUjf1TRZkCiPS',
                          headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    MongoDBClient.get_stats().insert_one({'_id': 'meta', 'dxCount': 5})

    meta_ = app_client.get('/stats', headers={'Authorization': f'Bearer {token_}'})
    assert meta_.status_code == 200
    assert meta_.json['dxCount'] == 5
