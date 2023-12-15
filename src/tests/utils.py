import logging
import os, json

import pytest

from src.bot import Bot
from src.utils import fake_llm, MongoDBClient


def setup_code():
    logging.getLogger().setLevel(logging.DEBUG)
    os.environ['FAKE_LLM'] = 'True'
    os.environ['STREAMING'] = 'False'
    os.environ['STRIPE_PRICE_ID'] = 'price_1OxAauBl169sjuIEwNeGOdjl'
    os.environ['STRIPE_SECRET_KEY'] = 'sk_test_51NZY8rBl169sjuIEjyYzBgnfW5U3u6170fb0qFOYnvaEuIPg5F5OkKZNqq6MEnOymjI0zSJxv7TUmqbGBuaZQIN5001uJs2c41'
    os.environ['STRIPE_ENDPOINT_SECRET'] = 'whsec_test_secret'

    MongoDBClient.create_new_mock_instance()

    fake_llm.clear()

    # Drop the collections before each test
    MongoDBClient().client.db.drop_collection('collection')
    MongoDBClient().client.db.drop_collection('full_conv_hist')

@pytest.fixture
def setup():
    setup_code()

def ask(bot: Bot, message: str = '_', profile: dict = None):
    """
    Helper function to ask a message to the bot.
    Also checks if the bot state is persisted correctly.
    Also ensures stateless nature of the "Bot" as an application.
    Also ensures that bot state and full_conv_hist constitute the entire state of the bot.
    """
    bot._ask(message)

    new_bot = Bot(username=bot.state.username, profile=profile)
    # Check for equality of all the keys in the bot state, except the conv_hist
    for key in bot.state.dict().keys():
        if key == 'conv_hist':
            continue
        else:
            assert bot.state.dict()[key] == new_bot.state.dict()[key]

    # Check for equality of conv_hist
    for agent in bot.state.conv_hist.keys():
        old_msg_list = bot.state.conv_hist[agent]
        new_msg_list = new_bot.state.conv_hist[agent]
        assert len(old_msg_list) == len(new_msg_list)
        for i in range(len(old_msg_list)):
            assert old_msg_list[i].content == new_msg_list[i].content
            assert old_msg_list[i].type == new_msg_list[i].type
            assert old_msg_list[i].additional_kwargs == new_msg_list[i].additional_kwargs
            assert old_msg_list == new_msg_list

    assert bot.state.dict() == new_bot.state.dict(), \
        "The bot state must be persisted correctly"
    assert bot.full_conv_hist.dict() == new_bot.full_conv_hist.dict(), \
        "The full_conv_hist must be persisted correctly"
    assert fake_llm.i == len(fake_llm.responses), \
        "All the responses must be consumed by the bot"
    return new_bot


def compare_state_dicts(initial_bot_state, final_bot_state):
    """
    Helper function to ensure that the bot state essentially remains the same.
    This is especially useful for testing timeouts when the botstate remains the same.
    """
    for key in initial_bot_state.keys():
        if key in ['engagement_minutes', 'last_updated',
                   'timeouts', 'prompt_tokens', 'completion_tokens',
                   'successful_requests', 'total_cost', 'max_token_count', 'conv_train_msgs']:
            continue
        else:
            assert initial_bot_state[key] == final_bot_state[key], \
                f"Key {key} must be equal in the initial and final bot states"


def load_mogo_records(collection_file, full_conv_hist_file=None, session_file=None, followup_care_file=None,
                      doctor_service_file=None):
    absolute_file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), collection_file))

    with open(absolute_file_path, 'r', encoding='utf-8') as file:
        MongoDBClient.get_botstate().insert_one(json.load(file))

    if full_conv_hist_file is not None:
        absolute_file_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), full_conv_hist_file))

        with open(absolute_file_path, 'r', encoding='utf-8') as file:
            MongoDBClient.get_full_conv_hist().insert_one(json.load(file))

    if session_file is not None:
        absolute_file_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), session_file))

        with open(absolute_file_path, 'r', encoding='utf-8') as file:
            MongoDBClient.get_sessions().insert_one(json.load(file))

    if followup_care_file is not None:
        absolute_file_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), followup_care_file))

        with open(absolute_file_path, 'r', encoding='utf-8') as file:
            MongoDBClient.get_followup_care().insert_one(json.load(file))

    if doctor_service_file is not None:
        absolute_file_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), doctor_service_file))

        with open(absolute_file_path, 'r', encoding='utf-8') as file:
            MongoDBClient.get_doctor_service_offer().insert_one(json.load(file))
