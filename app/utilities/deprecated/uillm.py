import json
import re

import requests


class UILLM:
    def ask_question(
        self,
        is_json=False,
        model="",
        temperature=0.7,
        max_tokens=3000,
    ):
        endpoint = "https://mindrouter-api.nkn.uidaho.edu/v1/chat/completions"

        if model == "":
            model = "llama3.1:70b"

        data = {
            "model": model,
            "temperature": temperature,
            "messages": [{"role": "user", "content": self}],
        }

        if is_json:
            data["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json", "Authorization": "Bearer no-key"}

        response = requests.post(endpoint, json=data, headers=headers)
        if response.status_code == 200:
            try:
                output = response.json()
                content = output["choices"][0]["message"]["content"]
                if content is None:
                    pass

                if is_json:
                    return json.loads(content)
                return content
            except json.JSONDecodeError:
                pass
        else:
            return None

    def list_models(self="pretty", verbose=False):
        endpoint = "https://mindrouter-api.nkn.uidaho.edu/api/tags"

        response = requests.get(endpoint)
        # allow users to silence the print
        if verbose:
            pass
        data = json.loads(response.text)
        # default view is a pretty print
        if self == "pretty":
            UILLM.display_models(data)
        # list option returns a list with only the model names
        elif self == "list":
            return UILLM.display_models_list(data)
        return None

    def display_models_list(self):
        return [x.get("name") for x in self.get("models")]

    def display_models(self) -> None:
        models = self.get("models", [])
        if not models:
            return

        for model in models:
            model.get("name", "N/A")
            details = model.get("details", {})
            details.get("family", "N/A")
            details.get("parameter_size", "N/A")
            details.get("quantization_level", "N/A")

    def parse_command_R(self):
        # strip leading and trailing newline characters
        self = self.strip("\n")

        # use a regular expression to extract the JSON part
        json_match = re.search(r"{.*}", self, re.DOTALL)
        if not json_match:
            msg = f"Unexpected response from command-r. JSON string not found in data: {self}"
            raise ValueError(
                msg,
            )

        json_str = json_match.group(0)
        # sometimes the json that command-R provides is not properly formatted. Use regular expression to attempt to fix (i.e. missing comma).
        json_str = json_str.strip()
        json_str = re.sub(r'(?<!")(\b\w+\b)(?!")(?=\s*:)', r'"\1"', json_str)
        json_str = re.sub(r'(?<=["\]}])\s*(?=["\[{])', ",", json_str)
        try:
            # parse the JSON string into a Python dictionary
            return json.loads(json_str)
        except json.JSONDecodeError:
            # raise the JSONDecodeError as the ask_question_to_model() method handles this exception
            raise

    def list_embeddings(self) -> None:
        endpoint = "https://mindrouter-api.nkn.uidaho.edu/api/tags"

        requests.get(endpoint)
        UILLM.display_models(self)

    def convert_string_to_embeddings(self, model="EMBED/all-minilm:22m"):
        endpoint = "https://mindrouter-api.nkn.uidaho.edu/api/embeddings"

        data = {"model": model, "prompt": self}

        response = requests.post(endpoint, json=data, headers={})
        if response.status_code == 200:
            return response.json()
        return None
