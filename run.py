from src.bot import Bot
from src.utils import MongoDBClient
import logging
from application import application # Loads the application level env variables

logging.getLogger().setLevel(logging.INFO)

MongoDBClient.get_botstate().delete_one({'username': 'test'})
MongoDBClient.get_full_conv_hist().delete_one({'conversation_id': 'test'})

def init():
    bot = Bot(username='test')
    for conv in bot.get_conv_hist():
        logging.info(conv)
init()

while True:
    bot = Bot(username='test')
    user_input = input('User Input:')
    for i, token in enumerate(bot.ask(user_input)):
        print(token, end='', flush=True)
    print()