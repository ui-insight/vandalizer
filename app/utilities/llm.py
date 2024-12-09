import sys
import json
import requests
from multiprocessing.pool import ThreadPool
import re
from dspy import LM
from datetime import datetime
import uuid
import openai
from openai import OpenAI


class ChatLM:
    def __init__(self, model_type="insight"):
        self.model_type = model_type

    def completion(self, structured_output=False, stream=False, **kwargs):
        if self.model_type == "openai":
            if structured_output:
                api_key = kwargs.pop("api_key", None)
                client = OpenAI(api_key=api_key)
                return client.beta.chat.completions.parse(**kwargs)
            else:
                completion = openai.chat.completions.create(**kwargs)
                output = completion.choices[0].message.content
                return output
        lm = InsightLM()
        response = lm(stream=stream, **kwargs)
        return response


class InsightLM(LM):
    def __init__(
        self,
        model="llama3.3:70b",
        api_key=None,
        cache=None,
        stream=False,
        **kwargs,
    ):
        super().__init__(model=model, cache=cache, **kwargs)
        self.api_key = api_key
        self.kwargs = kwargs
        self.cache = cache
        self.history = []
        self.global_history = []

    def request(self, messages=None, endpoint="v1/chat/completions", **kwargs):

        url = f"https://mindrouter-api.nkn.uidaho.edu/{endpoint}"
        data = {
            "model": self.model,
            "messages": messages,
            "stream": kwargs.get("stream", False),
            **kwargs,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        response = requests.post(url, json=data, headers=headers)

        if response.status_code == 200:
            return response.json()
        else:
            print("SERVER ERROR")
            print(response.status_code)
            print(response.text)
            return None

    def __call__(self, prompt=None, messages=None, **kwargs):
        # Build the request.
        cache = kwargs.pop("cache", self.cache)
        messages = messages or [{"role": "user", "content": prompt}]
        kwargs = {**self.kwargs, **kwargs}

        # Make the request and handle LRU & disk caching.
        response = self.request(messages=messages, **kwargs)
        if response is None:
            return None

        outputs = []
        if response.get("choices") is None:
            outputs = response["message"]["content"]
        else:
            outputs = [c["message"]["content"] for c in response["choices"]][0]

        # Logging, with removed api key & where `cost` is None on cache hit.
        kwargs = {k: v for k, v in kwargs.items() if not k.startswith("api_")}
        entry = dict(prompt=prompt, messages=messages, kwargs=kwargs, response=response)
        if response.get("usage"):
            entry = dict(**entry, outputs=outputs, usage=dict(response["usage"]))
        if response.get("response_cost"):
            entry = dict(
                **entry, cost=response.get("_hidden_params", {}).get("response_cost")
            )
        entry = dict(
            **entry,
            timestamp=datetime.now().isoformat(),
            uuid=str(uuid.uuid4()),
            model=self.model,
            model_type=self.model_type,
        )
        self.history.append(entry)
        self.update_global_history(entry)

        return outputs
