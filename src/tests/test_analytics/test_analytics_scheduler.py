import os

from src.analytics.analytics_scheduler import process_conversations
from src.tests.utils import load_mogo_records
from src.utils import MongoDBClient
from src.tests.test_apis.utils import app_client


def test_process_conversations(app_client):
    os.environ['ENVIRONMENT'] = 'staging'

    load_mogo_records('test_analytics/test_data/collection_find_care.json',
                      session_file='test_analytics/test_data/session.json',
                      followup_care_file='test_analytics/test_data/followup.json')

    process_conversations()

    convo = MongoDBClient.get_convo_analytics().find_one(
        {'convo_id': 'NHdfId8aDTWJcTVcDqzCqY9bJTUeK5PToNwRfCS0pRduIt2yw3'})

    expected_fields = {
        'convo_id': 'NHdfId8aDTWJcTVcDqzCqY9bJTUeK5PToNwRfCS0pRduIt2yw3',
        'agent_reached': 'concierge_agent',
        'farthest_agent_reached': 'find_care_agent',
        'user_id': 'test@test.com',
        'chief_complaint': 'Flatulence',
        'find_care_address': 'Oslo, Norway',
        'convo_created': '2024-03-10T12:02:22.607744',
        'location': {
            'type': 'Point',
            'coordinates': [77.09980453029009, 28.421657406917817]
        },
        'city': 'Gurugram District',
        'state': 'Haryana',
        'country': 'India',
        'country_code': 'IN',
        'specialist': 'gastroenterologist',
        'find_care_used': True,
        'dx_1': 'IRRITABLE BOWEL SYNDROME (IBS)',
        'dx_2': 'GASTRITIS',
        'dx_3': 'GASTROENTERITIS',
        'last_followup_outcome': 'all_better',
    }

    for key in convo.keys():
        # we don't want to assert these fields
        if key in ['_id', 'created', 'updated']:
            continue
        # Any other field should be present in the expected fields
        if key in expected_fields:
            assert convo[key] == expected_fields[key]
        else:
            assert False, f"Unexpected field found in convo: {key}. Update the test case accordingly"
