import logging
import os
from datetime import datetime, timedelta

from geopy import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from pydantic import ValidationError

from src.agents import FindCareAgent, EndAgent, FeedbackAgent, TxConversationAgent, TreatmentAgent, \
    DxConversationAgent, DiagnosisAgent, ExistingDiagnosisAgent, QuestionAgent
from src.bot_state import BotState
from src.followup.followup_care_state import FollowUpCareState
from src.user.users_account import find_user_session
from src.utils import MongoDBClient


def _farthest_agent_reached(state) -> str:
    agent_name = state.current_agent_name if state.current_agent_name and state.current_agent_name != '' else state.agent_names[state.current_agent_index],

    if agent_name in [EndAgent.name, FeedbackAgent.name]:
        return agent_name
    elif len(state.conv_hist.get(FindCareAgent.name, [])) > 0 or agent_name == FindCareAgent.name:
        return FindCareAgent.name
    elif len(state.conv_hist.get(TxConversationAgent.name, [])) > 0 or agent_name == TxConversationAgent.name:
        return TxConversationAgent.name
    elif len(state.conv_hist.get(TreatmentAgent.name, [])) > 0 or agent_name == TreatmentAgent.name:
        return TreatmentAgent.name
    elif len(state.conv_hist.get(DxConversationAgent.name, [])) > 0 or agent_name == DxConversationAgent.name:
        return DxConversationAgent.name
    elif len(state.conv_hist.get(DiagnosisAgent.name, [])) > 0 or agent_name == DiagnosisAgent.name:
        return DiagnosisAgent.name
    elif len(state.conv_hist.get(ExistingDiagnosisAgent.name, [])) > 0 or agent_name == ExistingDiagnosisAgent.name:
        return ExistingDiagnosisAgent.name
    elif len(state.conv_hist.get(QuestionAgent.name, [])) > 0 or agent_name == QuestionAgent.name:
        return QuestionAgent.name
    else:
        return agent_name


def process_conversations():
    logging.info('Processing conversations to extract analytics')

    if os.getenv('ENVIRONMENT', 'dev') not in ['staging']:
        logging.info(f'Not processing analytics in {os.getenv("ENVIRONMENT", "dev")} environment.')
        return

    for _ in range(50):
        yesterday = datetime.today() - timedelta(days=1)

        record = MongoDBClient.get_botstate().find_one_and_update(
            filter={
                'analytics_state': {'$ne': 'PROCESSED'},
                'created': {'$lte': yesterday.isoformat()}
            },
            update={'$set': {'analytics_state': 'PROCESSED'}},
            return_document=True)

        if record is None:
            logging.info('No more conversations to process. Exiting.')
            break

        try:
            state = BotState(username=record['username'])
        except ValidationError as e:
            logging.warning(
                f'Error processing conversation {record["username"]}. Probably bot state is not compatible.',
                exc_info=e)
            continue

        # TODO more fields and data to be extracted. This is just a start

        # check if convo belongs to a user session
        user_session = find_user_session(record['username'])

        analytics = {
            'updated': datetime.now().isoformat(),
            'convo_created': state.created,
            'agent_reached': state.current_agent_name if state.current_agent_name and state.current_agent_name != '' else state.agent_names[state.current_agent_index],
            'farthest_agent_reached': _farthest_agent_reached(state),
            'user_id': user_session['userName'] if user_session else '',
            'chief_complaint': state.chief_complaint,
            'find_care_address': state.address,
            'location': state.location,
            'specialist': state.specialist.inventory_name,
            'find_care_used':  any(message.type == 'function' for message in state.conv_hist.get(FindCareAgent.name, [])),
        }

        for i, dx in enumerate(state.diagnosis_list):
            analytics[f'dx_{i + 1}'] = dx

        care_state = FollowUpCareState(convo_id=state.username)

        if care_state.last_followup_outcome:
            analytics['last_followup_outcome'] = care_state.last_followup_outcome

        if state.location:
            city, state, country, country_code = get_location_by_coordinates(state.location['coordinates'][1],
                                                                             state.location['coordinates'][0])
            analytics['city'] = city
            analytics['state'] = state
            analytics['country'] = country
            analytics['country_code'] = country_code.upper()

        MongoDBClient.get_convo_analytics().update_one(
            filter={'convo_id': record['username']},
            update={'$set': analytics,
                    '$setOnInsert': {
                        'created': datetime.now().isoformat()
                    }
                    },
            upsert=True)


def get_location_by_coordinates(lat, lon) -> tuple:
    geolocator = Nominatim(user_agent="cody_reverse_geocode")
    geocode = RateLimiter(geolocator.reverse, min_delay_seconds=1)  # adding 1 second padding between calls
    location = geocode([lat, lon])
    address = location.raw['address']
    city = address.get('city', '')
    state = address.get('state', '')
    country = address.get('country', '')
    country_code = address.get('country_code', '')
    return city, state, country, country_code

# process_conversations()
