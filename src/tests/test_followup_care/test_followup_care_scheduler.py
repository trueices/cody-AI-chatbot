from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from src.followup import followup_care_scheduler
from src.followup.followup_care_scheduler import process_followup_care
from src.utils import MongoDBClient


@pytest.fixture
def client():
    MongoDBClient.create_new_mock_instance()
    yield MongoDBClient.get_followup_care()


def test_followup_care_flow(client, monkeypatch):
    today = datetime(2000, 1, 1)
    day_1 = today + timedelta(days=1)
    day_3 = today + timedelta(days=3)
    day_7 = today + timedelta(days=7)
    day_14 = today + timedelta(days=14)
    from src.bot_state import BotState
    state = BotState(username='test_user_name')
    from src.followup.followup_care import FollowupCare, FollowUpCareState
    from unittest import mock

    # Let's start with enrolling a new user into followup care.
    with mock.patch('src.followup.followup_care_state.datetime') as mock_datetime_fcs, \
            mock.patch('src.followup.followup_care.datetime') as mock_datetime_fc:
        mock_datetime_fc.today.return_value = today
        mock_datetime_fcs.now.return_value = today
        FollowupCare.enroll_convo(
            state, {'userId': 'test_user_id', 'email': 'test_email'})
    state = FollowUpCareState(convo_id='test_user_name')
    assert state.created == today
    assert state.next_followup_date == day_1
    assert FollowupCare.is_profile_followup_eligible(
        BotState(username='test_user_name'), {'followup': 'true'}) is True

    # Now, let's check on day 1.
    with mock.patch('src.followup.followup_care.datetime') as mock_datetime_fc:
        mock_datetime_fc.today.return_value = day_1
        process_followup_care()
    state = FollowUpCareState(convo_id='test_user_name')
    assert state.created == today
    assert state.next_followup_date == day_3
    assert FollowupCare.is_profile_followup_eligible(
        BotState(username='test_user_name'), {'followup': 'true'}) is True

    # Now, let's check on day 3.
    with mock.patch('src.followup.followup_care.datetime') as mock_datetime_fc:
        mock_datetime_fc.today.return_value = day_3
        process_followup_care()
    state = FollowUpCareState(convo_id='test_user_name')
    assert state.created == today
    assert state.next_followup_date == day_7
    assert FollowupCare.is_profile_followup_eligible(
        BotState(username='test_user_name'), {'followup': 'true'}) is True

    # Now, let's check on day 7.
    with mock.patch('src.followup.followup_care.datetime') as mock_datetime_fc:
        mock_datetime_fc.today.return_value = day_7
        process_followup_care()
    state = FollowUpCareState(convo_id='test_user_name')
    assert state.created == today
    assert state.next_followup_date == day_14
    assert FollowupCare.is_profile_followup_eligible(
        BotState(username='test_user_name'), {'followup': 'true'}) is True

    # Now, let's check on day 14.
    with mock.patch('src.followup.followup_care.datetime') as mock_datetime_fc:
        mock_datetime_fc.today.return_value = day_14
        process_followup_care()
    state = FollowUpCareState(convo_id='test_user_name')
    assert state.created == today
    assert state.next_followup_date is None
    assert FollowupCare.is_profile_followup_eligible(BotState(username='test_user_name'), {'followup': 'true'}) is True, \
        "The state should be eligible for followup even after the last followup date."



def test_process_followup_care_scheduler(client):
    today_start = datetime.today()
    yesterday = datetime.today() - timedelta(days=1)

    MongoDBClient.get_followup_care().insert_many([{'convo_id': 'test_convo_id_1',
                                                    'user_id': 'test_user_id_1',
                                                    'email_address': 'test_email_address',
                                                    'name': 'test_name_1',
                                                    'state': 'new',
                                                    'chief_complaint': 'test_chief_complaint',
                                                    'is_locked': False,
                                                    'updated': yesterday,
                                                    'created': yesterday,
                                                    'next_followup_date': today_start},
                                                   {'convo_id': 'test_convo_id_2',
                                                    'user_id': 'test_user_id_2',
                                                    'email_address': 'test_email_address',
                                                    'name': 'test_name_2',
                                                    'state': 'follow_up_1',
                                                    'chief_complaint': 'test_chief_complaint',
                                                    'is_locked': False,
                                                    'updated': yesterday,
                                                    'created': yesterday,
                                                    'next_followup_date': today_start + timedelta(days=1)},
                                                   {'convo_id': 'test_convo_id_3',
                                                    'user_id': 'test_user_id_3',
                                                    'email_address': 'test_email_address',
                                                    'name': 'test_name_3',
                                                    'state': 'opted_out',
                                                    'chief_complaint': 'test_chief_complaint',
                                                    'is_locked': False,
                                                    'updated': yesterday,
                                                    'created': yesterday,
                                                    'next_followup_date': today_start},
                                                   {'convo_id': 'test_convo_id_4',
                                                    'user_id': 'test_user_id_4',
                                                    'email_address': 'test_email_address',
                                                    'name': 'test_name_4',
                                                    'state': 'follow_up_3',
                                                    'chief_complaint': 'test_chief_complaint',
                                                    'is_locked': False,
                                                    'updated': yesterday,
                                                    'created': yesterday,
                                                    'next_followup_date': today_start},])

    assert MongoDBClient.get_followup_care().count_documents({}) == 4

    followup_care_scheduler.email_sender = Mock()

    process_followup_care()

    assert followup_care_scheduler.email_sender.send_followup_email.call_count == 2
    email_param = followup_care_scheduler.email_sender.send_followup_email.call_args_list[0][0][0]
    assert email_param.convo_id == 'test_convo_id_1'
    assert email_param.email_address == 'test_email_address'
    assert email_param.name == 'test_name_1'

    data = MongoDBClient.get_followup_care().find_one({'convo_id': 'test_convo_id_1'})
    assert data['state'] == 'follow_up_1'
    assert data['next_followup_date'].date() == (yesterday + timedelta(days=3)).date()
    assert data['is_locked'] is False

    data = MongoDBClient.get_followup_care().find_one({'convo_id': 'test_convo_id_2'})
    assert data['state'] == 'follow_up_1'
    assert data['next_followup_date'].date() == (today_start + timedelta(days=1)).date()
    assert data['is_locked'] is False
    assert data['updated'].date() == yesterday.date()

    data = MongoDBClient.get_followup_care().find_one({'convo_id': 'test_convo_id_3'})
    assert data['state'] == 'opted_out'
    assert data['next_followup_date'].date() == today_start.date()
    assert data['is_locked'] is False
    assert data['updated'].date() == yesterday.date()

    data = MongoDBClient.get_followup_care().find_one({'convo_id': 'test_convo_id_4'})
    assert data['state'] == 'follow_up_done'
    assert data['next_followup_date'] is None
    assert data['is_locked'] is False


def test_release_followup_care_locks(client):
    today = datetime.today()
    today_start = datetime(today.year, today.month, today.day)
    yesterday = today_start - timedelta(days=1)

    MongoDBClient.get_followup_care().insert_many([{'convo_id': 'test_convo_id_1',
                                                    'user_id': 'test_user_id_1',
                                                    'email_address': 'test_email_address',
                                                    'name': 'test_name_1',
                                                    'state': 'new',
                                                    'chief_complaint': 'test_chief_complaint',
                                                    'is_locked': True,
                                                    'updated': yesterday,
                                                    'created': yesterday,
                                                    'next_followup_date': today_start},
                                                   {'convo_id': 'test_convo_id_2',
                                                    'user_id': 'test_user_id_2',
                                                    'email_address': 'test_email_address',
                                                    'name': 'test_name_2',
                                                    'state': 'follow_up_1',
                                                    'chief_complaint': 'test_chief_complaint',
                                                    'is_locked': True,
                                                    'updated': yesterday,
                                                    'created': yesterday,
                                                    'next_followup_date': today_start + timedelta(days=1)},
                                                   {'convo_id': 'test_convo_id_3',
                                                    'user_id': 'test_user_id_3',
                                                    'email_address': 'test_email_address',
                                                    'name': 'test_name_3',
                                                    'state': 'opted_out',
                                                    'chief_complaint': 'test_chief_complaint',
                                                    'is_locked': True,
                                                    'updated': yesterday,
                                                    'created': yesterday,
                                                    'next_followup_date': today_start},])

    assert MongoDBClient.get_followup_care().count_documents({}) == 3

    followup_care_scheduler.release_followup_care_locks()

    data = MongoDBClient.get_followup_care().find_one({'convo_id': 'test_convo_id_1'})
    assert data['is_locked'] is False

    data = MongoDBClient.get_followup_care().find_one({'convo_id': 'test_convo_id_2'})
    assert data['is_locked'] is False

    data = MongoDBClient.get_followup_care().find_one({'convo_id': 'test_convo_id_3'})
    assert data['is_locked'] is False




