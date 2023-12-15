import os
import threading

import phonenumbers
import stripe
from langchain.schema import AIMessage

from src import agents
from src.agents.cody_care_questionnaires import get_questionaire
from src.agents.cody_care_utils import CodyCareUtils
from src.agents.utils import process_nav_input
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI
from src.notifications.email_sender import EmailSender, CodyCareConfirmationEmailParameters
from src.rx.doctor_service import DoctorService
from src.rx.doctor_service_state import DoctorServiceOfferEvent
from src.rx.ehr_service import EhrService
from src.user.users_account import is_verified_user
from src.utils import base_url


FORCE_LOGIN_MSG = """I will walk you through the steps to Get Treatment from a Licensed Doctor.

Please <a class="text-blue underline app-link" href="/sign-in">login</a> or <a class="text-blue underline app-link" href="/register">create an account</a> to get treatment now."""


class CodyCareAgent(agents.Agent):
    name = 'cody_care_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None) -> None:
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]
        self.profile = profile

    def act(self) -> bool:
        # check about patient state
        # use llm to convert the patient state to a Code
        # use the code to get the patient state
        # validate via akute if we have a prescriber available for the state
        # if we have a prescriber available, then we can proceed with the prescription

        # Force login
        if self.profile is None or not (self.profile.get('isLoggedIn', False) or self.profile.get('email')):
            self.llm.stream_callback.on_llm_new_token(FORCE_LOGIN_MSG)
            self.conv_hist.append(AIMessage(content=FORCE_LOGIN_MSG))
            return True
        else:
            return self.connect_doctor_service()

    def connect_doctor_service(self) -> bool:
        # For now, we are just making an entry on initial entry, but this will be done based on qualification questions
        latest_state = DoctorService.latest_event(self.state.username)

        if (latest_state.event is None
                # This means user is re entering the agent again after navigating away
                # We should check the latest state and act accordingly
                # For now we are just restarting the entire process
                or len(self.conv_hist) == 0
                or self.conv_hist[-1].content == FORCE_LOGIN_MSG):
            offer_id = DoctorService.create_offer()
            DoctorService.capture(offer_id, self.state.username, self.profile.get('email'),
                                  DoctorServiceOfferEvent.CAPTURE_STATE, {})
            self.conv_hist.append(AIMessage(content='Begin Doctor Service.'))
            self.llm.stream_callback.on_llm_new_token(f"""What state in the U.S. are you in right now?""")
            return True
        elif latest_state.event == DoctorServiceOfferEvent.CAPTURE_STATE:
            if latest_state.state == '' or latest_state.state is None:
                residing_state = CodyCareUtils.attempt_capture_state(
                    self.state, self.state.last_human_input)
                if residing_state == 'not_captured':

                    DoctorService.update_event_details(latest_state.offer_id, DoctorServiceOfferEvent.CAPTURE_STATE,
                                                       {'state_data': {
                                                           'reason': residing_state,
                                                           'input': self.state.last_human_input,
                                                       }})

                    self.llm.stream_callback.on_llm_new_token(
                        "I'm sorry, I didn't get that. Currently, we only support US states. Can you please enter a valid US state?")
                elif residing_state == 'not_supported':
                    DoctorService.update_event_details(latest_state.offer_id, DoctorServiceOfferEvent.CAPTURE_STATE,
                                                       {'state_data': {
                                                              'reason': residing_state,
                                                              'input': self.state.last_human_input,
                                                       }})
                    self.llm.stream_callback.on_llm_new_token(
                        "I'm sorry, we currently do not support the state you entered. We will let you know when we do. In the meantime, please check out our other options.")
                    self.state.next_agent(
                        name=agents.ConciergeAgent.name, reset_hist=True)
                    return False
                else:
                    DoctorService.update_event_details(latest_state.offer_id, DoctorServiceOfferEvent.CAPTURE_STATE,
                                                       {
                                                           'state_data': {},
                                                           'state': residing_state
                                                       })

                    self.llm.stream_callback.on_llm_new_token(CodyCareUtils.confirm_msg.format(
                        residing_state=residing_state, options=CodyCareUtils.options))
                return True
            else:
                response = process_nav_input(
                    self.state.last_human_input, CodyCareUtils.options, self.state)
                if response == 1:
                    DoctorService.update_event_details(latest_state.offer_id, DoctorServiceOfferEvent.CAPTURE_STATE,
                                                       {'state': latest_state.state})
                    self.llm.stream_callback.on_llm_new_token(
                        f"""Good News! We have Doctors ready to care for you in {latest_state.state}.

I am going to ask you some more questions to provide your Doctor with everything they need to get you all better.


""")
                    DoctorService.capture(latest_state.offer_id, self.state.username, self.profile.get(
                        'email'), DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE,
                        {"questionnaire": get_questionaire('ro')})
                    return False
                elif response == 2:
                    # Reset the state and start over.
                    DoctorService.update_event_details(
                        latest_state.offer_id, DoctorServiceOfferEvent.CAPTURE_STATE, {})
                    # Clearing the history
                    self.state.next_agent(
                        name=agents.CodyCareAgent.name, reset_hist=True)
                    return False
                else:
                    self.llm.stream_callback.on_llm_new_token(
                        f"Please enter a valid response.")
                    return True

        elif latest_state.event == DoctorServiceOfferEvent.RO_QUESTIONNAIRE_CAPTURE:
            return_type = self._process_questions(latest_state.offer_id, latest_state.event,
                                                  latest_state.questionnaire)
            if return_type != 'proceed':
                return return_type
            else:
                self.llm.stream_callback.on_llm_new_token(
                    "Ok, we're all set.\n\n\n")
                DoctorService.capture(latest_state.offer_id, self.state.username, self.profile.get(
                    'email'), DoctorServiceOfferEvent.QUESTIONNAIRE_DONE_OFFER_INITIATED, {
                    'questionnaire': get_questionaire('offer_consent')
                                      })

                return False

        elif latest_state.event == DoctorServiceOfferEvent.QUESTIONNAIRE_DONE_OFFER_INITIATED:
            return_type = self._process_questions(latest_state.offer_id, latest_state.event, latest_state.questionnaire)

            if return_type != 'proceed':
                return return_type

            elif latest_state.questionnaire[-1]['llm_response'] == 1:
                DoctorService.capture(latest_state.offer_id, self.state.username, self.profile.get('email'),
                                      DoctorServiceOfferEvent.OFFER_ACCEPTED,
                                      {})
                self.llm.stream_callback.on_llm_new_token(f"""Great! Let’s get your payment information.""")
            elif latest_state.questionnaire[-1]['llm_response'] == 2:
                self.state.next_agent(
                    name=agents.ConciergeAgent.name, reset_hist=True)
                return False

        elif latest_state.event == DoctorServiceOfferEvent.OFFER_ACCEPTED:
            # Handles for when webhook is delayed.
            if self.profile.get('checkoutStatus', '') == 'complete':
                stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
                charge_ = stripe.Charge.search(
                    query=f'metadata["offer_id"]:"{latest_state.offer_id}"')
                if charge_ and charge_.data[0].status == 'succeeded':
                    DoctorService.capture(latest_state.offer_id, self.state.username, self.profile.get('email'),
                                          DoctorServiceOfferEvent.OFFER_PAYMENT_DONE,
                                          {
                                              'payment': {
                                                  'id': charge_.data[0].payment_intent,
                                                  'receipt_url': charge_.data[0].receipt_url
                                              }
                                          })
                    return False
            self.llm.stream_callback.on_llm_new_token(
                "\n\n\nLooks like we have not received your payment yet. Please enter your payment details.")

        elif latest_state.event == DoctorServiceOfferEvent.OFFER_PAYMENT_DONE:
            verified_user = is_verified_user(self.profile.get('email'))

            if verified_user:
                self._trigger_consent_flow(latest_state.offer_id)
            else:
                self.llm.stream_callback.on_llm_new_token(
                    "\n\n\nNext the Doctor and your Pharmacy require us to verify your identity. For your safety and protection we use Veriff, which is in compliance with U.S. privacy laws.")
                DoctorService.capture(latest_state.offer_id, self.state.username, self.profile.get('email'),
                                      DoctorServiceOfferEvent.VERIFY_USER,
                                      {})

        elif latest_state.event == DoctorServiceOfferEvent.VERIFY_USER:
            if self.profile.get('verified'):
                # TODO Cross check if webhook is not yet received, so either wait a bit or act accordingly
                self._trigger_consent_flow(latest_state.offer_id)
            else:
                self.llm.stream_callback.on_llm_new_token(
                    "\n\n\nLooks like you are not verified yet. We will need to verify your account first.")

        elif latest_state.event == DoctorServiceOfferEvent.USER_VERIFIED:
            self._trigger_consent_flow(latest_state.offer_id)

        elif latest_state.event == DoctorServiceOfferEvent.USER_VERIFICATION_FAILED:
            self.llm.stream_callback.on_llm_new_token(
                "\n\n\nLooks like your previous verification attempt failed. We will need to verify again. Please make sure documents are correct.")

        elif latest_state.event == DoctorServiceOfferEvent.POLICY_CONSENT:
            return_type = self._process_questions(latest_state.offer_id, latest_state.event,
                                                  latest_state.questionnaire)

            if return_type != 'proceed':
                return return_type
            else:
                DoctorService.capture(latest_state.offer_id, self.state.username, self.profile.get('email'),
                                      DoctorServiceOfferEvent.ONBOARDING_QUESTIONNAIRE_CAPTURE,
                                      {
                                          'questionnaire': get_questionaire('onboarding')
                                      })
                return False

        elif latest_state.event == DoctorServiceOfferEvent.ONBOARDING_QUESTIONNAIRE_CAPTURE:
            return_type = self._process_questions(latest_state.offer_id, latest_state.event,
                                                  latest_state.questionnaire)
            if return_type != 'proceed':
                return return_type
            else:
                state_event = DoctorService.event_of_type(
                    latest_state.offer_id, DoctorServiceOfferEvent.CAPTURE_STATE)

                hcp_details = EhrService().match_prescriber(
                    search_params={'state': state_event.state})

                DoctorService.capture(latest_state.offer_id, self.state.username, self.profile.get('email'),
                                      DoctorServiceOfferEvent.HCP_MATCH,
                                      {
                                          'hcp': {
                                              'id': hcp_details.get('id'),
                                              'name': hcp_details.get('first_name') + ' ' + hcp_details.get('last_name'),
                                              'email': hcp_details.get('email'),
                                          }
                                      })

                content = ''
                if hcp_details.get('id'):
                    content = content + f"""Yay. You are matched. Your Doctor has begun to review your information.

You’ve been matched to your Doctor.

{hcp_details.get('bio')}


"""

                content = content + f"""Here are your Next Steps.

1. Go to the <a class="text-blue underline" href="https://apps.apple.com/us/app/akute-patient-portal/id1571802525" target="_blank">Apple App Store</a> or the <a class="text-blue underline" href="https://play.google.com/store/apps/details?id=com.akutehealth.patientportal&pli=1" target="_blank">Google Play Store</a>. Install the Akute Patient Portal for secure doctor-patient messaging. 
2. Within 2 hours you will receive a Code to activate the App. Please Activate the App.
3. Your Doctor will message you.
4. Need help? Check out <a class="text-blue underline app-link" href="{base_url()}help" target="_blank">cody.md/help</a> or email <a class="text-blue underline" href="mailto:help@cody.md">help@cody.md</a>. 
"""

            self.llm.stream_callback.on_llm_new_token(content)

            DoctorService.capture(latest_state.offer_id, self.state.username, self.profile.get('email'),
                                  DoctorServiceOfferEvent.SEND_TO_EHR,
                                  {})

            EmailSender().send_cody_care_confirmation(CodyCareConfirmationEmailParameters(
                name=self.state.patient_name, email_address=latest_state.user_id))

            threading.Thread(target=DoctorService.process_for_ehr,
                             args=(latest_state.offer_id,)).start()

        elif (latest_state.event == DoctorServiceOfferEvent.SEND_TO_EHR or
              latest_state.event == DoctorServiceOfferEvent.EHR_SENT):
            # check if user has questions in the input via llm
            # if user has questions intent, then answer questions in the boundaries of cody care
            self.llm.stream_callback.on_llm_new_token(
                "If you have a moment, please check out your My Story page to make sure your info is current. An up-to- date My Story helps us provide the best care for you.\n\n\n")
            self.state.next_agent(
                name=agents.FeedbackAgent.name, reset_hist=True)
            self.state.next_agent_name = agents.ConciergeAgent.name
            return False

        elif latest_state.event == DoctorServiceOfferEvent.EHR_PLAN_READY:
            return_type = self._process_questions(
                latest_state.offer_id, latest_state.event, latest_state.questionnaire)

            if return_type != 'proceed':
                return return_type

            if latest_state.questionnaire[-1].get('llm_response') == 1:
                content = f"""Excellent. You are on your way to feeling better.
                
Please update your profile at <a class="text-blue underline app-link" href="{base_url()}my-story" target="_blank">cody.md/my-story</a>.

<b>Support:</b> You have 7 days of support. Check out <a class="text-blue underline app-link" href="{base_url()}help" target="_blank">cody.md/help</a> or email <a class="text-blue underline" href="mailto:help@cody.md">help@cody.md</a>.

<b>Cody is not for emergencies.</b> If you are having an emergency, call 911 or go to your Emergency Room.

Please enter “Options” to see what you can do now.
"""
                self.llm.stream_callback.on_llm_new_token(content)

                DoctorService.capture(latest_state.offer_id, self.state.username, self.profile.get('email'),
                                      DoctorServiceOfferEvent.EHR_PLAN_ACKNOWLEDGED, {})

                return True

            elif latest_state.questionnaire[-1].get('llm_response') == 2:

                self.llm.stream_callback.on_llm_new_token(
                    """Please send an email to <a class="text-blue underline app-link" href="mailto:help@cody.md">help@cody.md</a> and let us know your questions or concerns.""")

                DoctorService.capture(latest_state.offer_id, self.state.username, self.profile.get('email'),
                                      DoctorServiceOfferEvent.EHR_PLAN_NOT_ACKNOWLEDGED, {})

                self.state.next_agent(
                    name=agents.ConciergeAgent.name, reset_hist=True)

            return False
        elif latest_state.event == DoctorServiceOfferEvent.EHR_PLAN_ACKNOWLEDGED:
            if self.state.last_human_input.lower() == 'options':
                self.state.next_agent(
                    name=agents.ConciergeAgent.name, reset_hist=True)
                return False
            else:
                self.llm.stream_callback.on_llm_new_token(
                    "I'm sorry, I didn't get that. Please enter 'Options' to see what you can do now.")
                return True

    def _trigger_consent_flow(self, offer_id):
        questionaire = get_questionaire('policy_consent')
        questionaire[0]['presented'] = True

        DoctorService.capture(offer_id, self.state.username, self.profile.get('email'),
                              DoctorServiceOfferEvent.POLICY_CONSENT,
                              {
                                  'questionnaire': questionaire
                              })

        self.llm.stream_callback.on_llm_new_token(
            '\n\n\n' + questionaire[0]['question'])

    def _process_questions(self, offer_id: str, event: DoctorServiceOfferEvent, questionnaire: dict) -> bool | None:
        """
        Process the questions asked in the questionnaire.
        If we return a valid bool, it means that we dont want to move to the next cody care event.
        If we return None, it means we want to continue to the next cody care event.
        """
        for question in questionnaire:
            if question.get('response') is None:
                # We need to process the question by asking the user
                if not question.get('presented'):
                    question['presented'] = True

                    DoctorService.update_event_details(offer_id=offer_id, event=event, event_data={
                        'questionnaire': questionnaire
                    })
                    self.llm.stream_callback.on_llm_new_token(
                        question['question'])
                    return True
                else:
                    if question.get('llm_prompt'):
                        value = CodyCareUtils.validate_questions_via_llm(
                            state=self.state, last_human_input=self.state.last_human_input,
                            prompt=question['llm_prompt'])
                        if value is None or value.get('value') == 'invalid':
                            self.llm.stream_callback.on_llm_new_token(
                                question['error_message'])
                            return True
                        else:
                            question['llm_response'] = value.get('value')

                    elif question['type'] == 'phone':
                        try:
                            number = phonenumbers.parse(
                                self.state.last_human_input, region="US")
                            if len(str(number.national_number)) != 10:
                                raise phonenumbers.phonenumberutil.NumberParseException(error_type=0, msg="Invalid number")
                            # This formatted_response will be used to fill EHR data.
                            question['formatted_response'] = str(number.national_number)
                        except phonenumbers.phonenumberutil.NumberParseException:
                            self.llm.stream_callback.on_llm_new_token(question.get('error_message'))
                            return True

                    elif question['type'] == 'choice':
                        response = process_nav_input(human_input=self.state.last_human_input,
                                                     options=question.get(
                                                         'choices', question['question']),
                                                     state=self.state)

                        question['llm_response'] = response

                        if response not in question['valid_choices']:
                            if question.get('error_message'):
                                self.llm.stream_callback.on_llm_new_token(
                                    question['error_message'])
                            else:
                                self.llm.stream_callback.on_llm_new_token(
                                    "I am sorry, I could not understand your input. Please select from the options "
                                    "provided.")

                            return True

                    question['response'] = self.state.last_human_input
                    DoctorService.update_event_details(offer_id=offer_id, event=event, event_data={
                        'questionnaire': questionnaire
                    })
                    action = self._perform_actions(question)
                    if action is not None:
                        return action
        return 'proceed'

    def _perform_actions(self, question: dict) -> bool | None:
        """
        Perform actions based on the question asked.
        If we return a bool, it means we want to disqualify the user.
        - True means we want the user input.
        - False means we want to continue the loop.
        None means we want to continue cody care.
        """
        if question['id'] == 'SYMPTOMS':
            # Check if the symptoms are severe
            if question['llm_response'] == 1:
                self.llm.stream_callback.on_llm_new_token(
                    f"{self.state.patient_name}, it’s important that you contact your primary care doctor, or go to your urgent care or emergency room to receive care now.\n\n\n")
                self.state.next_agent(
                    name=agents.EndAgent.name, reset_hist=True)
                return False

        elif question['id'] == 'PATIENT_WHO':
            if question['llm_response'] == 2:
                self.llm.stream_callback.on_llm_new_token(
                    f'We’d love to care for you, but the Doctor must care for the patient directly. Please encourage your friend or family to try <a class="text-blue underline app-link" href="{base_url()}">cody.md</a>.\n\n\n')
                self.state.next_agent(
                    name=agents.ConciergeAgent.name, reset_hist=True)
                return False
            elif question['llm_response'] == 1:
                self.llm.stream_callback.on_llm_new_token(
                    "Excellent. Moving along.\n\n\n")

        elif question['id'] == '18_PLUS':
            if question['llm_response'] == 2:
                self.llm.stream_callback.on_llm_new_token(
                    "We’d love to care for you, but patients for the Doctor Service must be at least 18 years of age.\n\n\n")
                self.state.next_agent(
                    name=agents.ConciergeAgent.name, reset_hist=True)
                return False

        elif question['id'] == 'POLICY_CONSENT':
            if question['llm_response'] == 1:
                content = f"""Yay! You are all set up.\n\n\nYou’re now being matched to your Doctor. Please answer these questions so your Doctor may safely and effectively care for you.


"""
                self.llm.stream_callback.on_llm_new_token(content)
                # Proceed with the cody care flow (qualify the user)
                return None
            elif question['llm_response'] == 2:
                self.llm.stream_callback.on_llm_new_token(
                    "Darn. We are unable to serve you if you do not approve our policies. Please send an email to help@cody.md with your questions and we’ll get right back.")
                self.state.next_agent(
                    name=agents.ConciergeAgent.name, reset_hist=True)
                return False

        return None
