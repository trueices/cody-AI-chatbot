import csv
import json
import logging
import os
import re
import textwrap
from datetime import datetime

from langchain.schema import SystemMessage

from src import agents
from src.ad.provider import Provider
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI, CustomChatOpenAI
from src.followup.followup_care import FollowupCare
from src.followup.followup_care_scheduler import send_test_email
from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup
from src.utils import MongoDBClient

dx_group_dict = {}


def init_dx_mapping():
    absolute_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                      '../../CodyMD Medical Terminology _ Taxonomy - DxGroupsV2.csv'))

    with open(absolute_file_path, 'r', encoding='utf-8') as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            key = row['Diagnosis'].strip()
            if key in dx_group_dict:
                logging.warning("Duplicate key found: " + key + " with value " + row['DxGroup'] + " and " + row[
                    'Specialist'])
                pass

            dx_group_dict[key] = {'dx_group': row['DxGroup'].strip(
            ), 'specialist': row['Specialist'].strip()}


class DiagnosisAgent(agents.Agent):
    init_dx_mapping()
    name = 'diagnosis_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None):
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]
        self.profile = profile if profile else {}

    def act(self) -> bool:
        # append system prompt to conv_hist only if it is empty
        if len(self.conv_hist) == 0:  # First system prompt
            system_prompt = f"""
You are a doctor. Your name is Cody.
In the previous stage, you have been conversing with a patient, about their symptoms.
You have already asked a set of questions and the patient has answered them.
Now, use the conversations to identify symptoms to perform a diagnosis.
DO NOT ASK ANY FOLLOWUP QUESTIONS.

Your output should be a list of 3 most likely diseases, along with their probabilities.

Output format:
"Based on what you've told me, I've prepared your Top 3 Condition List.
<h1>Your Top 3 Condition List</h1>
<b>1. Disease 1 (x% probability)</b> A one line brief description of Disease 1.
<b>2. Disease 2 (x% probability)</b> A one line brief description of Disease 2.
<b>3. Disease 3 (x% probability)</b> A one line brief description of Disease 3."

Do not add anything after the 3 Diagnosis List. Your task is to list out the three possible diseases. Do not provide any explanation or advise.
"""
            logging.debug('Calling the main agent...')
            prev_conv_hist = self.state.conv_hist[agents.MagicMinuteAgent.name].copy(
            )
            self.llm.stream_callback.on_llm_new_token("<div class='tx-plan'>")
            response = self.llm(
                prev_conv_hist + [SystemMessage(content=system_prompt)])

            if response.content:
                # Regex to extract the diagnosis list from the formatted response
                # Since diagnosis response is well-structured, we can use regex to extract the diagnosis list
                # This is needed for analytics.
                diagnosis_list = re.findall(
                    r'\d+\.\s(.*?)(?=\s\(\d+% probability\)|\Z)', response.content)

                if not diagnosis_list:
                    logging.warning("Diagnosis list is empty for conversation ID: " + self.state.username +
                                    ". Check if regex needs to be updated.")

                    self.llm.stream_callback.on_llm_new_token("</div>")
                    self.conv_hist.append(response)
                else:
                    in_diagnosis_list_ = [diag.strip().upper()
                                          for diag in diagnosis_list]
                    self.state.diagnosis_list = in_diagnosis_list_

                    self.llm.stream_callback.on_llm_new_token(Provider(self.state.mode)
                                                              .diagnosis(in_diagnosis_list_))

                    self.llm.stream_callback.on_llm_new_token("</div>")
                    self.conv_hist.append(response)

                    for diag in in_diagnosis_list_:
                        if diag:
                            diag_group = dx_group_dict.get(diag)

                            if not diag_group:
                                logging.warning("Attempting to map via rules as Diagnosis group not mapped for "
                                                "diagnosis: " + diag + "conversation" "ID: " + self.state.username)

                                # Attempting to map via rules
                                dx_group = DiagnosisAgent.dx_grouper_rules(self.state.username, diag,
                                                                           self.state.specialist)

                                if dx_group is None:
                                    logging.warning(
                                        "Unable to map Diagnosis group via rules for diagnosis: " + diag + "conversation ID: " + self.state.username + ".")

                                    MongoDBClient.get_dx_mapping_errors().insert_one({'diagnosis': diag,
                                                                                      'conversation_id': self.state.username,
                                                                                      'reason': 'Diagnosis group not found',
                                                                                      'created': datetime.now().isoformat()})
                                else:
                                    self.state.dx_group_list.add(dx_group)
                                    self.state.dx_specialist_list.add(
                                        dx_group.specialist)

                            else:
                                group_ = diag_group.get('dx_group')

                                # This logic is coz sheet contains Generalist as value, and we want it to be general
                                # Can be removed once we fix the inventory name in the sheet
                                if group_ == 'Generalist':
                                    group_ = 'general'

                                dx_group = SubSpecialtyDxGroup.from_inventory_name_no_default(
                                    group_)

                                if dx_group is None:
                                    logging.warning(
                                        "Diagnosis group not found for diagnosis: " + diag + " conversation ID: " + self.state.username + ". Possible bug in mapping code.")

                                    MongoDBClient.get_dx_mapping_errors().insert_one({'diagnosis': diag,
                                                                                      'conversation_id': self.state.username,
                                                                                      'reason': 'Bug in mapping code. '
                                                                                                'SubSpecialtyDxGroup missing '
                                                                                                'for ' + group_ + " with " +
                                                                                                diag_group.get(
                                                                                                    'specialist'),
                                                                                      'created': datetime.now().isoformat()})
                                else:
                                    self.state.dx_group_list.add(dx_group)
                                    self.state.dx_specialist_list.add(
                                        dx_group.specialist)

                # enroll the conversation to followup care if logged in convo
                if self.profile.get('isLoggedIn', False):
                    FollowupCare.enroll_convo(self.state, self.profile)

                    # This is just for quick testing of end to end flow for followup care in staging only
                    if os.getenv('ENVIRONMENT', 'dev') == 'staging':
                        logging.info(f'Triggering test email for followup care for convo id {self.state.username}')
                        send_test_email(self.state.username)

        self.state.next_agent()
        return False

    @staticmethod
    def dx_grouper_rules(convo_id: str, diag: str, specialist: Specialist = None) -> SubSpecialtyDxGroup:
        if 'cardiomyopathy' in diag.lower():
            return SubSpecialtyDxGroup.Cardiomyopathy
        elif 'folliculitis' in diag.lower():
            return SubSpecialtyDxGroup.SkinAndSoftTissueInfections
        elif 'epilepsy' in diag.lower():
            return SubSpecialtyDxGroup.SeizureorSeizureDisorder
        elif 'cystic fibrosis' in diag.lower():
            return SubSpecialtyDxGroup.CysticFibrosis
        elif 'neuropathy' in diag.lower():
            return SubSpecialtyDxGroup.Neuropathy
        elif 'keratitis' in diag.lower():
            return SubSpecialtyDxGroup.CorneaConditions
        elif 'seborrh' in diag.lower():
            return SubSpecialtyDxGroup.SeborrheicDermatitis
        elif DiagnosisAgent.has_any_word(['seborrheic dermatitis', 'seborrhea'], diag):
            return SubSpecialtyDxGroup.SeborrheicDermatitis
        elif DiagnosisAgent.has_any_word(['temporomandibular', 'tmj'], diag):
            return SubSpecialtyDxGroup.TMJDisorders
        elif DiagnosisAgent.has_any_word(['obsessive compulsive', 'obsessive-compulsive', 'ocd'], diag):
            return SubSpecialtyDxGroup.OCD
        elif 'sleep disorder' in diag.lower():
            return SubSpecialtyDxGroup.InsomniaAndOtherSleepDisorders
        elif 'sleep apnea' in diag.lower():
            return SubSpecialtyDxGroup.SleepApnea
        elif 'pregnancy' in diag.lower():
            return SubSpecialtyDxGroup.PregnancyConditions
        elif 'anemia' in diag.lower():
            return SubSpecialtyDxGroup.Anemia
        elif (DiagnosisAgent.has_any_word(['eye', 'lens'], diag)
              and DiagnosisAgent.has_any_word(['ruptur', 'dislocat', 'penetract', 'pierce'], diag)):
            return SubSpecialtyDxGroup.OcularTrauma
        elif DiagnosisAgent.has_any_word(['tendon strain', 'tendonitis'], diag):
            return SubSpecialtyDxGroup.Tendonitis
        elif (DiagnosisAgent.has_any_word(
                ['muscle', 'joint', 'tendon', 'ligament', 'muscul', 'ankle', 'wrist', 'cervic', 'knee', 'hamstring'],
                diag) and
              DiagnosisAgent.has_any_word(['strain', 'sprain'], diag)):
            return SubSpecialtyDxGroup.SprainsAndStrains
        elif DiagnosisAgent.has_any_word(['poison', 'reaction', 'side effect'], diag):
            if 'vaccine' in diag.lower():
                return SubSpecialtyDxGroup.AdverseReactionToVaccine
            elif DiagnosisAgent.has_any_word(
                    ['medication', 'contracept', 'drug', 'pill', 'biotic', 'medicine', 'cream', 'tablet'], diag):
                return SubSpecialtyDxGroup.AdverseReactionToMedication
            else:
                return SubSpecialtyDxGroup.AdverseReactionToAnotherSubstance
        elif DiagnosisAgent.has_any_word(['anxiety-induced', 'anxiety-related'], diag):
            return SubSpecialtyDxGroup.AnxietyDisorders
        # should come after anxiety-induced because vomiting can come with anxiety-induced
        elif 'vomiting' in diag.lower():
            return SubSpecialtyDxGroup.Vomiting
        elif 'gastritis' in diag.lower():
            return SubSpecialtyDxGroup.Gastritis
        elif DiagnosisAgent.has_any_word(['gastroesophageal reflux', 'gerd'], diag):
            return SubSpecialtyDxGroup.GERD
        elif 'insect' in diag.lower() and DiagnosisAgent.has_any_word(['sting', 'bite'], diag):
            return SubSpecialtyDxGroup.InsectStingOrBiteOrReaction
        elif 'skin irritation' in diag.lower():
            return SubSpecialtyDxGroup.Dermatitis
        elif 'diabetes mellitus' in diag.lower():
            return SubSpecialtyDxGroup.DiabetesMellitus
        elif 'hyperpigmentation' in diag.lower():
            return SubSpecialtyDxGroup.SkinPigmentation

        return DiagnosisAgent._categorize_via_llm(convo_id, diag, specialist)

    @staticmethod
    def _categorize_via_llm(convo_id: str, diag: str, specialist: Specialist) -> SubSpecialtyDxGroup:

        dx_mapping = MongoDBClient.get_dx_mapping().find_one({'diagnosis': diag})

        if dx_mapping is not None:
            logging.info(f'LLM identified diagnosis group for diagnosis {diag} found in database. Skipping calling '
                         f'live api')
            return SubSpecialtyDxGroup.from_inventory_name_no_default(dx_mapping['dx_group'])

        dx_groups_for_specialist = [sub_speciality.inventory_name for sub_speciality in SubSpecialtyDxGroup if
                                    sub_speciality.specialist == specialist] + ['UNKNOWN']

        function_schema_diagnosis_group = {
            "name": "categorize_diagnosis",
            "description": "Used to categorize the diagnosis to a diagnosis group.",
            "parameters": {
                "type": "object",
                "properties": {
                    "diagnosis_group": {
                        "description": "The diagnosis-group of the diagnosis.",
                        "type": "string",
                        "enum": dx_groups_for_specialist,
                    }

                },
                "required": ["diagnosis_group"]
            },
        }

        system_prompt = textwrap.dedent(
            f"""
Given a diagnosis, select the most relevant diagnosis group it belongs to.
diagnosis identified: {diag}
""")
        llm = CustomChatOpenAI(state=BotState(username=convo_id))

        response = llm([SystemMessage(content=system_prompt)],
                       functions=[function_schema_diagnosis_group],
                       function_call={"name": function_schema_diagnosis_group['name']})

        function_call = response.additional_kwargs.get("function_call")
        fields = function_schema_diagnosis_group['parameters']['required']

        if function_call is None:
            logging.warning(
                f'No diagnosis group identified for diagnosis {diag}')
            return None
        else:
            args = json.loads(function_call.get('arguments'))

        [diagnosis_group] = [args[field] for field in fields]

        llm_identified_dx_group = SubSpecialtyDxGroup.from_inventory_name_no_default(diagnosis_group)

        if llm_identified_dx_group is not None:
            MongoDBClient.get_dx_mapping().insert_one({'diagnosis': diag,
                                                       'source': 'llm',
                                                       'dx_group': llm_identified_dx_group.inventory_name,
                                                       'specialist': llm_identified_dx_group.specialist.inventory_name,
                                                       'created': datetime.now().isoformat()})
            return llm_identified_dx_group
        else:
            MongoDBClient.get_dx_mapping().insert_one({'diagnosis': diag,
                                                       'source': 'unknown',
                                                       'dx_group': 'Not found',
                                                       'specialist': 'Not found',
                                                       'created': datetime.now().isoformat()})

    @staticmethod
    def has_any_word(word_list: list[str], diag: str) -> bool:
        return any(word in diag.lower() for word in word_list)
