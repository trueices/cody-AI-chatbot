import pytest

from src.followup.followup_care_state import FollowUpCareState, FollowupState
from src.utils import MongoDBClient


@pytest.fixture
def client():
    MongoDBClient.create_new_mock_instance()
    yield MongoDBClient.get_followup_care()


def test_followup_state_already_present(client):
    MongoDBClient.get_followup_care().insert_one({'convo_id': 'test_convo_id',
                                                  'user_id': 'test_user_id',
                                                  'email_address': 'test_email_address',
                                                  'name': 'test_name',
                                                  'state': 'new',
                                                  'chief_complaint': 'test_chief_complaint',
                                                  'is_locked': False,
                                                  'updated': '2021-08-20T00:00:00',
                                                  'created': '2021-08-20T00:00:00'})

    # Get existing record
    care_state = FollowUpCareState(convo_id='test_convo_id')

    care_state.state = FollowupState.FOLLOW_UP_1

    care_state.upsert_to_db()

    data = MongoDBClient.get_followup_care().find_one({'convo_id': 'test_convo_id'})

    assert data['state'] == 'follow_up_1'
    assert data['user_id'] == 'test_user_id'


def test_followup_state_not_present(client):
    care_state = FollowUpCareState(convo_id='test_convo_id')

    # assert if exception is raised on upsert_to_db
    with pytest.raises(ValueError):
        care_state.upsert_to_db()

    care_state.user_id = 'test_user_id'
    care_state.state = FollowupState.RESOLVED

    care_state.upsert_to_db()

    data = MongoDBClient.get_followup_care().find_one({'convo_id': 'test_convo_id'})

    assert data['state'] == 'resolved'
    assert data['user_id'] == 'test_user_id'


def test_followup_state_no_state(client):
    care_state = FollowUpCareState()

    # assert if exception is raised on upsert_to_db
    with pytest.raises(ValueError):
        care_state.upsert_to_db()

    care_state.convo_id = 'test_convo_id'
    care_state.user_id = 'test_user_id'
    care_state.state = FollowupState.RESOLVED

    care_state.upsert_to_db()

    data = MongoDBClient.get_followup_care().find_one({'convo_id': 'test_convo_id'})

    assert data['state'] == 'resolved'
    assert data['user_id'] == 'test_user_id'
