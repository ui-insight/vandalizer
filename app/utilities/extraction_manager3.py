from typing import Any, Dict, List, Optional, Type, Union, Annotated
from pydantic import create_model, BaseModel
import openai
from openai import OpenAI
import json
import time
import openai
from pypdf import PdfReader
import os
import re
import csv
from io import StringIO
import json
from pydantic import BaseModel, Field, ValidationError
from app.utilities.document_readers import extract_text_from_doc
from app.utilities.llm import ChatLM
from app.utilities.llm_helpers import retry_llm_request
from app.utilities.config import model_type
from langfuse.decorators import observe
from langfuse import Langfuse

from app.utilities.agents import extract_entities_with_agent

langfuse = Langfuse()

trace = langfuse.trace()


class ExtractionManager3:
    root_path = ""

    def extract(self, extract_keys, pdf_paths, full_text=None):
        api_key = "***REMOVED***"

        # extractor = EntityExtractor(api_key)

        # if extract_keys is string convert to list by splitting on comma
        if isinstance(extract_keys, str):
            fields_to_extract = extract_keys.split(",")
        else:
            fields_to_extract = extract_keys
        # Extract entities

        print("Extracting keys: ", extract_keys, pdf_paths)

        start_time = time.time()
        openai.api_key = "***REMOVED***"
        doc_text = ""
        extractions = []
        start_time = time.time()
        if full_text is None:
            for pdf_path in pdf_paths:
                doc_text = extract_text_from_doc(doc_path=pdf_path)
                if doc_text:
                    # data = extractor.extract_entities(doc_text, fields_to_extract)
                    data = extract_entities_with_agent(
                        text=doc_text, keys=fields_to_extract
                    )
                    extractions = data
                    print("Data item: ", data)
                    print("Extracting: ", extractions)

        else:
            doc_text = full_text
            data = extract_entities_with_agent(text=doc_text, keys=fields_to_extract)
            # data = extractor.extract_entities(doc_text, fields_to_extract)
            extractions = data

        # model = "gpt-3.5-turbo-0125"
        # if len(prompt) > 50000:
        #    model = "gpt-4-turbo"

        print("Extraction: ", extractions)
        # print(data.model_dump_json(indent=2))

        print(f"Completion processing time: {time.time() - start_time:.2f} seconds")

        return extractions


# class EntityExtractor:
#     def __init__(self, api_key: str):
#         """Initialize the EntityExtractor with OpenAI API key."""
#         self.client = OpenAI(api_key=api_key)

#     def infer_field_types(self, keys: List[str], context: str = "") -> Dict[str, type]:
#         """
#         Use GPT to infer appropriate types for the given field keys.

#         Args:
#             keys: List of field names to infer types for
#             context: Optional context about the data to help with type inference

#         Returns:
#             Dictionary mapping field names to their inferred Python types
#         """
#         prompt = f"""Given these field names{' and context' if context else ''}:

# Field names:
# {json.dumps(keys, indent=2)}

# {f'Context: {context}' if context else ''}

# For each field, determine the most appropriate data type and description from these options:
# - str
# - int
# - float
# - bool
# - List[str]
# - List[int]
# - List[float]
# - Optional[str]
# - Optional[int]
# - Optional[float]
# - Optional[bool]

# Return a json object where keys are field names and values are the recommended type names and descriptions exactly as shown above.
# Consider making fields Optional if they might not always be present."""

#         chat_lm = ChatLM(model_type)
#         response = chat_lm.completion(
#             messages=[
#                 {
#                     "role": "assistant",
#                     "content": "You are a data modeling expert. Infer appropriate data types for fields based on their names and context. Return only valid json.",
#                 },
#                 {"role": "user", "content": prompt},
#             ],
#             response_format={"type": "json_object"},
#         )

#         print("response: ", response)

#         type_mapping = {
#             "str": (str, ...),
#             "int": (int, ...),
#             "float": (float, ...),
#             "bool": (bool, ...),
#             "List[str]": (List[str], ...),
#             "List[int]": (List[int], ...),
#             "List[float]": (List[float], ...),
#             "Dict[str, str]": (Dict[str, str], ...),
#             "Optional[str]": (Optional[str], ...),
#             "Optional[int]": (Optional[int], ...),
#             "Optional[float]": (Optional[float], ...),
#             "Optional[bool]": (Optional[bool], ...),
#         }

#         try:
#             type_suggestions = json.loads(response)
#             return {
#                 key: type_mapping.get(type_str.strip(), (Any, ...))
#                 for key, type_str in type_suggestions.items()
#             }
#         except Exception as e:
#             raise ValueError(f"Failed to parse type inference response: {str(e)}")

#     def _create_dynamic_model(self, fields: Dict[str, tuple]) -> Type[BaseModel]:
#         """
#         Create a Pydantic model dynamically based on provided fields.

#         Args:
#             fields: Dictionary mapping field names to tuples of (type, default)
#         """
#         return create_model(
#             "DynamicEntity",
#             **{field_name: field_spec for field_name, field_spec in fields.items()},
#         )

#         # use pydantic Field to wrap the type and default value
#         # return create_model(
#         #     "DynamicEntity",
#         #     **{
#         #         field_name: (
#         #             field_spec[0],
#         #             Field(default=field_spec[1], description=field_spec[2]),
#         #         )
#         #         for field_name, field_spec in fields.items()
#         #     },
#         # )

#     def _generate_extraction_prompt(self, text: str, fields: Dict[str, tuple]) -> str:
#         """Generate a prompt for the GPT model to extract entities."""
#         field_descriptions = [
#             f"- {field}: {field_type[0]}" for field, field_type in fields.items()
#         ]
#         field_str = "\n".join(field_descriptions)

#         multiple_entity_instruction = (
#             "\n\nImportant: Extract ALL relevant entities from the text only if it is present. "
#             "Return a JSON array of objects, where each object represents a distinct entity. "
#             "If no multiple entities are found, return a single-item array."
#         )

#         return f"""Extract the following information from the text below only if it is present:

# {field_str}

# Return the information in JSON format and be as precise as possible{multiple_entity_instruction}

# Text:
# {text}"""

#     def extract_entities(
#         self,
#         text: str,
#         keys: List[str],
#         context: str = "",
#         max_retries: int = 3,
#     ) -> BaseModel:
#         """
#         Extract entities from text using GPT and return structured output.

#         Args:
#             text: Input text to extract information from
#             keys: List of fields to extract
#             context: Optional context to help with type inference
#             custom_types: Optional dictionary of pre-defined types as (type, default) tuples

#         Returns:
#             Pydantic model instance with extracted information
#         """
#         # Infer types for fields
#         inferred_types = self.infer_field_types(keys, context)

#         print("inferred_types: ", inferred_types)

#         # Create dynamic Pydantic model
#         DynamicModel = self._create_dynamic_model(inferred_types)
#         ExtractionModel = create_model(
#             "ExtractionModel", entities=(List[DynamicModel], ...)
#         )
#         print("DynamicModel: ", DynamicModel)

#         # Generate prompt
#         prompt = self._generate_extraction_prompt(text, inferred_types)

#         # Get completion from GPT
#         # Parse response
#         try:

#             messages = [
#                 {
#                     "role": "system",
#                     "content": "You are a precise entity extraction assistant. Extract only the requested information and return it in valid JSON format.",
#                 },
#                 {"role": "user", "content": prompt},
#             ]
#             response = retry_llm_request(
#                 model_type="openai",
#                 client=self.client,
#                 messages=messages,
#                 model_class=ExtractionModel,
#                 max_retries=max_retries,
#             )
#             print("Request Response: ", response)
#             return response

#         except Exception as e:
#             raise ValueError(f"Failed to parse GPT response: {str(e)}")
