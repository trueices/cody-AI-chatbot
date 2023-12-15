import base64

import pytest

from application import application
from src.tests.utils import setup_code


def get_credentials():
    username = 'cody_frontend'
    password = 'frontend@123'
    credentials = base64.b64encode(
        f'{username}:{password}'.encode()).decode('utf-8')
    return credentials


@pytest.fixture
def app_client():
    setup_code()
    with application.test_client() as client:
        yield client
