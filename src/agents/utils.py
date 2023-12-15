import json
import logging
import os
from typing import Union

import pandas as pd
from langchain.schema import FunctionMessage, BaseMessage
from langchain.tools.base import BaseTool

from src.bot_stream_llm import CustomChatOpenAI
from langchain.schema import FunctionMessage, BaseMessage, SystemMessage, AIMessage
from langchain.tools.base import BaseTool

import pandas as pd
from src.bot_state import BotState
from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup

GREETINGS_df = pd.read_csv(f"{os.path.dirname(__file__)}/greetings.csv")


def _get_greeting_and_options(spdx):
    supported_sp_dxs = GREETINGS_df['SPECIALITY/DXGROUP'].str.lower().unique().tolist()

    if spdx.inventory_name.lower() in supported_sp_dxs:
        row = GREETINGS_df[GREETINGS_df['SPECIALITY/DXGROUP'].str.lower()
                           == spdx.inventory_name.lower()].iloc[0]
        greeting = row['GREETING'].replace('\r', '')
        options = row['OPTIONS'].replace('\r', '')
        return {'greeting': greeting, 'options': options}

    return None


def load_greetings() -> dict[Specialist | SubSpecialtyDxGroup, dict[str, str]]:
    supported_sp_dx_objs = {
        sp: _get_greeting_and_options(sp) for sp in Specialist}
    supported_sp_dx_objs.update({dx_group: _get_greeting_and_options(
        dx_group) for dx_group in SubSpecialtyDxGroup})
    return {key: value for key, value in supported_sp_dx_objs.items() if value is not None}


PRIORITY_FIELD_df = pd.read_csv(
    f"{os.path.dirname(__file__)}/priority_fields.csv")


def get_supported_sps() -> list[Specialist | SubSpecialtyDxGroup]:
    supported_spdxs = set(PRIORITY_FIELD_df['SPECIALITY/DXGROUP'].str.lower())
    supported_spdxobjs = []
    for sp in Specialist:
        if sp.inventory_name.lower() in supported_spdxs:
            supported_spdxobjs.append(sp)
    for dx_group in SubSpecialtyDxGroup:
        if dx_group.inventory_name.lower() in supported_spdxs:
            supported_spdxobjs.append(dx_group)
    assert len(supported_spdxobjs) == len(supported_spdxs), "Some specialists/Dx groups are not supported"
    return supported_spdxobjs


def load_priority_fields(specialist: Specialist, dx_group: SubSpecialtyDxGroup, chief_complaint: str = None) -> tuple[
        dict, int, int]:
    df = PRIORITY_FIELD_df[PRIORITY_FIELD_df['SPECIALITY/DXGROUP'].str.lower()
                           == dx_group.inventory_name.lower()]
    if len(df) == 0:
        df = PRIORITY_FIELD_df[PRIORITY_FIELD_df['SPECIALITY/DXGROUP'].str.lower()
                               == specialist.inventory_name.lower()]
    if len(df) == 0:
        # This means we should default to Generalist.
        df = PRIORITY_FIELD_df[PRIORITY_FIELD_df['SPECIALITY/DXGROUP'].str.lower()
                                 == Specialist.Generalist.inventory_name.lower()]


    fields = {}
    for i, row in df.iterrows():
        # TODO Quick and dirty way to cleanup data in priority fields for now

        if chief_complaint is not None:
            field = (row['FIELD'].replace('{Chief Complaint}', chief_complaint)
                     .replace('{chief complaint}', chief_complaint)
                     .replace('{}', chief_complaint)
                     .replace('{ }', chief_complaint)
                     )
        else:
            field = row['FIELD']

        fields[field] = {
            k: v.replace('{Chief Complaint}', chief_complaint)
            .replace('{chief complaint}', chief_complaint)
            .replace('{}', chief_complaint)
            .replace('{ }', chief_complaint)

            if isinstance(v, str) and chief_complaint is not None else v

            for k, v in row.items() if pd.notna(v) and
            k not in ['FIELD', 'MIN POINTS', 'CONFIDENCE INTERVAL',
                      'SPECIALITY/DXGROUP']
        }

    min_points = df['MIN POINTS'].iloc[0]
    confidence_interval = df['CONFIDENCE INTERVAL'].iloc[0]
    # rest of the rows should be nan
    assert df['MIN POINTS'].iloc[1:].isnull(
    ).values.all(), "Invalid priority_fields.csv"
    assert df['CONFIDENCE INTERVAL'].iloc[1:].isnull(
    ).values.all(), "Invalid priority_fields.csv"
    return fields, int(min_points), int(confidence_interval)


def check_function_call(response: BaseMessage, tools: list[BaseTool]) -> Union[
        tuple[FunctionMessage, dict], tuple[None, None]]:
    """
    Function returns a tuple of FunctionMessage and arguments
    """
    # Create a dictionary of tools
    tool_dict = {tool.name: tool for tool in tools}

    # Check if a function call is present in the response
    function_call = response.additional_kwargs.get("function_call")
    if function_call is not None:
        # Find the tool
        tool_to_run = tool_dict.get(function_call.get('name'))
        logging.debug(f'Running tool: {tool_to_run.name}')

        # Loading arguments
        arguments: dict = json.loads(function_call.get('arguments'))
        logging.debug(f'Arguments: {arguments}')

        tool_result = tool_to_run.run(arguments)
        logging.debug(f'Tool results: {tool_result}')

        return FunctionMessage(
            name=function_call.get('name'), content=tool_result), arguments
    else:
        return None, None


def parse_feedback_rating(human_input) -> str | None:
    try:
        rating = int(round(float(human_input)))

        if rating > 5:
            logging.info(f"Rating {rating} is greater than 5. Adjusting to 5.")
            rating = 5

        return rating
    except ValueError:
        logging.warning(
            f"Could not parse {human_input} as a number. Skipping feedback rating.")
        return None


def process_nav_input(human_input: str, options: str, state: BotState):
    # Attempt to parse the last human input as a number
    try:
        return int(human_input)
    except ValueError:
        pass  # continue to process the input
    return parse_nav_via_llm(human_input, options, state)


def parse_nav_via_llm(human_input: str, options: str, state: BotState):
    system_prompt = """
User has been presented with some options.

Based on the user's input, respond with which option number they have selected. Only respond with the number.
Try to match the user input to the options as closely as possible.
If you are not able to understand the user's input based on option, respond with the option number as 0.

Your output should be a JSON with the following keys:
- option_number: int (The option number selected by the user.)

EXAMPLE:
OPTIONS:
1. Let’s discuss your Top 3 Condition List
2. Let’s take a look at Treatments.
3. Other options.
USER INPUT: lets discuss
OUTPUT:
{
"option_number": 1
}"""
    content = f"""
OPTIONS:
{options}
USER INPUT: {human_input}"""
    llm = CustomChatOpenAI(state=state)
    conv_hist = [SystemMessage(content=system_prompt),
                 AIMessage(content=content)]
    kwarg_args = {"response_format": {"type": "json_object"}}
    response = llm(conv_hist, seed=0, **kwarg_args).content
    try:
        response: dict = json.loads(response)
        response_number = response.get('option_number', 0)
    except json.JSONDecodeError:
        return 0
    try:
        number = int(response_number)
        return number
    except ValueError:
        return 0
