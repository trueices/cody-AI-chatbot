import logging
import re
import csv

from src.utils import MongoDBClient

logging.getLogger().setLevel(logging.INFO)

dry_run = True
generate_exception_csv = False

csv_file_path = "exceptions.csv"


def init():
    # conv_hist.diagnosis_agent is array and need to check if it has elements
    created_date_regex = '2023'

    query = {'created': {'$regex': created_date_regex},
             'conv_hist.diagnosis_agent': {'$exists': True, '$ne': []},
             'diagnosis_list': {'$exists': False}
             }

    documents = MongoDBClient.get_botstate().count_documents(query)

    logging.info("Total documents to be processed: ", documents)

    find_all = MongoDBClient.get_botstate().find(query)

    counter = 0

    if generate_exception_csv:
        # Open and wipe the file
        with open(csv_file_path, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Created Date", "Convo ID", "Reason"])

    for record in find_all:

        agent_ = record.get('conv_hist').get('diagnosis_agent')
        for message in agent_:
            counter += 1
            if message.get('role') == 'assistant':
                if message:
                    if (not message.get('content').startswith('Based on what you') and
                            not message.get('content').startswith('Based on the information') and
                            not message.get('content').startswith('Based on the symptoms')):
                        logging.info("Skipping as this does not looks like diagnosis response for id: "
                              + record.get('username') + " message: " + message.get('content'))

                        write_exception(
                            message, record, "Does not look like diagnosis response")
                    else:
                        diagnosis_list = re.findall(r'\d+\.\s(.*?)(?=\s\(\d+% probability\)|\Z)',
                                                    message.get('content'))

                        if not diagnosis_list:
                            logging.info("Diagnosis list is empty for conversation ID: " + record.get('username') +
                                  ". Check if regex needs to be updated. Diag: " + message.get('content'))
                            write_exception(message, record,
                                            "Does not match regex")
                        else:
                            diag_list = [diag.strip().upper()
                                         for diag in diagnosis_list]
                            if dry_run:
                                logging.info(
                                    str(counter) + " Diagnosis list for  ID: " + record.get('username') + " is " + str(
                                        diag_list))
                            else:
                                logging.info(str(counter) + ' Updating ID: ' + record.get('username') + ' with ' + str(
                                    diag_list))

                                MongoDBClient.get_botstate().update_one({'_id': record.get('_id')},
                                                                        {'$set': {'diagnosis_list': diag_list}})

                break


def write_exception(message, record, reason):
    if generate_exception_csv:
        with open(csv_file_path, 'a', newline='') as file:
            writer = csv.writer(file)

            writer.writerow([record.get('created'), record.get('username'),
                             reason])


init()
