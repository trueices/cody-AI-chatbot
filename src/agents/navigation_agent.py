import logging
from datetime import datetime
from typing import Type, Tuple

import humanize
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain.tools.base import BaseTool
from langchain.tools.render import format_tool_to_openai_function
from pydantic import BaseModel, Field

from src import agents
from src.agents.utils import check_function_call, load_greetings
from src.bot_state import BotState
from src.bot_stream_llm import CustomChatOpenAI, StreamChatOpenAI
from enum import Enum

from src.followup.followup_care import FollowupCare
from src.followup.followup_care_state import FollowupState, FollowUpCareState
from src.sub_specialist import SubSpecialtyDxGroup
from src.utils import base_url


class IntentEnum(str, Enum):
    symptom_or_suspected_condition = 'symptom_or_suspected_condition'
    confirmed_condition = 'confirmed_condition'
    health_related_question = 'health_related_question'


class ToolCheck(BaseModel):
    intent: IntentEnum = Field(..., description='The intent of the user')


class CaptureIntentTool(BaseTool):
    name = 'capture_intent_tool'
    description = ('Carries the intent to the next step of the agent.')
    args_schema: Type[BaseModel] = ToolCheck

    def _run(self, intent) -> str:
        return 'Intent captured'


class NavigationAgent(agents.Agent):
    name = 'navigation_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None):
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]
        self.tools = [
            CaptureIntentTool()
        ]
        if len(self.conv_hist) == 0 \
                and len(self.state.conv_hist[agents.ChiefComplaintAgent.name]) == 0 \
                and len(self.state.conv_hist[agents.QuestionAgent.name]) == 0 \
                and len(self.state.conv_hist[agents.ExistingDiagnosisAgent.name]) == 0:

            care_state = FollowupCare.get_latest_followup_care_state(profile)
            if care_state and care_state.is_followup_eligible() and care_state.state != FollowupState.NEW:
                content = self._followup_greeting(care_state.name,
                                                  care_state.chief_complaint,
                                                  care_state.convo_id)

            # If followup protocol was done, or it was resolved, we need to acknowledge the user for new conversation
            elif care_state and care_state.state in [FollowupState.RESOLVED, FollowupState.FOLLOW_UP_DONE]:
                content = self._followup_acknowledgement_greeting(care_state)
            else:
                content, _ = self._greeting()

            self.conv_hist.append(AIMessage(content=content))
            self.llm.stream_callback.full_conv_hist.append_token(
                content)  # We will need a better way to do this in the future.

    def act(self) -> bool:
        # Special re-entry to the navigation agent after visiting question or existing diagnosis agent.
        if len(self.conv_hist) == 0 \
                and (len(self.state.conv_hist[agents.QuestionAgent.name]) > 0 or
                     len(self.state.conv_hist[agents.ExistingDiagnosisAgent.name]) > 0):
            content, options = self._greeting()
            self.conv_hist.append(AIMessage(
                content=content))  # The entire greeting (including options) should be available to the LLM to set the context right.
            self.llm.stream_callback.on_llm_new_token(options)  # Only the options should be displayed to the user.
            return True

        # human input appended in history
        self.conv_hist.append(HumanMessage(
            content=self.state.last_human_input))

        # Adding a check for the number of messages in the conversation history
        if len(self.conv_hist) >= 25:
            overuse_message = (
                "Unfortunately, I cant go any longer here. Please start a new conversation.")
            self.llm.stream_callback.on_llm_new_token(overuse_message)
            return True

        logging.debug('Waiting for the main agent...')
        conv_hist = [SystemMessage(
            content=self._configure_system_prompt())] + self.conv_hist[-10:]
        functions = [format_tool_to_openai_function(
            tool) for tool in self.tools]
        llm = CustomChatOpenAI(state=self.state) # Not streaming since the function call is sometimes accompanied by a message which is not ideal.
        response = llm(conv_hist, seed=0, functions=functions, prompt_test='prompt_test' in self.state.mode)
        self.conv_hist.append(response)


        # Checking if a function call was mad
        function_response, arguments = check_function_call(
            response, self.tools)
        if function_response is None:
            self.llm.stream_callback.on_llm_new_token(response.content)
            return True
        else:
            # Add the response to the conversation memory
            intent = arguments['intent']
            if intent == IntentEnum.health_related_question:
                self.state.next_agent(name=agents.QuestionAgent.name, reset_hist=True)
            elif intent == IntentEnum.confirmed_condition:
                self.state.next_agent(name=agents.ExistingDiagnosisAgent.name, reset_hist=True)
            else:
                self.state.next_agent(name=agents.ChiefComplaintAgent.name, reset_hist=True)
            return False

    @staticmethod
    def _configure_system_prompt() -> str:
        # Configuring the system prompt based on the number of messages in the conversation history
        system_prompt = f"""
You are a doctor. Your name is Cody.
Your job is:
1. Identify the intent of user's response: (symptom/suspected condition, confirmed condition, or health related question).
2. Confirm with the patient.
3. If confirmed, call the {CaptureIntentTool().name}. If not confirmed, ask the patient to clarify.

Instructions: 
- DO NOT ASK ANY FOLLOWUP QUESTIONS, except a confirmation from the user to proceed with the selected problem.
- Your job is not to provide any answers but to identify the intent, confirm with the user, and call the {CaptureIntentTool().name}.
- Do not call the {CaptureIntentTool().name} without getting a confirmation from the user.
- Keep your outputs under one or two sentences.
- The user should not know that you called the {CaptureIntentTool().name} tool. Do it discretely.

Example of "symptom" are: pain, soreness, pressure, cough, pus, discoloration, bloating
Example of "condition" are: diabetes, hypertension, rheumatoid arthritis, psoriasis. fibromyalgia. 

Example conversation for {IntentEnum.symptom_or_suspected_condition}:
Human: I have a back pain
<back pain is a symptom, so you should ask the user to confirm the intent.>
AI: So you want to focus on your back pain today, is that correct?
Human: Yes
<Function call: {CaptureIntentTool().name} with intent being {IntentEnum.symptom_or_suspected_condition}.>
End of example conversation.

Example conversation for {IntentEnum.symptom_or_suspected_condition}:
Human: diabetes
<diabetes is a condition, so should ask if diagnosed>
AI: Has a healthcare professional diagnosed you with diabetes?
Human: No
<Function call: {CaptureIntentTool().name} with intent being {IntentEnum.symptom_or_suspected_condition}.>
End of example conversation.

Example conversation for {IntentEnum.confirmed_condition}:
Human: diabetes
<diabetes is a condition, so should ask if diagnosed>
AI: Has a healthcare professional diagnosed you with diabetes?
Human: yes
<Function call: {CaptureIntentTool().name} with intent being {IntentEnum.confirmed_condition}.>
End of example conversation.

Example conversation for {IntentEnum.health_related_question}:
Human: What is cholesterol?
AI: So you want to focus on understanding cholesterol today, is that correct?
Human: Yes
<Function call: {CaptureIntentTool().name} with intent being {IntentEnum.health_related_question}.>
End of example conversation.

REMEMBER, do not say anything after the user confirms the intent. Just call the {CaptureIntentTool().name}.
"""
        return system_prompt

    def _followup_greeting(self, patient_name, prev_chief_complaint, convo_id):
        content, options = self._greeting()

        url = f"{base_url()}convo/{convo_id}?followup=true"
        content = f"""Hello, {patient_name}!

Welcome back!

I'm Cody, your AI Doctor, here to help you get better. I've been trained by licensed doctors.

Before we proceed, in our previous conversation, you mentioned that you had {prev_chief_complaint}. Let's followup on that <a class="text-blue underline app-link" href="{url}">here</a>.


{options}"""
        return content

    def _followup_acknowledgement_greeting(self, care_state: FollowUpCareState) -> str:
        content, options = self._greeting()
        now = datetime.now()
        created = care_state.created

        # if duration is more than 180 days, we need to append a complaint text
        complaint_text = '.'
        if (now - created).days < 180:
            complaint_text = f' and you were dealing with {care_state.chief_complaint}.'

        duration = humanize.naturaltime(now - created)

        content = f"""Hello, {care_state.name}!

It looks like we last chatted around {duration}{complaint_text}

I hope you are doing well.


{options}”"""
        return content

    def _greeting(self) -> Tuple[str, str]:
        greetings = load_greetings()
        if self.state.subSpecialty in greetings:
            content = greetings[self.state.subSpecialty]
        elif self.state.specialist in greetings:
            content = greetings[self.state.specialist]
        else:
            content = greetings[SubSpecialtyDxGroup.Generalist]

        greeting_with_options = f"{content.get('greeting')}\n\n\n{content.get('options')}"
        if self.state.patient_name is not None:
            greeting_with_options = greeting_with_options.replace('Hello!', f'Hello {self.state.patient_name}!')
        # For now, we are just adding languages just for first time users.
        else:
            greeting_with_options = greeting_with_options.replace('Hello!', 'Hello नमस्ते Hola Kamust 你好 Bonjour')
        return greeting_with_options, content.get('options')
