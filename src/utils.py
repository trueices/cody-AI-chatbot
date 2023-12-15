import logging
import os
import re
import sys
from queue import Queue
from typing import List, Tuple

import ecs_logging
import pymongo
from langchain.llms.base import LLM
from openai.error import Timeout as OpenAITimeout
from pymongo.collection import Collection
from pymongo.database import Database

from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ecs_logging.StdlibFormatter(
    exclude_fields=[
        "log.original",
        "error.message",
        "process"
    ]
))
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)


class FakeListLLM(LLM):
    """Fake LLM for testing purposes."""

    responses: List[str] = []
    additional_kwargs: Queue = None
    i: int = 0

    @property
    def _llm_type(self) -> str:
        """Return type of llm."""
        return "fake-list"

    def _call(self, *args, **kwargs) -> str:
        """Return next response"""
        if self.i < len(self.responses):
            response = self.responses[self.i]
            self.i += 1
            if response.lower() == "timeout":
                raise OpenAITimeout
            else:
                return response
        else:
            raise IndexError("No more responses")

    def get_additional_kwargs(self) -> dict:
        """Return additional kwargs."""
        if not self.additional_kwargs.empty():
            return self.additional_kwargs.get()
        else:
            return {}

    def clear(self):
        """Clear responses and additional kwargs."""
        self.i = 0
        self.responses = []
        self.additional_kwargs = Queue()


fake_llm: FakeListLLM = FakeListLLM()


class MongoDBClient:
    """
    Singleton class for initializing and fetching the mongo client.
    It will prevent creating multiple instances of the mongo client.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.client = cls._instance._create_client()
        return cls._instance

    def _create_client(self):
        uri = os.getenv("MONGO_URI")
        client = pymongo.MongoClient(uri)
        logging.info("Connected to database.")
        return client

    @classmethod
    def create_new_mock_instance(cls):
        cls._instance = super().__new__(cls)
        from mongomock import MongoClient
        cls._instance.client = MongoClient(
            "mongodb://localhost:27017/bot_state_db")

    @classmethod
    def get_client(cls):
        return cls().client

    @classmethod
    def get_db(cls) -> Database:
        return cls().client['bot_state_db']

    @classmethod
    def get_botstate(cls) -> Collection:
        return cls.get_db()['collection']

    @classmethod
    def get_full_conv_hist(cls) -> Collection:
        return cls.get_db()['full_conv_hist']

    @classmethod
    def get_dx_mapping_errors(cls) -> Collection:
        return cls.get_db()['dx_mapping_errors']

    @classmethod
    def get_dx_mapping(cls) -> Collection:
        return cls.get_db()['diagnosis_mapping']

    @classmethod
    def get_stats(cls) -> Collection:
        return cls.get_db()['Stats']

    @classmethod
    def get_chat_conversation(cls) -> Collection:
        return cls.get_db()['ChatConversation']

    @classmethod
    def get_ats(cls) -> Collection:
        return cls.get_db()['ATS']

    @classmethod
    def get_followup_care(cls) -> Collection:
        return cls.get_db()['followup_care']

    @classmethod
    def get_convo_analytics(cls) -> Collection:
        return cls.get_db()['convo_analytics']

    @classmethod
    def get_sessions(cls) -> Collection:
        return cls.get_db()['sessions']

    @classmethod
    def get_users(cls) -> Collection:
        return cls.get_db()['users']

    @classmethod
    def get_doctor_service_offer(cls):
        return cls.get_db()['doctor_service_offer']


def map_url_name(character: str) -> Tuple[Specialist, SubSpecialtyDxGroup]:
    # First check for sub-speciality
    dx_group = SubSpecialtyDxGroup.from_url(character)
    specialist = dx_group.specialist

    # If sub-speciality is not found, check for specialist
    if dx_group == SubSpecialtyDxGroup.Generalist:
        specialist = Specialist.from_url(character)

    return specialist, dx_group


def refresh_view():
    MongoDBClient.get_chat_conversation().aggregate([
        {
            "$match": {
                "servicing_agent": {
                    "$nin": [
                        "",
                        "chief_complaint_agent",
                        "followup_agent",
                        "name_enquiry_agent"
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": {},
                "dxCount": {
                    "$sum": 1
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "dxCount": 1
            }
        },
        {
            "$out": "Stats"
        }
    ])


def base_url():
    if os.getenv('ENVIRONMENT', 'dev') == 'production':
        return "https://cody.md/"
    elif os.getenv('ENVIRONMENT', 'dev') == 'dev':
        return "http://localhost:3000/"
    else:
        return "https://staging.cody.md/"


def demo_mode(mode: str) -> re.Match:
    return mode and re.match(r'(.+)_(.+)_demo', mode) if mode and isinstance(mode, str) else None
