from src.tests.test_apis.utils import get_credentials, app_client
from src.tests.utils import load_mogo_records


def test_meta_endpoint_response(app_client):
    response = app_client.get('/new_token?session_id=mgvg2skD9ecihUlx8CHA4SorKdHv9xcZ7YqLbsUjf1TRZkCiPS',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    load_mogo_records('test_apis/test_data/diagnosis/collection.json',
                      'test_apis/test_data/diagnosis/full_convo_history.json')

    meta_ = app_client.get(
        '/ask/meta', headers={'Authorization': f'Bearer {token_}'})
    assert meta_.status_code == 200
    assert meta_.json.keys() == {'cc_specialist',
                                 'cc_sub_speciality',
                                 'chief_complaint',
                                 'diagnosis_list',
                                 'dx_group_list',
                                 'dx_specialist_list',
                                 'serving_agent_name',
                                 'concierge_option'}
    assert meta_.json['chief_complaint'] == 'faint line on pregnancy test'
    assert meta_.json['serving_agent_name'] == 'diagnosis_agent'
    assert len(meta_.json['diagnosis_list']) == 3
    assert len(meta_.json['dx_group_list']) == 2
    assert len(meta_.json['dx_specialist_list']) == 2
    assert meta_.json['concierge_option'] == 'detailed'


def test_meta_endpoint_response_doctor_service_payment(app_client):
    response = app_client.get('/new_token?session_id=FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    load_mogo_records('test_apis/test_data/cody_care_agent/collection.json',
                      None, doctor_service_file='test_apis/test_data/cody_care_agent/doctor_service_offer_payment.json')

    meta_ = app_client.get(
        '/ask/meta', headers={'Authorization': f'Bearer {token_}'})
    assert meta_.status_code == 200

    assert meta_.json.keys() == {'cc_specialist',
                                 'cc_sub_speciality',
                                 'chief_complaint',
                                 'diagnosis_list',
                                 'dx_group_list',
                                 'dx_specialist_list',
                                 'serving_agent_name',
                                 'initiate_payment',
                                 'offer_id',
                                 'concierge_option'
                                 }

    assert meta_.json['serving_agent_name'] == 'cody_care_agent'
    assert meta_.json['initiate_payment'] is True
    assert meta_.json['offer_id'] == 'MN3PUJ0E0PJCPLCWYQHOK9BX2V0VCNXT3XFH0A4PARTM7H1ZXH'


def test_meta_endpoint_response_doctor_service_verification(app_client):
    response = app_client.get('/new_token?session_id=FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    load_mogo_records('test_apis/test_data/cody_care_agent/collection.json',
                      None, doctor_service_file='test_apis/test_data/cody_care_agent/doctor_service_offer_verification.json')

    meta_ = app_client.get(
        '/ask/meta', headers={'Authorization': f'Bearer {token_}'})
    assert meta_.status_code == 200

    assert meta_.json.keys() == {'cc_specialist',
                                 'cc_sub_speciality',
                                 'chief_complaint',
                                 'diagnosis_list',
                                 'dx_group_list',
                                 'dx_specialist_list',
                                 'serving_agent_name',
                                 'initiate_verification',
                                 'offer_id',
                                 'concierge_option'
                                 }

    assert meta_.json['serving_agent_name'] == 'cody_care_agent'
    assert meta_.json['initiate_verification'] is True
    assert meta_.json['offer_id'] == 'MN3PUJ0E0PJCPLCWYQHOK9BX2V0VCNXT3XFH0A4PARTM7H1ZXH'

def test_meta_endpoint_response_doctor_service_verification_failed(app_client):
    response = app_client.get('/new_token?session_id=FXLJmBn5kT1DNxs3BVH1svcMKBjtgwi5gyb0ANFO35dF0WBrbi',
                              headers={'Authorization': f'Basic {get_credentials()}'})

    token_ = response.json['access_token']

    load_mogo_records('test_apis/test_data/cody_care_agent/collection.json',
                      None, doctor_service_file='test_apis/test_data/cody_care_agent/doctor_service_offer_verification_failed.json')

    meta_ = app_client.get(
        '/ask/meta', headers={'Authorization': f'Bearer {token_}'})
    assert meta_.status_code == 200

    assert meta_.json.keys() == {'cc_specialist',
                                 'cc_sub_speciality',
                                 'chief_complaint',
                                 'diagnosis_list',
                                 'dx_group_list',
                                 'dx_specialist_list',
                                 'serving_agent_name',
                                 'initiate_verification',
                                 'offer_id',
                                 'concierge_option'
                                 }

    assert meta_.json['serving_agent_name'] == 'cody_care_agent'
    assert meta_.json['initiate_verification'] is True
    assert meta_.json['offer_id'] == 'MN3PUJ0E0PJCPLCWYQHOK9BX2V0VCNXT3XFH0A4PARTM7H1ZXH'
