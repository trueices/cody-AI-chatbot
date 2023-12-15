import atexit
import logging

from src.followup.followup_care import FollowupCare
from src.followup.followup_care_state import FollowUpCareState
from src.notifications.email_sender import EmailSender, FollowUpEmailParameters
from src.utils import MongoDBClient

email_sender = EmailSender()


def process_followup_care():
    logging.info("Processing followup care.")

    for _ in range(50):
        followup_convo = FollowupCare.eligible_convo_with_lock()

        if followup_convo is None:
            logging.info("No more followup care to process. Exiting.")
            break

        logging.info(f"Processing followup care for {followup_convo.convo_id}")

        email_params = FollowUpEmailParameters(followup_convo.name, followup_convo.convo_id, followup_convo.email_address)
        email_sender.send_followup_email(email_params)

        logging.info(f"Sent followup email to {followup_convo.email_address} for {followup_convo.convo_id}. "
                     f"Released lock.")

        FollowupCare.release_lock_update_state(followup_convo)


def send_test_email(convo_id: str):
    state = FollowUpCareState(convo_id=convo_id)

    if state.user_id is None:
        logging.error(f"Invalid convo_id {convo_id} provided for test email.")
        return

    email_params = FollowUpEmailParameters(state.name, state.convo_id, state.email_address)
    email_sender.send_followup_email(email_params)


def release_followup_care_locks():
    # Not logging as logger might have been shut down by the time this function is called.
    print("Application is shutting down. Releasing followup care locks.")
    # release locks on the records which were locked 24 hours ago.
    update_many = MongoDBClient.get_followup_care().update_many({'is_locked': True, },
                                                                {'$set': {'is_locked': False}})

    print(f"Released {update_many.modified_count} followup care locks.")


atexit.register(release_followup_care_locks)
