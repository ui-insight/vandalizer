"""Extraction engine  - ported from ExtractionManagerNonTyped.

All methods are synchronous so they can run in Celery workers or via asyncio.to_thread.
The caller must pre-fetch any async data (SystemConfig, document texts) and pass it in.
"""

import json
import logging
import os
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator
from pydantic_ai import Agent, BinaryContent
from app.services._json_schema_utils import inline_defs

from app.models.system_config import DEFAULT_EXTRACTION_CONFIG, _deep_merge
from app.services.llm_service import (
    create_chat_agent,
    get_agent_model,
    get_model_api_protocol,
)

logger = logging.getLogger(__name__)

# Content that can be passed to extraction methods: plain text or page images.
ExtractionContent = Union[str, list[BinaryContent]]

# Maximum number of pages to render from a single PDF to avoid memory issues.
MAX_PDF_PAGES_FOR_IMAGES = 50


class ExtractionEngine:
    """Synchronous extraction engine. Thread-safe for use in Celery workers."""

    def __init__(self, system_config_doc: dict | None = None, domain: str | None = None):
        """
        Args:
            system_config_doc: Pre-fetched SystemConfig as a plain dict for sync access.
            domain: Domain identifier for domain-specific prompts (nsf, nih, dod, doe).
        """
        self._sys_cfg = system_config_doc or {}
        self._domain = domain
        self.tokens_in = 0
        self.tokens_out = 0
        self._usage_lock = threading.Lock()

    def _record_usage(self, result) -> None:
        """Accumulate token usage from a pydantic-ai RunResult."""
        try:
            usage = result.usage()
            with self._usage_lock:
                self.tokens_in += usage.request_tokens or 0
                self.tokens_out += usage.response_tokens or 0
        except (AttributeError, TypeError):
            pass  # usage() not available on all result types

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        extract_keys: list[str] | str,
        document_uuids: list[str] | None = None,
        model: str | None = None,
        full_text: str | None = None,
        extraction_config_override: dict | None = None,
        doc_texts: list[str] | None = None,
        field_metadata: list[dict] | None = None,
        doc_file_paths: list[str] | None = None,
    ) -> list:
        """Run extraction. Returns list of entity dicts.

        Args:
            extract_keys: Fields to extract (list or comma-separated string).
            document_uuids: Not used directly  - caller should pass doc_texts.
            model: Model name override.
            full_text: Single document text (shortcut for doc_texts=[full_text]).
            extraction_config_override: Per-extraction config overrides.
            doc_texts: Pre-loaded document texts.
            field_metadata: Per-field metadata (is_optional, enum_values) from search set items.
            doc_file_paths: File paths for image-based extraction (used when use_images is enabled).
        """
        # Normalize keys
        if isinstance(extract_keys, str):
            fields_to_extract = [k.strip() for k in extract_keys.split(",")]
        else:
            fields_to_extract = [k.strip() for k in extract_keys]

        extraction_cfg = self._resolve_config(extraction_config_override)
        model = self._resolve_model(extraction_cfg, model)
        key_chunks = self._resolve_key_chunks(fields_to_extract, extraction_cfg)
        use_repetition = extraction_cfg.get("repetition", {}).get("enabled", False)
        use_images = extraction_cfg.get("use_images", False)

        # Build metadata map
        meta_map: dict[str, dict] = {}
        if field_metadata:
            meta_map = {m["key"]: m for m in field_metadata}

        # Image-based extraction when enabled AND model is actually multimodal
        if use_images and doc_file_paths and self._model_is_multimodal(model):
            model_supports_pdf = self._model_supports_pdf(model)
            all_results = []
            for idx, file_path in enumerate(doc_file_paths):
                content = self._load_file_content(file_path, model_supports_pdf)
                if content is not None:
                    doc_results = self._extract_document(
                        content, key_chunks, model, extraction_cfg, use_repetition, meta_map
                    )
                    all_results.extend(doc_results)
                else:
                    # Fallback to OCR text if file can't be loaded for images
                    texts = doc_texts or []
                    if idx < len(texts) and texts[idx]:
                        logger.warning(
                            "Image loading failed for %s, falling back to text", file_path
                        )
                        doc_results = self._extract_document(
                            texts[idx], key_chunks, model, extraction_cfg, use_repetition, meta_map
                        )
                        all_results.extend(doc_results)
            return all_results

        # Text-based extraction (default path)
        texts = doc_texts or []
        if full_text is not None:
            texts = [full_text]
        if not texts:
            logger.warning("No document texts provided for extraction — returning empty results")
            return []

        all_results = []
        for doc_text in texts:
            doc_results = self._extract_document(
                doc_text, key_chunks, model, extraction_cfg, use_repetition, meta_map
            )
            all_results.extend(doc_results)

        return all_results

    def build_from_documents(self, doc_texts: list[str], model: str) -> dict | None:
        """Generate extraction entities from document text using LLM."""
        config_model = self._get_extraction_config_from_sys().get("model", "")
        if config_model:
            model = config_model

        doc_text = "".join(doc_texts)
        prompt = (
            'Your job is to build an extraction set from the following information. '
            'Take the information given, and the instructions to extract the important information from this text. '
            'You will create an array of entities that an LLM could use and faithfully reproduce to extract the same '
            'values from this text every time. Return an array formatted as json with the format '
            '{"entities": ["value1", "value2", "etc"]} containing entities for important information in the text. '
            'Do not nest values, keep the array flat and one-dimensional. '
            'Important: The entity names should be Human Readable. Use spaces and Title Case.\n\nPassage:\n'
            + doc_text
        )
        system_prompt = (
            "You are a data scientist working on a project to extract entities and their properties "
            "from a passage. Ensure all entity names are Human Readable with spaces, not underscores."
        )

        chat_agent = create_chat_agent(model, system_prompt=system_prompt, system_config_doc=self._sys_cfg)
        result = chat_agent.run_sync(prompt)
        self._record_usage(result)
        output = result.output.replace("\\n", "").replace("```json", "").replace("```", "")

        if "{" in output and "}" in output:
            return json.loads(output.strip())
        return None

    # ------------------------------------------------------------------
    # Config / model / chunking resolution
    # ------------------------------------------------------------------

    def _get_extraction_config_from_sys(self) -> dict:
        """Build extraction config from pre-fetched system config."""
        config = deepcopy(DEFAULT_EXTRACTION_CONFIG)
        sys_ext_cfg = self._sys_cfg.get("extraction_config", {})
        if sys_ext_cfg:
            _deep_merge(config, sys_ext_cfg)
        else:
            ext_model = self._sys_cfg.get("extraction_model", "")
            ext_strategy = self._sys_cfg.get("extraction_strategy", "")
            if ext_model:
                config["model"] = ext_model
            if ext_strategy:
                from app.models.system_config import _apply_legacy_strategy
                _apply_legacy_strategy(config, ext_strategy)
        return config

    def _resolve_config(self, override: dict | None = None) -> dict:
        cfg = self._get_extraction_config_from_sys()
        if override:
            cfg = deepcopy(cfg)
            _deep_merge(cfg, override)
        return cfg

    def _resolve_model(self, cfg: dict, model: str | None) -> str:
        config_model = cfg.get("model", "")
        if config_model:
            return config_model
        if model:
            return model
        # Fallback to first available model
        models = self._sys_cfg.get("available_models", [])
        if models:
            return models[0].get("name", "")
        return ""

    def _get_model_config(self, model_name: str) -> dict:
        """Look up a model's config dict from available_models."""
        for m in self._sys_cfg.get("available_models", []):
            if m.get("name") == model_name:
                return m
        return {}

    def _model_is_multimodal(self, model_name: str) -> bool:
        """Check if the given model has multimodal capability."""
        return bool(self._get_model_config(model_name).get("multimodal", False))

    def _model_supports_pdf(self, model_name: str) -> bool:
        """Check if the given model has supports_pdf enabled."""
        return bool(self._get_model_config(model_name).get("supports_pdf", False))

    def _resolve_key_chunks(self, keys: list[str], cfg: dict) -> list[list[str]]:
        chunking = cfg.get("chunking", {})
        if chunking.get("enabled") and chunking.get("max_keys_per_chunk", 0) > 0:
            return self._chunk_keys(keys, chunking["max_keys_per_chunk"])
        return [keys]

    # ------------------------------------------------------------------
    # File loading for multimodal extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _load_file_content(file_path: str, model_supports_pdf: bool) -> "list[BinaryContent] | None":
        """Load a file as multimodal content for LLM input.

        Returns a list of BinaryContent (page images or a single PDF blob),
        or None if the file cannot be loaded.
        """
        ext = os.path.splitext(file_path)[1].lower()

        # Image files — return as-is
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"):
            mime_map = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp",
                ".bmp": "image/bmp", ".tiff": "image/tiff",
            }
            try:
                with open(file_path, "rb") as f:
                    return [BinaryContent(data=f.read(), media_type=mime_map.get(ext, "image/png"))]
            except Exception as e:
                logger.error("Failed to read image file %s: %s", file_path, e)
                return None

        # PDFs
        if ext == ".pdf":
            # Native PDF support — send the raw file
            if model_supports_pdf:
                try:
                    with open(file_path, "rb") as f:
                        data = f.read()
                    logger.info("Sending PDF natively: %s", file_path)
                    return [BinaryContent(data=data, media_type="application/pdf")]
                except Exception as e:
                    logger.error("Failed to read PDF %s: %s", file_path, e)
                    return None

            # Image-only model — render pages to PNG
            try:
                import fitz  # pymupdf

                doc = fitz.open(file_path)
                total_pages = len(doc)
                render_pages = min(total_pages, MAX_PDF_PAGES_FOR_IMAGES)
                if total_pages > MAX_PDF_PAGES_FOR_IMAGES:
                    logger.warning(
                        "PDF %s has %d pages, capping at %d for image rendering",
                        file_path, total_pages, MAX_PDF_PAGES_FOR_IMAGES,
                    )
                pages: list[BinaryContent] = []
                for page in doc[:render_pages]:
                    # 144 DPI (2x zoom) balances quality and memory
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    pages.append(BinaryContent(data=pix.tobytes("png"), media_type="image/png"))
                doc.close()
                logger.info("Rendered %d/%d page(s) from %s", render_pages, total_pages, file_path)
                return pages
            except Exception as e:
                logger.error("Failed to render PDF pages from %s: %s", file_path, e)
                return None

        logger.warning("Unsupported file type for multimodal extraction: %s", ext)
        return None

    # ------------------------------------------------------------------
    # Per-document extraction (unified for text and multimodal)
    # ------------------------------------------------------------------

    def _extract_document(
        self, content: ExtractionContent, key_chunks: list[list[str]],
        model: str, cfg: dict, use_repetition: bool,
        meta_map: dict[str, dict] | None = None,
    ) -> list:
        doc_results = []
        for chunk_keys in key_chunks:
            if use_repetition:
                chunk_result = self._extract_with_consensus(content, chunk_keys, model, cfg, meta_map)
            else:
                chunk_result = self._dispatch_extraction(content, chunk_keys, model, cfg, meta_map)
            doc_results.extend(chunk_result)

        if len(key_chunks) > 1:
            return self._merge_chunk_results(doc_results)
        return doc_results

    # ------------------------------------------------------------------
    # Dispatch layer (unified for text and multimodal)
    # ------------------------------------------------------------------

    def _dispatch_extraction(self, content: ExtractionContent, keys: list[str], model_name: str, config: dict, meta_map: dict[str, dict] | None = None) -> list:
        mode = config.get("mode", "two_pass")

        if mode == "one_pass":
            one_pass = config.get("one_pass", {})
            thinking = one_pass.get("thinking", True)
            structured = one_pass.get("structured", True)
            pass_model = one_pass.get("model", "") or model_name
            return self._execute_single_pass(content, keys, pass_model, thinking, structured, meta_map)

        # two_pass (default)
        two_pass = config.get("two_pass", {})
        pass_1_cfg = two_pass.get("pass_1", {})
        pass_2_cfg = two_pass.get("pass_2", {})
        return self._execute_two_pass(content, keys, model_name, pass_1_cfg, pass_2_cfg, meta_map)

    def _execute_single_pass(self, content: ExtractionContent, keys: list[str], model_name: str, thinking: bool, structured: bool, meta_map: dict[str, dict] | None = None) -> list:
        if structured:
            return self._extract_structured(content, keys, model_name, thinking_override=thinking, meta_map=meta_map)
        else:
            return self._extract_fallback_json(content, keys, model_name, thinking_override=thinking, meta_map=meta_map)

    def _execute_two_pass(
        self, content: ExtractionContent, keys: list[str], model_name: str,
        pass_1_cfg: dict, pass_2_cfg: dict,
        meta_map: dict[str, dict] | None = None,
    ) -> list:
        p1_model = pass_1_cfg.get("model", "") or model_name
        p1_thinking = pass_1_cfg.get("thinking", True)
        p1_structured = pass_1_cfg.get("structured", False)

        p2_model = pass_2_cfg.get("model", "") or model_name
        p2_thinking = pass_2_cfg.get("thinking", False)
        p2_structured = pass_2_cfg.get("structured", True)

        # Pass 1
        if p1_structured:
            draft = self._extract_structured(content, keys, p1_model, thinking_override=p1_thinking, meta_map=meta_map)
        else:
            draft = self._extract_fallback_json(content, keys, p1_model, thinking_override=p1_thinking, meta_map=meta_map)

        draft_hint = self._build_draft_hint(draft)

        # Pass 2 — for multimodal two-pass, only re-send images if we have
        # no usable draft (otherwise pass 2 uses the draft + text-only prompt
        # to refine, which is cheaper and avoids double-sending images).
        if draft_hint and self._is_multimodal_content(content):
            p2_content: ExtractionContent = self._format_draft_as_text(draft_hint, keys)
        else:
            p2_content = content

        if p2_structured:
            final = self._extract_structured(
                p2_content, keys, p2_model,
                thinking_override=p2_thinking,
                draft_hint=draft_hint,
                allow_fallback=False,
                meta_map=meta_map,
            )
        else:
            final = self._extract_fallback_json(p2_content, keys, p2_model, thinking_override=p2_thinking, meta_map=meta_map)

        return final or draft or []

    @staticmethod
    def _format_draft_as_text(draft: dict, keys: list[str]) -> str:
        """Convert a draft extraction to a text representation for pass 2.

        This avoids re-sending all page images for the refinement pass.
        """
        lines = []
        for key in keys:
            val = draft.get(key)
            lines.append(f"{key}: {val if val is not None else '[not found]'}")
        return "Draft extraction results:\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def _chunk_keys(self, keys: list[str], max_per_chunk: int) -> list[list[str]]:
        return [keys[i:i + max_per_chunk] for i in range(0, len(keys), max_per_chunk)]

    def _merge_chunk_results(self, results: list) -> list:
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

    def _extract_with_consensus(self, content: ExtractionContent, keys: list[str], model_name: str, config: dict, meta_map: dict[str, dict] | None = None) -> list:
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_1 = executor.submit(self._dispatch_extraction, content, keys, model_name, config, meta_map)
            future_2 = executor.submit(self._dispatch_extraction, content, keys, model_name, config, meta_map)
            result_1 = future_1.result()
            result_2 = future_2.result()

        norm_1 = self._normalize_to_dict(result_1)
        norm_2 = self._normalize_to_dict(result_2)

        if norm_1 == norm_2:
            return result_1 if result_1 else result_2

        result_3 = self._dispatch_extraction(content, keys, model_name, config, meta_map)
        norm_3 = self._normalize_to_dict(result_3)

        consensus = self._majority_vote(keys, [norm_1, norm_2, norm_3])
        return [consensus]

    def _normalize_to_dict(self, results: list) -> dict:
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

    # ------------------------------------------------------------------
    # Draft hint
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Prompt helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_multimodal_content(content: ExtractionContent) -> bool:
        return isinstance(content, list) and bool(content) and isinstance(content[0], BinaryContent)

    def _get_domain_supplement(self) -> str:
        """Get domain-specific prompt supplement if a domain is set."""
        if not self._domain:
            return ""
        from app.services.domain_prompts import get_domain_template
        admin_overrides = self._sys_cfg.get("extraction_config", {}).get("domain_templates")
        template = get_domain_template(self._domain, admin_overrides)
        if not template:
            return ""
        return "\n\n" + template.get("system_supplement", "")

    def _build_fields_prompt(self, keys: list[str], meta_map: dict[str, dict] | None = None) -> str:
        """Build a fields description string with enum/optional annotations and domain hints."""
        from app.services.domain_prompts import get_field_hint
        admin_overrides = self._sys_cfg.get("extraction_config", {}).get("domain_templates") if self._domain else None

        parts = []
        for key in keys:
            fm = (meta_map or {}).get(key, {})
            desc = key
            annotations = []
            enum_vals = fm.get("enum_values", [])
            if enum_vals:
                annotations.append(f"allowed values: {', '.join(enum_vals)}")
            if fm.get("is_optional"):
                annotations.append("optional")
            # Add domain-specific hint
            if self._domain:
                hint = get_field_hint(self._domain, key, admin_overrides)
                if hint:
                    annotations.append(f"hint: {hint}")
            if annotations:
                desc = f"{key} ({'; '.join(annotations)})"
            parts.append(desc)
        return ", ".join(parts)

    def _describe_content(self, content: ExtractionContent) -> str:
        """Return a human label for the content type (for system prompts)."""
        if self._is_multimodal_content(content):
            items = content  # type: ignore[assignment]
            if len(items) == 1 and items[0].media_type == "application/pdf":
                return "attached PDF document"
            return "attached document page images"
        return "text"

    def _build_user_prompt(
        self,
        content: ExtractionContent,
        fields_str: str,
        draft_hint: dict | None = None,
        fallback_mode: bool = False,
    ) -> Union[str, list]:
        """Build the user prompt, handling both text and multimodal content."""
        is_mm = self._is_multimodal_content(content)

        if is_mm:
            items: list[BinaryContent] = content  # type: ignore[assignment]
            is_pdf = len(items) == 1 and items[0].media_type == "application/pdf"
            if is_pdf:
                source_desc = "the attached PDF document"
            else:
                source_desc = f"the attached document pages ({len(items)} page(s))"

            if fallback_mode:
                text_part = (
                    f"Extract the following fields from {source_desc} and return them as a JSON object.\n"
                    f"Return ONLY valid JSON, no markdown, no code blocks, no explanations.\n\n"
                    f"Fields to extract: {fields_str}\n\n"
                    f'Return a JSON object with these exact field names. If a field is not found, use null.\n'
                    f'Example format: {{"Field Name 1": "value", "Field Name 2": null, ...}}'
                )
            else:
                text_part = f"Extract the following fields from {source_desc}: {fields_str}"

            if draft_hint:
                draft_json = json.dumps(draft_hint, ensure_ascii=False)
                text_part = f"Draft extraction (may be incorrect):\n{draft_json}\n\n{text_part}"

            return [text_part, *items]

        # Plain text
        text: str = content  # type: ignore[assignment]
        if fallback_mode:
            prompt = (
                f"Extract the following fields from the text and return them as a JSON object.\n"
                f"Return ONLY valid JSON, no markdown, no code blocks, no explanations.\n\n"
                f"Fields to extract: {fields_str}\n\nText:\n{text}\n\n"
                f'Return a JSON object with these exact field names. If a field is not found, use null.\n'
                f'Example format: {{"Field Name 1": "value", "Field Name 2": null, ...}}'
            )
        else:
            prompt = f"Extract the following fields: {fields_str}\n\nText:\n{text}"

        if draft_hint:
            draft_json = json.dumps(draft_hint, ensure_ascii=False)
            prompt = f"Draft extraction (may be incorrect):\n{draft_json}\n\n{prompt}"

        return prompt

    # ------------------------------------------------------------------
    # Structured extraction
    # ------------------------------------------------------------------

    def _extract_structured(
        self,
        content: ExtractionContent,
        keys: list[str],
        model_name: str,
        thinking_override: Optional[bool] = None,
        draft_hint: dict | None = None,
        allow_fallback: bool = True,
        meta_map: dict[str, dict] | None = None,
    ) -> list:
        # Build dynamic Pydantic model
        field_definitions = {}
        for key in keys:
            safe_key = "".join(c if c.isalnum() else "_" for c in key)
            if not safe_key:
                safe_key = "field"
            if safe_key[0].isdigit():
                safe_key = f"_{safe_key}"
            original_safe_key = safe_key
            counter = 1
            while safe_key in field_definitions:
                safe_key = f"{original_safe_key}_{counter}"
                counter += 1

            # Use Literal type for enum fields
            fm = (meta_map or {}).get(key, {})
            enum_vals = fm.get("enum_values", [])
            if enum_vals:
                field_type = Optional[Literal[tuple(enum_vals)]]  # type: ignore[valid-type]
            else:
                field_type = Optional[str]
            field_definitions[safe_key] = (field_type, Field(default=None, alias=key))

        DynamicEntity = create_model(
            "DynamicEntity",
            __config__=ConfigDict(extra="allow", populate_by_name=True),
            **field_definitions,
        )

        class ExtractionModel(BaseModel):
            model_config = ConfigDict(extra="allow")
            entities: List[DynamicEntity]

            @model_validator(mode="before")
            @classmethod
            def coerce_entities(cls, value):
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
                schema = inline_defs(schema)
            return schema

        api_protocol = get_model_api_protocol(model_name, self._sys_cfg)
        structured_retries = 3

        source_label = self._describe_content(content)
        system_prompt = (
            f"You are a precise entity extraction assistant. Extract the requested information from the {source_label}. "
            f"Extract the exact text as it appears in the document. Do not infer types, do not convert numbers, "
            "do not change formatting. Keep everything as strings. "
            "If a field is not found, leave it as null. "
            "Return a JSON object with an 'entities' key containing a list of extracted objects."
        )
        system_prompt += self._get_domain_supplement()

        try:
            fields_str = self._build_fields_prompt(keys, meta_map)
            prompt = self._build_user_prompt(content, fields_str, draft_hint=draft_hint)

            model_settings = None
            if api_protocol == "vllm":
                schema = _build_structured_output_schema()
                model_settings = {
                    "extra_body": {
                        "structured_outputs": {"json": schema}
                    }
                }

            model = get_agent_model(model_name, thinking_override=thinking_override, system_config_doc=self._sys_cfg)
            agent = Agent(
                model,
                system_prompt=system_prompt,
                output_type=ExtractionModel,
                retries=structured_retries,
                output_retries=structured_retries,
            )

            result = agent.run_sync(prompt, model_settings=model_settings)
            self._record_usage(result)

            if not hasattr(result, "output") or result.output is None:
                return []

            entities = result.output.entities
            raw_entities = []
            for entity in entities:
                if hasattr(entity, "model_dump"):
                    raw_entities.append(entity.model_dump(by_alias=True))
                elif isinstance(entity, dict):
                    raw_entities.append(entity)

            return self._filter_empty_entities(raw_entities)

        except Exception as e:
            error_msg = str(e)
            if ("output validation" in error_msg or "retries" in error_msg.lower()
                    or "validation error" in error_msg.lower()):
                if allow_fallback:
                    return self._extract_fallback_json(content, keys, model_name, thinking_override=thinking_override, meta_map=meta_map)
                return []
            return []

    def _filter_empty_entities(self, entities: list) -> list:
        def is_non_empty(e: dict) -> bool:
            if not isinstance(e, dict) or not e:
                return False
            return any(v not in (None, "", [], {}) for v in e.values())
        return [e for e in entities if is_non_empty(e)]

    # ------------------------------------------------------------------
    # Fallback JSON extraction
    # ------------------------------------------------------------------

    def _extract_fallback_json(
        self,
        content: ExtractionContent,
        keys: list[str],
        model_name: str,
        thinking_override: Optional[bool] = None,
        meta_map: dict[str, dict] | None = None,
    ) -> list:
        try:
            source_label = self._describe_content(content)
            fields_str = self._build_fields_prompt(keys, meta_map)
            prompt = self._build_user_prompt(content, fields_str, fallback_mode=True)

            system_prompt = (
                f"You are a precise entity extraction assistant. Extract the requested information from the {source_label}. "
                "Return ONLY valid JSON, no markdown formatting, no code blocks, no explanations. "
                "If a field is not found, use null."
            )
            system_prompt += self._get_domain_supplement()

            chat_agent = create_chat_agent(
                model_name,
                system_prompt=system_prompt,
                thinking_override=thinking_override,
                system_config_doc=self._sys_cfg,
            )
            result = chat_agent.run_sync(prompt)
            self._record_usage(result)

            output = result.output
            if "```json" in output:
                output = output.split("```json")[1].split("```")[0].strip()
            elif "```" in output:
                output = output.split("```")[1].split("```")[0].strip()

            try:
                parsed = json.loads(output.strip())
                if isinstance(parsed, dict):
                    entity = {key: parsed.get(key) for key in keys}
                    return [entity]
                elif isinstance(parsed, list):
                    return parsed
                return []
            except json.JSONDecodeError:
                return []

        except Exception:
            return []
