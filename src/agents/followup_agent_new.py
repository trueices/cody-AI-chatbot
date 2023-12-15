import difflib
import json
import logging
import textwrap
from typing import Tuple

from langchain.schema import SystemMessage, AIMessage

from src import agents
from src.bot_state import BotState
from src.bot_stream_llm import CustomChatOpenAI


class DXGv3:
    @classmethod
    def get_next_question_and_score(cls, self: agents.FollowupAgent, fields: dict) -> Tuple[str, int]:
        self.state.priority_fields_asked = []
        fields = cls.remove_irrelevant_fields(self.state, fields)
        updated_fields = cls.remove_filled_fields(self, fields)

        summarized_convo = DXGv3._summarize_convo(self.conv_hist, self.state)
        self.debug('---Summarized Convo---', bold=True)
        self.debug(summarized_convo)
        self.summary = summarized_convo

        score = cls.pf_check(
            self, updated_fields, fields, summarized_convo)
        if score is None:  # Exit condition
            return None, None
        updated_fields = cls.remove_filled_fields(self, fields)
        question = cls.question_generation(
            self, updated_fields, summarized_convo)
        # self.state.generated_questions.append(question)
        return question, score

    @staticmethod
    def remove_irrelevant_fields(state: BotState, fields: dict) -> dict:
        # Remove fields that are irrelevant
        updated_fields = {}

        # Check if relevance is recorded. If yes, skip checking relevance again.
        if not state.priority_field_relevance:
            # Relevance not recorded, check relevance
            for field in list(fields):
                state.priority_field_relevance[field] = True
                if fields[field].get('COMPULSORY') == 'No':
                    if not DXGv3.is_field_relevant(state, field):
                        state.priority_field_relevance[field] = False

        # Build updated fields list from relevant fields
        for field in list(fields):
            if state.priority_field_relevance[field] == True:
                updated_fields[field] = fields[field]
        return updated_fields

    def remove_filled_fields(self: agents.FollowupAgent, fields: dict) -> dict:
        # Remove fields that are already asked.
        updated_fields = {}
        for field in list(fields):
            if field not in self.state.priority_fields_asked:
                field_dict = {
                    key: value for key, value in fields[field].items() if key != 'FILL SCORE'}
                updated_fields[field] = field_dict
        return updated_fields

    @staticmethod
    def pattern_matching(generated: dict, actual: list) -> dict:
        """
        Match the generated fields with the actual field names using similarity.
        """
        mapping = {}
        mapped_indices = set()

        for str1 in list(generated):
            max_sim = 0
            max_idx = None

            for idx2, str2 in enumerate(actual):
                if idx2 not in mapped_indices:
                    similarity = difflib.SequenceMatcher(
                        None, str1, str2).ratio()
                    if similarity > max_sim:
                        max_sim = similarity
                        max_idx = idx2

            if max_idx is not None:
                mapping[actual[max_idx]] = generated[str1]
                mapped_indices.add(max_idx)
        return mapping

    @staticmethod
    def pf_check(self: agents.FollowupAgent, updated_fields: dict, fields: dict,
                 summarized_convo: str) -> int:
        """
        PF Check stands for Priority Field Check.
        Checks which priority fields are filled and returns the total score."""
        if len(self.conv_hist) <= 1:
            return 0

        updated_fields_list = list(updated_fields.keys())
        logging.debug("UPDATED FIELDS: ", updated_fields)
        system_prompt = textwrap.dedent(
            f"""
You are a knowledgeable clinician assistant.
You have a SUMMARY OF CONVERSATION with a patient who is expressing concerns regarding the topic: {self.state.chief_complaint}

Your job is to extract field values from the SUMMARY OF CONVERSATION.
Here is a list of Fields:
{updated_fields_list}

Your output should be a JSON with the following keys:
{updated_fields_list}
The value of the key should be a string indicating the value of the field as mentioned in SUMMARY OF CONVERSATION.
If a field was not mentioned in the SUMMARY OF CONVERSATION, use a value of "N/A", or skip the key.

DO NOT HALLUCINATE. Skip a field if it is not mentioned in the SUMMARY OF CONVERSATION.

EXAMPLE INPUT: 
CHIEF COMPLAINT: cough 
LIST OF FIELDS: ['previous medical diagnoses', 'year of birth', 'location of cough', 'getting worse, getting better, staying the same, or varies', 'started suddenly or gradually', 'other symptoms']
SUMMARY OF CONVERSATION: The patient is experiencing a productive cough with green 
mucus, rated at a severity of 6 on a scale of 1 to 10. The cough is constant throughout the day and night, 
with some worsening when lying down. They also have a temperature of 101.3F and tightness in breathing. There is no 
weight loss, but they have no appetite. The patient has no previous medical diagnoses or relevant conditions.

EXAMPLE OUTPUT:
{{
"previous medical diagnoses": "No previous medical diagnoses",
"year of birth": "N/A",
"location of cough": "N/A",
"getting worse, getting better, staying the same, or varies": "Worsening when lying down",
"started suddenly or gradually": "N/A",
"other symptoms": "Temperature of 101.3F, tightness in breathing, no weight loss, no appetite"
}}
""")
        content = f"""
CHIEF COMPLAINT: concerned about the topic {self.state.chief_complaint}
LIST OF FIELDS: {updated_fields_list}
SUMMARY OF CONVERSATION: {summarized_convo}"""
        llm = CustomChatOpenAI(state=self.state)
        conv_hist = [SystemMessage(
            content=system_prompt), AIMessage(content=content)]
        kwarg_args = {"response_format": {"type": "json_object"}}
        response = llm(conv_hist, seed=0, **kwarg_args, prompt_test = 'prompt_test' in self.state.mode).content
        response: dict = json.loads(response)

        # Field matching...
        # Step 1: Remove fields whose value is invalid.
        generated_fields = {}
        for field_name in response.keys():
            if response[field_name].strip().lower() not in ['n/a', 'not mentioned', 'none', 'unknown', 'none mentioned']:
                generated_fields[field_name] = response[field_name]
        # Step 2: Match using similarity, the generated fields and the actual fields.
        generated_fields = DXGv3.pattern_matching(
            generated_fields, list(fields.keys()))

        # self.debug('---PFC System Prompt----', bold=True)
        # self.debug(system_prompt)
        # self.debug('---PFC AI prompt---', bold=True)
        # self.debug(content)
        self.debug('---PFC Response---', bold=True)
        for key, val in generated_fields.items():
            self.debug(f"{key}: {val}")

        # Append the answered fields answered to the list
        for field in generated_fields:
            if field not in self.state.priority_fields_asked and field in fields:
                self.state.priority_fields_asked.append(field)
        logging.info(f"Fields asked: {self.state.priority_fields_asked}")

        # If a priority field is explicitly asked once, we mark it as filled.
        for field in self.state.fields_asked_once:
            if field not in self.state.priority_fields_asked:
                self.state.priority_fields_asked.append(field)

        # Exit condition
        if len(self.state.priority_fields_asked) == len(fields):
            return None

        # Calculate the total score
        total_score = 0
        for field in list(fields):
            if field in self.state.priority_fields_asked:
                total_score += fields[field]['FILL SCORE']
        self.debug(f"Total score: {total_score}")
        return total_score

    @staticmethod
    def question_generation(self: agents.FollowupAgent, updated_fields: dict, summarized_convo: str) -> str:
        """
        QG stands for Question Generation for the next followup question.
        """
        updated_fields_list = list(updated_fields.keys())
        self.debug('---QG---', bold=True)
        llm = CustomChatOpenAI(state=self.state)
        field_name = updated_fields_list[0]
        self.debug(f'mode: strictly fill {field_name}')
        self.state.fields_asked_once.append(field_name)
        # We tried giving all priority fields at a time and allowing the model to ask natural questions,
        # but it ended up causing the model to repeat questions.
        system_prompt = f"""
You are talking to {self.state.patient_name}, who is concerned about {self.state.chief_complaint}.
You are Cody, an AI {self.state.specialist.name}.
Here is a PRIORITY FIELD associated with the topic of {self.state.specialist.display_name_speciality}

PRIORITY FIELD: {field_name}
DETAILS: {updated_fields[field_name]}

GENERATE A QUESTION as a {self.state.specialist.name} specialist relevant for answering the PRIORITY FIELD field.
DO NOT ask questions which are already answered in SUMMARY OF CONVERSATION below.

When asking questions, try to use examples. For example: 
1. "Have you recently started taking any new medications or supplements? For example, aspirin, ibuprofen, or blood thinners?"
2. "Have you recently been exposed to any new allergens or irritants? For example, pollen, dust, or smoke?"
3. "Have you been diagnosed with any medical conditions? For example, high blood pressure, blood clotting disorders, or liver disease?"

Respond with a JSON object with the following key:
question: string (the question to ask regarding the PRIORITY FIELD)

Example 1:
PRIORITY FIELD: Sex
OUTPUT:
{{
"question": "May I know your sex?
}}
"""
        content = f"""SUMMARY OF CONVERSATION: {summarized_convo}"""
        response = llm([SystemMessage(content=system_prompt),
                        AIMessage(content=content)],
                       response_format={"type": "json_object"},
                       prompt_test = 'prompt_test' in self.state.mode
                       )

        # self.debug('---QG System prompt----', bold=True)
        # self.debug(system_prompt)
        # self.debug('---QG AI Prompt---', bold=True)
        # self.debug(content)
        response = json.loads(response.content)
        # self.debug('---QG Response---', bold=True)
        # self.debug(str(response))
        # self.debug('--------', bold=True)
        # In case the model fails to generate a question, we ask a default question (to be safe).
        return response.get('question', 'I am sorry, can you please type that again?')

    @staticmethod
    def talk(self: agents.FollowupAgent, question: str):
        """
        Generates and sends the final response to the patient.
        This is the final step in the followup agent.
        """
        if len(self.conv_hist) == 0:
            self.llm.stream_callback.on_llm_new_token(question)
            self.conv_hist.append(AIMessage(content=question))
            return
        else:
            turn_count = int(len(self.conv_hist) / 2)
            if turn_count % 3 == 0:  # Subsequent prompts
                phrases = 'You should try to use phrases like "Hmm.. I see, I understand, Ah, Ok.. etc." to show empathy.\n'
                phrases += 'And make sure to use them at the right time.\n'
            elif turn_count % 3 == 1:
                phrases = 'You should try to use phrases like "Alright, noted. Acknowledged... Got it... etc." to show empathy.\n'
                phrases += 'And make sure to use them at the right time.\n'
            else:
                phrases = ''
            system_prompt = textwrap.dedent(
                f"""
You are Cody, an AI {self.state.specialist.name}.
You are talking to {self.state.patient_name}, who is concerned about {self.state.chief_complaint}.
Your job is to create a fact that provides some additional information or context to the patient's last message.
If the human asks a question, you should provide an answer to the question in the response.
{phrases}
Your output should be a JSON with the following keys:
- response: string (the response to the patient's last message in the form of a fact or an answer.)

EXAMPLE 1:
AI: Sorry to hear about that. Headaches can tough. By the way, have you been experiencing any other symptoms along with the headaches? Like nausea, dizziness, or sensitivity to light?
Human: Nope
OUTPUT:
{{
"response": "Nausea, dizziness and light senstivity are common symptoms that can accompany headaches, but it is good to know that you are not experiencing them."
}}

EXAMPLE 2:
AI: Gastritis can be quite painful. What is your year of birth?
Human: why do you need that?
OUTPUT:
{{
"response": "The year of birth can help me understand the patient's age and provide better care."
}}
""")
            content = f"""AI: {self.conv_hist[-2].content}
Human: {self.conv_hist[-1].content}"""

            conv_hist = [SystemMessage(
                content=system_prompt), AIMessage(content=content)]
            llm = CustomChatOpenAI(state=self.state)
            response = llm(conv_hist, response_format={
                           "type": "json_object"},
                           prompt_test = 'prompt_test' in self.state.mode).content
            response: dict = json.loads(response)
            response = response.get('response', '')
            # Extract the first line ending with a period or question mark.
            # This is because sometimes, the response contains information regarding health care provider which we want to avoid.
            response = response.split('.')[0]
            if response != '':
                response += '.'
            self.llm.stream_callback.on_llm_new_token(
                response + "\n\n\n" + question)
            self.conv_hist.append(AIMessage(content=response+' '+question))

            # self.debug('---HQG System prompt----', bold=True)
            # self.debug(system_prompt)
            # self.debug('---HQG AI Prompt---', bold=True)
            # self.debug(content)
            # self.debug('---HQG Response---', bold=True)
            # self.debug(response)

    @staticmethod
    def _summarize_convo(conv_hist: list[dict], state: BotState) -> str:
        # Consider chief complaint convo history in summary as well, as
        # patient can share quite some details already
        chief_complaint_history: list[dict] = []

        for msg in state.conv_hist[agents.NavigationAgent.name][1:]:
            if msg.type in ['human', 'ai'] and msg.content != '':
                chief_complaint_history.append(msg)

        system_prompt = f"""
You are a doctor expert at summarizing patient conversation clinically .You have been conversing with a patient, about their symptoms.
You have already asked a set of questions and the patient has answered them.
Now, use the conversation history and summarize the conversation with as much detail as possible. 

if a particular thing is just asked and not answered, do not include it in the summary.

Add as much clinical information as possible in the summary. DO NOT provide any explanation or advise just summarize the conversation history.

CONVERSATION HISTORY:
"""
        system_prompt += '\n'.join(
            [f'{msg.type}: {msg.content}' for msg in chief_complaint_history])

        system_prompt += '\n'

        system_prompt += '\n'.join(
            [f'{msg.type}: {msg.content}' for msg in conv_hist])

        llm = CustomChatOpenAI(state=state)
        prompt = [SystemMessage(
            content=system_prompt)]

        response = llm(prompt, seed=0).content

        return response

    @staticmethod
    def check_confidence(self: agents.FollowupAgent, threshold: int):
        llm = CustomChatOpenAI(state=self.state)
        system_prompt = textwrap.dedent(
            f"""
You are chatting with a patient.
Based on the SUMMARY OF CONVERSATION provided below, create a list of top 3 diagnoses, and a Confidence Score.

Confidence Score should reflect the level of certainty based on the information provided.
Confidence Score should be assigned based on the completeness and quality of diagnostic data.
Confidence Score is an assessment of how well the diagnosis data fits the recognized pattern for a specific diagnosis.
Keep in mind that a high Confidence Score should be reserved for cases where there is substantial relevant information.

Your output should be a JSON with the following keys:
thought: A few words, describing your thought process.
diagnosis: The top 3 diagnoses, as a list of strings.
confidence_score: An integer between 1 to 100, indicating your confidence in the diagnosis.

SUMMARY OF CONVERSATION: {self.summary}
""")
        response = llm([SystemMessage(content=system_prompt)],
                       response_format={"type": "json_object"})
        response = json.loads(response.content)
        # self.debug('---confidence---', bold=True)
        # self.debug(f"Thought: {response['thought']}")
        # self.debug(f"Diagnosis: {response['diagnosis']}")
        # self.debug(f"Confidence Score: {response['confidence_score']}")
        score = int(response.get('confidence_score', 0))

        if score > self.state.confidence_score and score >= threshold:
            content = f'Ah, I see. I am now {score}% confident of your Top 3 Condition List. For the most accurate results, I would like to ask you more questions. However, you may enter "Go" anytime and I will share your Top 3 Condition List.\n'
            self.llm.stream_callback.on_llm_new_token(content)
        self.state.confidence_score = score

    @staticmethod
    def is_field_relevant(state: BotState, field: str):
        """Check if the current field is relevant or not."""
        llm = CustomChatOpenAI(state=state)
        content = f'CHIEF COMPLAINT: {state.chief_complaint}\n'
        content += f'FIELD: {field}\n'
        from src.agents.followup_utils import field_relevant_system_prompt
        response = llm([SystemMessage(content=field_relevant_system_prompt),
                        AIMessage(content=content)],
                       response_format={"type": "json_object"}
                       )
        response = json.loads(response.content)
        # self.debug('----relevant?----')
        # self.debug(f'FIELD NAME: {field}')
        # self.debug(f"reasoning: {response['reasoning']}")
        # self.debug(f"relevant: {response['relevant']}")
        return response.get('relevant', False)
