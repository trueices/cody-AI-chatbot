from textwrap import dedent

from src.utils import base_url

ONBOARDING_QUESTIONNAIRE_BASE = [
    {
        "id": "PHONE",
        "question": f"""What is your phone number? 
[111-222-3333]
Your Doctor will use it to contact you.""",
        "error_message": "I am sorry, phone number looks invalid. Please enter a valid 10 digit phone number in the format 123-456-7890.",
        "type": "phone",
        "required": True,
    },
    {
        "id": "DOB",
        "question": f"""What is your date of birth?
[ Month, Day, Year]
""",
        "error_message": "I am sorry, date of birth looks invalid. Please enter a valid date of birth in the format: November 24, 2000",
        "type": "date",
        "required": True,
        "llm_prompt": dedent("""Check if USER INPUT is a valid date of birth.
Incorrect spelling is allowed.
        
Your output should be a JSON with the following keys:

- value: string (Date of birth in the format MM/DD/YYYY or invalid)
EXAMPLE:
                
USER INPUT: Its Nov 16, 2000
OUTPUT:
{
        "value": "11/16/2000"
}    

USER INPUT: What is my date of birth?
OUTPUT:
{
        "value": "invalid"
}
""")
    },
    {
        "id": "SEX_AT_BIRTH",
        "question": f"""What is your sex assigned at birth?

1. Female
2. Male
3. Intersex
4. Skip
""",
        "type": "choice",
        "valid_choices": [1, 2, 3, 4],
        "required": True
    },
    {
        "id": "GENDER",
        "question": f"""What is your gender?

1. Female
2. Male
3. Non--binary
4. Other
5. Skip
""",
        "type": "choice",
        "valid_choices": [1, 2, 3, 4, 5],
        "required": True
    },
    {
        "id": "MEDICATIONS",
        "question": f"""What prescription and nonprescription medications are you currently taking? If none, please say “None”. """,
        "type": "text",
        "required": True,
        "error_message": f"""I am sorry, medications look invalid. Please enter a valid medications only e.g. aspirin, ibuprofen, lisinopril. If you do not take any medications, please say "None".""",
        "llm_prompt": dedent("""Check if USER INPUT contains valid medications.
Incorrect spelling is allowed.

Your output should be a JSON with the
- value: string (Medications, None or invalid)

EXAMPLE:

USER INPUT: aspirin, ibuprofen, lisinopril
OUTPUT:
{
        "value": "aspirin, ibuprofen, lisinopril"
}

USER INPUT: None
OUTPUT:
{
        "value": "None"
}


USER INPUT: i dont understand
OUTPUT:
{
        "value": "invalid"
}

USER INPUT: I take aspirin, ibuprofen, lisinopril
OUTPUT:
{
        "value": "aspirin, ibuprofen, lisinopril"
}"""),
    },
    {
        "id": "ALLERGIES",
        "question": f"""Please list all your medication allergies. If none, please say, “None”""",
        "type": "text",
        "required": True,
        "error_message": f"""I am sorry, allergies look invalid. Please enter a valid allergies only e.g. penicillin, sulfa, aspirin. If you do not have any allergies, please say "None".""",
        "llm_prompt": dedent("""Check if USER INPUT contains valid allergies.
Incorrect spelling is allowed.

Your output should be a JSON with the
- value: string (Allergies, None or invalid)

EXAMPLE:

USER INPUT: penicillin, sulfa, aspirin
OUTPUT:
{
        "value": "penicillin, sulfa, aspirin"
}

USER INPUT: None
OUTPUT:
{
        "value": "None"
}


USER INPUT: i dont understand
OUTPUT:
{
        "value": "invalid"
}

USER INPUT: I have allergies to penicillin, sulfa, aspirin
OUTPUT:
{
        "value": "penicillin, sulfa, aspirin"
}
""")
    },
    {
        "id": "MEDICAL_CONDITIONS",
        "question": f"""What are your current medical conditions? 
For example, you can say “diabetes:” If none, please say, “None”. 
""",
        "type": "text",
        "required": True,
        "error_message": f"""I am sorry, medical conditions look invalid. Please enter a valid medical conditions only e.g. diabetes, hypertension, migraine. If you do not have any medical conditions, please say "None".""",
        "llm_prompt": dedent("""Check if USER INPUT contains valid medical conditions.
Incorrect spelling is allowed.

Your output should be a JSON with the
- value: string (Medical conditions, None or invalid)

EXAMPLE:

USER INPUT: diabetes, hypertension, migraine
OUTPUT:
{
        "value": "diabetes, hypertension, migraine"
}

USER INPUT: None
OUTPUT:
{
        "value": "None"
}


USER INPUT: i dont understand
OUTPUT:
{
        "value": "invalid"
}

USER INPUT: I have diabetes, hypertension, migraine
OUTPUT:
{
        "value": "diabetes, hypertension, migraine"
}
""")
    },
    {
        "id": "PHARMACY",
        "question": f"""What is your preferred pharmacy?
[Enter pharmacy name, pharmacy address, pharmacy phone number]
""",
        "type": "text",
        "required": True,
        "error_message": f"""I’m sorry, please clarify your pharmacy information. 

Please enter your preferred pharmacy information like this:

Pharmacy Name: Walgreens
Pharmacy Address (111 Main Street, Portland, Oregon, 97210)
Pharmacy Phone Number (111-222-333)
""",
        "llm_prompt": dedent("""Check if USER INPUT is a valid pharmacy information in the United States.
Incorrect spelling is allowed.
        
USER INPUT should include pharmacy name, city, and zip.
        
Your output should be a JSON with the following keys:
- value: string (Pharmacy information)
EXAMPLE:

USER INPUT: CVS Pharmacy, 1234 Main Street, Portland, OR 97210
OUTPUT:
{
        "value": "CVS Pharmacy, 1234 Main Street, Portland, OR 97210"
}

USER INPUT: CVS Pharmacy, Portland 97210
OUTPUT:
{
        "value": "CVS Pharmacy, Portland 97210"
}

USER INPUT: CVS Pharmacy
OUTPUT:
{
        "value": "invalid"
}
""")
    },
]


POLICY_CONSENT_QUESTIONNAIRE_BASE = [
    {
        "id": "POLICY_CONSENT",
        "question": f"""Please review our policies and approve to continue.

    - <a class="text-blue underline" href="{base_url()}patient-policies" target="_blank">Patient Policies</a>
    - <a class="text-blue underline" href="{base_url()}privacy-policy-for-patient-care" target="_blank">Privacy Policy</a>
    - <a class="text-blue underline" href="{base_url()}financial-policy" target="_blank">Financial Policy</a>

1. I approve of these policies.
2. I do NOT approve of these policies.
""",
        "type": "choice",
        "valid_choices": [1, 2],
        "required": True,
        "choices": "1. I approve or Acknowledge \n2. I decline or do not approve or  do not acknowledge",
        "error_message": "I am sorry, I could not understand your input. Either approve or decline the consent.",
    }
]


RO_QUESTIONNAIRE_BASE = [
    {
        "id": "SYMPTOMS",
        "question": """Are you experiencing any of the following today?

- fever over 101.0 F
- abdominal or pelvic pain that make it difficult to move
- lightheadedness or dizziness that disrupts daily activities
- shortness of breath
- chest pain
- Intensive vomiting or diarrhea
- blood in diarrhea or in vomit

1. Yes, I am experiencing one or more of these symptoms
2. No, I am not experiencing any of these symptoms""",
        "type": "choice",
        "valid_choices": [1, 2],
        "required": True
    },
    {
        "id": "PATIENT_WHO",
        "question": """Who is the patient?

1. I am the patient
2. I am NOT the patient.""",
        "type": "choice",
        "valid_choices": [1, 2],
        "required": True
    },
    {
        "id": "18_PLUS",
        "question": """Please confirm that you are at least 18 years of age.

1. Yes.
2. No, I am not yet 18.
""",
        "type": "choice",
        "valid_choices": [1, 2],
        "required": True
    }
]


PLAN_ACKNOWLEDGEMENT_QUESTIONNAIRE_BASE = [
    {
        "id": "PLAN_ACKNOWLEDGEMENT",
        "question": """1. I approve of my Certified Plan.
2. I do Not approve. I have questions.
""",
        "type": "choice",
        "valid_choices": [1, 2],
        "required": True,
        "error_message": "I am sorry, I could not understand your input. Either approve or decline the plan."
    }
]

OFFER_CONSENT_QUESTIONNAIRE_BASE = [
    {
        "id": "OFFER_CONSENT",
        "question": """<div class="tx-plan">
<h1>🩺The Doctor Service is just $39</h1>
<p>Everything you need to get well.</p>
<br>
<b>Doctor Review</b>
<p>The Doctor will review everything we talked about.</p>
<br>
<b>Doctor Chat</b>
<p>The Doctor will message you.</p>
<br>
<b>Certified Plan</b>
<p>Your Doctor will prepare your Certified Plan that covers everything you need to get well.</p>
<br>
<b>Medication Prescriptions</b>
<p>Your Doctor will order prescriptions if needed.</p>
<br>
<b>Tests and Referrals</b>
<p>Your Doctor will order tests and referrals if needed.</p>
<br>
<b>Follow-up</b>
<p>You are not alone. We will check in on you.</p>
<br>
<b>7 Days of Unlimited Support</b>
<br>
<b>The Cody Guarantee</b>
<p>Not satisfied. No problem. We’ll make it right.</p>
</div>


Would you like to order the Cody Doctor Service?
    
1. Yes, I want The Doctor Service.
2. No thanks. What else can I do now?""",
        "type": "choice",
        "valid_choices": [1, 2],
        "choices": "1. Yes, I want The Doctor Service.\n2. No thanks. What else can I do now?",
        "required": True,
        "error_message": "I am sorry, I could not understand your input. Either say yes or no."
    }
]


def get_questionaire(option: str):
    """
    Returns deep copy of the questionnaire based on the option.
    """
    import copy
    if option == 'onboarding':
        return copy.deepcopy(ONBOARDING_QUESTIONNAIRE_BASE)
    elif option == 'policy_consent':
        return copy.deepcopy(POLICY_CONSENT_QUESTIONNAIRE_BASE)
    elif option == 'ro':
        return copy.deepcopy(RO_QUESTIONNAIRE_BASE)
    elif option == 'plan_acknowledgement':
        return copy.deepcopy(PLAN_ACKNOWLEDGEMENT_QUESTIONNAIRE_BASE)
    elif option == 'offer_consent':
        return copy.deepcopy(OFFER_CONSENT_QUESTIONNAIRE_BASE)
