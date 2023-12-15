import logging
import os
import re
from datetime import datetime
from typing import Tuple

import us

from src.agents.cody_care_questionnaires import get_questionaire
from src.bot_state import BotState
from src.notifications.email_sender import EmailSender, CodyCareCertifiedPlanEmailParameters, \
    TaskAssignedHcpEmailParameters
from src.rx.doctor_service_state import DoctorServiceOfferEvent, DoctorServiceOfferState
from src.rx.ehr_service import EhrService
from src.user.users_account import find_user, update_user_ehr_id
from src.utils import MongoDBClient, base_url


class DoctorService:
    CONVO_DESCRIPTION_TEMPLATE = """
Conversation ID: {convo_id}
<br>
<br>
Chief Complaint: {chief_complaint}
<br>
<br>
Top 3 Diagnoses: {top_3_diagnoses}
<br>
<br>
"""

    HELP_TEXT = f"""<b>Prescriptions:</b> If medications were prescribed, please connect with your preferred pharmacy to arrange payment and pickup/delivery.

<b>Tests</b>: If tests were ordered or recommended, please connect with the laboratory to arrange your testing.

<b>Referrals:</b>  If referrals were ordered, please schedule your referrals.

<b>Follow-up:</b> We will follow up with you in 24 hours and then in a few says. Please respond and let us know how you are doing.

<b>Support:</b> You have 7 days of support. Check out <a class="text-blue underline app-link" href="{base_url()}help" target="_blank">cody.md/help</a> or email <a class="text-blue underline" href="mailto:help@cody.md">help@cody.md</a>.

<b>Cody is not for emergencies.</b> If you are having an emergency, call 911 or go to your Emergency Room."""

    @staticmethod
    def create_offer() -> str:
        """
        Create an offer for the doctor service.
        """
        # Generate random 50 character string
        import random
        import string
        offer_id = ''.join(random.choices(
            string.ascii_uppercase + string.digits, k=50))
        return offer_id

    @staticmethod
    def capture(offer_id: str,
                convo_id: str,
                user_id: str,
                event: DoctorServiceOfferEvent, event_data: dict):
        """
        Capture the doctor service event.
        """

        doctor_service_state = DoctorServiceOfferState()
        doctor_service_state.offer_id = offer_id
        doctor_service_state.user_id = user_id
        doctor_service_state.event = event
        doctor_service_state.convo_id = convo_id

        # Event data needs to be stored in the separate fields
        doctor_service_state.populate_fields(event_data)

        doctor_service_state.insert_to_db()

    @staticmethod
    def latest_event(convo_id: str) -> DoctorServiceOfferState:
        """
        Returns the latest doctor service event for a user, if it exists.
        """

        latest_offer = MongoDBClient.get_doctor_service_offer().find_one(
            {'convo_id': convo_id}, sort=[('created', -1)])

        return DoctorServiceOfferState().populate_fields(latest_offer) if latest_offer else DoctorServiceOfferState()

    @staticmethod
    def latest_event_by_offer(offer_id: str) -> DoctorServiceOfferState:
        """
        Returns the latest doctor service event for a user, if it exists.
        """

        latest_offer = MongoDBClient.get_doctor_service_offer().find_one(
            {'offer_id': offer_id}, sort=[('created', -1)])

        return DoctorServiceOfferState().populate_fields(latest_offer) if latest_offer else DoctorServiceOfferState()

    @staticmethod
    def event_of_type(offer_id: str, event: DoctorServiceOfferEvent) -> DoctorServiceOfferState:
        """
        Returns the latest doctor service event for a user, if it exists.
        """

        latest_offer = MongoDBClient.get_doctor_service_offer().find_one(
            {'offer_id': offer_id, 'event': event.inventory_name}, sort=[('created', -1)])

        return DoctorServiceOfferState().populate_fields(latest_offer) if latest_offer else DoctorServiceOfferState()

    @staticmethod
    def payment_verification_status(convo_id: str, current_agent_name: str) -> Tuple[bool, bool, str]:
        """
        check if conversation is eligible for payment and verification.
        """

        if current_agent_name != 'cody_care_agent':
            return False, False, None

        service = DoctorService.latest_event(convo_id)

        # TODO May be more condition will come inn.
        if service.event == DoctorServiceOfferEvent.OFFER_ACCEPTED:
            return True, False, service.offer_id

        if service.event in [DoctorServiceOfferEvent.VERIFY_USER, DoctorServiceOfferEvent.USER_VERIFICATION_FAILED]:
            return False, True, service.offer_id

        return False, False, None

    @staticmethod
    def update_event_details(offer_id: str, event: DoctorServiceOfferEvent, event_data: dict):
        """
        Ability to update the event details on the existing event.
        This method will be used to update the event details like payment, pharmacy, etc. as conversation progresses on the same event.
        For example, when capturing state, questionnaires, etc.

        Its being hardened to make sure only valid fields are updated and nothing else is possible to update.
        """
        latest_offer = MongoDBClient.get_doctor_service_offer().find_one(
            {'offer_id': offer_id}, sort=[('created', -1)])

        if latest_offer and latest_offer['event'] != event.inventory_name:
            raise Exception(
                f"Cannot update event details for {event.inventory_name} as latest event is {latest_offer['event']}. Only latest event can be updated.")

        # Checking if event data fields are valid and supported in the DoctorServiceOfferState
        doctor_service_state = DoctorServiceOfferState()
        doctor_service_state.populate_fields(event_data)

        update_record = event_data.copy()
        update_record['updated'] = datetime.now()

        MongoDBClient.get_doctor_service_offer().update_one({'offer_id': offer_id, 'event': event.inventory_name},
                                                            {'$set': update_record},
                                                            upsert=True)

    @staticmethod
    def process_for_ehr(offer_id):
        """
        This method will be responsible for sending the prescription to the EHR.
        Gathering info from different events and bot state.
        :param offer_id: The ID of the offer.
        :return: None
        """
        try:
            ehr_service = EhrService()

            offer_events = DoctorService._all_events_on_offer(offer_id)

            user_ = find_user(offer_events[0].user_id)

            convo_state = BotState(username=offer_events[0].convo_id)

            onboarding_event = DoctorServiceOfferState()
            state_event = DoctorServiceOfferState()
            hcp_match_event = DoctorServiceOfferState()

            # Find the relevant events
            for event in offer_events:
                if event.event == DoctorServiceOfferEvent.ONBOARDING_QUESTIONNAIRE_CAPTURE:
                    onboarding_event = event
                elif event.event == DoctorServiceOfferEvent.CAPTURE_STATE:
                    state_event = event
                elif event.event == DoctorServiceOfferEvent.HCP_MATCH:
                    hcp_match_event = event

            # Generate the description for the prescription
            desc = DoctorService.CONVO_DESCRIPTION_TEMPLATE.format(convo_id=convo_state.username,
                                                                   chief_complaint=convo_state.chief_complaint,
                                                                   top_3_diagnoses=', '.join(
                                                                       convo_state.diagnosis_list))

            patient_phone_number = ''
            patient_sex_at_birth = ''
            patient_dob = ''

            # Extract relevant information from the onboarding questionnaire
            for question in onboarding_event.questionnaire:
                if question['id'] == 'DOB':
                    desc = desc + \
                           'DOB: {dob}<br><br>'.format(dob=question['llm_response'])
                    patient_dob = question['llm_response']
                elif question['id'] == 'GENDER':
                    desc = desc + \
                           'Gender: {gender}<br><br>'.format(
                               gender=question['response'])
                elif question['id'] == 'MEDICATIONS':
                    desc = desc + \
                           'Medications: {medications}<br><br>'.format(
                               medications=question['response'])
                elif question['id'] == 'MEDICAL_CONDITIONS':
                    desc = desc + \
                           'Medical History: {medical_history}<br><br>'.format(
                               medical_history=question['response'])
                elif question['id'] == 'ALLERGIES':
                    desc = desc + 'Allergies: {allergies}<br><br>'.format(
                        allergies=question['response'])
                elif question['id'] == 'PHONE':
                    patient_phone_number = question['formatted_response']
                elif question['id'] == 'PHARMACY':
                    desc = desc + \
                           'Pharmacy: {pharmacy}<br><br>'.format(
                               pharmacy=question['response'])
                elif question['id'] == 'SEX_AT_BIRTH':

                    mapping = {
                        1: 'female',
                        2: 'male',
                        3: 'other',
                        4: 'unknown'
                    }

                    patient_sex_at_birth = mapping.get(
                        question.get('llm_response', 4))

            desc = desc + 'Magic Minutes: {magic_minutes}<br><br>'.format(
                magic_minutes=convo_state.conv_hist['magic_minute_agent'][-1].content)

            # Create the patient in the EHR if necessary
            if user_ and not user_.get('ehr_id'):
                patient_details = {'first_name': user_.get('firstName', {}).get('value'),
                                   'last_name': user_.get('lastName', {}).get('value'), 'email': user_['email'],
                                   'sex': patient_sex_at_birth}

                if patient_phone_number:
                    patient_details['primary_phone_number'] = patient_phone_number
                    patient_details['primary_phone_type'] = 'mobile'

                if patient_dob:
                    # change date_of_birth from format '11/16/2000' to '2000-11-16'
                    patient_details['date_of_birth'] = datetime.strptime(
                        patient_dob, '%m/%d/%Y').strftime('%Y-%m-%d')

                if state_event and state_event.state:
                    patient_details['appointment_state'] = us.states.lookup(
                        state_event.state).abbr

                    # Since we don't know this, its necessary to make patient e-prescribing ready in Akute
                    patient_details['address_line_1'] = 'NA'
                    patient_details['address_city'] = 'NA'
                    patient_details['address_state'] = patient_details['appointment_state']
                    patient_details['address_zipcode'] = '99999'

                ehr_patient = ehr_service.create_patient(patient_details)

                if ehr_patient.get('statusCode') == 201:
                    ehr_id = ehr_patient['data']['id']
                    update_user_ehr_id(user_['email'], ehr_id)
                    user_['ehr_id'] = ehr_id

                if user_.get('ehr_id') is None:
                    logging.error(
                        'Failed to create patient in EHR, response: {}'.format(ehr_patient))
                    raise Exception(
                        'Failed to create patient in EHR, response: {}'.format(ehr_patient))

            task_payload = {
                'patient_id': user_['ehr_id'],
                'task': f"Pending Visit: {convo_state.chief_complaint}",
                'description': desc,
                'priority': 'p2',
                'status': 'not-started'
            }

            if hcp_match_event.hcp and hcp_match_event.hcp.get('id'):
                task_payload['owner_id'] = hcp_match_event.hcp['id']

            task_ = ehr_service.create_task(task_payload)

            if task_.get('statusCode') == 201:
                DoctorService.capture(offer_id, offer_events[0].convo_id, offer_events[0].user_id,
                                      DoctorServiceOfferEvent.EHR_SENT, {
                                          'ehr_task_id': task_['data']['id']
                                      })

                EmailSender().send_task_assigned_hcp(
                    TaskAssignedHcpEmailParameters(
                        name=hcp_match_event.hcp['name'],
                        email_address=hcp_match_event.hcp['email'],
                        task_id=task_['data']['id']
                    )
                )

                # TODO temporary sending to admin emails configured in env
                admin_emails = os.getenv('ADMIN_EMAILS').split(',') if os.getenv('ADMIN_EMAILS') else []

                for email in admin_emails:
                    EmailSender().send_task_assigned_hcp(
                        TaskAssignedHcpEmailParameters(
                            name=email,
                            email_address=email,
                            task_id=task_['data']['id']
                        )
                    )

            else:
                logging.error(
                    'Failed to create task in EHR, response: {}'.format(task_))
                raise Exception(
                    'Failed to create task in EHR, response: {}'.format(task_))
        except Exception as e:
            logging.error(
                f'Error processing for EHR for offer_id: {offer_id}. Error: {e}', exc_info=e)
            raise e

    @staticmethod
    def _all_events_on_offer(offer_id):
        records_ = MongoDBClient.get_doctor_service_offer().find(
            {'offer_id': offer_id})
        offer_events = []
        for record in records_:
            event_ = DoctorServiceOfferState().populate_fields(record)
            offer_events.append(event_)
        return offer_events

    @staticmethod
    def process_for_certified_plan(offer_id: str):
        try:
            event_of_type = DoctorService.event_of_type(
                offer_id, DoctorServiceOfferEvent.EHR_TASK_DONE)

            if not event_of_type.user_id:
                logging.info(
                    f'No event with EHR_TASK_DONE found for offer_id: {offer_id}. Skipping processing!')
                return

            plan = EhrService().get_plan(patient_id=event_of_type.ehr_task.get('patient_id'),
                                         start_date=event_of_type.ehr_task.get('date_created')[:10])

            # Remove extra new lines to avoid multiple bubbles
            plan = re.sub('\n{3,}', '\n\n', plan)

            # Need to update current agent to CodyCareAgent in case user had interacted with other agents.
            from src.bot import Bot
            bot = Bot(username=event_of_type.convo_id)
            from src import agents
            plan = f"{bot.state.patient_name}, your Doctor completed your 🩺Certified Plan.\n\nPlease review your 🩺Certified Plan and Approve it below.\n\n\n" + plan

            questionnaire = get_questionaire('plan_acknowledgement')

            bot.full_conv_hist.append_token('\n\n\n' +
                                            plan + '\n\n\n' +
                                            DoctorService.HELP_TEXT + '\n\n\n' +
                                            questionnaire[0]['question'])

            bot.state.next_agent(name=agents.CodyCareAgent.name)
            bot.update_conv()

            EmailSender().send_cody_care_plan_ready(CodyCareCertifiedPlanEmailParameters(
                name=bot.state.patient_name,
                email_address=event_of_type.user_id,
                convo_id=event_of_type.convo_id))

            questionnaire[0]['presented'] = True

            DoctorService.capture(event_of_type.offer_id, event_of_type.convo_id, event_of_type.user_id,
                                  DoctorServiceOfferEvent.EHR_PLAN_READY,
                                  {
                                      'questionnaire': questionnaire
                                  })

        except Exception as e:
            logging.error(f"Error processing for certified plan for offer_id: {offer_id}. Error: {e}", exc_info=e)
            raise e

    @staticmethod
    def get_event_for_task_id(task_id) -> DoctorServiceOfferState | None:
        """
        Get the event for the given task id.
        """
        records = MongoDBClient.get_doctor_service_offer().find({'ehr_task_id': task_id,
                                                                 'event': DoctorServiceOfferEvent.EHR_SENT.inventory_name})
        try:
            return DoctorServiceOfferState().populate_fields(records[0])
        except IndexError:
            # Record not found, meaning task id is not associated with any event.
            return None
