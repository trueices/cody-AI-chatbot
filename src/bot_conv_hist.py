"""
To be used for keeping track of the conversation history visible to the user.
"""

from typing import List
from pydantic import BaseModel
import logging
from src.utils import MongoDBClient

class BotConvHist(BaseModel):
    conversation_id: str = None
    full_conv_hist: List[dict] = []

    class Config:
        validate_assignment = True
        extra = 'allow'

    # initialize from a username parameter
    def __init__(self, conversation_id: str):
        super().__init__()
        self.conversation_id = conversation_id
        data: dict = MongoDBClient.get_full_conv_hist().find_one(
            {'conversation_id': conversation_id})

        # Only if you have data in the database, load it.
        if data is not None:
            for key, value in data.items():
                if key == '_id':
                    continue
                setattr(self, key, value)

    def append_token(self, token: str) -> None:
        if len(self.full_conv_hist) == 0 or self.full_conv_hist[-1]['role'] == 'user':
            self.full_conv_hist.append({'role': 'assistant', 'content': token})
        else:
            self.full_conv_hist[-1]['content'] += token

    def upsert_to_db(self):
        data_dict: dict = self.dict(by_alias=True)

        logging.debug(f'Upserting to database..')
        # Inserting or updating the data to the database
        MongoDBClient.get_full_conv_hist().update_one(
            filter={'conversation_id': self.conversation_id},
            update={'$set': data_dict},
            upsert=True)
