import os
import time
import openai
import json
from app.utilities.agents import extract_entities_with_agent
from app.utilities.document_readers import extract_text_from_doc
from app.utilities.config import model_type
from app.utilities.llm import ChatLM

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class ExtractionManager3:
    root_path = ""

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

        chat_lm = ChatLM(model_type)
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

    def extract(self, extract_keys, pdf_paths, full_text=None):

        # if extract_keys is string convert to list by splitting on comma
        if isinstance(extract_keys, str):
            fields_to_extract = extract_keys.split(",")
        else:
            fields_to_extract = extract_keys
        # Extract entities

        time.time()
        openai.api_key = OPENAI_API_KEY
        doc_text = ""
        extractions = []
        time.time()
        if full_text is None:
            for pdf_path in pdf_paths:
                doc_text = extract_text_from_doc(doc_path=pdf_path)
                if doc_text:
                    data = extract_entities_with_agent(
                        text=doc_text,
                        keys=fields_to_extract,
                    )
                    extractions = data

        else:
            doc_text = full_text
            data = extract_entities_with_agent(text=doc_text, keys=fields_to_extract)
            extractions = data

        return extractions
