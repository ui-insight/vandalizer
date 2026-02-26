import os
import time
import openai
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Any, List
from pydantic import create_model, BaseModel, ConfigDict, model_validator, Field
from pydantic_ai import Agent
from pydantic_ai._json_schema import InlineDefsJsonSchemaTransformer
from app.utilities.agents import (
    get_agent_model,
    create_chat_agent,
    get_model_api_protocol,
)
from app.utilities.config import (
    get_default_model_name,
    get_extraction_config,
)
from app.models import SmartDocument, ActivityEvent
from devtools import debug

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class ExtractionManagerNonTyped:
    root_path = ""

    def build_from_documents(self, document_uuids, model):
        config_model = get_extraction_config().get("model", "")
        if config_model:
            model = config_model
        openai.api_key = OPENAI_API_KEY
        doc_text = ""
        time.time()
        for document_uuid in document_uuids:
            doc = SmartDocument.objects(uuid=document_uuid).first()
            doc_text += doc.raw_text

        prompt = (
            """Your job is to build an extraction set from the following information. Take the information given, and the instructions to extract the important information from this text. You will create an array of entities that an LLM could use and faithly reproduce to extract the same values from this text every time. When asked to populate values for the entity types you return, it should give the user the important information from this document every time. Return an array formatted as json with the format {"entities": ["value1", "value2", "etc"]} containing entities for important information in the text. Do not nest values, keep the array flat and one-dimensional. Do not inclued the values, just the entity names in a single array of string values.

Important: The entity names should be Human Readable. Do not use underscores or camelCase. Use spaces and Title Case. For example, use "Invoice Number" instead of "invoice_number".

          Passage:

        """
            + doc_text
        )

        system_prompt = "You are a data scientist working on a project to extract entities and their properties from a passage. You are tasked with extracting the entities and their properties from the following passage. Ensure all entity names are Human Readable with spaces, not underscores."

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

    def extract(self, extract_keys, document_uuids, model=None, full_text=None,
                extraction_config_override: dict | None = None, activity_id: str | None = None):
        # Normalize keys
        if isinstance(extract_keys, str):
            fields_to_extract = extract_keys.split(",")
        else:
            fields_to_extract = extract_keys
        fields_to_extract = [k.strip() for k in fields_to_extract]

        # Load system extraction config, then apply per-extraction overrides
        extraction_cfg = self._resolve_config(extraction_config_override)

        # Determine model (config override > provided > default)
        model = self._resolve_model(extraction_cfg, model)

        openai.api_key = OPENAI_API_KEY

        doc_texts = self._resolve_doc_texts(document_uuids, full_text)
        key_chunks = self._resolve_key_chunks(fields_to_extract, extraction_cfg)
        use_repetition = extraction_cfg.get("repetition", {}).get("enabled", False)

        all_results = []
        for doc_text in doc_texts:
            doc_results = self._extract_document(
                doc_text, key_chunks, model, extraction_config_override or {}, use_repetition, activity_id
            )
            all_results.extend(doc_results)

        return all_results

    # ------------------------------------------------------------------
    # Config / model / chunking resolution
    # ------------------------------------------------------------------

    def _resolve_config(self, override: dict | None = None) -> dict:
        """Load system config and merge per-extraction overrides."""
        cfg = get_extraction_config()
        if override:
            from app.models import _deep_merge
            from copy import deepcopy
            cfg = deepcopy(cfg)
            _deep_merge(cfg, override)
        return cfg

    def _resolve_model(self, cfg: dict, model: str | None) -> str:
        """Determine the model to use: config override > provided > default."""
        config_model = cfg.get("model", "")
        if config_model:
            return config_model
        if model:
            return model
        return get_default_model_name()

    def _resolve_key_chunks(self, keys: list[str], cfg: dict) -> list[list[str]]:
        """Split keys into chunks if chunking is enabled."""
        chunking = cfg.get("chunking", {})
        if chunking.get("enabled") and chunking.get("max_keys_per_chunk", 0) > 0:
            return self._chunk_keys(keys, chunking["max_keys_per_chunk"])
        return [keys]

    def _extract_document(
        self, doc_text: str, key_chunks: list[list[str]],
        model: str, cfg: dict, use_repetition: bool, activity_id: str | None = None
    ) -> list:
        """Run extraction (with optional chunking and repetition) for one document."""
        doc_results = []
        for chunk_keys in key_chunks:
            if use_repetition:
                chunk_result = self._extract_with_consensus(doc_text, chunk_keys, model, cfg)
            else:
                chunk_result = self._dispatch_extraction(doc_text, chunk_keys, model, cfg, activity_id)
            doc_results.extend(chunk_result)

        if len(key_chunks) > 1:
            return self._merge_chunk_results(doc_results)
        return doc_results

    # ------------------------------------------------------------------
    # Document text resolution
    # ------------------------------------------------------------------

    def _resolve_doc_texts(self, document_uuids, full_text=None) -> list[str]:
        """Return list of document text strings to extract from."""
        if full_text is not None:
            return [full_text]
        texts = []
        for document_uuid in document_uuids:
            doc = SmartDocument.objects(uuid=document_uuid).first()
            if not doc:
                debug(f"Document not found: {document_uuid}")
                continue
            if not doc.raw_text or len(doc.raw_text.strip()) == 0:
                debug(f"Document {document_uuid} has no text content")
                continue
            debug(f"Extracting from document {document_uuid}, text length: {len(doc.raw_text)}")
            texts.append(doc.raw_text)
        return texts

    # ------------------------------------------------------------------
    # Dispatch layer
    # ------------------------------------------------------------------

    def _dispatch_extraction(
        self, text: str, keys: list[str], model_name: str, config: dict, activity_id: str | None = None
    ) -> list:
        """Route to the correct extraction method based on config."""
        mode = config.get("mode", "two_pass")

        if mode == "one_pass":
            if activity_id:
                ActivityEvent.objects(id=activity_id).update(set__progress_message="Starting single pass extraction...")
            one_pass = config.get("one_pass", {})
            thinking = one_pass.get("thinking", True)
            structured = one_pass.get("structured", True)
            pass_model = one_pass.get("model", "") or model_name
            return self._execute_single_pass(text, keys, pass_model, thinking, structured)

        # two_pass (default)
        if activity_id:
            ActivityEvent.objects(id=activity_id).update(set__progress_message="Starting Pass 1 of 2...")
        two_pass = config.get("two_pass", {})
        pass_1_cfg = two_pass.get("pass_1", {})
        pass_2_cfg = two_pass.get("pass_2", {})
        
        result = self._execute_two_pass(text, keys, model_name, pass_1_cfg, pass_2_cfg, activity_id)
        if activity_id:
            ActivityEvent.objects(id=activity_id).update(set__progress_message="Extraction complete.")
            
        return result

    def _execute_single_pass(
        self, text: str, keys: list[str], model_name: str, thinking: bool, structured: bool
    ) -> list:
        """Execute a single extraction pass with the given thinking/structured settings."""
        if structured:
            return self._extract_structured(text, keys, model_name, thinking_override=thinking)
        else:
            return self._extract_fallback_json(text, keys, model_name, thinking_override=thinking)

    def _execute_two_pass(
        self, text: str, keys: list[str], model_name: str,
        pass_1_cfg: dict, pass_2_cfg: dict, activity_id: str | None = None
    ) -> list:
        """Execute two-pass extraction with independent per-pass configuration."""
        p1_model = pass_1_cfg.get("model", "") or model_name
        p1_thinking = pass_1_cfg.get("thinking", True)
        p1_structured = pass_1_cfg.get("structured", False)

        p2_model = pass_2_cfg.get("model", "") or model_name
        p2_thinking = pass_2_cfg.get("thinking", False)
        p2_structured = pass_2_cfg.get("structured", True)

        # Pass 1
        if p1_structured:
            draft = self._extract_structured(text, keys, p1_model, thinking_override=p1_thinking)
        else:
            draft = self._extract_fallback_json(text, keys, p1_model, thinking_override=p1_thinking)

        if activity_id:
            ActivityEvent.objects(id=activity_id).update(set__progress_message="Pass 1 complete. Analyzing draft...")
            
        draft_hint = self._build_draft_hint(draft)

        # Pass 2
        if activity_id:
            ActivityEvent.objects(id=activity_id).update(set__progress_message="Starting Pass 2 of 2...")
        if p2_structured:
            final = self._extract_structured(
                text, keys, p2_model,
                thinking_override=p2_thinking,
                draft_hint=draft_hint,
                allow_fallback=False,
            )
        else:
            final = self._extract_fallback_json(text, keys, p2_model, thinking_override=p2_thinking)

        if final:
            return final
        if draft:
            return draft
        return []

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def _chunk_keys(self, keys: list[str], max_per_chunk: int) -> list[list[str]]:
        """Split extraction keys into chunks of max_per_chunk size."""
        return [keys[i:i + max_per_chunk] for i in range(0, len(keys), max_per_chunk)]

    def _merge_chunk_results(self, results: list) -> list:
        """Merge results from multiple key-chunk extraction calls into unified entities."""
        if not results:
            return []
        merged = {}
        for item in results:
            if isinstance(item, dict):
                for k, v in item.items():
                    if k not in merged or merged[k] in (None, "", [], {}):
                        merged[k] = v
        return [merged] if merged else []

    # ------------------------------------------------------------------
    # Repetition / Consensus
    # ------------------------------------------------------------------

    def _extract_with_consensus(
        self, text: str, keys: list[str], model_name: str, config: dict
    ) -> list:
        """Run extraction twice in parallel; if not unanimous, run a third and majority-vote."""
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_1 = executor.submit(self._dispatch_extraction, text, keys, model_name, config)
            future_2 = executor.submit(self._dispatch_extraction, text, keys, model_name, config)
            result_1 = future_1.result()
            result_2 = future_2.result()

        norm_1 = self._normalize_to_dict(result_1)
        norm_2 = self._normalize_to_dict(result_2)

        if norm_1 == norm_2:
            debug("Consensus reached on first two runs")
            return result_1 if result_1 else result_2

        debug("No consensus between first two runs, running third extraction")
        result_3 = self._dispatch_extraction(text, keys, model_name, config)
        norm_3 = self._normalize_to_dict(result_3)

        consensus = self._majority_vote(keys, [norm_1, norm_2, norm_3])
        return [consensus]

    def _normalize_to_dict(self, results: list) -> dict:
        """Flatten a list of entity dicts into a single merged dict for comparison."""
        if not results:
            return {}
        if isinstance(results, dict):
            return results
        merged = {}
        for item in results:
            if isinstance(item, dict):
                merged.update(item)
        return merged

    def _majority_vote(self, keys: list[str], results: list[dict]) -> dict:
        """For each key, pick the value that appears most often across results."""
        consensus = {}
        for key in keys:
            values = [r.get(key) for r in results]
            counter = Counter(
                json.dumps(v, ensure_ascii=False) if v is not None else "__NULL__"
                for v in values
            )
            most_common_serialized, _ = counter.most_common(1)[0]
            if most_common_serialized == "__NULL__":
                consensus[key] = None
            else:
                consensus[key] = json.loads(most_common_serialized)
        return consensus

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
        # We sanitize keys to be valid Python identifiers and use aliases for the actual JSON keys
        field_definitions = {}
        for key in keys:
            # Sanitize key to be a valid variable name (replace spaces/special chars)
            safe_key = "".join(c if c.isalnum() else "_" for c in key)
            if not safe_key:
                safe_key = "field"  # Fallback for completely invalid keys
            if safe_key[0].isdigit():
                safe_key = f"_{safe_key}"

            # Ensure uniqueness
            original_safe_key = safe_key
            counter = 1
            while safe_key in field_definitions:
                safe_key = f"{original_safe_key}_{counter}"
                counter += 1

            # Map sanitized name to original key via alias
            field_definitions[safe_key] = (Optional[str], Field(default=None, alias=key))

        DynamicEntity = create_model(
            "DynamicEntity",
            __config__=ConfigDict(extra="allow", populate_by_name=True),
            **field_definitions
        )

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
            schema = ExtractionModel.model_json_schema(by_alias=True)
            if "$defs" in schema:
                schema = InlineDefsJsonSchemaTransformer(schema).walk()
            return schema

        api_protocol = get_model_api_protocol(model_name)
        structured_retries = 3 if api_protocol == "vllm" else 3

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
            debug(f"Structured extraction failed (will attempt fallback): {e}")
            
            # Log detailed validation errors if available
            if hasattr(e, 'cause') and e.cause:
                debug(f"Underlying cause: {e.cause}")
            if hasattr(e, 'errors'): # Pydantic ValidationError
                debug(f"Validation errors: {e.errors()}")
            if hasattr(e, 'json'):
                debug(f"Validation error JSON: {e.json()}")

            # Check if it's a validation error (common with VLLM)
            if "output validation" in error_msg or "retries" in error_msg.lower() or "validation error" in error_msg.lower():
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
