import json
import os

import requests_mock

from src.rx.ehr_service import EhrService


def test_all_supported_state(monkeypatch):
    monkeypatch.setenv('AKUTE_API_KEY', 'test_key')
    monkeypatch.setenv('AKUTE_BASE_URL', 'https://api.staging.akutehealth.com')

    prescribers = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/akute/prescribers.json'))

    with open(prescribers, 'r', encoding='utf-8') as file:
        prescribers_data = file.read()

        with requests_mock.Mocker() as req:
            req.get('https://api.staging.akutehealth.com/v1/users',
                    status_code=500)

            states_ = EhrService().all_supported_state()

            assert states_ == set()

            mock = req.get('https://api.staging.akutehealth.com/v1/users',
                           json=json.loads(prescribers_data))

            states_ = EhrService().all_supported_state()

            assert states_ == {'california', 'arizona'}

            states_ = EhrService().all_supported_state()

            assert states_ == {'california', 'arizona'}
            assert mock.call_count == 1


def test_match_prescriber(monkeypatch):
    monkeypatch.setenv('AKUTE_API_KEY', 'test_key')
    monkeypatch.setenv('AKUTE_BASE_URL', 'https://api.staging.akutehealth.com')

    prescribers = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/akute/prescribers.json'))

    with open(prescribers, 'r', encoding='utf-8') as file:
        prescribers_data = file.read()

        with requests_mock.Mocker() as req:
            req.get('https://api.staging.akutehealth.com/v1/users',
                    json=json.loads(prescribers_data))

            prescriber = EhrService().match_prescriber({
                'state': 'California'
            })

            assert prescriber.get('id') == '634c7e2b2ceaa80009a25652'

            prescriber = EhrService().match_prescriber({
                'state': 'Arizona'
            })

            assert prescriber.get('id') == '634c83742688fa3e21c7c9d4'

            prescriber = EhrService().match_prescriber({
                'state': 'Texas'
            })

            assert prescriber.get('id') is None


def test_match_prescriber_no_bio(monkeypatch):
    monkeypatch.setenv('AKUTE_API_KEY', 'test_key')
    monkeypatch.setenv('AKUTE_BASE_URL', 'https://api.staging.akutehealth.com')

    prescribers = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/akute/prescribers.json'))

    with open(prescribers, 'r', encoding='utf-8') as file:
        prescribers_data = file.read()

        prescriber_json = json.loads(prescribers_data)

        for prescriber in prescriber_json:
            if prescriber.get('bio'):
                del prescriber['bio']

        with requests_mock.Mocker() as req:
            req.get('https://api.staging.akutehealth.com/v1/users',
                    json=prescriber_json)

            prescriber = EhrService().match_prescriber({
                'state': 'California'
            })

            assert prescriber.get('id') == '634c7e2b2ceaa80009a25652'


def test_get_plan(monkeypatch):
    monkeypatch.setenv('AKUTE_API', 'test_key')
    monkeypatch.setenv('AKUTE_BASE_URL', 'https://api.staging.akutehealth.com')

    notes = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/akute/notes.json'))
    with open(notes, 'r', encoding='utf-8') as file:
        notes_data = file.read()

    with requests_mock.Mocker() as req:
        req.get('https://api.staging.akutehealth.com/v1/notes',
                json=json.loads(notes_data))

        plan = EhrService().get_plan(patient_id='1234',
                                     start_date='2024-04-01')

        assert plan.startswith('PLAN 2: Here is your Certified Plan')
