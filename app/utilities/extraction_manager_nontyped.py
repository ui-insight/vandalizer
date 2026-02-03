import os
import time
import openai
import json
from typing import Optional, Any, List
from pydantic import create_model, BaseModel, ConfigDict, model_validator
from pydantic_ai import Agent
from pydantic_ai._json_schema import InlineDefsJsonSchemaTransformer
from app.utilities.agents import (
    get_agent_model,
    create_chat_agent,
    get_model_api_protocol,
)
from app.utilities.config import (
    get_default_model_name,
    get_extraction_model_name,
    get_extraction_strategy,
)
from app.models import SmartDocument
from devtools import debug

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class ExtractionManagerNonTyped:
    root_path = ""

    def build_from_documents(self, document_uuids, model):
        extraction_model = get_extraction_model_name()
        if extraction_model:
            model = extraction_model
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

    def extract(self, extract_keys, document_uuids, model=None, full_text=None):
        # if extract_keys is string convert to list by splitting on comma
        if isinstance(extract_keys, str):
            fields_to_extract = extract_keys.split(",")
        else:
            fields_to_extract = extract_keys
        
        # Clean up keys
        fields_to_extract = [k.strip() for k in fields_to_extract]

        # Determine extraction model (system override > provided > default)
        extraction_model = get_extraction_model_name()
        if extraction_model:
            model = extraction_model
        elif model is None:
            model = get_default_model_name()

        extraction_strategy = get_extraction_strategy()

        time.time()
        openai.api_key = OPENAI_API_KEY
        time.time()
        extraction = []
        
        if full_text is None:
            for document_uuid in document_uuids:
                doc = SmartDocument.objects(uuid=document_uuid).first()
                if not doc:
                    debug(f"Document not found: {document_uuid}")
                    continue
                doc_text = doc.raw_text
                if not doc_text or len(doc_text.strip()) == 0:
                    debug(f"Document {document_uuid} has no text content (length: {len(doc_text) if doc_text else 0})")
                    continue
                debug(f"Extracting from document {document_uuid}, text length: {len(doc_text)}")
                result = self._extract_nontyped(
                    doc_text,
                    fields_to_extract,
                    model,
                    strategy=extraction_strategy,
                )
                debug(
                    f"Extraction result for document {document_uuid}: {len(result)} entities"
                )
                extraction.extend(result)
        else:
            doc_text = full_text
            extraction = self._extract_nontyped(
                doc_text,
                fields_to_extract,
                model,
                strategy=extraction_strategy,
            )

        return extraction

    def _extract_nontyped(
        self,
        text: str,
        keys: list[str],
        model_name: str,
        strategy: str | None = None,
    ) -> list:
        strategy_to_use = (strategy or "two_pass").strip().lower()

        if strategy_to_use == "one_pass_thinking":
            return self._extract_structured(
                text,
                keys,
                model_name,
                thinking_override=True,
            )

        if strategy_to_use == "one_pass_no_thinking":
            return self._extract_structured(
                text,
                keys,
                model_name,
                thinking_override=False,
            )

        if strategy_to_use == "two_pass":
            return self._extract_two_pass(text, keys, model_name)

        debug(f"Unknown extraction strategy '{strategy_to_use}', defaulting to two_pass")
        return self._extract_two_pass(text, keys, model_name)

    def _extract_two_pass(self, text: str, keys: list[str], model_name: str) -> list:
        # Pass 1: thinking-enabled draft (unstructured)
        draft_entities = self._extract_fallback_json(
            text,
            keys,
            model_name,
            thinking_override=True,
        )
        draft_hint = self._build_draft_hint(draft_entities)

        # Pass 2: structured output with thinking disabled
        final_entities = self._extract_structured(
            text,
            keys,
            model_name,
            thinking_override=False,
            draft_hint=draft_hint,
            allow_fallback=False,
        )

        if final_entities:
            return final_entities

        if draft_entities:
            return draft_entities

        return []

    def _build_draft_hint(self, draft_entities: list | dict | None) -> dict | None:
        if not draft_entities:
            return None

        if isinstance(draft_entities, dict):
            return draft_entities

        if isinstance(draft_entities, list):
            if len(draft_entities) == 1 and isinstance(draft_entities[0], dict):
                return draft_entities[0]

            merged = {}
            for entity in draft_entities:
                if not isinstance(entity, dict):
                    continue
                for key, value in entity.items():
                    if key in merged:
                        continue
                    if value in (None, "", [], {}):
                        continue
                    merged[key] = value
            return merged or None

        return None

    def _extract_structured(
        self,
        text: str,
        keys: list[str],
        model_name: str,
        thinking_override: Optional[bool] = None,
        draft_hint: dict | None = None,
        allow_fallback: bool = True,
    ) -> list:
        # Create a dynamic Pydantic model where all fields are Optional[str]
        # This avoids type inference issues and forces the LLM to return strings
        field_definitions = {key: (Optional[str], None) for key in keys}

        DynamicEntity = create_model("DynamicEntity", **field_definitions)

        # Define the output model as a list of these entities
        class ExtractionModel(BaseModel):
            model_config = ConfigDict(extra="allow")
            entities: List[DynamicEntity]

            @model_validator(mode="before")
            @classmethod
            def coerce_entities(cls, value):
                # Accept multiple shapes and normalize into {"entities": [...]}
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except Exception:
                        return value

                if isinstance(value, list):
                    return {"entities": value}

                if isinstance(value, dict):
                    if "entities" in value:
                        entities = value.get("entities")
                        if isinstance(entities, dict):
                            value["entities"] = [entities]
                        return value
                    return {"entities": [value]}

                return value

        def _build_structured_output_schema() -> dict:
            schema = ExtractionModel.model_json_schema()
            if "$defs" in schema:
                schema = InlineDefsJsonSchemaTransformer(schema).walk()
            return schema

        api_protocol = get_model_api_protocol(model_name)
        structured_retries = 1 if api_protocol == "vllm" else 3

        system_prompt = (
            "You are a precise entity extraction assistant. Extract the requested information from the text. "
            "Extract the exact text as it appears in the document. Do not infer types, do not convert numbers, "
            "do not change formatting. Keep everything as strings. "
            "If a field is not found, leave it as null. "
            "Return a JSON object with an 'entities' key containing a list of extracted objects."
        )

        try:
            # Construct a clear prompt listing the fields
            fields_str = ", ".join(keys)
            prompt = f"Extract the following fields: {fields_str}\n\nText:\n{text}"

            if draft_hint:
                draft_json = json.dumps(draft_hint, ensure_ascii=False)
                prompt = (
                    "Draft extraction (may be incorrect):\n"
                    f"{draft_json}\n\n"
                    f"{prompt}"
                )

            debug(
                f"Structured extraction: model={model_name} keys={len(keys)} text_length={len(text)}"
            )

            model_settings = None
            if api_protocol == "vllm":
                schema = _build_structured_output_schema()
                model_settings = {
                    "extra_body": {
                        "structured_outputs": {
                            "json": schema,
                        }
                    }
                }

            model = get_agent_model(model_name, thinking_override=thinking_override)
            agent = Agent(
                model,
                system_prompt=system_prompt,
                output_type=ExtractionModel,
                retries=structured_retries,
                output_retries=structured_retries,
            )

            result = agent.run_sync(
                prompt,
                model_settings=model_settings,
            )

            # Convert back to list of dicts
            if not hasattr(result, "output") or result.output is None:
                debug("Agent result has no output attribute or output is None")
                return []

            entities = result.output.entities

            # Convert Pydantic models to dicts
            raw_entities = []
            for entity in entities:
                if hasattr(entity, "model_dump"):
                    raw_entities.append(entity.model_dump())
                elif isinstance(entity, dict):
                    raw_entities.append(entity)
                else:
                    debug(f"Unexpected entity type: {type(entity)}, value: {entity}")

            # Filter empty entities to match original behavior
            filtered = self._filter_empty_entities(raw_entities)
            debug(f"Structured extraction returned {len(filtered)} entities")

            return filtered

        except Exception as e:
            error_msg = str(e)
            debug(f"Extraction failed: {e}")
            import traceback
            debug(f"Traceback: {traceback.format_exc()}")
            # Check if it's a validation error (common with VLLM)
            if "output validation" in error_msg or "retries" in error_msg.lower():
                if allow_fallback:
                    debug("Output validation failed, attempting fallback with raw JSON parsing")
                    return self._extract_fallback_json(
                        text,
                        keys,
                        model_name,
                        thinking_override=thinking_override,
                    )
                debug("Output validation failed, skipping fallback for structured pass")
                return []

            # Fallback or return empty list
            return []

    def _filter_empty_entities(self, entities: list) -> list:
        """Filter out empty entities from the list."""
        def is_non_empty(e: dict) -> bool:
            if not isinstance(e, dict) or not e:
                return False
            return any(v not in (None, "", [], {}) for v in e.values())

        return [e for e in entities if is_non_empty(e)]
    
    def _extract_fallback_json(
        self,
        text: str,
        keys: list[str],
        model_name: str,
        thinking_override: Optional[bool] = None,
    ) -> list:
        """Fallback extraction method that parses raw JSON from LLM response."""
        try:
            from app.utilities.agents import create_chat_agent
            
            # Create a simpler prompt that asks for JSON directly
            fields_str = ", ".join([f'"{k}"' for k in keys])
            prompt = f"""Extract the following fields from the text and return them as a JSON object.
Return ONLY valid JSON, no markdown, no code blocks, no explanations.

Fields to extract: {fields_str}

Text:
{text}

Return a JSON object with these exact field names. If a field is not found, use null.
Example format: {{"Field Name 1": "value", "Field Name 2": null, ...}}
"""
            
            system_prompt = (
                "You are a precise entity extraction assistant. Extract the requested information from the text. "
                "Return ONLY valid JSON, no markdown formatting, no code blocks, no explanations. "
                "If a field is not found, use null."
            )
            
            chat_agent = create_chat_agent(
                model_name,
                system_prompt=system_prompt,
                thinking_override=thinking_override,
            )
            result = chat_agent.run_sync(prompt)
            
            # Parse the JSON response
            output = result.output
            debug(f"Fallback extraction raw output: {output}")
            
            # Remove markdown code blocks if present
            if "```json" in output:
                output = output.split("```json")[1].split("```")[0].strip()
            elif "```" in output:
                output = output.split("```")[1].split("```")[0].strip()
            
            # Parse JSON
            try:
                parsed = json.loads(output.strip())
                debug(f"Parsed JSON: {parsed}")
                
                # Convert to list format expected by the rest of the code
                if isinstance(parsed, dict):
                    # Ensure all keys are present
                    entity = {}
                    for key in keys:
                        entity[key] = parsed.get(key, None)
                    return [entity]
                elif isinstance(parsed, list):
                    return parsed
                else:
                    debug(f"Unexpected parsed JSON type: {type(parsed)}")
                    return []
            except json.JSONDecodeError as je:
                debug(f"Failed to parse JSON: {je}")
                debug(f"Output that failed to parse: {output}")
                return []
                
        except Exception as e:
            debug(f"Fallback extraction also failed: {e}")
            import traceback
            debug(f"Fallback traceback: {traceback.format_exc()}")
            return []
