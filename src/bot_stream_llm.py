import logging
import os
import queue
import re
from typing import Any

from langchain.callbacks.base import BaseCallbackHandler
from langchain.callbacks.openai_info import standardize_model_name, get_openai_token_cost_for_model
from langchain.chat_models import ChatOpenAI
from langchain.schema import ChatGeneration
from langchain.schema.messages import BaseMessage, AIMessage

from src.bot_conv_hist import BotConvHist
from src.bot_state import BotState
from src.utils import fake_llm


class ThreadedGenerator:
    def __init__(self):
        self.queue = queue.Queue()

    def __iter__(self):
        return self

    def __next__(self):
        item = self.queue.get()
        if item is StopIteration:
            raise item
        return item

    def send(self, data):
        self.queue.put(data)

    def close(self):
        self.queue.put(StopIteration)


class StreamCallback(BaseCallbackHandler):
    def __init__(self, gen: ThreadedGenerator, full_conv_hist: BotConvHist):
        self.gen = gen
        self.full_conv_hist = full_conv_hist

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.full_conv_hist.append_token(token)
        # Splitting the token on spaces to ensure better streaming effect.
        chunks = re.split(r'(\s+)', token)
        for chunk in chunks:
            self.gen.send(chunk)

    @property
    def ignore_retry(self) -> bool:
        return True


class CustomChatOpenAI:
    """
    Custom ChatOpenAI object, created for the sole purpose of tracking the API tokens and costs.
    Hence, it is essential to pass the BotState object to this class, for tracking the costs.
    """

    def __init__(self, state: BotState, **kwargs):
        self.state = state
        self.llm_kwargs = kwargs
        # Add additional parameters in llm_kwargs
        if 'temperature' not in self.llm_kwargs:
            self.llm_kwargs['temperature'] = 0
        if 'max_retries' not in self.llm_kwargs:
            self.llm_kwargs['max_retries'] = 2
        if 'request_timeout' not in self.llm_kwargs:
            self.llm_kwargs['request_timeout'] = 15
        if 'model' not in self.llm_kwargs:
            self.llm_kwargs['model'] = 'gpt-3.5-turbo'

    def __call__(self, *args, prompt_test: bool = False, inputs=None, **llm_call_kwargs: Any) -> BaseMessage:
        # Extract from args
        conv_hist = args[0]

        use_fake_llm = os.getenv('FAKE_LLM', 'False').lower() == 'true'

        if use_fake_llm:
            llm = fake_llm
        else:
            llm = ChatOpenAI(**self.llm_kwargs)

        if prompt_test:
            _prompt_test(conv_hist=conv_hist,
                         llm_kwargs=self.llm_kwargs,
                         inputs=inputs,
                         **llm_call_kwargs)

        llm_result = llm.generate([conv_hist], **llm_call_kwargs)
        generations_ = llm_result.generations[0][0]

        # check if generations_ is of type ChatGeneration
        if isinstance(generations_, ChatGeneration):
            # typecast to ChatGeneration
            response = generations_.message
        else:
            if fake_llm:
                response = AIMessage(content=generations_.text.strip(),
                                     additional_kwargs=fake_llm.get_additional_kwargs())
            else:
                response = generations_.text

        # Calculating tokens
        if isinstance(llm, ChatOpenAI):
            prompt_tokens = llm.get_num_tokens_from_messages(conv_hist)
            completion_tokens = llm.get_num_tokens_from_messages([response])

            # Calculating cost
            model_name = standardize_model_name(llm.model_name)
            prompt_cost = get_openai_token_cost_for_model(
                model_name, prompt_tokens)
            completion_cost = get_openai_token_cost_for_model(
                model_name, completion_tokens, is_completion=True
            )
            cost = prompt_cost + completion_cost
            logging.debug(f"Prompt tokens: {prompt_tokens}")
            logging.debug(f"Completion tokens: {completion_tokens}")
            logging.debug(f"Cost: {cost}")
        else:
            prompt_tokens = 0
            completion_tokens = 0
            cost = 0

        # Updating state
        if self.state is not None:
            self.state.total_cost += cost
            self.state.prompt_tokens += prompt_tokens
            self.state.completion_tokens += completion_tokens
            self.state.max_token_count = max(
                self.state.max_token_count, prompt_tokens + completion_tokens
            )
            self.state.successful_requests += 1
        return response


class StreamChatOpenAI:
    def __init__(self,
                 state: BotState = None,
                 gen: ThreadedGenerator = ThreadedGenerator(),
                 full_conv_hist: BotConvHist = None,
                 **kwargs):
        self.streaming = os.getenv('STREAMING', 'True').lower() == 'true'
        self.stream_callback = StreamCallback(
            gen=gen, full_conv_hist=full_conv_hist)
        self.llm = CustomChatOpenAI(state=state, callbacks=[
                                    self.stream_callback], streaming=self.streaming, **kwargs)

    def __call__(self, *args, **kwargs: Any) -> BaseMessage:
        response = self.llm.__call__(*args, **kwargs)
        if not self.streaming:
            logging.info("Switching to non streaming mode temporarily")
            self.stream_callback.on_llm_new_token(response.content)
        return response


def _prompt_test(conv_hist, llm_kwargs, times=100, inputs=None, **llm_call_kwargs):
    """
    Function solely for the purpose of internal dev prompt testing.
    Maybe in the future, we can think of opening this up to business."""
    import threading
    llm_kwargs['max_retries'] = 0
    results = []

    def run_llm(conv_hist, seed):
        llm = ChatOpenAI(**llm_kwargs)
        llm_call_kwargs['seed'] = seed
        response = llm(conv_hist, **llm_call_kwargs)
        results.append(response)
    all_conv_hists = []
    if inputs is not None:
        all_conv_hists = [conv_hist[:-1] +
                          [AIMessage(content=input)] for input in inputs]
        times = len(inputs)
    else:
        all_conv_hists = [conv_hist] * times

    threads = []
    for i in range(times):
        threads.append(threading.Thread(
            target=run_llm, args=(all_conv_hists[i], i)))
        threads[-1].start()
    logging.info('Started all threads')

    for t in threads:
        t.join()

    import pandas as pd
    list_of_dicts = []
    list_of_strings = []
    list_of_func_calls = []
    for r in results:
        try:
            import json
            list_of_dicts.append(json.loads(r.content))
        except:
            list_of_strings.append(r.content)
            list_of_func_calls.append(
                str(r.additional_kwargs.get('function_call', '')))
            pass
    df = pd.DataFrame(list_of_dicts)
    print('-------------------')
    for key in df.keys():
        print(df[key].value_counts())
    print(pd.DataFrame(list_of_strings).value_counts())
    print(pd.DataFrame(list_of_func_calls).value_counts())
    print('-------------------')
    return results[0]
