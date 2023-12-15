import textwrap
import json
import logging

from langchain.schema import SystemMessage

from src import agents
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI, CustomChatOpenAI
from src.sub_specialist import SubSpecialtyDxGroup
from src.specialist import Specialist


class RouterAgent(agents.Agent):
    name = 'router_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None):
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]

    def _categorize(self, schema: dict) -> str:
        system_prompt = textwrap.dedent(
            f"""
Given a chief complaint, select the most relevant category it belongs to.
Chief complaint identified: {self.state.chief_complaint}
""")
        llm = CustomChatOpenAI(state=self.state)
        response = llm([SystemMessage(content=system_prompt)],
                       functions=[schema],
                       function_call={"name": schema['name']})
        self.conv_hist.append(response)

        function_call = response.additional_kwargs.get("function_call")
        fields = schema['parameters']['required']
        if function_call is None:
            logging.warning(
                f'No specialist assigned for id {self.state.username}')
            return [None for _ in fields]
        else:
            args = json.loads(function_call.get('arguments'))
            return [args[field] for field in fields]

    def act(self) -> bool:
        # This check is to make sure we don't run agent if we have already categorized the chief complaint via
        # targeted urls
        if self.state.specialist is Specialist.Generalist:
            function_schema_specialist = {
                "name": "categorize_chief_complaint",
                "description": "Used to categorize the chief complaint to a specialist.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "specialist": {
                            "description": "The specialist of the chief complaint.",
                            "type": "string",
                            "enum": [specialist.name for specialist in Specialist],
                        },
                    },
                    "required": ["specialist"]
                },
            }
            self.state.specialist = Specialist.from_name(self._categorize(function_schema_specialist)[0])

            if self.state.specialist != Specialist.Generalist:
                function_schema_sub_speciality = {
                    "name": "categorize_chief_complaint",
                    "description": "Used to categorize the chief complaint to a sub-speciality.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sub_speciality": {
                                "description": "The sub-speciality of the chief complaint.",
                                "type": "string",
                                "enum": [sub_speciality.name for sub_speciality in SubSpecialtyDxGroup if
                                         sub_speciality.specialist == self.state.specialist],
                            },
                            "is_disease_name": {
                                "description": "Is the chief complaint a disease name?",
                                "type": "boolean"
                            }

                        },
                        "required": ["sub_speciality", "is_disease_name"]
                    },
                }
                [sub_speciality, is_disease_name] = self._categorize(function_schema_sub_speciality)
                if is_disease_name:
                    self.state.subSpecialty = SubSpecialtyDxGroup.from_name(sub_speciality)

        self.state.next_agent()
        return False