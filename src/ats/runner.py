from langchain.schema import HumanMessage, SystemMessage
import json
import logging
from src.bot_state import BotState
from src.bot_stream_llm import CustomChatOpenAI
from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup
from src.agents.utils import load_priority_fields
from difflib import SequenceMatcher

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

def get_most_similar_field_value(field: str, args: dict[str, str]) -> str:
    # get the most similar field
    most_similar_field = max(args.keys(), key=lambda x: similar(x, field))
    similarity = similar(most_similar_field, field)

    if similarity < 0.5:
        logging.warning(f'Field "{field}" is not present in args. Most similar field is "{most_similar_field}"')
        return 'none'
    elif similarity < 1:
        logging.info(f'Field "{field}" and "{most_similar_field}" are similar. Similarity score: {similarity}')
    # get the value of the most similar field
    return args[most_similar_field]


def field_completion_score(args: dict[str, str], fields: dict[str, str]):
    if len(args) != len(fields):
        logging.warning(f'Number of fields in args ({len(args)}) does not match number of fields in fields ({len(fields)})')
    score = 0
    total = 0

    # convert keys to lowercase for comparison
    args = {key.lower(): value for key, value in args.items()}
    fields = {key.lower(): value for key, value in fields.items()}

    unfilled_fields = []
    
    for field, attributes in fields.items():
        POINT = attributes['FILL SCORE']
        
        value = get_most_similar_field_value(field, args).lower()
        if value not in ['none', 'unknown', '', 'n/a', 'none mentioned', 'not mentioned']:
            score += POINT
        else:
            unfilled_fields.append(field)
        total += POINT

    return round(score/total*100, 2), unfilled_fields


def ats_run(sp: Specialist, subsp:SubSpecialtyDxGroup, mm_summary: str, bot_state: BotState = None):
        # Load the priority fields
    fields, _, _ = load_priority_fields(sp, subsp)

    prompt = '\n'.join([f'{key}: str|None' for key, _ in fields.items()])
    # Defining system prompt
    system_prompt = f"""
The user has provided a medical transcription of their visit to the doctor. 
Your job is to parse certain fields from a medical transcription.
If the field information is not present, the field value is passed as 'NONE'.

For each field, you should return a string value containing the information in a few words.
If information is not present for a field, return 'None'.
Your output should be a JSON with the following keys: (all keys are required)

{prompt}

TRANSCRIPTION:
{mm_summary}
"""
    llm = CustomChatOpenAI(state=bot_state)
    response = llm([SystemMessage(content=system_prompt), HumanMessage(content=mm_summary)],
                   response_format={"type": "json_object"}).content
    args: dict = json.loads(response)

    score, unfilled_fields = field_completion_score(args, fields)

    return score, unfilled_fields, args