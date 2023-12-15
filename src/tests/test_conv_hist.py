from src.utils import MongoDBClient
from src.bot import Bot
from src.tests.utils import setup, load_mogo_records

def test_initial(setup):
    bot = Bot(username='test')

    # Check if the conv history has the initial message
    assert len(bot.get_conv_hist()) == 1
    assert len(bot.state.get_conv_hist()) == 1
    assert len(bot.full_conv_hist.full_conv_hist) == 1

    # The initial message shouldnt be written to the db
    assert MongoDBClient.get_botstate().count_documents({}) == 0
    assert MongoDBClient.get_full_conv_hist().count_documents({}) == 0

def test_full_conv_missing_compatability(setup):
    # To check cases when botstate conv history is populated but full_conv_hist is not.
    # This is the case for old botstate documents.

    load_mogo_records('test_apis/test_data/diagnosis/collection.json')
    username = MongoDBClient.get_botstate().find_one({})['username']
    # Making sure the initial conditions of the database are maintained.
    assert MongoDBClient.get_botstate().count_documents({}) == 1
    assert MongoDBClient.get_full_conv_hist().count_documents({}) == 0

    # This call should automatically populate the empty full_conv_hist in db.
    Bot(username=username)

    # Database check to see if full_conv_hist is populated.
    assert MongoDBClient.get_botstate().count_documents({}) == 1
    assert MongoDBClient.get_full_conv_hist().count_documents({}) == 1

def test_full_conv_present_compatability(setup):
    # To check if the database records are tampered on a normal init call.
    load_mogo_records('test_apis/test_data/diagnosis/collection.json', 
                      'test_apis/test_data/diagnosis/full_convo_history.json')
    username = MongoDBClient.get_botstate().find_one({})['username']
    # Making sure the initial conditions of the database are maintained.
    assert MongoDBClient.get_botstate().count_documents({}) == 1
    assert MongoDBClient.get_full_conv_hist().count_documents({}) == 1
    botstate = MongoDBClient.get_botstate().find_one({})
    full_conv_hist = MongoDBClient.get_full_conv_hist().find_one({})

    # Making the init call. Database should not be tampered since full_conv_hist is already present.
    Bot(username=username)

    # Now, let's check if the database was tampered.
    assert botstate == MongoDBClient.get_botstate().find_one({})
    assert full_conv_hist == MongoDBClient.get_full_conv_hist().find_one({})
