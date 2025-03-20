import random
import uuid
from datetime import datetime

import openai
import requests
from dspy import LM
from openai import OpenAI


class ChatLM:
    def __init__(self, model_type="insight"):
        self.model_type = model_type

    def completion(self, structured_output=False, stream=False, **kwargs):
        if self.model_type == "openai":
            model = kwargs.pop("model", "gpt-4o")
            messages = kwargs.pop("messages", [])
            if structured_output:
                api_key = kwargs.pop("api_key", None)
                client = OpenAI(api_key=api_key)
                return client.beta.chat.completions.parse(
                    model=model, messages=messages, **kwargs
                )
            else:
                completion = openai.chat.completions.create(
                    model=model, messages=messages, **kwargs
                )
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
        endpoint="v1/chat/completions",
        **kwargs,
    ):
        super().__init__(model=model, cache=cache, **kwargs)
        self.api_key = api_key
        self.stream = stream
        self.endpoint = endpoint
        self.kwargs = kwargs
        self.cache = cache
        self.history = []
        self.global_history = []
        # add temperature key in kwargs if not present
        if "temperature" not in self.kwargs:
            self.kwargs["temperature"] = 0.7

        self.host = f"https://mindrouter-api.nkn.uidaho.edu/{self.endpoint}"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def request(self, messages=None, **kwargs):
        data = {
            "model": self.model,
            "messages": messages,
            "stream": self.stream,
            **kwargs,
        }

        response = requests.post(self.host, json=data, headers=self.headers)

        if response.status_code != 200:
            print("Error: ", response.text)
            return None
        response = response.json()
        if response.get("error") == "No instances available for model":
            data["model"] = random.choice(
                ["mistral-large:123b", "qwen2.5:72b", "llama3.2:3b"]
            )
            response = requests.post(self.host, json=data, headers=self.headers)
            response = response.json()
        print("chat response: ", response)

        return response

    def __call__(self, prompt=None, messages=None, **kwargs):
        # Build the request.
        kwargs.pop("cache", self.cache)
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

        print("outputs: ", outputs)
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

        return outputs
