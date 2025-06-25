import json
import os
import time

import openai

from app.utilities.config import settings
from app.utilities.document_readers import extract_text_from_doc
from app.utilities.llm import ChatLM

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class ExtractionManager2:
    root_path = ""

    def getPrompt(self, context, features):
        return (
            """Your job is to extract a list of entities from document(s). These are the entities you need to extract, no more. Entities:
        """
            + "\n".join(features)
            + """

        If a property is not present, represent it as "Not Found".

        Format the output as JSON, with the entity name as the key and a single string as the value. Make sure the entity name is exactly as it is listed. Do not include any additional text. Do not nest json values format it as {"entity": "value"}.

        Passage:

        """
            + context
        )

    def extract(self, extract_keys, pdf_paths, full_text=None):
        time.time()
        openai.api_key = OPENAI_API_KEY
        doc_text = ""
        if full_text is None:
            for pdf_path in pdf_paths:
                doc_text = extract_text_from_doc(doc_path=pdf_path)

        else:
            doc_text = full_text
        time.time()

        prompt = self.getPrompt(doc_text, extract_keys)
        # model = "gpt-3.5-turbo-0125"
        # if len(prompt) > 50000:
        #    model = "gpt-4-turbo"
        model = "gpt-4o"

        time.time()

        chat_lm = ChatLM(settings.model_type)
        output = chat_lm.completion(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a data scientist working on a project to extract entities and their properties from a passage. You are tasked with extracting the entities and their properties from the following passage.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        output = output.replace("\\n", "")
        output = output.replace("```json", "")
        output = output.replace("```", "")

        if "{" in output and "}" in output:
            return json.loads(output.strip())
        return None

    def build_from_documents(self, pdf_paths):
        openai.api_key = OPENAI_API_KEY
        doc_text = ""
        time.time()
        for pdf_path in pdf_paths:
            doc_text += "\n\n" + extract_text_from_doc(doc_path=pdf_path)

        prompt = (
            """Your job is to build an extraction set from the following information. Take the information given, and the instructions to extract the important information from this text. You will create an array of entities that an LLM could use and faithly reproduce to extract the same values from this text every time. When asked to populate values for the entity types you return, it should give the user the important information from this document every time. Return an array formatted as json with the format {"entities": ["value1", "value2", "etc"]} containing entities for important information in the text. Do not nest values, keep the array flat and one-dimensional. Do not inclued the values, just the entity names in a single array of string values.

          Passage:

        """
            + doc_text
        )

        model = "gpt-4o"

        chat_lm = ChatLM(Settings.model_type)
        output = chat_lm.completion(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a data scientist working on a project to extract entities and their properties from a passage. You are tasked with extracting the entities and their properties from the following passage. ",
                },
                {"role": "user", "content": prompt},
            ],
        )
        output = output.replace("\\n", "")
        output = output.replace("```json", "")
        output = output.replace("```", "")

        if "{" in output and "}" in output:
            return json.loads(output.strip())
        return None
