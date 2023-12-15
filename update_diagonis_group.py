import csv
import logging
from datetime import datetime

from src.agents import DiagnosisAgent
from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup
from src.utils import MongoDBClient

logging.getLogger().setLevel(logging.INFO)


dry_run = True
generate_exception_csv = True

csv_file_path = "exceptions.csv"

dx_group_dict = {}


def init_dx_mapping():
    with open('CodyMD Medical Terminology _ Taxonomy - DxGroupsV2.csv', 'r') as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            key = row['Diagnosis']
            if key in dx_group_dict:
                logging.info("Duplicate key found: " + key + " with value " + row['DxGroup'] + " and " + row['Specialist'])
                pass
            dx_group_dict[key] = {'dx_group': row['DxGroup'], 'specialist': row['Specialist']}


init_dx_mapping()


def init():
    # conv_hist.diagnosis_agent is array and need to check if it has elements
    collection = MongoDBClient.get_botstate()
    created_date_regex = '2023-10'

    query = {'created': {'$regex': created_date_regex},
             'conv_hist.diagnosis_agent': {'$exists': True, '$ne': []},
             'diagnosis_list': {'$exists': True, '$ne': []},
             #'dx_group_list': {'$exists': False}
             }

    documents = collection.count_documents(query)

    logging.info("Total documents to be processed: ", documents)

    find_all = collection.find(query)

    counter = 0

    if generate_exception_csv:
        # Open and wipe the file
        with open(csv_file_path, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Created Date", "Convo ID", "Reason"])

    for record in find_all:

        diag_list = record.get('diagnosis_list')
        dx_group_set: set[SubSpecialtyDxGroup] = set()
        for diag in diag_list:
            counter += 1
            if diag:
                diag_group = dx_group_dict.get(diag)

                if not diag_group:
                    logging.info(
                        str(counter) + " Applying rules, Diagnosis group not found for diagnosis: " + diag + " conversation ID: " + record.get(
                            'username'))

                    dx_group = DiagnosisAgent.dx_grouper_rules(record.get(
                        'username'), diag, Specialist.from_inventory_name(record.get('specialist')))

                    if dx_group is None:
                        logging.info(str(counter) + " Rule applied still unable to map Diagnosis group for diagnosis: " + diag + " conversation ID: "
                              + record.get('username'))

                        if generate_exception_csv:
                            write_exception(diag, record, "Diagnosis group not found")
                    else:
                        if generate_exception_csv:
                            write_exception(diag, record, "Mapped via rules")

                    if not dry_run:
                        if dx_group is None:
                            MongoDBClient.get_dx_mapping_errors().insert_one({'diagnosis': diag,
                                                                              'conversation_id': record.get(
                                                                                  'username'),
                                                                              'reason': 'Diagnosis group not found',
                                                                              'created': datetime.now().isoformat()})
                        else:
                            dx_group_set.add(dx_group)
                else:
                    group_ = diag_group.get('dx_group')

                    if group_ == 'Generalist':
                        group_ = 'general'

                    dx_group = SubSpecialtyDxGroup.from_inventory_name_no_default(group_.strip())

                    if dx_group is None:
                        logging.info(str(counter) + " Diagnosis group not found for diagnosis: " + diag + " conversation ID: "
                              + record.get('username') + " Possible bug in mapping code. Record to be created "
                              + group_ + " with " + diag_group.get('specialist'))
                        if generate_exception_csv:
                            write_exception(diag, record, "Diagnosis group not found while mapping to code")

                        if not dry_run:
                            MongoDBClient.get_dx_mapping_errors().insert_one({'diagnosis': diag,
                                                                               'conversation_id': record.get(
                                                                                   'username'),
                                                                               'reason': 'Bug in mapping code. '
                                                                                         'SubSpecialtyDxGroup missing '
                                                                                         'for ' + group_ + " with " +
                                                                                         diag_group.get('specialist'),
                                                                               'created': datetime.now().isoformat()})

                    else:
                        dx_group_set.add(dx_group)

        if dry_run:
            logging.info(str(counter) + " Diagnosis list for  ID: " + record.get('username') + " is " + str(dx_group_set))
        else:
            collection.update_one({'username': record.get('username')},
                                  {'$set': {'dx_group_list': [dx_group.inventory_name for dx_group in dx_group_set],
                                            'dx_specialist_list': [dx_group.specialist.inventory_name for dx_group in
                                                                   dx_group_set]}})


def write_exception(message, record, reason):
    if generate_exception_csv:
        with open(csv_file_path, 'a', newline='') as file:
            writer = csv.writer(file)

            writer.writerow([record.get('created'), record.get('username'),
                             reason])


init()
