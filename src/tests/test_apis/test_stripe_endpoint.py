import json
import os

import stripe

from src.rx.doctor_service import DoctorService
from src.rx.doctor_service_state import DoctorServiceOfferEvent
from src.tests.test_apis.utils import app_client, get_credentials
from src.tests.utils import load_mogo_records


def test_stripe_create_session_endpoint(app_client):
    response = app_client.get('/new_token?session_id=FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    load_mogo_records('test_apis/test_data/cody_care_agent/collection.json',
                      None, doctor_service_file='test_apis/test_data/cody_care_agent/doctor_service_offer_payment.json')

    response = app_client.post('/create-checkout-session',
                               headers={'Content-Type': 'application/json',
                                        'Authorization': f'Bearer {token_}'})

    assert response.status_code == 200
    assert response.json['sessionId'] is not None

    response = app_client.get(f'/session-status?session_id={response.json["sessionId"]}',
                              headers={'Authorization': f'Bearer {token_}'})

    assert response.status_code == 200
    assert response.json['status'] == 'open'


def test_stripe_create_session_endpoint_no_offer_accepted_event(app_client):
    response = app_client.get('/new_token?session_id=FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    load_mogo_records('test_apis/test_data/cody_care_agent/collection.json',
                      None)

    response = app_client.post('/create-checkout-session',
                               headers={'Content-Type': 'application/json',
                                        'Authorization': f'Bearer {token_}'})

    assert response.status_code == 400
    assert response.json['error'] == 'No active service for this conversation'


def test_stripe_webhook_event_valid_payment_done(app_client):
    absolute_file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/cody_care_agent/stripe_webhook.json'))

    load_mogo_records('test_apis/test_data/cody_care_agent/collection.json',
                      None, doctor_service_file='test_apis/test_data/cody_care_agent/doctor_service_offer_payment.json')

    with open(absolute_file_path, 'r', encoding='utf-8') as file:
        file_data = json.load(file)

        payload, sig_header = valid_header(file_data)

        response = app_client.post('/stripe-webhook',
                                   headers={'Content-Type': 'application/json',
                                            'Stripe-Signature': sig_header},
                                   data=payload)

        assert response.status_code == 200

        service_event = DoctorService.latest_event('FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi')

        assert service_event.event == DoctorServiceOfferEvent.OFFER_PAYMENT_DONE
        assert service_event.payment['id'] == 'pi_3Ozj01Bl169sjuIE3wFvruKL'
        assert service_event.payment['receipt_url'] is not None


def test_stripe_webhook_event_not_valid_event_for_accept_offer(app_client):
    absolute_file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'test_data/cody_care_agent/stripe_webhook.json'))

    with open(absolute_file_path, 'r', encoding='utf-8') as file:
        file_data = json.load(file)

        payload, sig_header = valid_header(file_data)

        response = app_client.post('/stripe-webhook',
                                   headers={'Content-Type': 'application/json',
                                            'Stripe-Signature': sig_header},
                                   data=payload)

        assert response.status_code == 400
        assert response.json['error'] == 'Invalid service event'

        service_event = DoctorService.latest_event('FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi')

        assert service_event.event is None


def valid_header(file_data):
    # construct valid header for stripe webhook
    payload = json.dumps(file_data)
    secret = os.environ['STRIPE_ENDPOINT_SECRET']
    import time
    timestamp = int(time.time())
    signature = stripe.WebhookSignature._compute_signature(f'{timestamp}.{payload}', secret)
    sig_header = f't={timestamp},v1={signature}'
    return payload, sig_header
