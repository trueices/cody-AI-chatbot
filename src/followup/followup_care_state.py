from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from src.utils import MongoDBClient


class FollowupState(Enum):
    NEW = ("new", 1)
    FOLLOW_UP_1 = ("follow_up_1", 3)
    FOLLOW_UP_2 = ("follow_up_2", 7)
    FOLLOW_UP_3 = ("follow_up_3", 14)
    FOLLOW_UP_DONE = "follow_up_done"
    RESOLVED = "resolved"
    OPTED_OUT = "opted_out"

    def __init__(self, inventory_name: str, days_to_followup: int = None):
        self.inventory_name = inventory_name
        self.days_to_followup = days_to_followup

    @staticmethod
    def from_inventory_name(name: str):
        for state in FollowupState:
            if state.inventory_name.lower() == name.lower():
                return state

        raise Exception(f"Invalid name {name} found. This should not happen")

    @staticmethod
    def state_not_eligible_for_followups() -> set:
        return [state.inventory_name for state in FollowupState if state.days_to_followup is None]


class FollowUpCareState(BaseModel):
    convo_id: str = None
    user_id: str = None
    email_address: str = None
    name: str = None
    state: FollowupState = FollowupState.NEW
    chief_complaint: str = None
    is_locked: bool = False
    updated: datetime = None
    created: datetime = None
    next_followup_date: datetime = None
    last_followup_outcome: str = None
    # Used to keep track of the states initiated by the user.
    state_initiated: bool = False

    # TODO might have to add more fields as we implement scheduling but idea is that this collection has all the
    #  information about the follow up care for a particular conversation.

    def __init__(self, convo_id: str = None):
        super().__init__()

        if convo_id is not None:
            data: dict = MongoDBClient.get_followup_care().find_one({'convo_id': convo_id})

            if data is not None:
                self.populate_fields(data)
            else:
                self.convo_id = convo_id

    def populate_fields(self, data: dict):
        for key, value in data.items():
            if key == '_id':
                continue

            if key == 'state':
                value = FollowupState.from_inventory_name(value)

            setattr(self, key, value)
        return self

    def is_followup_eligible(self, allow_followup_done=False) -> bool:
        # If the state is not initiated and state is eligible for followup.
        # the user_id should not be None, which means conversation is enrolled
        # and state is not in the list of states not eligible for followups.
        non_eligible_states = FollowupState.state_not_eligible_for_followups()
        if allow_followup_done:
            non_eligible_states.remove(
                FollowupState.FOLLOW_UP_DONE.inventory_name)
        return not self.state_initiated and \
            self.user_id is not None and \
            self.state.inventory_name not in non_eligible_states

    def upsert_to_db(self):
        if self.convo_id is None:
            raise ValueError('convo_id cannot be None')

        if self.user_id is None:
            raise ValueError('user_id cannot be None')

        self.updated = datetime.now()

        if self.created is None:
            self.created = datetime.now()

        data_dict: dict = self.dict(by_alias=True)
        data_dict['state'] = self.state.inventory_name

        MongoDBClient.get_followup_care().update_one(filter={'convo_id': self.convo_id},
                                                     update={'$set': data_dict},
                                                     upsert=True)
