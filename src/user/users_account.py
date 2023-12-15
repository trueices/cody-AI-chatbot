import datetime

from src.utils import MongoDBClient


# This is a temporary interface to interact with user account and sessions.
# Any interaction to get user or session data should be done via this class.
# This is so that we have clear boundary for now and have possibility to replace this with api later

def find_user_session(session_id: str):
    return MongoDBClient.get_sessions().find_one({'ai_session': session_id})


def is_verified_user(user_id: str):
    user_ = MongoDBClient.get_users().find_one({'email': user_id})

    if user_:
        return user_.get('verified', {}).get('value', False)


def update_user_verified(user_id: str):
    MongoDBClient.get_users().update_one({'email': user_id},
                                         {'$set': {'verified': {'value': True, 'autofilled': True}}})


def find_user(user_id: str):
    return MongoDBClient.get_users().find_one({'email': user_id})


def update_user_ehr_id(user_id: str, ehr_id: str):
    MongoDBClient.get_users().update_one({'email': user_id},
                                         {'$set': {
                                             'ehr_id': ehr_id,
                                             'updated_at': datetime.datetime.now()
                                         }})
