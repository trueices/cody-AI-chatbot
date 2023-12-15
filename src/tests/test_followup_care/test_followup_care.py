from datetime import date, datetime, timedelta

import pytest

from src import agents
from src.bot_state import BotState
from src.followup.followup_care import FollowupCare
from src.utils import MongoDBClient


@pytest.fixture
def client():
    MongoDBClient.create_new_mock_instance()
    yield MongoDBClient.get_followup_care()


def test_enroll_convo(client):
    bot_state = BotState(username='test_username')

    FollowupCare.enroll_convo(
        bot_state, {'userId': 'test_user_id', 'email': 'test_email'})

    record = MongoDBClient.get_followup_care().find_one(
        {'convo_id': 'test_username'})

    today = date.today()
    next_followup = datetime(today.year, today.month,
                             today.day) + timedelta(days=1)

    assert record is not None
    assert record['convo_id'] == 'test_username'
    assert record['user_id'] == 'test_user_id'
    assert record['email_address'] == 'test_email'
    assert record['state'] == 'new'
    assert record['next_followup_date'].date() == next_followup.date()


def test_is_profile_followup_eligible(client):
    bot_state = BotState(username='test_convo_id')

    FollowupCare.enroll_convo(
        bot_state, {'userId': 'test_user_id', 'email': 'test_email'})

    # Setting an empty conv history for the FollowupCareAgent
    bot_state.conv_hist[agents.FollowupCareAgent.name] = []

    assert FollowupCare.is_profile_followup_eligible(
        bot_state, {'followup': 'true'}) is True
    assert FollowupCare.is_profile_followup_eligible(
        bot_state, {'followup': 'false'}) is False
    assert FollowupCare.is_profile_followup_eligible(
        bot_state, {'followup': 'invalid'}) is False

    bot_state = BotState(
        username='test_convo_id_no_followup')
    assert FollowupCare.is_profile_followup_eligible(
        bot_state, {'followup': 'true'}) is False


def test_get_latest_followup_care_state(client):
    MongoDBClient.get_followup_care().insert_one({
        'convo_id': 'test_convo_id',
        'user_id': 'test_user_id',
        'email_address': 'test_email',
        'state': 'new',
        'created': datetime.now(),
        'next_followup_date': datetime.today() + timedelta(days=1),
    })

    assert FollowupCare.get_latest_followup_care_state({}) is None

    assert FollowupCare.get_latest_followup_care_state(
        {'email': 'test_email'}) is not None

    MongoDBClient.get_followup_care().insert_one({
        'convo_id': 'test_convo_id_2',
        'user_id': 'test_user_id',
        'email_address': 'test_email',
        'state': 'new',
        'created': datetime.now() + timedelta(minutes=1),
        'next_followup_date': datetime.today() + timedelta(days=1),
    })

    state_conv2 = FollowupCare.get_latest_followup_care_state({'email': 'test_email'})

    FollowupCare.opt_out('test_convo_id_2')

    state_latest = FollowupCare.get_latest_followup_care_state({'email': 'test_email'})

    assert state_conv2 is not None
    assert state_conv2.convo_id == 'test_convo_id_2'

    assert state_latest is not None
    assert state_latest.convo_id == 'test_convo_id'
