import logging
import re
import textwrap
import json
import random
from typing import Tuple

from langchain.schema import HumanMessage, SystemMessage, AIMessage

from src import agents
from src.agents.utils import load_priority_fields, get_supported_sps
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI, CustomChatOpenAI


class FollowupAgent(agents.Agent):
    name = 'followup_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None):
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]
        self.profile = profile

        # We use these to reset the state in case of exceptions like timeout.
        self.initial_priority_fields_asked = self.state.priority_fields_asked.copy()
        self.initial_conv_hist = self.conv_hist.copy()
        self.initial_confidence_score = self.state.confidence_score
        self.initial_debug_messages_list = self.state.debug_messages_list.copy()
        self.initial_thought_process = self.state.thought_process
        self.initial_priority_field_relevance = self.state.priority_field_relevance.copy()
        self.initial_fields_asked_once = self.state.fields_asked_once.copy()

    def act(self) -> bool:
        supported_list = get_supported_sps()
        self.convo_training()
        if self.state.subSpecialty in supported_list:
            self.state.priority_field_src = 'subSpecialty'
            return self.act_sp()
        else:
            self.state.priority_field_src = 'specialist'
            return self.act_sp()

    def act_sp(self) -> bool:
        # During the initial stage, the human input is from prev agent's interactions, so we dont need to include it.
        if len(self.conv_hist) != 0:
            if self.conv_hist[-1].type != 'human':
                self.conv_hist.append(HumanMessage(
                    content=self.state.last_human_input))
                # Continue to the next agent if the user says "next"
                if self.state.last_human_input.lower().strip() == 'go':
                    self.state.next_agent()
                    return False

        # Load the priority fields
        fields, min_points, confidence_interval = load_priority_fields(
            self.state.specialist, self.state.subSpecialty, self.state.chief_complaint)

        # Call the next agent after sufficient number of questions are asked
        if len(self.conv_hist) >= 40:  # [AI, Human ... 20 times]
            self.state.next_agent()
            return False

        try:
            if self.state.priority_field_src == 'subSpecialty':
                question, score = self.generate_question_sub_specialist(fields)
            else:
                self.state.dxg_version = 'dxgv3'
                question, score = agents.DXGv3.get_next_question_and_score(
                    self, fields)
            if question == None:
                self.state.next_agent()
                return False
            # Confidence check
            if score >= min_points:
                if self.state.dxg_version == 'dxgv3':
                    agents.DXGv3.check_confidence(self, confidence_interval)
                else:
                    self.check_confidence(confidence_interval)

            self.debug("---end----", bold=True)

            if self.state.dxg_version == 'dxgv3':
                agents.DXGv3.talk(self, question)
            else:
                self.hqg(question)
            return True
        except Exception as e:
            self.reset_state()
            raise e

    def generate_question_sub_specialist(self, fields) -> Tuple[str, int]:
        # Remove fields that are already asked
        updated_fields = []
        for field in list(fields):
            if field.lower().strip() not in self.state.priority_fields_asked:
                updated_fields.append(field)
            if len(updated_fields) == 3:
                break

        logging.debug(f"UPDATED FIELDS: {updated_fields}")
        system_prompt = textwrap.dedent(
            f"""
You are Cody, a specialist doctor in {self.state.specialist.name}.
You are treating a patient who have expressed concerns regarding the topic: {self.state.chief_complaint}

Here is a suggested LIST OF FIELDS you can ask about:
{updated_fields}

Use this LIST OF FIELDS to select the next field to ask, based on the conversation history.
Select only one field from the list. Maintain the sequence of the fields.
Your output should be a JSON with the following keys:

thought: A few words, describing your thought process.
fields_answered: list of strings (the fields that are already answered by the patient/user. Can be empty. Should be among {updated_fields})
next_field: string (the field selected to create the next question. Should be one among {updated_fields})
question: string (The next question to ask regarding the next_field)

Note:
1. If the user responds to a field saying that they dont know, you should consider the field filled/answered.
2. But if the user responds by asking a question or by responding in a way that doesnt make sense, you should consider the field not filled/answered.
3. Your volcabulary of fields should only be among the list {updated_fields}.
4. DO not hallucinate or make up any information.
5. If a field in {updated_fields} is filled, you should include it in the list of fields_answered. The next_field should be a field that you have not asked yet.
6. The priority of fields is based on the sequence of the list of fields. The first field in the list has the highest priority.

Example 1:
CHIEF COMPLAINT: concerned about Tremor
LIST OF FIELDS: ['Diagnosed with Neurologic Condition' , 'Headache', 'Balance changes', 'Intensity']
CONVERSATION HISTORY:
ai: What is you age?
user: 60
ai: Have you been diagnosed with any neurologic condition?
user: No
ai: Ok.. Have you had headaches associated with your tremors?
user: Yes, sometimes
OUTPUT:
{{
"thought": "Among the LIST OF FIELDS, the fields "Diagnosed with Neurologic Condition" and "Headache" have been asked and answered. So, both are marked as filled.",
"fields_answered": ["Diagnosed with Neurologic Condition", "Headache"],
"next_field": "Balance changes",
"question": "Have you had any changes in the way you balance yourself?",
}}

Example 2:
CHIEF COMPLAINT: concerned about acne
LIST OF FIELDS: ['Sex' , 'Year of birth', 'dermatological conditions']
CONVERSATION HISTORY:
OUTPUT:
{{
"thought": "There's no conversation history, so no fields are answered. The first field "Sex" has the highest priority since it comes first in the list. Hence it is used as the next_field to ask.",
"fields_answered": [],
"next_field": "Sex",
"question": "What is your sex?",
}}

Example 3:
CHIEF COMPLAINT: concerned about severe headache
LIST OF FIELDS: ['year of birth', 'Sex', 'Intensity']
CONVERSATION HISTORY:
ai: What is your year of birth?
user: yes
OUTPUT:
{{
"thought": "This response does not provide the year of birth. So, year of birth is not filled. Let me ask again.",
"fields_answered": [],
"next_field": "year of birth",
"question": "What is your year of birth?",
}}

Example 4:
CHIEF COMPLAINT: concerned about acne
LIST OF FIELDS: ['whiteheads', 'blackheads']
CONVERSATION HISTORY:
ai: Do you have any whiteheads?
user: what is whitehead?
OUTPUT:
{{
"thought": "Human has enquired about whiteheads. But I still dont know if the user has whiteheads or not. Let me ask again.",
"fields_answered": [],
"next_field": "whiteheads",
"question": "Do you have any whiteheads?",
}}

Example 5:
CHIEF COMPLAINT: concerned about severe headache
LIST OF FIELDS: ['year of birth', 'Sex', 'Intensity']
CONVERSATION HISTORY:
ai: What is your year of birth?
user: male
OUTPUT:
{{
"thought": "Human's last response to the question about year of birth doesnt make sense. So, year of birth is not filled. Let me ask again.",
"fields_answered": [],
"next_field": "year of birth",
"question": "What is your year of birth?",
}}

""")
        content = f"""
CHIEF COMPLAINT: concerned about the topic {self.state.chief_complaint}
LIST OF FIELDS: {updated_fields}
CONVERSATION HISTORY:"""
        content += '\n'.join(
            [f'{msg.type}: {msg.content}' for msg in self.conv_hist[-4:]])
        content += '\n'
        llm = CustomChatOpenAI(state=self.state)
        conv_hist = [SystemMessage(
            content=system_prompt), AIMessage(content=content)]
        kwarg_args = {"response_format": {"type": "json_object"}}
        response = llm(conv_hist, seed=0, **kwarg_args).content
        response: dict = json.loads(response)
        response['thought'] = response.get('thought', '')
        response['fields_answered'] = response.get('fields_answered', [])
        response['next_field'] = response.get('next_field', '')
        response['question'] = response.get('question', '')
        self.debug('---Q generation---')
        self.debug(f"Thought: {response['thought']}")
        self.debug(f"Fields answered: {response['fields_answered']}")
        self.debug(f"Next Field: {response['next_field']}")
        self.debug(f"Question: {response['question']}")
        self.state.thought_process = response['thought']

        self.state.priority_fields_asked = [
            field.lower().strip() for field in self.state.priority_fields_asked]
        response['fields_answered'] = [field.lower().strip()
                                       for field in response['fields_answered']]
        list_of_fields = [field.lower().strip() for field in list(fields)]

        # Append the answered fields answered to the list
        for field in response['fields_answered']:
            if field not in self.state.priority_fields_asked and field in list_of_fields:
                self.state.priority_fields_asked.append(field)
        logging.info(f"Fields asked: {self.state.priority_fields_asked}")

        # Exit condition
        if len(self.state.priority_fields_asked) == len(list_of_fields):
            return None, None

        # Calculate the total score
        total_score = 0
        for field in list(fields):
            if field.lower().strip() in self.state.priority_fields_asked:
                total_score += fields[field]['FILL SCORE']
        self.debug(f"Total score: {total_score}")
        return response['question'], total_score

    def hqg(self, question: str):
        """
        Humanized Question Generation
        Get's a question as input and humanizes it.
        Also considers the conversation history, is receptive of user responses and adds phrases accordingly.
        """
        if len(self.conv_hist) == 0:
            self.llm.stream_callback.on_llm_new_token(question)
            response = AIMessage(content=question)
        else:
            # Counting turns.
            turn_count = int(len(self.conv_hist)/2)
            if turn_count % 3 == 0:  # Subsequent prompts
                phrases = 'You should try to use phrases like "Hmm.. I see, I understand, Ah, Ok.. etc." to show empathy.\n'
                phrases += 'Keep the phrases short and to the point.\n'
                phrases += 'And make sure to use them at the right time.\n'
            elif turn_count % 3 == 1:
                phrases = 'You should try to use phrases like "Alright, noted. Acknowledged... Got it... etc." to show empathy.'
                phrases += 'Keep the phrases short and to the point.\n'
                phrases += 'And make sure to use them at the right time.\n'
            else:
                phrases = 'Do not use any phrases. Just ask the question directly.\n'
            system_prompt = textwrap.dedent(f"""
You are Cody, an AI Doctor.
You are an expert at making a conversation with the patient.
Do not let the conversation deviate from the topic of the health issue.
You are empathetic. But you respond in short sentences which are easier to read.
You are part of an ongoing followup conversation with a patient.
Make sure you provide an answer to any questions or concerns the patient has, in brief.
{phrases}
Patient/user name: {self.state.patient_name}
The patient is concerned about: {self.state.chief_complaint}
""")
            thought = ''
            if self.state.thought_process != '':
                thought = f"Here is your thought process, based on the previous conversation: {self.state.thought_process}"
            system_prompt_2 = textwrap.dedent(f"""{thought}
Now, ask the next following question: {question}
If possible, try to connect the question with the previous conversation.""")
            # logging.debug(system_prompt)
            # logging.debug(system_prompt_2)
            full_conv = [SystemMessage(content=system_prompt)] +\
                self.conv_hist +\
                [SystemMessage(content=system_prompt_2)]
            response = self.llm(full_conv)
        self.conv_hist.append(response)

    def reset_state(self):
        # Reset the state variables if any error occurs
        self.state.priority_fields_asked = self.initial_priority_fields_asked.copy()
        self.conv_hist[:] = self.initial_conv_hist.copy()
        self.state.confidence_score = self.initial_confidence_score
        self.state.debug_messages_list = self.initial_debug_messages_list.copy()
        self.state.thought_process = self.initial_thought_process
        self.state.priority_field_relevance = self.initial_priority_field_relevance
        self.state.fields_asked_once = self.initial_fields_asked_once

    def debug(self, msg: str, bold=False):
        if '_debug' in self.state.mode:
            self.llm.stream_callback.on_llm_new_token("<div class='tx-plan'>")
            if bold:
                self.llm.stream_callback.on_llm_new_token(f"<b>{msg}</b>")
            else:
                self.llm.stream_callback.on_llm_new_token(msg)
            self.llm.stream_callback.on_llm_new_token("</div>\n")
        self.state.debug_messages_list.append(msg)

    def check_confidence(self, threshold: int):
        llm = CustomChatOpenAI(state=self.state)
        system_prompt = "CONVERSATION HISTORY:\n"
        system_prompt += '\n'.join(
            [f'{msg.type}: {msg.content}' for msg in self.conv_hist])
        system_prompt += '\n'

        system_prompt += textwrap.dedent(
            f"""
You are chatting with a patient.
Based on the conversation history, create a list of top 3 diagnoses, and a Confidence Score.

Confidence Score should reflect the level of certainty based on the information provided.
Confidence Score should be assigned based on the completeness and quality of diagnostic data.
Confidence Score is an assessment of how well the diagnosis data fits the recognized pattern for a specific diagnosis.
Keep in mind that a high Confidence Score should be reserved for cases where there is substantial relevant information.

Your output should be a JSON with the following keys:
thought: A few words, describing your thought process.
diagnosis: The top 3 diagnoses, as a list of strings.
confidence_score: An integer between 1 to 100, indicating your confidence in the diagnosis.
""")
        response = llm([SystemMessage(content=system_prompt)],
                       response_format={"type": "json_object"})
        response = json.loads(response.content)
        # self.debug('---Confidence---', bold=True)
        # self.debug(f"Thought: {response['thought']}")
        # self.debug(f"Diagnosis: {response['diagnosis']}")
        # self.debug(f"Confidence Score: {response['confidence_score']}")
        score = int(response['confidence_score'])

        if score > self.state.confidence_score and score >= threshold:
            content = f'Ah, I see. I am now {score}% confident of your Top 3 Condition List. For the most accurate results, I would like to ask you more questions. However, you may enter "Go" anytime and I will share your Top 3 Condition List.\n\n\n'
            self.llm.stream_callback.on_llm_new_token(content)
        self.state.confidence_score = score

    def convo_training(self):
        if random.random() > 0.2:  # Only send the message 20% of the time
            return

        if len(self.state.conv_train_msgs) >= 2:  # Dont send more than 2 convo training messages
            return

        LOGGED_OUT = [
            (f"PROTIP: Feel free to chat with me in your preferred language.", 1, 2),
            (f"By the way {self.state.patient_name}, our conversations are always private.", 2, 3),
            ("PROTIP: Remember to create an account or log in to save our conversation.", 3, 7),
            ("PROTIP: Securely share our conversation with family, a friend, or a doctor. Just log in and select a conversation to share.", 3, 8),
            ("PROTIP: Did you know you can customize Cody? Yep! Log in and tap the pencil icon by Cody.", 3, 9),
            ("I'll check in with you to make sure you're feeling better. Just log in and I'll check on you.", 3, 10),
            ("After you get your diagnosis list, we'll go over treatments and find a doctor that matches your needs.", 5, 7)
        ]

        LOGGED_IN = [
            (f"PROTIP: Feel free to chat with me in your preferred language.", 1, 2),
            ('PROTIP: Securely share our conversation with family, a friend, or a doctor. Just select tap "Chat History" and the select a conversation to share.', 3, 8),
            ("PROTIP: Did you know you can customize Cody?  Yep! Just tap the pencil icon by Cody.", 3, 9),
            ("After you get your diagnosis list, we'll go over treatments and find a doctor that matches your needs.", 5, 7)
        ]

        MSGS = LOGGED_IN if self.profile and self.profile.get(
            'isLoggedIn', False) else LOGGED_OUT

        # Filter out messages based on conv history length
        # The conv history length appears in the sequence: 0(can be treated as -1), 1, 3, 5, 7, 9, 11, 13, 15, 17, 19
        # The message sequence appears in the sequence: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
        # Hence, we multiply by 2 and subtract 3 to get the message sequence
        MSGS = [msg for msg in MSGS if len(
            self.conv_hist) >= msg[1]*2-3 and len(self.conv_hist)/2 <= msg[2]*2-3]

        # Filter out the messages that have already been sent
        MSGS = [msg[0]
                for msg in MSGS if msg[0] not in self.state.conv_train_msgs]
        if len(MSGS) == 0:
            return
        chosen_msg = MSGS[0]
        self.llm.stream_callback.on_llm_new_token(chosen_msg + '\n\n\n')
        self.state.conv_train_msgs.append(chosen_msg)
