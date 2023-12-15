import json
import os
from unittest.mock import Mock, call

import pytest
from langchain.schema import AIMessage

from src.agents import DiagnosisAgent
from src.followup.followup_care_state import FollowupState
from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup
from src.agents.diagnosis_agent import dx_group_dict
from src.utils import MongoDBClient, fake_llm
from src.bot import Bot
from src import agents
from src.tests.utils import setup, ask


@pytest.fixture
def client():
    os.environ['FAKE_LLM'] = 'True'
    os.environ['STREAMING'] = 'False'
    fake_llm.clear()
    MongoDBClient.create_new_mock_instance()
    yield MongoDBClient.get_dx_mapping_errors()


def test_dx_group_parsing_mapping_missing(client):
    bot_state = Mock()
    bot_state.mode = ""
    bot_state.username = "test_user"
    bot_state.specialist = Specialist.Generalist
    llm_mock = Mock()

    bot_state.conv_hist = {
        "diagnosis_agent": [],
        "magic_minute_agent": [AIMessage(content="Summary")]
    }

    # mock llm_mock initialization to return a specific value
    instance = llm_mock.return_value
    instance.content = ("Based on what you've told me, I've prepared your Top 3 Diagnosis List.\n\n<b>1. ALLERGIC "
                        "RHINITIS NEW (10% probability)</b> : A one line brief description of Disease\n\n<b>2. GASTROENTERITIS NEW "
                        "(30% probability)</b> : A one line brief description of Disease\n\n<b>3. GASTROESOPHAGEAL REFLUX "
                        "DISEASE (GERD) NEW (20% probability)</b> : A one line brief description of Disease")

    fake_llm.responses += ['', '']

    DiagnosisAgent(bot_state, llm_mock).act()

    assert bot_state.dx_group_list.add.call_count == 1
    assert bot_state.dx_specialist_list.add.call_count == 1

    assert MongoDBClient.get_dx_mapping_errors().count_documents({}) == 2
    record = MongoDBClient.get_dx_mapping_errors().find_one({'diagnosis': 'ALLERGIC RHINITIS NEW'})

    assert record['conversation_id'] == "test_user"
    assert "Diagnosis group not found" in record['reason']

    record = MongoDBClient.get_dx_mapping_errors().find_one({'diagnosis': 'GASTROENTERITIS NEW'})

    assert record['conversation_id'] == "test_user"
    assert "Diagnosis group not found" in record['reason']

    record = MongoDBClient.get_dx_mapping_errors().find_one({'diagnosis': 'GASTROESOPHAGEAL REFLUX DISEASE (GERD) NEW'})

    assert record is None


def test_dx_group_parsing_code_mapping_missing(client):
    bot_state = Mock()
    bot_state.username = "test_user"
    bot_state.specialist = Specialist.Generalist
    llm_mock = Mock()
    fake_llm.responses += ['', '']

    dx_group_dict['ALLERGIC RHINITIS MISS'] = {'dx_group': 'Allergic Rhinitis', 'specialist': 'Allergist'}

    bot_state.conv_hist = {
        "diagnosis_agent": [],
        "magic_minute_agent": [AIMessage(content="Summary")]
    }

    # mock llm_mock initialization to return a specific value
    instance = llm_mock.return_value
    instance.content = ("Based on what you've told me, I've prepared your Top 3 Diagnosis List.\n\n<b>1. ALLERGIC "
                        "RHINITIS MISS (10% probability)</b> : A one line brief description of Disease\n\n<b>2. GASTROENTERITIS NEW "
                        "(30% probability)</b> : A one line brief description of Disease\n\n<b>3. GASTROESOPHAGEAL REFLUX "
                        "DISEASE (GERD) NEW (20% probability)</b> : A one line brief description of Disease")

    DiagnosisAgent(bot_state, llm_mock).act()

    assert bot_state.dx_group_list.add.call_count == 1
    assert bot_state.dx_specialist_list.add.call_count == 1

    assert MongoDBClient.get_dx_mapping_errors().count_documents({}) == 2
    record = MongoDBClient.get_dx_mapping_errors().find_one({'diagnosis': 'ALLERGIC RHINITIS MISS'})

    assert record['conversation_id'] == "test_user"
    assert "Bug in mapping code." in record['reason']

    record = MongoDBClient.get_dx_mapping_errors().find_one({'diagnosis': 'GASTROENTERITIS NEW'})

    assert record['conversation_id'] == "test_user"
    assert "Diagnosis group not found" in record['reason']

    record = MongoDBClient.get_dx_mapping_errors().find_one({'diagnosis': 'GASTROESOPHAGEAL REFLUX DISEASE (GERD) NEW'})

    assert record is None


def test_dx_group_parsing(client):
    bot_state = Mock()
    bot_state.username = "test_user"
    llm_mock = Mock()

    bot_state.conv_hist = {
        "diagnosis_agent": [],
        "magic_minute_agent": [AIMessage(content="Summary")]
    }

    # mock llm_mock initialization to return a specific value
    instance = llm_mock.return_value
    instance.content = ("Based on what you've told me, I've prepared your Top 3 Diagnosis List.\n\n<b>1. ALLERGIC "
                        "RHINITIS (10% probability)</b> : A one line brief description of Disease\n\n<b>2. GASTROENTERITIS "
                        "(30% probability)</b> : A one line brief description of Disease\n\n<b>3. GASTROESOPHAGEAL REFLUX "
                        "DISEASE (GERD) (20% probability)</b> : A one line brief description of Disease")

    DiagnosisAgent(bot_state, llm_mock).act()

    assert bot_state.dx_group_list.add.call_count == 3
    assert bot_state.dx_specialist_list.add.call_count == 3

    assert bot_state.dx_group_list.add.has_calls(call(SubSpecialtyDxGroup.AllergicRhinitis),
                                                 call(SubSpecialtyDxGroup.Gastroenteritis),
                                                 call(SubSpecialtyDxGroup.GERD))

    assert bot_state.dx_specialist_list.add.has_calls(call(Specialist.Allergist),
                                                      call(Specialist.Gastroenterologist),
                                                      call(Specialist.Gastroenterologist))

    assert MongoDBClient.get_dx_mapping_errors().count_documents({}) == 0


def test_rules_anxiety_disorder(client):
    dx_group = DiagnosisAgent.dx_grouper_rules('test_user', 'ANXIETY-RELATED BREATHING DIFFICULTIES',
                                               Specialist.Psychiatrist)

    assert dx_group == SubSpecialtyDxGroup.AnxietyDisorders


def test_rules_gastritis(client):
    dx_group = DiagnosisAgent.dx_grouper_rules('test_user', 'GASTRITIS FLARE-UP', Specialist.Gastroenterologist)

    assert dx_group == SubSpecialtyDxGroup.Gastritis


def test_rules_gerd(client):
    dx_group = DiagnosisAgent.dx_grouper_rules('test_user', 'GASTROESOPHAGEAL REFLUX DISEASE (GERD) FLARE-UP',
                                               Specialist.Gastroenterologist)

    assert dx_group == SubSpecialtyDxGroup.GERD

    dx_group = DiagnosisAgent.dx_grouper_rules('test_user', 'GERD (GASTROESOPHAGEAL REFLUX DISEASE)',
                                               Specialist.Gastroenterologist)

    assert dx_group == SubSpecialtyDxGroup.GERD


def test_rules_adverse_reaction(client):
    dx_group = DiagnosisAgent.dx_grouper_rules('test_user', 'SIDE EFFECTS OF GERD MEDICATIONS',
                                               Specialist.AdverseReactionSpecialist)

    assert dx_group == SubSpecialtyDxGroup.AdverseReactionToMedication

    dx_group = DiagnosisAgent.dx_grouper_rules('test_user', 'SIDE EFFECTS OF THE 8 PILL METHOD',
                                               Specialist.AdverseReactionSpecialist)

    assert dx_group == SubSpecialtyDxGroup.AdverseReactionToMedication

    dx_group = DiagnosisAgent.dx_grouper_rules('test_user', 'SIDE EFFECTS OF MIFEPRISTONE',
                                               Specialist.AdverseReactionSpecialist)

    assert dx_group == SubSpecialtyDxGroup.AdverseReactionToAnotherSubstance

    dx_group = DiagnosisAgent.dx_grouper_rules('test_user', 'GASTROINTESTINAL SIDE EFFECTS OF ANTIBIOTICS',
                                               Specialist.AdverseReactionSpecialist)

    assert dx_group == SubSpecialtyDxGroup.AdverseReactionToMedication

    dx_group = DiagnosisAgent.dx_grouper_rules('test_user', 'SIDE EFFECT OF TROXERUTIN CREAM',
                                               Specialist.AdverseReactionSpecialist)

    assert dx_group == SubSpecialtyDxGroup.AdverseReactionToMedication

    dx_group = DiagnosisAgent.dx_grouper_rules('test_user', 'COVID-19 VACCINE ADVERSE REACTION',
                                               Specialist.AdverseReactionSpecialist)

    assert dx_group == SubSpecialtyDxGroup.AdverseReactionToVaccine


def test_rules_insect(client):
    dx_group = DiagnosisAgent.dx_grouper_rules('test_user', 'OTHER INSECT BITE', Specialist.Dermatologist)

    assert dx_group == SubSpecialtyDxGroup.InsectStingOrBiteOrReaction


def test_grouping_via_llm_rule(client):
    fake_llm.responses += ['']
    fake_llm.additional_kwargs.put({'function_call': {
        'name': 'categorize_diagnosis_group',
        'arguments': json.dumps({'diagnosis_group': 'BruiseorContusion'})
    }})

    DiagnosisAgent.dx_grouper_rules('test_username', 'ECCHYMOSIS (BRUISING)',
                                    Specialist.Dermatologist)

    assert MongoDBClient.get_dx_mapping().count_documents({}) == 1

    record = MongoDBClient.get_dx_mapping().find_one({'diagnosis': 'ECCHYMOSIS (BRUISING)'})

    assert record['diagnosis'] == 'ECCHYMOSIS (BRUISING)'
    assert SubSpecialtyDxGroup.BruiseorContusion.inventory_name == record['dx_group']

    mapping = MongoDBClient.get_dx_mapping().find_one({'diagnosis': 'ECCHYMOSIS (BRUISING)'})

    assert mapping['dx_group'] == SubSpecialtyDxGroup.BruiseorContusion.inventory_name

    # test that results are now fetched from the database
    DiagnosisAgent.dx_grouper_rules('test_username', 'ECCHYMOSIS (BRUISING)',
                                    Specialist.Dermatologist)

    assert MongoDBClient.get_dx_mapping().count_documents({}) == 1


def test_grouping_via_llm_rule_unable_to_map(client):
    fake_llm.responses += ['']
    fake_llm.additional_kwargs.put({'function_call': {
        'name': 'categorize_diagnosis_group',
        'arguments': json.dumps({'diagnosis_group': 'UNKNOWN'})
    }})

    DiagnosisAgent.dx_grouper_rules('test_username', 'ECCHYMOSIS (BRUISING)',
                                    Specialist.AdverseReactionSpecialist)

    assert MongoDBClient.get_dx_mapping().count_documents({}) == 1
    record = MongoDBClient.get_dx_mapping().find_one({'diagnosis': 'ECCHYMOSIS (BRUISING)'})

    assert record['dx_group'] == 'Not found'
    assert record['specialist'] == 'Not found'
    assert record['source'] == 'unknown'


def test_grouping_use_dx_if_already_found(client):
    MongoDBClient.get_dx_mapping().insert_one({'diagnosis': 'ECCHYMOSIS (BRUISING)',
                                               'dx_group': 'BruiseorContusion',
                                               'specialist': 'Dermatologist',
                                               'source': 'admin'})

    DiagnosisAgent.dx_grouper_rules('test_username', 'ECCHYMOSIS (BRUISING)',
                                    Specialist.AdverseReactionSpecialist)

    assert MongoDBClient.get_dx_mapping().count_documents({}) == 1
    record = MongoDBClient.get_dx_mapping().find_one({'diagnosis': 'ECCHYMOSIS (BRUISING)'})

    assert record['dx_group'] == 'BruiseorContusion'
    assert record['specialist'] == 'Dermatologist'
    assert record['source'] == 'admin'


def test_diagnosis_agent_able_to_group(setup):
    bot = Bot(username='test')

    bot.state.next_agent(name=agents.DiagnosisAgent.name)

    # Faking a diagnosis
    fake_llm.responses += ["Based on what you've told me, I've prepared your Top 3 Diagnosis List.\n\n<b>1. ALLERGIC "
                           "RHINITIS (10% probability)</b> : A one line brief description of Disease\n\n<b>2. GASTROENTERITIS "
                           "(30% probability)</b> : A one line brief description of Disease\n\n<b>3. GASTROESOPHAGEAL REFLUX "
                           "DISEASE (GERD) (20% probability)</b> : A one line brief description of Disease"]

    bot = ask(bot)

    assert bot.state.dx_group_list == {SubSpecialtyDxGroup.AllergicRhinitis, SubSpecialtyDxGroup.Gastroenteritis,
                                       SubSpecialtyDxGroup.GERD}
    assert bot.state.dx_specialist_list == {Specialist.Otolaryngologist, Specialist.Gastroenterologist}


def test_followup_care_enrollment_when_logged_in_and_enabled(client):
    os.environ['FOLLOWUP_CARE_ENABLED'] = 'True'

    profile = {
        'email': 'test@test.com',
        'userId': 'test_user',
        'isLoggedIn': True
    }

    bot = Bot(username='test', profile=profile)
    bot.state.chief_complaint = 'Cough'
    bot.state.patient_name = 'test'

    bot.state.next_agent(name=agents.DiagnosisAgent.name)

    # Faking a diagnosis
    fake_llm.responses += ["Based on what you've told me, I've prepared your Top 3 Diagnosis List.\n\n<b>1. ALLERGIC "
                           "RHINITIS (10% probability)</b> : A one line brief description of Disease\n\n<b>2. GASTROENTERITIS "
                           "(30% probability)</b> : A one line brief description of Disease\n\n<b>3. GASTROESOPHAGEAL REFLUX "
                           "DISEASE (GERD) (20% probability)</b> : A one line brief description of Disease"]

    ask(bot, profile=profile)

    record = MongoDBClient.get_followup_care().find_one({'convo_id': 'test'})

    assert record['convo_id'] == 'test'
    assert record['name'] == 'test'
    assert record['chief_complaint'] == 'Cough'
    assert record['state'] == FollowupState.NEW.inventory_name
    assert record['user_id'] == 'test_user'
    assert record['email_address'] == 'test@test.com'
    assert record['is_locked'] is False
    assert record['updated'] is not None
    assert record['created'] is not None

