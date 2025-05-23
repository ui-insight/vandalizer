import random
import uuid
from datetime import datetime

import openai
import requests
import tiktoken
from devtools import debug
from openai import OpenAI

from app.models import UserModelConfig


class ChatLM:
    def __init__(self, model=None, user_id=None) -> None:
        model_type, model_name = "openai", "gpt-4o"
        if model is not None:
            self.model = model
            model_type, model_name = model.split("/")
        else:
            if user_id is not None:
                model_config = UserModelConfig.objects.first(user=user_id)
                self.model = model_config.name
                if model_config is not None:
                    model_type, model_name = model_config.name.split("/")

        self.model_type = model_type
        self.model_name = model_name
        debug(f"Model type: {self.model_type}")
        debug(f"Model name: {self.model_name}")

    def completion(self, structured_output=False, stream=False, **kwargs):
        if self.model_type == "openai":
            # model = kwargs.pop("model", "gpt-4o")
            messages = kwargs.pop("messages", [])
            if structured_output:
                api_key = kwargs.pop("api_key", None)
                client = OpenAI(api_key=api_key)
                return client.beta.chat.completions.parse(
                    model=self.model_name,
                    messages=messages,
                    **kwargs,
                )
            completion = openai.chat.completions.create(
                model=self.model,
                messages=messages,
                **kwargs,
            )
            return completion.choices[0].message.content
        lm = InsightLM()
        return lm(stream=stream, **kwargs)


class InsightLM:
    def __init__(
        self,
        model="llama3.3:70b",
        api_key=None,
        cache=None,
        stream=False,
        endpoint="v1/chat/completions",
        **kwargs,
    ) -> None:
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
            return None
        response = response.json()
        if response.get("error") == "No instances available for model":
            data["model"] = random.choice(
                ["mistral-large:123b", "qwen2.5:72b", "llama3.2:3b"],
            )
            response = requests.post(self.host, json=data, headers=self.headers)
            response = response.json()

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
            outputs = next(c["message"]["content"] for c in response["choices"])

        # Logging, with removed api key & where `cost` is None on cache hit.
        kwargs = {k: v for k, v in kwargs.items() if not k.startswith("api_")}
        entry = {
            "prompt": prompt,
            "messages": messages,
            "kwargs": kwargs,
            "response": response,
        }
        if response.get("usage"):
            entry = dict(**entry, outputs=outputs, usage=dict(response["usage"]))
        if response.get("response_cost"):
            entry = dict(
                **entry,
                cost=response.get("_hidden_params", {}).get("response_cost"),
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


def remove_code_markers(text: str) -> str:
    """Removes code block markers and language specifiers from LLM responses.

    Args:
        answer (str): The raw LLM response text

    Returns:
        str: Formatted text with code blocks and language specifiers removed

    """
    # Split the text into lines
    lines = text.split("\n")
    formatted_lines = []

    for line in lines:
        # Check for code block markers with or without language specification
        if "```" in line:
            # If line only contains the code block marker with optional language
            if line.strip().startswith("```") and len(line.strip().split()) <= 2:
                continue
            # If code block marker is part of a content line, remove just the markers
            line = line.replace("```", "")

        formatted_lines.append(line)

    # Join the lines back together
    return "\n".join(formatted_lines)


# Implementation based on the discussion:
# https://community.openai.com/t/whats-the-new-tokenization-algorithm-for-gpt-4o/746708/3
# gpt-4o seems to be using "o200k_base" encoding
def num_tokens_from_text(text: str, model="gpt-4o"):
    """Return the number of tokens in a text string."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    # List of models that use the same tokenizer
    if model in {
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
        "gpt-4-turbo",
        "gpt-4-turbo-2024-04-09",
        "gpt-4o",
        "gpt-4o-2024-05-13",
    }:
        # These models use the same tokenizer, so we can just encode and count
        return len(encoding.encode(text))
    if model == "gpt-3.5-turbo-0301":
        # This model might have slightly different tokenization
        return len(encoding.encode(text))
    if "gpt-3.5-turbo" in model:
        return len(encoding.encode(text))
    if "gpt-4" in model:
        return len(encoding.encode(text))
    msg = f"""num_tokens_from_text() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how text is converted to tokens."""
    raise NotImplementedError(
        msg,
    )
