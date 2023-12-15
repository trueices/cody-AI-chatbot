import logging
import textwrap
from typing import Type

from bs4 import BeautifulSoup
from langchain.schema import AIMessage, HumanMessage, SystemMessage
from langchain.tools import BaseTool
from langchain.tools.render import format_tool_to_openai_function
from pydantic import BaseModel, Field

from src import agents
from src.ad.provider import Provider
from src.agents.utils import parse_feedback_rating, check_function_call
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI
from src.care.care_provider import CareSearch
from src.care.care_provider_renderer import CareProviderRenderer
from src.specialist import Specialist


class ToolCheck(BaseModel):
    address: str = Field(..., description='The address of the user to find care')
    pass


class FindCareAddressTool(BaseTool):
    name = 'find_care_address_tool'
    description = 'the address of the user to find care. It can be a complete address or city or any nearby landmark.'
    args_schema: Type[BaseModel] = ToolCheck

    def _run(self, address) -> str:
        return 'Address captured'

class FindCareAgent(agents.Agent):
    name = 'find_care_agent'
    FEEDBACK_QUESTION = "Please rate doctor location on a scale of 1 to 5 where 1 means the locations are very far from you and 5 means the locations are very near you."
    tools = [FindCareAddressTool()]
    care_provider_renderer = CareProviderRenderer()

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None) -> None:
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]
        self.profile = profile

    def act(self) -> bool:
        if self.state.next_agent_name == agents.ExistingDiagnosisAgent.name:
            return self.handle_find_care_existing_dx()

        if self.profile is None or not self.profile.get('isLoggedIn', False):
            FORCE_LOGIN_MESSAGE = f"""Please <a class="text-blue underline app-link" href="/sign-in">login</a> or <a class="text-blue underline app-link" href="/register">create an account</a> to view the best doctors near you.

Why create a Free Cody account?

It’s free, secure and gives you many healthy goodies like:
- Find the best doctor
- Cody checks in on you
- Customize Cody
- Save and Share Conversations
And more…
"""
            self.llm.stream_callback.on_llm_new_token(FORCE_LOGIN_MESSAGE)
            self.conv_hist.append(AIMessage(content=FORCE_LOGIN_MESSAGE))
            return True
        else:
            return self.find_care()

    def handle_find_care_existing_dx(self) -> bool:
        # find care
        response, self.conv_hist = agents.FindCareAgent.get_llm_response(dx_name=self.state.existing_dx,
                                                                         human_input=self.state.last_human_input,
                                                                         address=self.state.address,
                                                                         conv_hist=self.conv_hist,
                                                                         llm=self.llm)
        self.conv_hist.append(response)

        # Checking if a function call was made
        function_response, arguments = check_function_call(
            response, agents.FindCareAgent.tools)

        if function_response is None:
            return True
        else:
            # Add the response to the conversation memory
            self.conv_hist.append(function_response)
            address_ = arguments['address']
            self.state.address = address_
            msg, has_search_result = agents.FindCareAgent._lookup_find_care(address_=self.state.address,
                                                                            dx_name=self.state.existing_dx, tx_plan='',
                                                                            username=self.state.username,
                                                                            errors=self.state.errors_care,
                                                                            specialist=self.state.specialist)

            self.conv_hist.append(AIMessage(content=msg))
            self.llm.stream_callback.on_llm_new_token(
                self.conv_hist[-1].content)
            # if no search result, then offer user to try again with new address
            if not has_search_result:
                self.state.next_agent(
                    name=agents.FindCareAgent.name, reset_hist=False)
                self.state.next_agent_name = agents.ExistingDiagnosisAgent.name
                return True
            else:
                self.state.next_agent(
                    name=agents.ExistingDiagnosisAgent.name, reset_hist=True)
                return False


    def find_care(self, on_load: bool = False) -> bool:
        ad: str = Provider(self.state.mode).find_care()
        if ad != "":
            self.conv_hist.append(AIMessage(content=ad))
            self.llm.stream_callback.on_llm_new_token(self.conv_hist[-1].content)
            self.state.next_agent(name=agents.AdDemoAgent.name, reset_hist=True)
            return True
        else:
            treatment_index = int(self.state.treatment_plans_seen[-1]) - 1
            dx_name = self.state.diagnosis_list[treatment_index]

            # check if last AI message in convo history has feedback question
            if len(self.conv_hist) > 0 and FindCareAgent.FEEDBACK_QUESTION in self.conv_hist[-1].content:
                self.state.care_feedback_rating = parse_feedback_rating(
                    self.state.last_human_input)
                msg = "Thank you for the valuable feedback!\n\n\n"
                self.conv_hist.append(HumanMessage(
                    content=self.state.last_human_input))
                self.conv_hist.append(AIMessage(content=msg))
                self.llm.stream_callback.on_llm_new_token(self.conv_hist[-1].content)
                self.state.next_agent(name=agents.ConciergeAgent.name, reset_hist=True)
                return False

            if on_load:
                self.conv_hist.append(AIMessage(
                    content=f"""\n\n\nThanks for logging in.

Please let me know your address to find the best doctor nearest you."""))
                self.llm.stream_callback.on_llm_new_token(self.conv_hist[-1].content)
                return True

            response, self.conv_hist = self.get_llm_response(dx_name=dx_name, human_input=self.state.last_human_input,
                                                             address=self.state.address, conv_hist=self.conv_hist, llm=self.llm)
            self.conv_hist.append(response)

            # Checking if a function call was made
            function_response, arguments = check_function_call(response, self.tools)

            if function_response is None:
                return True
            else:
                # Add the response to the conversation memory
                self.conv_hist.append(function_response)
                self.state.address = arguments['address']
                tx_plan = self.state.treatment_plans.get(str(self.state.treatment_plans_seen[-1]))
                msg, has_search_result = self._lookup_find_care(self.state.address, dx_name, tx_plan, self.state.username,
                                                                errors=self.state.errors_care, specialist=self.state.specialist)

                self.conv_hist.append(AIMessage(content=msg))
                self.llm.stream_callback.on_llm_new_token(
                    self.conv_hist[-1].content)

                # If feedback is not collected, and least one care option is found, collect feedback
                if self.state.care_feedback_rating is None and has_search_result:
                    return self._feedback_collection()
                # if no search result, then offer user to try again with new address
                elif not has_search_result:
                    self.state.next_agent(
                        name=agents.FindCareAgent.name, reset_hist=False)
                    return True
                else:
                    # If feedback is collected, go to the next agent
                    self.state.next_agent(
                        name=agents.ConciergeAgent.name, reset_hist=True)
                    return False

    @staticmethod
    def _lookup_find_care(address_, dx_name, tx_plan, username, errors:list[str], specialist:Specialist) -> tuple[str, bool]:
        search_result = True
        # Striping out abbreviation if DX has one
        dx_name = dx_name.split('(')[0].strip()
        
        # Parse the HTML content
        soup = BeautifulSoup(tx_plan, "html.parser")
        search_terms = []
        # Find the value of a specific HTML tag
        care_options_tag = soup.find_all("ul", limit=1)
        all_referrals = care_options_tag[0].find_all("li") if len(care_options_tag) > 0 else []
        for referral in all_referrals:
            if referral.find("b") is not None:
                ref = referral.find("b").text
            else:
                logging.warning(
                    f'One of the Referral tag not found in bold for convo id {username}. This means '
                    f'llm messed up responding correctly. tag: {referral}')
                ref = referral.text
            # Sometime llm responds with when there is no specialist referral
            # remove string called Specialist from search terms
            if ref != 'Specialists' and ref != 'Primary Care':
                search_terms.append(ref.lower())
        if len(search_terms) == 0:
            search_terms.append(specialist.inventory_name.lower())
        search_terms.append(dx_name.lower())
        search_terms.append('near ' + address_)
        search = CareSearch(search_terms=search_terms)
        try:
            logging.info(f'Finding care for convo id {username} with search terms {search_terms}')
            msg = agents.FindCareAgent.care_provider_renderer.render(search)

            # Google search api behaves weirdly when specialist is passed together with primary care.
            # So we first try to find care with specialist and then with primary care.
            if msg == "":
                logging.info(
                    f'Falling back to primary care for convo id {username} with search terms {dx_name.lower()}')
                msg = agents.FindCareAgent.care_provider_renderer.render(
                    CareSearch(search_terms=[dx_name.lower(), 'doctor', 'near ' + address_])
                    if address_ else CareSearch(search_terms=[dx_name.lower(), 'doctor']))

        except Exception as e:
            logging.error(f'Unable to find care for convo id {username} with message {str(e)}',
                          exc_info=e)
            errors.append(type(e).__name__)
            msg = "Sorry, I couldn't find any care options for you. Please try again by providing another address."
            search_result = False
        if msg == "":
            logging.info(f'Could not find care for convo id {username}.')
            msg = "Sorry, I couldn't find any care options for you. Please try again by providing another address."
            search_result = False
        msg += "\n\n\n"
        return msg, search_result

    def _feedback_collection(self):
        self.conv_hist.append(AIMessage(content=FindCareAgent.FEEDBACK_QUESTION))
        self.llm.stream_callback.on_llm_new_token(self.conv_hist[-1].content)
        return True
    
    @staticmethod
    def get_llm_response(dx_name: str, human_input: str, address: str, conv_hist: list[dict], llm: StreamChatOpenAI):
        system_prompt = textwrap.dedent(f"""
        Your job is to ask user about about the address of the patient where they are looking to find doctors for 
        the diagnosis {dx_name.lower()}.
        
        Your job has 3 parts:
        1. Ask users address where they are looking to find doctors for the diagnosis {dx_name.lower()}.
        2. Confirm with the patient if they want to continue with the address.
        3. If confirmed, call the {FindCareAddressTool().name}. If not confirmed, ask the patient to clarify the 
        address.
        
        If user asks explicitly why, Explain to the user that the address is needed to find the best doctors near 
        the patient. Full address is not needed, either city or nearby landmarks will work.
        
        Instructions: - Do not try to provide any answers to the health problem. If the user asks for answers, 
        just say that "I will need the address to find best doctors near you." 
        - Do not call the {FindCareAddressTool().name} without the user's confirmation.
        - Keep your outputs under one or two sentences.
        - The user should not know that you called the {FindCareAddressTool().name} tool. Do it discretely.
        
        Example conversation:
        AI: May I know your address or city and state to find the best doctors near you?
        Human: Sure, Its 1234 Main St, New York, NY 10001
        AI: Should I proceed with the address 1234 Main St, New York, NY 10001?
        Human: Yes
        then, the AI calls the {FindCareAddressTool().name} discretely, with the address identified as "1234 Main St, New York, NY 10001".
        End of example conversation.
        """)

        if len(conv_hist) != 0:
            conv_hist.append(HumanMessage(content=human_input))

        if address and len(conv_hist) == 0:
            conv_hist.append(AIMessage(content=f"May I know your address or city and state to find the best doctors near you?"))
            conv_hist.append(HumanMessage(content=address))

        response = llm([SystemMessage(content=system_prompt)] + conv_hist[-5:], functions=[
            format_tool_to_openai_function(tool) for tool in agents.FindCareAgent.tools])
        return response, conv_hist
