import datetime
import json

import humanize
from langchain.schema import HumanMessage, SystemMessage

from src import agents
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI, CustomChatOpenAI
from src.followup.followup_care import FollowupCare


class FollowupCareAgent(agents.Agent):
    name = 'followup_care_agent'

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None):
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]            

    def act(self) -> bool:
        # If the conversation history is not empty, add the last human input to the conversation history
        if len(self.conv_hist) != 0:
            self.conv_hist.append(HumanMessage(content=self.state.last_human_input))
        if len(self.conv_hist) < 2: # Followup care agent should start with the greeting
            return self.greeting()
        elif len(self.conv_hist) < 8: # Followup care agent should ask at least 3 more questions
            return self.ask_more_questions()
        else:
            return self.identify_status_of_problem()

    def greeting(self, stream:bool=True):
        prompt = f"""
You are following up with a patient after a previous conversation with them.
Your job is to create a greeting message in a particular format.

<EXAMPLE>
USER DATA:
CHIEF COMPLAINT: coughing at night with phlegm
PATIENT NAME: Sam
SUMMARY OF CONVERSATION:
Sam, here's what I've understood so far:\n- You have come to me regarding your coughing at night with phlegm.\n- You mentioned experiencing shortness of breath and wheezing along with the coughing.\n- Your phlegm is clear and cloudy in color and consistency.\n- Your symptoms seem to be worse at night or early in the morning.\n- Over-the-counter cough or cold medications did not provide relief.\n- You have a history of asthma and have been using a nebulizer, which has helped improve your symptoms.\n- Your symptoms improve when using your asthma inhaler regularly.\n- You have not tried any home remedies or natural remedies for your symptoms.

<EXAMPLE OUTPUT>
Hi Sam, last we talked, you were having cough at night, with phlegm.

Let’s see how you are doing.

Please let me know if your cough is:
1. worse
2. the same
3. improving
4. all better
<END OF OUTPUT>

Note:
Make sure you dont use the word "mentioned" in the greeting message.
For example, dont use a phrase like "you mentioned that you were having a headache". Instead, use "you were having a headache".
"""
        
        user_data = f"""
USER DATA:
CHIEF COMPLAINT: {self.state.chief_complaint.strip()}
PATIENT NAME: {self.state.patient_name}
PREVIOUS SUMMARY OF CONVERSATION:
{self.state.conv_hist[agents.MagicMinuteAgent.name][0].content.strip()}"""
        self.conv_hist[:] = [SystemMessage(content=user_data)]
        conv_hist = [SystemMessage(content=prompt)] + self.conv_hist
        today = datetime.date.today()
        header = f"\n\n\n<b><u>CodyMD Check-In {'{} {} {}'.format(humanize.ordinal(today.day), today.strftime('%B'), today.year)}</u></b>"
        self.llm.stream_callback.on_llm_new_token(header)

        if stream:
            response = self.llm(conv_hist)
        else:
            response = CustomChatOpenAI(state=self.state)(conv_hist)
            # We manually append the greeting to the full conversation history 
            # which will be presented to the user during the init call a conv history.
            # Also, adding new lines for separate chat bubble
            response.content = "\n\n" + response.content
            self.llm.stream_callback.full_conv_hist.append_token(
                response.content)

        response.content = header + response.content
        self.conv_hist.append(response)
        return True
    
    def ask_more_questions(self):
        prompt = f"""
You are talking to a patient, who is experiencing the issue: {self.state.chief_complaint}.
The patient has already provided their own "Subjective perspective" on their status, when you asked them whether their issue is "the same, worse or all better".
Now, you need to do followup care, where you ask clinical questions with the aim of determining the patient's objective clinical “Recovery Status” which is defined by one of three states:
a) recovering as expected;
b) not healing as expected; or
c) fully recovered.
Remember to not directly ask about the patient's recovery status. Your job to to look for clues in the conversation to determine the patient's recovery status.
The patient may feel that they are recovering, but the clinical questions may reveal that they are not recovering as expected.

But start with asking whether the patient has seen a health care professional for their issue or are they handling it themselves?
Then, start with one clinical question at a time, to discern the "Recovery Status" of the patient. 

Make your questions more emotional and empathetic to make the user feel comfortable and open up to you.
Remember that the patient may be in a vulnerable state and may not be able to express themselves clearly. Be patient and understanding.
Also, ask only one question at a time. Do not ask multiple questions in one go.

Sample conversation:
ai: Last we talked, you were having a headache. Is it better, worse or the same?
user: It's better, thanks!
ai: Great to hear that. Have you seen a doctor for this issue? Or are you handling it yourself?
user: No, I haven't seen a doctor.
ai: Okay. How is your sleep? Are you able to sleep well?
user: I do have headaches at night.
ai: Sorry to hear that. Do you have it every night? Or is it only on some nights?
user: It's almost every night.
ai: Looks like you are not getting better. I would recommend you to see a doctor.
"""
        response = self.llm([SystemMessage(content=prompt)] + self.conv_hist)
        self.conv_hist.append(response)
        return True

    def identify_status_of_problem(self):
        prompt = f"""
You are talking to a patient, who is experiencing the issue: {self.state.chief_complaint}.
Based on the conversation history, your job is to identify the status of the patient's problem, and generate a final guidance message to the patient.
The status of the problem can be all better, healing as expected or not healing as expected and requires escalation to urgent care or ED.
The guidance message should follow the pattern below:

Guidance should contain the following components:

1. Assessment and acknowledgment of the user’s perspective.
Check if the initial self assessment answer (all better, same or worse) aligns with the later parts of the conversation followup.
If aligned, then you can deliver your recovery status message without acknowledging the user’s perspective. However, if there is a misalignment, then you must acknowledge the user perspective. For example,  if the patient selects “All better” but later says that they are still having minor headaches at night, you’ll need to acknowledge the user’s perspective like this: "{self.state.patient_name}, I’m glad you’re feeling much better, but it seems to me that you’re still recovering from your headache".

2. Provide care guidance.
If off the expected course and has seen a doctor, encourage to return to doctor.
If off the expected course and has not seen a doctor, make clear that now is the time to see a doctor.

3. Set expectations
I will check in with you again to see how you are doing.

4. Sign off with empathy. 
I hope you feel better soon.


Your output should be a JSON with the following keys:
guidance: str (A message to the patient)
status_of_problem: enum (all_better, healing_as_expected, not_healing_as_expected)

Sample output:
{{
    "guidance": "{self.state.patient_name}, I'm sorry to hear that you are not feeling better. However, based on what you’ve told me, it sounds like you’re recovering from your headache. Make sure you see a doctor if you are not feeling better soon. I will check in with you again to see how you are doing. I hope you feel better soon.",
    "status_of_problem": "healing_as_expected"
}}
"""
        llm = CustomChatOpenAI(state=self.state)
        response = llm([SystemMessage(content=prompt)] + self.conv_hist, response_format={"type": "json_object"})
        self.conv_hist.append(response)
        response:dict = json.loads(response.content)
        response['guidance'] = response.get('guidance', 'I hope you feel better soon.') # Default to I hope you feel better soon.
        response['status_of_problem'] = response.get('status_of_problem', 'not_healing_as_expected') # Default to not_healing_as_expected

        FollowupCare.update_followup_outcome(convo_id=self.state.username, outcome=response['status_of_problem'])
        self.state.analytics_state = None

        self.llm.stream_callback.on_llm_new_token(response['guidance']+ "\n\n\n")
        self.state.concierge_option = 'detailed'
        self.state.next_agent(name=agents.ConciergeAgent.name, reset_hist=True)
        return False


