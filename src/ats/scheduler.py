from src.ats.runner import ats_run
from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup
from src.utils import MongoDBClient
from src.agents.utils import get_supported_sps
import logging

def run_ats_on_recent_convs():
    # Get recent conversations from collection
    convs = MongoDBClient.get_botstate().find(
        {"conv_hist.magic_minute_agent": {"$exists": True, "$ne": []},
         "priority_fields_asked": {"$exists": True, "$ne": []}}
    ).sort(
        "created", -1
    ).limit(5)

    for data in convs:
        # If ATS has already been run on this conversation, stop the operation.
        if MongoDBClient.get_ats().find_one({"username": data["username"]}):
            logging.info(
                f'ATS has already been run on {data["username"]}. Hence, skipping the process.')
            return

        logging.info(f'Running ATS on {data["username"]}')
        sp = Specialist.from_inventory_name(data['specialist'])
        subsp = SubSpecialtyDxGroup.from_inventory_name(data['subSpecialty'])

        # Magic Minute conversation
        summary = data["conv_hist"]["magic_minute_agent"][0]['content']

        if sp not in get_supported_sps() and subsp not in get_supported_sps():
            logging.warning(
                f'Unsupported specialist {sp} or sub-specialist {subsp}')
            continue

        score, unfilled_fields, args = ats_run(sp, subsp, summary)
        ats_data = {
            "score": score,
            "unfilled_fields": unfilled_fields,
            "args": args,
            "date": data["created"][:10],
            "specialist": data["specialist"],
            "subSpecialty": data["subSpecialty"],
            "dxg_version": data["dxg_version"]
        }
        MongoDBClient.get_ats().update_one(filter={'username': data['username']},
                                           update={'$set': ats_data},
                                           upsert=True)