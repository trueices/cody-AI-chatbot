"""
To be used for keeping track of the bot state as a context.
"""

import logging
from datetime import datetime
from typing import List, Any

from langchain.adapters.openai import convert_message_to_dict, convert_dict_to_message
from langchain.schema import BaseMessage, AIMessage, HumanMessage
from pydantic import BaseModel

from src.utils import Specialist, SubSpecialtyDxGroup, MongoDBClient

VERSION = '0.16.0-alpha'

class BotState(BaseModel):
    ip_address: str = None
    deployed: str = datetime.now().isoformat()
    created: str = None
    last_updated: str = None
    engagement_minutes: float = 0.0
    username: str = None  # Should be called "conversation_id". Not changed for legacy purposes.
    conv_hist: dict[str, List[BaseMessage]] = {}
    current_agent_index: int = 0
    current_agent_name: str = None
    next_agent_name: str = None
    hist_for_que_gen: str = ''
    last_human_input: str = None
    chief_complaint: str = None
    patient_name: str = None
    diagnosis_list: List[str] = []
    agent_names: List[str] = []
    prompt_tokens: int = 0
    completion_tokens: int = 0
    successful_requests: int = 0
    total_cost: float = 0.0
    max_token_count: int = 0
    version: str = VERSION
    treatment_plans_seen: list = []
    treatment_plans: dict[str, str] = {}
    specialist: Specialist = Specialist.Generalist
    subSpecialty: SubSpecialtyDxGroup = SubSpecialtyDxGroup.Generalist
    character_src: str = 'router'
    feedback_rating: int = None
    dx_group_list: set[SubSpecialtyDxGroup] = set()
    dx_specialist_list: set[Specialist] = set()
    mode: str = ''

    # Error handling fields
    errors: List[Any] = []
    error_types: List[str] = []
    timeouts: int = 0

    # Followup agent fields
    priority_fields_asked: List[str] = []
    priority_field_relevance: dict = {}
    priority_field_src: str = None
    confidence_score: int = 0
    debug_messages_list: List[str] = []
    thought_process: str = ''
    dxg_version: str = None
    conv_train_msgs: List[str] = []
    fields_asked_once: List[str] = []

    # Concierge agent fields
    concierge_option:str = 'detailed'
    # Find care agent fields
    errors_care: List[str] = []
    care_feedback_rating: int = None
    address: str = None
    # Question agent fields
    question_agent_feedback: int = None
    location: dict = None
    # Existing diagnosis agent fields
    existing_dx: str = ''
    existing_dx_tx: str = ''
    analytics_state: str = None

    class Config:
        validate_assignment = True
        extra = 'allow'

    # initialize from a username parameter
    def __init__(self, username: str):
        super().__init__()
        self.username = username
        data: dict = MongoDBClient.get_botstate().find_one({'username': username})

        # Only if you have data in the database, load it.
        if data is not None:
            for key, value in data.items():
                if key == '_id':
                    continue
                if key == 'conv_hist':
                    # Converting conv_hist dict messages to BaseMessage format after loading
                    for agent_name, messages in value.items():
                        value[agent_name] = [
                            convert_dict_to_message(message) for message in messages]
                if key == 'specialist':
                    value = Specialist.from_inventory_name(value)
                if key == 'subSpecialty':
                    value = SubSpecialtyDxGroup.from_inventory_name(value)
                if key == 'dx_group_list':
                    value = [SubSpecialtyDxGroup.from_inventory_name(desc) for desc in value]
                if key == 'dx_specialist_list':
                    value = [Specialist.from_inventory_name(name) for name in value]
                if key == 'mode' and value is None:
                    value = ''
                # Finally, set attributes
                setattr(self, key, value)

    def upsert_to_db(self):
        # Calculating the time difference between created and last_updated
        if self.created is None:
            self.created = datetime.now().isoformat()
        self.last_updated = datetime.now().isoformat()
        self.version = VERSION # Version should be updated every time the bot state is updated.
        regex = "%Y-%m-%dT%H:%M:%S.%f"
        d1 = datetime.strptime(self.last_updated, regex)
        d2 = datetime.strptime(self.created, regex)
        self.engagement_minutes = (d1 - d2).total_seconds() / 60

        data_dict: dict = self.dict(by_alias=True)

        # Converting conv_hist messages to proper dict message format before saving
        temp_conv_dist = {}
        for agent_name, messages in self.conv_hist.items():
            temp_conv_dist[agent_name] = [
                convert_message_to_dict(message) for message in messages]
        data_dict['conv_hist'] = temp_conv_dist
        data_dict['specialist'] = self.specialist.inventory_name
        data_dict['subSpecialty'] = self.subSpecialty.inventory_name

        data_dict['dx_group_list'] = [dx_group.inventory_name for dx_group in self.dx_group_list]
        data_dict['dx_specialist_list'] = [spc.inventory_name for spc in self.dx_specialist_list]

        logging.debug(f'Upsert to database..')
        # Inserting or updating the data to the database
        MongoDBClient.get_botstate().update_one(filter={'username': self.username},
                                                update={'$set': data_dict},
                                                upsert=True)

    def next_agent(self, name: str = None, reset_hist=False):
        if name is None:
            name = self.next_agent_name
        self.next_agent_name = None # Always reset the next_agent_name after every next_agent call, to avoid forgetting to reset it.
        if name is not None:
            self.current_agent_name = name
            self.current_agent_index = self.agent_names.index(name)
        else:
            self.current_agent_index += 1
            self.current_agent_name = self.agent_names[self.current_agent_index]
        # Clearing history of the current agent, if required.
        if reset_hist:
            self.conv_hist[self.current_agent_name][:] = []
        logging.debug(f'Next agent activated: {self.current_agent_name}')

    def get_conv_hist(self) -> List[dict]:
        conv_hist = []
        for agent_name in self.agent_names:
            for message in self.conv_hist[agent_name]:
                # check if message is of type AIMessage
                if isinstance(message, AIMessage) and message.additional_kwargs.get("function_call") is None:
                    conv_hist.append(convert_message_to_dict(message))
                elif isinstance(message, HumanMessage):
                    conv_hist.append(convert_message_to_dict(message))

        return conv_hist
    
    def get_last_diagnosis(self) -> str:
        """
        Returns the last diagnosis seen by the user.
        """
        if len(self.diagnosis_list) == 0:
            return ''
        diagnosis = self.diagnosis_list[0].title()
        if len(self.treatment_plans_seen) > 0:
            diagnosis = self.diagnosis_list[int(self.treatment_plans_seen[-1]) - 1].title()
        return diagnosis
    
    def get_last_treatment_plan(self) -> str:
        """
        Returns the last treatment plan seen by the user.
        """
        if len(self.treatment_plans_seen) == 0:
            return ''
        return self.treatment_plans[str(self.treatment_plans_seen[-1])]

    def set_location(self, longitude: float, latitude: float):
        self.location = {
            'type': 'Point',
            'coordinates': [longitude, latitude]
        }
