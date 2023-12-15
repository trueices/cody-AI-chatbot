import logging
import os
from textwrap import dedent
from urllib.parse import urlparse

from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain.utilities.google_serper import GoogleSerperAPIWrapper
from numpy.core.defchararray import lower

from src import agents
from src.ad.provider import Provider
from src.bot_state import BotState
from src.bot_stream_llm import StreamChatOpenAI
from src.utils import demo_mode

os.environ["SERPER_API_KEY"] = os.getenv('SERPER_API_KEY', 'NA')


class TreatmentAgent(agents.Agent):
    name = 'treatment_agent'

    ORGANIC_CONTENT_TEMPLATE_WITH_DATE = dedent(
        """\
        <li><a class="text-blue underline" href="{website}" target="_blank">{title}</a>
        <p>
        {date}
        <br>
        {root_domain}
        <br>
        {snippet}
        </p>
        </li>
        """)

    ORGANIC_CONTENT_TEMPLATE_WITHOUT_DATE = dedent(
        """\
        <li><a class="text-blue underline" href="{website}" target="_blank">{title}</a>
        <p>
        {root_domain}
        <br>
        {snippet}
        </p>
        </li>
        """)

    def __init__(self, state: BotState, llm: StreamChatOpenAI, profile: dict = None):
        self.state = state
        self.llm = llm
        self.conv_hist = self.state.conv_hist[self.name]

    def act(self) -> bool:
        # Checking if the flow comes from the existing diagnosis agent.
        if self.state.next_agent_name == agents.ExistingDiagnosisAgent.name:
            if self.state.existing_dx_tx == '':
                tx_plan = self.generate_treatment_plan(llm=self.llm,
                                                       disease_name=self.state.existing_dx,
                                                       mode=self.state.mode)
                self.state.existing_dx_tx = tx_plan.content
            else:
                self.llm.stream_callback.on_llm_new_token(
                    self.state.existing_dx_tx)
            self.llm.stream_callback.on_llm_new_token("\n\n\n")
            self.state.next_agent(reset_hist=True)
            return False

        options = "\n".join([f"{i + 1}. {disease.title()}" for i,
                            disease in enumerate(self.state.diagnosis_list)])

        if len(self.conv_hist) == 0:
            return self._custom_msg(f"Ok, to view a treatment plan enter the number of the diagnosis.\n{options}")
        else:
            # append the last human input to the conversation history
            self.conv_hist.append(HumanMessage(
                content=self.state.last_human_input))
            if self.state.last_human_input.strip().lower() in ['options', 'option']:
                self.state.concierge_option = 'detailed'
                self.state.next_agent(
                    name=agents.ConciergeAgent.name, reset_hist=True)
                return False
            else:
                response_number = self._process_tx_input(options)
                if response_number != 0:
                    return self._handle_tx_options(response_number, options)
                else:
                    return True

    def _handle_tx_options(self, number, options):
        if number not in [1, 2, 3]:
            return self._custom_msg('Please select a valid disease number.')
        elif number in [int(i) for i in self.state.treatment_plans_seen]:
            plan = self.state.treatment_plans[str(number)]
            self._custom_msg(plan + '\n\n\n')
            self.state.concierge_option = 'find_care'
            self.state.next_agent(
                name=agents.ConciergeAgent.name, reset_hist=True)
            return False
        else:
            self.state.treatment_plans_seen.append(number)
            treatment_plan = self.generate_treatment_plan(llm=self.llm,
                                                          disease_name=self.state.diagnosis_list[number-1],
                                                          mode=self.state.mode)
            # treatment_plans is a dict due to legacy reasons
            self.state.treatment_plans[str(number)] = treatment_plan.content
            self.conv_hist.append(treatment_plan)
            self._custom_msg('\n\n\n')
            self.state.concierge_option = 'find_care'
            self.state.next_agent(
                name=agents.ConciergeAgent.name, reset_hist=True)
            return False

    def _custom_msg(self, msg):
        custom_message = AIMessage(content=msg)
        self.llm.stream_callback.on_llm_new_token(custom_message.content)
        self.conv_hist.append(custom_message)
        return True  # Because all the custom messages should be followed by a human input

    @staticmethod
    def generate_treatment_plan(llm: StreamChatOpenAI, disease_name: str, mode: str):
        # Read from the treatment plan file
        with open(f"{os.path.dirname(__file__)}/tx-plan-prompt.html", 'r') as f:
            prompt = f.read()
        div_header = "<div class='tx-plan'>"
        div_footer = "</div>"
        llm.stream_callback.on_llm_new_token(div_header)
        response = llm([SystemMessage(content=prompt),
                       AIMessage(content=disease_name)])

        # Only render dynamic content for real patients
        demo_match = demo_mode(mode)

        if not demo_match:
            try:
                results = GoogleSerperAPIWrapper().results(
                    disease_name + " treatment for patients")

                if results and len(results.get('organic')) > 0:
                    html_reference_result = f"</li></ul><h2>Best {lower(disease_name)} treatment references for you:</h2>"
                    llm.stream_callback.on_llm_new_token(html_reference_result)
                    response.content += html_reference_result
                    html_reference_result += "<ul>"

                    llm.stream_callback.on_llm_new_token("<ul>")
                    for result in results.get('organic')[:3]:
                        url = result.get('link')
                        parsed_url = urlparse(url)
                        root_domain = ''
                        if parsed_url is not None:
                            root_domain = parsed_url.netloc

                        if result.get('date', '') != '':
                            article = TreatmentAgent.ORGANIC_CONTENT_TEMPLATE_WITH_DATE.format(
                                website=url, title=result.get('title'), date=result.get('date', ''),
                                root_domain=root_domain, snippet=result.get('snippet'))
                        else:
                            article = TreatmentAgent.ORGANIC_CONTENT_TEMPLATE_WITHOUT_DATE.format(
                                website=url, title=result.get('title'), root_domain=root_domain,
                                snippet=result.get('snippet'))

                        html_reference_result += article
                        llm.stream_callback.on_llm_new_token(article)

                    html_reference_result += "</ul>"
                    response.content += html_reference_result
            except Exception as e:
                logging.error(
                    f"Error in fetching search results for {disease_name}", exc_info=e)
        else:
            logging.info(
                f"Skipping search results for {disease_name} as it's a demo patient")
            llm.stream_callback.on_llm_new_token(Provider(mode)
                                                 .treatment(disease_name))

        llm.stream_callback.on_llm_new_token(div_footer)
        response.content = div_header + response.content + div_footer
        return response

    def _process_tx_input(self, options):
        from src.agents.utils import process_nav_input
        number = process_nav_input(
            self.state.last_human_input, options, self.state)
        if number == 0:
            self.llm.stream_callback.on_llm_new_token(
                "Please type a valid option to view a treatment plan.")
        return number
