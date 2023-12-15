import json
import os
import time

from src.rx.doctor_service import DoctorService, DoctorServiceOfferEvent
from src.tests.test_apis.utils import app_client
from utils import compute_signature


def test_akute_ehr_task_complete(app_client, monkeypatch):
    monkeypatch.setenv('AKUTE_WEBHOOK_SECRET',
                       'whsec_FMOBUksDqUGCE9UsxPPtnYFm14FLroLm')
    monkeypatch.setattr(time, 'time', lambda: 1712826554.0)
    headers = {
        'x-akute-signature': 't=1712826554,v1=d54b0de319760e94d8bd597143850f47aa7c54c502af7c7156d1eb3a70fca2c6',
        'Content-Type': 'application/json'
    }
    absolute_file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/cody_care_agent/akute_webhook.json'))

    with open(absolute_file_path, 'r', encoding='utf-8') as file:
        file_data = file.read()
        compressed_data = json.dumps(json.loads(file_data), separators=(',', ':'))

    DoctorService.capture('offer_id', 'convo_id', 'user_id', DoctorServiceOfferEvent.EHR_SENT, {
        'ehr_task_id': '6615815b0f950b0a26a80499',
    })

    response = app_client.post(
        '/akute-webhook', headers=headers, data=compressed_data)

    assert response.status_code == 200
    assert response.json['message'] == 'success'


def test_akute_task_not_found(app_client, monkeypatch):
    monkeypatch.setenv('AKUTE_WEBHOOK_SECRET',
                       'whsec_FMOBUksDqUGCE9UsxPPtnYFm14FLroLm')
    monkeypatch.setattr(time, 'time', lambda: 1712826554.0)
    headers = {
        'x-akute-signature': 't=1712826554,v1=d54b0de319760e94d8bd597143850f47aa7c54c502af7c7156d1eb3a70fca2c6',
        'Content-Type': 'application/json'
    }

    absolute_file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/cody_care_agent/akute_webhook.json'))

    with open(absolute_file_path, 'r', encoding='utf-8') as file:
        file_data = file.read()
        compressed_data = json.dumps(json.loads(file_data), separators=(',', ':'))

    response = app_client.post(
        '/akute-webhook', headers=headers, data=compressed_data)

    assert response.status_code == 200
    assert response.json['message'] == 'No event found for task 6615815b0f950b0a26a80499'


def test_auth_failure(app_client, monkeypatch):
    monkeypatch.setenv('AKUTE_WEBHOOK_SECRET',
                       'random_secret')
    monkeypatch.setattr(time, 'time', lambda: 1712826554.0)
    headers = {
        'x-akute-signature': 't=1712826554,v1=d54b0de319760e94d8bd597143850f47aa7c54c502af7c7156d1eb3a70fca2c6',
        'Content-Type': 'application/json'
    }

    absolute_file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/cody_care_agent/akute_webhook.json'))

    with open(absolute_file_path, 'r', encoding='utf-8') as file:
        file_data = file.read()
        compressed_data = json.dumps(json.loads(file_data), separators=(',', ':'))

    response = app_client.post(
        '/akute-webhook', headers=headers, data=compressed_data)

    assert response.status_code == 401
    assert response.json['error'] == 'Unauthorized'


def test_akute_task_incomplete(app_client, monkeypatch):
    monkeypatch.setenv('AKUTE_WEBHOOK_SECRET',
                       'whsec_FMOBUksDqUGCE9UsxPPtnYFm14FLroLm')
    monkeypatch.setattr(time, 'time', lambda: 1712826554.0)
    headers = {
        'x-akute-signature': 't=1712826554,v1=d54b0de319760e94d8bd597143850f47aa7c54c502af7c7156d1eb3a70fca2c6',
        'Content-Type': 'application/json'
    }
    absolute_file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/cody_care_agent/akute_webhook.json'))

    with open(absolute_file_path, 'r', encoding='utf-8') as file:
        file_data = file.read()
        data = json.loads(file_data)
        data['status'] = 'in-progress'
        compressed_data = json.dumps(data, separators=(',', ':'))

    signature = compute_signature(1712826554, compressed_data, 'whsec_FMOBUksDqUGCE9UsxPPtnYFm14FLroLm')
    headers['x-akute-signature'] = f't=1712826554,v1={signature}'
    response = app_client.post(
        '/akute-webhook', headers=headers, data=compressed_data)

    assert response.status_code == 200
    assert response.json['message'] == 'Task not completed'
