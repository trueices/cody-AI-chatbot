from src.tests.test_apis.utils import get_credentials
from src import bot_state
from application import application


def test_index():
    response = application.test_client().get('/')
    assert response.status_code == 200
    assert response.data.decode() == f"Welcome to Cody! v{bot_state.VERSION}"


def test_new_token():
    # add basic auth headers to test client and call endpoint called /new_token with the test client
    response_1 = application.test_client().get(
        '/new_token', headers={'Authorization': f'Basic {get_credentials()}'})
    response_2 = application.test_client().get(
        '/new_token', headers={'Authorization': f'Basic {get_credentials()}'})

    assert response_1.status_code == 200
    assert response_2.status_code == 200
    assert response_1.json['access_token'] is not None
    assert response_2.json['access_token'] is not None
    assert response_1.json['access_token'] != response_2.json['access_token']
    assert len(response_1.json['access_token']) > 100
