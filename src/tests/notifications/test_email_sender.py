import os
from unittest.mock import Mock

from src.notifications.email_sender import EmailSender, FollowUpEmailParameters, CodyCareConfirmationEmailParameters, \
    CodyCareCertifiedPlanEmailParameters, TaskAssignedHcpEmailParameters


def init():
    os.environ['MOCK_EMAIL'] = 'true'
    email_sender = EmailSender()
    email_sender.pinpoint = Mock()
    return email_sender

def test_followup_care_email_sending_production():
    os.environ['ENVIRONMENT'] = 'production'
    email_sender = init()

    template_param = FollowUpEmailParameters(
        name='John Doe',
        convo_id='123',
        email_address='test@test.com')

    email_sender.send_followup_email(template_param)

    email_sender.pinpoint.send_messages.assert_called_once()

    request = email_sender.pinpoint.send_messages.call_args[1]

    assert request['ApplicationId'] == '28381c0365eb45ba907d56fbdfcb8bbb'
    assert request['MessageRequest'] == {
        'Addresses': {
            'test@test.com': {
                'ChannelType': 'EMAIL',
                'Substitutions': {
                    "name": [
                        'John Doe'
                    ],
                    "followup_link": [
                        'https://cody.md/convo/123?followup=true'
                    ],
                    "optout_link": [
                        'https://cody.md/care/optout/123'
                    ]
                }
            },
        },
        'MessageConfiguration': {
            'EmailMessage': {
                'FromAddress': 'CodyMD Your AI Doctor <noreply@cody.md>',
            }
        },
        'TemplateConfiguration': {
            'EmailTemplate': {
                'Name': 'Followup_care_message',
                'Version': '5'
            }
        }
    }


def test_followup_care_email_sending_staging():
    os.environ['ENVIRONMENT'] = 'staging'

    email_sender = init()

    template_param = FollowUpEmailParameters(
        name='John Doe',
        convo_id='123',
        email_address='test@test.com')

    email_sender.send_followup_email(template_param)

    email_sender.pinpoint.send_messages.assert_called_once()

    request = email_sender.pinpoint.send_messages.call_args[1]

    assert request['ApplicationId'] == '92fcf7a945ad4634aa2852d22e3f8d9a'
    assert request['MessageRequest'] == {
        'Addresses': {
            'test@test.com': {
                'ChannelType': 'EMAIL',
                'Substitutions': {
                    "name": [
                        'John Doe'
                    ],
                    "followup_link": [
                        'https://staging.cody.md/convo/123?followup=true'
                    ],
                    "optout_link": [
                        'https://staging.cody.md/care/optout/123'
                    ]
                }
            }
        },
        'MessageConfiguration': {
            'EmailMessage': {
                'FromAddress': 'CodyMD(Staging) Your AI Doctor <noreply@cody.md>',
            }
        },
        'TemplateConfiguration': {
            'EmailTemplate': {
                'Name': 'Followup_care_message',
                'Version': '5'
            }
        }
    }


def test_followup_care_email_sending_dev():
    os.environ['ENVIRONMENT'] = 'dev'
    email_sender = init()

    template_param = FollowUpEmailParameters(
        name='John Doe',
        convo_id='123',
        email_address='test@test.com')

    email_sender.send_followup_email(template_param)

    email_sender.pinpoint.send_messages.assert_not_called()


def test_followup_care_email_sending_exception():
    os.environ['ENVIRONMENT'] = 'staging'
    email_sender = init()

    email_sender.pinpoint.send_messages.side_effect = Exception('Test exception')

    template_param = FollowUpEmailParameters(
        name='John Doe',
        convo_id='123',
        email_address='test@test.com')

    email_sender.send_followup_email(template_param)

    email_sender.pinpoint.send_messages.assert_called_once()


def test_cody_care_email_sending_production():
    os.environ['ENVIRONMENT'] = 'production'
    email_sender = init()

    template_param = CodyCareConfirmationEmailParameters(
        name='John Doe',
        email_address='test@test.com')

    email_sender.send_cody_care_confirmation(template_param)

    email_sender.pinpoint.send_messages.assert_called_once()

    request = email_sender.pinpoint.send_messages.call_args[1]

    assert request['ApplicationId'] == '28381c0365eb45ba907d56fbdfcb8bbb'
    assert request['MessageRequest'] == {
        'Addresses': {
            'test@test.com': {
                'ChannelType': 'EMAIL',
                'Substitutions': {
                    "name": [
                        'John Doe'
                    ],
                    "help_page_url": [
                        'https://cody.md/help'
                    ],
                }
            },
        },
        'MessageConfiguration': {
            'EmailMessage': {
                'FromAddress': 'CodyMD Your AI Doctor <noreply@cody.md>',
            }
        },
        'TemplateConfiguration': {
            'EmailTemplate': {
                'Name': 'Cody_Care_Conformation_Email_Payment',
                'Version': '1'
            }
        }
    }


def test_cody_care_email_sending_staging():
    os.environ['ENVIRONMENT'] = 'staging'

    email_sender = init()

    template_param = CodyCareConfirmationEmailParameters(
        name='John Doe',
        email_address='test@test.com')

    email_sender.send_cody_care_confirmation(template_param)

    email_sender.pinpoint.send_messages.assert_called_once()

    request = email_sender.pinpoint.send_messages.call_args[1]

    assert request['ApplicationId'] == '92fcf7a945ad4634aa2852d22e3f8d9a'
    assert request['MessageRequest'] == {
        'Addresses': {
            'test@test.com': {
                'ChannelType': 'EMAIL',
                'Substitutions': {
                    "name": [
                        'John Doe'
                    ],
                    "help_page_url": [
                        'https://staging.cody.md/help'
                    ],
                }
            }
        },
        'MessageConfiguration': {
            'EmailMessage': {
                'FromAddress': 'CodyMD(Staging) Your AI Doctor <noreply@cody.md>',
            }
        },
        'TemplateConfiguration': {
            'EmailTemplate': {
                'Name': 'Cody_Care_Conformation_Email_Payment',
                'Version': '1'
            }
        }
    }


def test_cody_care_email_sending_dev():
    os.environ['ENVIRONMENT'] = 'dev'
    email_sender = init()

    template_param = CodyCareConfirmationEmailParameters(
        name='John Doe',
        email_address='test@test.com')

    email_sender.send_cody_care_confirmation(template_param)

    email_sender.pinpoint.send_messages.assert_not_called()


def test_care_care_email_sending_exception():
    os.environ['ENVIRONMENT'] = 'staging'
    email_sender = init()

    email_sender.pinpoint.send_messages.side_effect = Exception('Test exception')

    template_param = CodyCareConfirmationEmailParameters(
        name='John Doe',
        email_address='test@test.com')

    email_sender.send_cody_care_confirmation(template_param)

    email_sender.pinpoint.send_messages.assert_called_once()


def test_cody_care_plan_production():
    os.environ['ENVIRONMENT'] = 'production'
    email_sender = init()

    template_param = CodyCareCertifiedPlanEmailParameters(
        name='John Doe',
        email_address='test@test.com',
        convo_id='123')

    email_sender.send_cody_care_plan_ready(template_param)

    email_sender.pinpoint.send_messages.assert_called_once()

    request = email_sender.pinpoint.send_messages.call_args[1]

    assert request['ApplicationId'] == '28381c0365eb45ba907d56fbdfcb8bbb'
    assert request['MessageRequest'] == {
        'Addresses': {
            'test@test.com': {
                'ChannelType': 'EMAIL',
                'Substitutions': {
                    "name": [
                        'John Doe'
                    ],
                    "convo_url": [
                        'https://cody.md/convo/123'
                    ],
                }
            },
        },
        'MessageConfiguration': {
            'EmailMessage': {
                'FromAddress': 'CodyMD Your AI Doctor <noreply@cody.md>',
            }
        },
        'TemplateConfiguration': {
            'EmailTemplate': {
                'Name': 'Cody_Care_Certified_Plan_Ready',
                'Version': '1'
            }
        }
    }


def test_cody_care_plan_sending_staging():
    os.environ['ENVIRONMENT'] = 'staging'

    email_sender = init()

    template_param = CodyCareCertifiedPlanEmailParameters(
        name='John Doe',
        email_address='test@test.com',
        convo_id='123')

    email_sender.send_cody_care_plan_ready(template_param)

    email_sender.pinpoint.send_messages.assert_called_once()

    request = email_sender.pinpoint.send_messages.call_args[1]

    assert request['ApplicationId'] == '92fcf7a945ad4634aa2852d22e3f8d9a'
    assert request['MessageRequest'] == {
        'Addresses': {
            'test@test.com': {
                'ChannelType': 'EMAIL',
                'Substitutions': {
                    "name": [
                        'John Doe'
                    ],
                    "convo_url": [
                        'https://staging.cody.md/convo/123'
                    ],
                }
            }
        },
        'MessageConfiguration': {
            'EmailMessage': {
                'FromAddress': 'CodyMD(Staging) Your AI Doctor <noreply@cody.md>',
            }
        },
        'TemplateConfiguration': {
            'EmailTemplate': {
                'Name': 'Cody_Care_Certified_Plan_Ready',
                'Version': '1'
            }
        }
    }


def test_cody_care_plan_sending_dev():
    os.environ['ENVIRONMENT'] = 'dev'
    email_sender = init()

    template_param = CodyCareCertifiedPlanEmailParameters(
        name='John Doe',
        email_address='test@test.com',
        convo_id='123')

    email_sender.send_cody_care_plan_ready(template_param)

    email_sender.pinpoint.send_messages.assert_not_called()


def test_care_care_plan_sending_exception():
    os.environ['ENVIRONMENT'] = 'staging'
    email_sender = init()

    email_sender.pinpoint.send_messages.side_effect = Exception('Test exception')

    template_param = CodyCareCertifiedPlanEmailParameters(
        name='John Doe',
        email_address='test@test.com',
        convo_id='123')

    email_sender.send_cody_care_plan_ready(template_param)

    email_sender.pinpoint.send_messages.assert_called_once()


def test_cody_task_assigned_production():
    os.environ['ENVIRONMENT'] = 'production'
    email_sender = init()

    template_param = TaskAssignedHcpEmailParameters(
        name='John Doe',
        email_address='test@test.com',
        task_id='123')

    email_sender.send_task_assigned_hcp(template_param)

    email_sender.pinpoint.send_messages.assert_called_once()

    request = email_sender.pinpoint.send_messages.call_args[1]

    assert request['ApplicationId'] == '28381c0365eb45ba907d56fbdfcb8bbb'
    assert request['MessageRequest'] == {
        'Addresses': {
            'test@test.com': {
                'ChannelType': 'EMAIL',
                'Substitutions': {
                    "name": [
                        'John Doe'
                    ],
                    "task_url": [
                        'https://app.akutehealth.com/inbox/tasks/123'
                    ],
                }
            },
        },
        'MessageConfiguration': {
            'EmailMessage': {
                'FromAddress': 'CodyMD Your AI Doctor <noreply@cody.md>',
            }
        },
        'TemplateConfiguration': {
            'EmailTemplate': {
                'Name': 'Task_Assigned_HCP',
                'Version': '1'
            }
        }
    }


def test_cody_task_assigned_staging():
    os.environ['ENVIRONMENT'] = 'staging'

    email_sender = init()

    template_param = TaskAssignedHcpEmailParameters(
        name='John Doe',
        email_address='test@test.com',
        task_id='123')

    email_sender.send_task_assigned_hcp(template_param)

    email_sender.pinpoint.send_messages.assert_called_once()

    request = email_sender.pinpoint.send_messages.call_args[1]

    assert request['ApplicationId'] == '92fcf7a945ad4634aa2852d22e3f8d9a'
    assert request['MessageRequest'] == {
        'Addresses': {
            'test@test.com': {
                'ChannelType': 'EMAIL',
                'Substitutions': {
                    "name": [
                        'John Doe'
                    ],
                    "task_url": [
                        'https://app.staging.akutehealth.com/inbox/tasks/123'
                    ],
                }
            }
        },
        'MessageConfiguration': {
            'EmailMessage': {
                'FromAddress': 'CodyMD(Staging) Your AI Doctor <noreply@cody.md>',
            }
        },
        'TemplateConfiguration': {
            'EmailTemplate': {
                'Name': 'Task_Assigned_HCP',
                'Version': '1'
            }
        }
    }


def test_cody_task_assigned_sending_dev():
    os.environ['ENVIRONMENT'] = 'dev'
    email_sender = init()

    template_param = TaskAssignedHcpEmailParameters(
        name='John Doe',
        email_address='test@test.com',
        task_id='123')

    email_sender.send_task_assigned_hcp(template_param)

    email_sender.pinpoint.send_messages.assert_not_called()


def test_cody_task_assigned_sending_exception():
    os.environ['ENVIRONMENT'] = 'staging'
    email_sender = init()

    email_sender.pinpoint.send_messages.side_effect = Exception('Test exception')

    template_param = TaskAssignedHcpEmailParameters(
        name='John Doe',
        email_address='test@test.com',
        task_id='123')

    email_sender.send_task_assigned_hcp(template_param)

    email_sender.pinpoint.send_messages.assert_called_once()
