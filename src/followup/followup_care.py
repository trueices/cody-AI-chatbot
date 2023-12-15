from datetime import timedelta, datetime

from src.bot_state import BotState
from src.followup.followup_care_state import FollowUpCareState, FollowupState
from src.utils import MongoDBClient


# This will be the interface to interact with followup care state in different ways
# when we write scheduler as well


class FollowupCare:

    @staticmethod
    def enroll_convo(state: BotState, profile: dict):
        care_state = FollowUpCareState()

        # get stuff from the state and profile
        care_state.convo_id = state.username
        care_state.name = state.patient_name
        care_state.chief_complaint = state.chief_complaint

        care_state.state = FollowupState.NEW
        care_state.user_id = profile['userId']
        care_state.email_address = profile['email']

        care_state.next_followup_date = datetime.today() + timedelta(
            days=care_state.state.days_to_followup)

        care_state.upsert_to_db()

    @staticmethod
    def is_profile_followup_eligible(state: BotState, profile: dict) -> bool:
        """
        Returns True if a given profile and conversation, is eligible for followup care.
        This reflects the case when the user is coming from a conversation link.
        """
        if profile and profile.get('followup', False) == 'true':
            care_state = FollowUpCareState(state.username)
            if care_state.is_followup_eligible(allow_followup_done=True):
                return True
        return False

    @staticmethod
    def get_latest_followup_care_state(profile: dict) -> FollowUpCareState:
        """
        Returns the latest followup care state for a user, if it exists which is not opted out.
        """
        if profile and profile.get('email', None):
            care_state = MongoDBClient.get_followup_care().find_one({'email_address': profile['email'],
                                                                     'state': {'$nin': [
                                                                         FollowupState.OPTED_OUT.inventory_name]}},
                                                                    sort=[('created', -1)])
            return FollowUpCareState().populate_fields(care_state) if care_state else None
        return None

    @staticmethod
    def eligible_convo_with_lock() -> FollowUpCareState:
        today_date_time = datetime.today()
        record = MongoDBClient.get_followup_care().find_one_and_update(
            filter={
                'state': {'$nin': FollowupState.state_not_eligible_for_followups()},
                'next_followup_date': {'$lte': today_date_time},
                'is_locked': False,
            },
            update={'$set': {'is_locked': True}},
            return_document=True
        )

        return FollowUpCareState().populate_fields(record) if record else None

    @staticmethod
    def update_followup_outcome(convo_id: str, outcome: str):
        followup = FollowUpCareState(convo_id)

        # check if follow-up record exists before updating
        if followup.user_id:
            followup.last_followup_outcome = outcome

            if outcome == 'all_better':
                followup.state = FollowupState.RESOLVED
                followup.next_followup_date = None

            followup.upsert_to_db()

    @staticmethod
    def release_lock_update_state(followup: FollowUpCareState):
        """
        Releases the lock and updates the followup date on the followup care record.
        """
        followup.state = FollowupCare._next_state(followup.state)
        followup.state_initiated = False

        if followup.state.days_to_followup:
            # Calculate the next followup date
            followup.next_followup_date = followup.created + \
                                          timedelta(days=followup.state.days_to_followup)
        else:
            followup.next_followup_date = None

        followup.is_locked = False  # Release the lock
        followup.upsert_to_db()  # Writing to the database

    @staticmethod
    def _next_state(state: FollowupState) -> FollowupState:
        """Returns the next state in the followup state machine.
        """
        if state == FollowupState.NEW:
            return FollowupState.FOLLOW_UP_1
        elif state == FollowupState.FOLLOW_UP_1:
            return FollowupState.FOLLOW_UP_2
        elif state == FollowupState.FOLLOW_UP_2:
            return FollowupState.FOLLOW_UP_3
        elif state == FollowupState.FOLLOW_UP_3:
            return FollowupState.FOLLOW_UP_DONE

    @staticmethod
    def mark_followup_initiated(convo_id: str):
        """
        Marks the followup state as initiated.
        """
        MongoDBClient.get_followup_care().update_one(
            {'convo_id': convo_id},
            {'$set': {'state_initiated': True}}
        )

    @staticmethod
    def opt_out(conv_id: str) -> int:
        update_result = MongoDBClient.get_followup_care().update_one({'convo_id': conv_id},
                                                                     {'$set': {
                                                                         'state': FollowupState.OPTED_OUT.inventory_name}})

        return update_result.modified_count
