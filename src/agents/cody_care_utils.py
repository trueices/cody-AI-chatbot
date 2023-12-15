import json

from langchain.schema import SystemMessage, AIMessage

from src.bot_stream_llm import CustomChatOpenAI
from src.bot_state import BotState
from src.rx.ehr_service import EhrService


class CodyCareUtils:
    options = "1. Yes\n2. No"
    confirm_msg = "To confirm, you are currently in {residing_state}, U.S.\n{options}"

    @staticmethod
    def attempt_capture_state(state: BotState, last_human_input: str) -> str:
        system_prompt = """
Your task is to capture the state of the user where they reside.
To qualify for the state:
- The user must be in the United States.
- The state must be a valid state in the United States.

If the state is valid, your output should be a JSON object with the following format:
{{
    "state": "California"
}}
If the state is not valid, you should output the following:
{{
    "error": "Invalid state"
}}
"""
        # We will parse the user input and check if it is a valid state.
        system_prompt += f"USER: {last_human_input}"
        response = CustomChatOpenAI(state=state)([SystemMessage(
            content=system_prompt)], response_format={"type": "json_object"}).content
        response: dict = json.loads(response)
        state_captured = response.get('state', 'not_captured')
        if state_captured != 'not_captured':
            # Check if the state is supported.
            states = EhrService().all_supported_state()
            if state_captured.lower() not in states:
                state_captured = 'not_supported'
        return state_captured

    @staticmethod
    def validate_questions_via_llm(state: BotState, last_human_input: str, prompt: str, **kwargs) -> dict:
        content = f"USER INPUT: {last_human_input}"
        conv_hist = [SystemMessage(content=prompt),
                     AIMessage(content=content)]
        response = CustomChatOpenAI(state=state)(
            conv_hist,
            response_format={"type": "json_object"},
            **kwargs
        ).content
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {
                'value': "invalid"
            }
