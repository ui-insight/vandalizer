import json
import os
import time

import openai
from devtools import debug

from app.models import SmartDocument
from app.utilities.agents import create_chat_agent, extract_entities_with_agent
from app.utilities.config import settings

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class ExtractionManager3:
    root_path = ""

    def build_from_documents(self, document_uuids, model):
        openai.api_key = OPENAI_API_KEY
        doc_text = ""
        time.time()
        for document_uuid in document_uuids:
            doc = SmartDocument.objects(uuid=document_uuid).first()
            doc_text += doc.raw_text

        prompt = (
            """Your job is to build an extraction set from the following information. Take the information given, and the instructions to extract the important information from this text. You will create an array of entities that an LLM could use and faithly reproduce to extract the same values from this text every time. If an entity is not found, return "Not Found" for that entity. When asked to populate values for the entity types you return, it should give the user the important information from this document every time. Return an array formatted as json with the format {"entities": ["value1", "value2", "etc"]} containing entities for important information in the text. Do not nest values, keep the array flat and one-dimensional. Do not inclued the values, just the entity names in a single array of string values.

          Passage:

        """
            + doc_text
        )

        system_prompt = "You are a data scientist working on a project to extract entities and their properties from a passage. You are tasked with extracting the entities and their properties from the following passage. "

        if not model:
            model = settings.base_model

        chat_agent = create_chat_agent(model, system_prompt=system_prompt)
        result = chat_agent.run_sync(prompt)
        output = result.output
        debug(output)
        output = output.replace("\\n", "")
        output = output.replace("```json", "")
        output = output.replace("```", "")

        if "{" in output and "}" in output:
            return json.loads(output.strip())
        return None

    def extract(self, extract_keys, document_uuids, model, full_text=None):
        # if extract_keys is string convert to list by splitting on comma
        if isinstance(extract_keys, str):
            fields_to_extract = extract_keys.split(",")
        else:
            fields_to_extract = extract_keys
        # Extract entities

        time.time()
        openai.api_key = OPENAI_API_KEY
        time.time()
        extraction = []
        if not model:
            model = settings.base_model

        if full_text is None:
            for document_uuid in document_uuids:
                doc = SmartDocument.objects(uuid=document_uuid).first()
                doc_text = doc.raw_text
                result = extract_entities_with_agent(
                    text=doc_text,
                    keys=fields_to_extract,
                    model_name=model,
                )
                extraction.append(result)
        else:
            doc_text = full_text
            extraction = extract_entities_with_agent(
                text=doc_text,
                keys=fields_to_extract,
                model_name=model,
            )

        return extraction
