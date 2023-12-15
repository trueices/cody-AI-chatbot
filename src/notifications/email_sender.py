import logging
import os

import boto3
from src.utils import base_url


class FollowUpEmailParameters:
    def __init__(self, name: str, convo_id: str, email_address: str):
        self.template_version = '5'
        self.template_name = 'Followup_care_message' \
            if os.getenv('ENVIRONMENT',
                         'dev') == 'production' else 'Followup_care_message'

        self.from_address = 'CodyMD Your AI Doctor <noreply@cody.md>' if os.getenv('ENVIRONMENT',
                                                                                   'dev') == 'production' else 'CodyMD(Staging) Your AI Doctor <noreply@cody.md>'
        self.name = name
        self.convo_id = convo_id
        self.email_address = email_address

    def followup_url(self):
        return f"""{base_url()}convo/{self.convo_id}?followup=true"""

    def opt_out_url(self):
        return f"""{base_url()}care/optout/{self.convo_id}"""


class CodyCareConfirmationEmailParameters:
    def __init__(self, name: str, email_address: str):
        self.template_version = '1'
        self.template_name = 'Cody_Care_Conformation_Email_Payment'

        self.from_address = 'CodyMD Your AI Doctor <noreply@cody.md>' if os.getenv('ENVIRONMENT',
                                                                                   'dev') == 'production' else 'CodyMD(Staging) Your AI Doctor <noreply@cody.md>'
        self.name = name
        self.email_address = email_address

    @staticmethod
    def help_page_url():
        return f"""{base_url()}help"""


class TaskAssignedHcpEmailParameters:
    def __init__(self, name: str, email_address: str, task_id: str):
        self.template_version = '1'
        self.template_name = 'Task_Assigned_HCP'

        self.from_address = 'CodyMD Your AI Doctor <noreply@cody.md>' if os.getenv('ENVIRONMENT',
                                                                                   'dev') == 'production' else 'CodyMD(Staging) Your AI Doctor <noreply@cody.md>'

        self.name = name
        self.email_address = email_address
        self.task_id = task_id

    def task_url(self):
        if os.getenv('ENVIRONMENT', 'dev') == 'production':
            # TODO - Change to production URL
            return f"""https://app.akutehealth.com/inbox/tasks/{self.task_id}"""
        else:
            return f"""https://app.staging.akutehealth.com/inbox/tasks/{self.task_id}"""


class CodyCareCertifiedPlanEmailParameters:
    def __init__(self, name: str, email_address: str, convo_id: str):
        self.template_version = '1'
        self.template_name = 'Cody_Care_Certified_Plan_Ready'

        self.from_address = 'CodyMD Your AI Doctor <noreply@cody.md>' if os.getenv('ENVIRONMENT',
                                                                                   'dev') == 'production' else 'CodyMD(Staging) Your AI Doctor <noreply@cody.md>'
        self.name = name
        self.email_address = email_address
        self.convo_id = convo_id

    def convo_url(self):
        return f"""{base_url()}convo/{self.convo_id}"""


class EmailSender:
    def __init__(self):
        if os.getenv('MOCK_EMAIL', 'false') == 'true':
            self.pinpoint = None
        else:
            self.pinpoint = boto3.client('pinpoint', region_name='us-east-1')
        self.PINPOINT_APPLICATION_ID = '28381c0365eb45ba907d56fbdfcb8bbb' if os.getenv('ENVIRONMENT',
                                                                                       'dev') == 'production' else '92fcf7a945ad4634aa2852d22e3f8d9a'

    def send_followup_email(self, template_param: FollowUpEmailParameters) -> None:
        substitutions = {
            "name": [
                template_param.name
            ],
            "followup_link": [
                template_param.followup_url()
            ],
            "optout_link": [
                template_param.opt_out_url()
            ]
        }

        self._send_email(template_param, substitutions)

    def send_cody_care_confirmation(self, template_param: CodyCareConfirmationEmailParameters) -> None:
        substitutions = {
            "name": [
                template_param.name
            ],
            "help_page_url": [
                template_param.help_page_url()
            ]
        }

        self._send_email(template_param, substitutions)

    def send_task_assigned_hcp(self, template_param: TaskAssignedHcpEmailParameters) -> None:
        substitutions = {
            "name": [
                template_param.name
            ],
            "task_url": [
                template_param.task_url()
            ],
        }

        self._send_email(template_param, substitutions)

    def send_cody_care_plan_ready(self, template_param: CodyCareCertifiedPlanEmailParameters) -> None:
        substitutions = {
            "name": [
                template_param.name
            ],
            "convo_url": [
                template_param.convo_url()
            ],
        }

        self._send_email(template_param, substitutions)

    def _send_email(self, template_param, substitutions):
        if os.getenv('ENVIRONMENT', 'dev') not in ['staging', 'production']:
            logging.info(
                f"""Not sending email in non-staging/production environment. Values received: €{template_param}""")
            return None

        try:
            response = self.pinpoint.send_messages(
                ApplicationId=self.PINPOINT_APPLICATION_ID,
                MessageRequest={
                    'Addresses': {
                        template_param.email_address: {
                            'ChannelType': 'EMAIL',
                            'Substitutions': substitutions
                        },
                    },
                    'MessageConfiguration': {
                        'EmailMessage': {
                            'FromAddress': template_param.from_address,
                        }
                    },
                    'TemplateConfiguration': {
                        'EmailTemplate': {
                            'Name': template_param.template_name,
                            'Version': template_param.template_version
                        }
                    }
                }
            )
            logging.info(
                f"""Email sent to {template_param.email_address}. Response: €{response['MessageResponse']['Result'][template_param.email_address]['MessageId']}""")
        except Exception as e:
            logging.error(f"""Error sending email: €{e}""", exc_info=e)
            return None
