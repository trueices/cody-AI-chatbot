import logging

from src.utils import MongoDBClient

logging.getLogger().setLevel(logging.INFO)

dry_run = True


def init():
    # conv_hist.diagnosis_agent is array and need to check if it has elements

    query = {'conv_hist.feedback_agent': {'$exists': True, '$ne': [], '$not': {'$size': 1}},
             'feedback_rating': {'$exists': False},
             }

    documents = MongoDBClient.get_botstate().count_documents(query)

    logging.info("Total documents to be processed: ", documents)

    find_all = MongoDBClient.get_botstate().find(query)

    for record in find_all:

        agent_ = record.get('conv_hist').get('feedback_agent')
        for message in agent_:
            # find first human message
            if message.get('role') == 'user':
                logging.info("Human response for conversation ID: " + record.get('username') + " is: " + message.get(
                    'content'))

                try:
                    rating = int(round(float(message.get('content'))))

                    if rating > 5:
                        logging.info(
                            f"Rating {rating} is greater than 5. Adjusting to 5.")
                        rating = 5

                    record['feedback_rating'] = rating

                    if not dry_run:
                        logging.info("Updating feedback rating to " + str(rating) + " for conversation ID: " + record.get(
                            'username'))

                        MongoDBClient.get_botstate().update_one({'_id': record.get('_id')},
                                                                {'$set': {'feedback_rating': rating}})
                    else:
                        logging.info("DRY RUN: feedback rating to " + str(rating) + " for conversation ID: " + record.get(
                            'username'))

                except ValueError:
                    logging.info(
                        f"Could not parse {message.get('content')} as a number. Skipping feedback rating.")


init()
