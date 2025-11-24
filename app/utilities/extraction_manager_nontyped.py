import os
import time
import openai
import json
from typing import Optional, Any, List
from pydantic import create_model, BaseModel
from pydantic_ai import Agent
from app.utilities.agents import get_agent_model, create_chat_agent
from app.utilities.config import settings
from app.models import SmartDocument
from devtools import debug

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
            """Your job is to build an extraction set from the following information. Take the information given, and the instructions to extract the important information from this text. You will create an array of entities that an LLM could use and faithly reproduce to extract the same values from this text every time. When asked to populate values for the entity types you return, it should give the user the important information from this document every time. Return an array formatted as json with the format {"entities": ["value1", "value2", "etc"]} containing entities for important information in the text. Do not nest values, keep the array flat and one-dimensional. Do not inclued the values, just the entity names in a single array of string values.

          Passage:

        """
            + doc_text
        )

        system_prompt = "You are a data scientist working on a project to extract entities and their properties from a passage. You are tasked with extracting the entities and their properties from the following passage. "

        chat_agent = create_chat_agent(settings.base_model, system_prompt=system_prompt)
        result = chat_agent.run_sync(prompt)
        output = result.output
        debug(output)
        output = output.replace("\\n", "")
        output = output.replace("```json", "")
        output = output.replace("```", "")

        if "{" in output and "}" in output:
            return json.loads(output.strip())
        return None

    def extract(self, extract_keys, document_uuids, full_text=None):
        # if extract_keys is string convert to list by splitting on comma
        if isinstance(extract_keys, str):
            fields_to_extract = extract_keys.split(",")
        else:
            fields_to_extract = extract_keys
        
        # Clean up keys
        fields_to_extract = [k.strip() for k in fields_to_extract]

        time.time()
        openai.api_key = OPENAI_API_KEY
        time.time()
        extraction = []
        
        if full_text is None:
            for document_uuid in document_uuids:
                doc = SmartDocument.objects(uuid=document_uuid).first()
                doc_text = doc.raw_text
                result = self._extract_nontyped(doc_text, fields_to_extract)
                extraction.extend(result)
        else:
            doc_text = full_text
            extraction = self._extract_nontyped(doc_text, fields_to_extract)

        return extraction

    def _extract_nontyped(self, text: str, keys: list[str]) -> list:
        # Create a dynamic Pydantic model where all fields are Optional[str]
        # This avoids type inference issues and forces the LLM to return strings
        field_definitions = {key: (Optional[str], None) for key in keys}
        
        DynamicEntity = create_model('DynamicEntity', **field_definitions)
        
        # Define the output model as a list of these entities
        class ExtractionModel(BaseModel):
            entities: List[DynamicEntity]

        model = get_agent_model(settings.base_model)
        
        system_prompt = (
            "You are a precise entity extraction assistant. Extract the requested information from the text. "
            "Extract the exact text as it appears in the document. Do not infer types, do not convert numbers, "
            "do not change formatting. Keep everything as strings. "
            "If a field is not found, leave it as null. "
            "Return a JSON object with an 'entities' key containing a list of extracted objects."
        )

        agent = Agent(
            model,
            system_prompt=system_prompt,
            output_type=ExtractionModel,
            retries=3,
        )

        try:
            # Construct a clear prompt listing the fields
            fields_str = ", ".join(keys)
            prompt = f"Extract the following fields: {fields_str}\n\nText:\n{text}"
            
            result = agent.run_sync(prompt)
            
            # Convert back to list of dicts
            entities = result.data.entities
            
            # Convert Pydantic models to dicts
            raw_entities = [entity.model_dump() for entity in entities]
            
            # Filter empty entities to match original behavior
            return self._filter_empty_entities(raw_entities)
            
        except Exception as e:
            debug(f"Extraction failed: {e}")
            # Fallback or return empty list
            return []

    def _filter_empty_entities(self, entities: list) -> list:
        """Filter out empty entities from the list."""
        def is_non_empty(e: dict) -> bool:
            if not isinstance(e, dict) or not e:
                return False
            return any(v not in (None, "", [], {}) for v in e.values())

        return [e for e in entities if is_non_empty(e)]
