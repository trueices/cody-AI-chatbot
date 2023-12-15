from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from src.utils import MongoDBClient


class DoctorServiceOfferEvent(Enum):
    CAPTURE_STATE = 'capture_state'
    RO_QUESTIONNAIRE_CAPTURE = 'ro_questionnaire_capture'
    QUESTIONNAIRE_DONE_OFFER_INITIATED = 'questionnaire_done_offer_initiated'
    OFFER_ACCEPTED = 'offer_accepted'
    OFFER_PAYMENT_DONE = 'offer_payment_done'
    VERIFY_USER = 'verify_user'
    USER_VERIFIED = 'user_verified'
    USER_VERIFICATION_FAILED = 'user_verification_failed'
    POLICY_CONSENT = 'policy_consent'
    ONBOARDING_QUESTIONNAIRE_CAPTURE = 'onboarding_questionnaire_capture'
    HCP_MATCH = 'hcp_match'
    SEND_TO_EHR = 'send_to_ehr'
    EHR_SENT = 'ehr_sent'
    EHR_TASK_DONE = 'ehr_task_done'
    EHR_PLAN_READY = 'ehr_plan_ready'
    EHR_PLAN_ACKNOWLEDGED = 'ehr_plan_acknowledged'
    EHR_PLAN_NOT_ACKNOWLEDGED = 'ehr_plan_not_acknowledged'


    def __init__(self, inventory_name: str):
        self.inventory_name = inventory_name

    @staticmethod
    def from_inventory_name(name: str):
        for event in DoctorServiceOfferEvent:
            if event.inventory_name.lower() == name.lower():
                return event

        raise Exception(f"Invalid name {name} found. This should not happen")


class DoctorServiceOfferState(BaseModel):
    convo_id: str = None
    user_id: str = None
    offer_id: str = None
    event: DoctorServiceOfferEvent = None
    created: datetime = None
    updated: datetime = None
    payment: dict = None
    questionnaire: dict = None
    verification: dict = None
    ehr_task_id: str = None
    ehr_task: dict = None
    state_data: dict = None
    state: str = None
    hcp: dict = None

    def __init__(self):
        super().__init__()

    def populate_fields(self, data: dict):
        for key, value in data.items():
            if key == '_id':
                continue

            if key == 'event':
                value = DoctorServiceOfferEvent.from_inventory_name(value)

            setattr(self, key, value)
        return self

    def insert_to_db(self):
        if self.convo_id is None:
            raise ValueError('convo_id cannot be None')

        if self.user_id is None:
            raise ValueError('user_id cannot be None')

        self.updated = datetime.now()

        if self.created is None:
            self.created = datetime.now()

        data_dict: dict = self.dict(by_alias=True, exclude_none=True)
        data_dict['event'] = self.event.inventory_name

        MongoDBClient.get_doctor_service_offer().insert_one(data_dict)
