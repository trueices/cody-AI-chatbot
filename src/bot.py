import logging
import re
import threading
import traceback
from typing import List, Type

from openai.error import Timeout as OpenAITimeout

from src import agents
from src.bot_conv_hist import BotConvHist
from src.bot_state import BotState
from src.bot_stream_llm import ThreadedGenerator, StreamChatOpenAI
from src.followup.followup_care import FollowupCare
from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup
from src.utils import map_url_name, demo_mode
from src.agents.cody_care_agent import FORCE_LOGIN_MSG

class Bot:
    def __init__(self,
                 username: str,
                 profile: dict = None,
                 ip_address: str = None):
        # Initializing the bot state.
        self.state = BotState(username=username)

        self.state.ip_address = ip_address

        self.full_conv_hist = BotConvHist(conversation_id=username)

        # Initializing stream and llm for the bot.
        self.stream = ThreadedGenerator()
        self.llm = StreamChatOpenAI(gen=self.stream, state=self.state, full_conv_hist=self.full_conv_hist)

        # Eventually we might want to have this profile itself to be persisted on bot state but YAGNI for now.
        # Since only thing we need now is name to profile which is already persisted on bot state.
        self._profile_bot(profile)

        self.agents: List[Type[agents.Agent]] = [
            agents.NavigationAgent,
            agents.ChiefComplaintAgent,
            agents.RouterAgent,
            agents.NameEnquiryAgent,
            agents.FollowupAgent,
            agents.MagicMinuteAgent,
            agents.DiagnosisAgent,
            agents.ConciergeAgent,
            agents.TreatmentAgent,
            agents.FindCareAgent,
            agents.FeedbackAgent,
            agents.EndAgent,
            agents.AdDemoAgent,
            agents.FollowupCareAgent,
            agents.DxConversationAgent,
            agents.TxConversationAgent,
            agents.QuestionAgent,
            agents.ExistingDiagnosisAgent,
            agents.CodyCareAgent,
        ]
        self.state.agent_names = [agent.name for agent in self.agents]
        # Initialize the conversation history for each agent, if not already present.
        for agent_name in self.state.agent_names:
            if agent_name not in self.state.conv_hist:
                self.state.conv_hist[agent_name] = []

        # Finally, initialize all the agents.
        self.agents = [agent(state=self.state, llm=self.llm, profile=profile) for agent in self.agents]

        if self.state.current_agent_name is None:
            self.state.current_agent_name = self.state.agent_names[0] # Start with NavigationAgent
        # Set current agent index according to name.
        self.state.current_agent_index = self.state.agent_names.index(self.state.current_agent_name)

        # This covers cases when the user had previously started a conversation using 
        # an earlier version of bot, but history is not yet persisted in the full_conv_hist.
        if len(self.state.get_conv_hist()) > 1 and self.full_conv_hist.full_conv_hist == []:
            self.full_conv_hist.full_conv_hist = self.state.get_conv_hist()
            self.update_conv()

        assert len(self.agents) == len(set(self.state.agent_names)), 'Number of agents and agent names do not match.'

        # If convo is eligible
        if FollowupCare.is_profile_followup_eligible(state=self.state, profile=profile):
            # Clear up the convo history for followup care
            self.state.conv_hist[agents.FollowupCareAgent.name][:] = []
            # Find followup care agent index
            index = self.state.agent_names.index(agents.FollowupCareAgent.name)
            # call greeting method of followup care agent
            self.agents[index].greeting(stream=False)
            # Confirming that the followup is initiated only when the OpenAI call is successful
            # and response is sent. If the call fails, the followup is not marked initiated.
            FollowupCare.mark_followup_initiated(convo_id=self.state.username)
            # Next agent should be the followup care agent
            self.state.next_agent(name=agents.FollowupCareAgent.name)
            # Save the state
            self.update_conv()

        # last convo history of agent has force login message
        elif profile and profile.get('email') and \
                self.state.current_agent_name == agents.FindCareAgent.name and \
                len(self.state.conv_hist[agents.FindCareAgent.name]) > 0 and \
                "to view the best doctors near you" in self.state.conv_hist[agents.FindCareAgent.name][-1].content:
            index = self.state.agent_names.index(agents.FindCareAgent.name)
            self.agents[index].find_care(True)
            self.update_conv()
        
        elif profile and profile.get('email') and \
                self.state.current_agent_name == agents.CodyCareAgent.name and \
                len(self.state.conv_hist[agents.CodyCareAgent.name]) > 0 and \
                FORCE_LOGIN_MSG in self.state.conv_hist[agents.CodyCareAgent.name][-1].content:
            self._ask(user_input='')

    def _ask(self,
             user_input: str = None,
             update_db: bool = True,
             raise_exception: bool = True) -> None:
        try:
            # Update the conversation history after the human input.
            self.update_conv(update_db, user_input)

            if user_input and self.state.mode == '' and demo_mode(user_input):
                self.state.mode = user_input
                self.llm.stream_callback.on_llm_new_token(
                    f'Received your request for {user_input}. Please continue with the convo.')
                self.update_conv(update_db)  # Update the conversation history
                self.stream.close()  # Close the stream.
                return

            counter: int = 0

            while True:
                input_req = self.agents[self.state.current_agent_index].act()
                self.update_conv(update_db)
                if input_req is not False:  # continue only if input_req is False
                    break
                # Prevent infinite loops.
                counter += 1
                if counter > 5:
                    logging.error("Looping too much, exiting")
                    break
            self.stream.close()

        except OpenAITimeout as e:
            logging.warning("Timeout error captured:" + re.escape(str(e)), exc_info=e)
            self.llm.stream_callback.on_llm_new_token(
                '\n\n\nSorry, that took too long to process for us. Can you please type that again?')
            self.state.timeouts += 1
            self.update_conv(update_db)
            self.stream.close()

        except Exception as e:
            extra_info = {'username': self.state.username}
            logging.error("Unknown error captured: " + re.escape(str(e)), exc_info=e, extra=extra_info)
            self.llm.stream_callback.on_llm_new_token('\n\n\nSorry, there was an issue on our end. Can you please type '
                                                      'that again?')
            # We are trying to capture the traceback here and add it to mongo state. This will help us debug the issue better.
            # Later, we can fix the issues and backfill the state.
            trace = [e for e in traceback.TracebackException.from_exception(e).format()]
            trace.reverse()
            trace = trace[:4]  # 4 lines of traceback should be enough.
            self.state.errors.append(trace)
            self.state.error_types.append(trace[0].split(':')[0])
            self.update_conv(update_db)
            self.stream.close()
            if raise_exception:
                raise e

    def _profile_bot(self, profile):
        if profile:
            name = profile.get('name', None)

            if name is not None:
                self.state.patient_name = name

            character = profile.get('character', None)

            # only if the character hasn't been set yet
            if self.state.specialist is Specialist.Generalist and \
                    self.state.subSpecialty is SubSpecialtyDxGroup.Generalist and \
                    character is not None:
                self.state.specialist, self.state.subSpecialty = map_url_name(character)
                self.state.character_src = 'AOV'

            if profile.get('longitude', None) and profile.get('latitude', None):
                self.state.set_location(profile['longitude'], profile['latitude'])

    def ask(self, *args, **kwargs):
        # We dont want unhandled exceptions to crash the server.
        # Hence, we will log exceptions on the server, but not raise them.
        kwargs['raise_exception'] = False
        threading.Thread(target=self._ask, args=args, kwargs=kwargs).start()
        return self.stream

    def get_conv_hist(self) -> List[dict]:
        return self.full_conv_hist.full_conv_hist

    def update_conv(self, update_db: bool = True, user_input: str = None):
        """
        Upserts data to the database and updates the last human input if required.

        Args:
            update_db (bool): Whether to update the database or not.
            user_input (str, optional): The user input to be updated. Defaults to None.
        """
        if user_input is not None:
            self.full_conv_hist.full_conv_hist.append({'role': 'user', 'content': user_input})
            self.state.last_human_input = user_input

        if update_db:
            self.state.upsert_to_db()
            self.full_conv_hist.upsert_to_db()
