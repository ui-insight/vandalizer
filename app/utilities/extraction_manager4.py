"""Improved extraction manager with better batching, context, and result handling."""

from __future__ import annotations

import json
import os
import textwrap
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import openai
from devtools import debug

from app.models import SearchSetItem, SmartDocument
from app.utilities.agents import create_chat_agent, extract_entities_with_agent
from app.utilities.config import settings
from app.utilities.llm_helpers import remove_code_markers

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


@dataclass(frozen=True)
class ExtractionField:
    """Represents metadata about a field to extract."""

    name: str
    description: str | None = None
    type_hint: str | None = None


@dataclass
class DocumentExtraction:
    """Holds extraction details for a single document."""

    document_uuid: str
    document_title: str | None
    entities: list[dict] = field(default_factory=list)
    chunks_processed: int = 0
    chunk_errors: list[str] = field(default_factory=list)

    def add_entities(self, new_entities: Iterable[dict]) -> None:
        """Add entities to the document result, deduplicating entries."""
        seen = {json.dumps(entity, sort_keys=True) for entity in self.entities}
        for entity in new_entities:
            signature = json.dumps(entity, sort_keys=True)
            if signature in seen:
                continue
            seen.add(signature)
            self.entities.append(entity)


@dataclass
class ExtractionRunResult:
    """Aggregated result for an extraction run."""

    entities: list[dict]
    by_document: list[DocumentExtraction]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.entities)

    def __iter__(self):
        return iter(self.entities)

    def __getitem__(self, index):
        return self.entities[index]

    def to_serializable(self) -> dict:
        """Return a JSON-serializable representation of the run."""
        return {
            "entities": self.entities,
            "by_document": [
                {
                    "document_uuid": doc.document_uuid,
                    "document_title": doc.document_title,
                    "entities": doc.entities,
                    "chunks_processed": doc.chunks_processed,
                    "chunk_errors": doc.chunk_errors,
                }
                for doc in self.by_document
            ],
            "warnings": self.warnings,
            "errors": self.errors,
        }


class ExtractionManager4:
    """Coordinate extraction runs with batching, context, and richer results."""

    root_path = ""

    def __init__(
        self,
        *,
        model_name: str | None = None,
        max_workers: int = 4,
        chunk_size: int = 6000,
        chunk_overlap: int = 400,
    ) -> None:
        self.model_name = model_name or settings.base_model
        self.max_workers = max(1, max_workers)
        self.chunk_size = max(1000, chunk_size)
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size // 2))
        if OPENAI_API_KEY:
            openai.api_key = OPENAI_API_KEY

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def build_from_documents(
        self,
        document_uuids: Sequence[str],
        model: str | None = None,
    ) -> dict | None:
        """Suggest extraction fields based on documents."""
        documents = self._load_documents(document_uuids)
        if not documents:
            return None

        assembled_text = "\n\n---\n\n".join(
            textwrap.dedent(
                f"""Document title: {doc['title'] or 'Untitled'}\nDocument UUID: {doc['uuid']}\n\n{doc['text'].strip()}"""
            )
            for doc in documents
        )

        prompt = textwrap.dedent(
            """\
            Your job is to propose an extraction schema for the provided material.
            Using the supplied documents and their instructions, produce a JSON object with this exact shape:
            {"entities": ["Field Name 1", "Field Name 2", "..."]}.
            Focus on the information a user would consistently want to capture from similar documents.
            Do not include actual values, only the entity names. The array must be flat.

            Documents:
            """
        )

        system_prompt = (
            "You are a data scientist defining structured extraction schemas. "
            "Return only valid JSON that matches the requested shape."
        )

        chat_agent = create_chat_agent(model or self.model_name, system_prompt=system_prompt)
        result = chat_agent.run_sync(prompt + assembled_text)
        output = remove_code_markers(result.output)
        output = output.replace("\\n", "").strip()

        if not output:
            return None

        try:
            return json.loads(output)
        except json.JSONDecodeError:
            debug("Failed to parse build_from_documents output", output)
            return None

    def extract(
        self,
        extraction_items: Sequence[str] | Sequence[SearchSetItem] | Sequence[dict],
        document_uuids: Sequence[str],
        *,
        full_text: str | None = None,
        searchset_uuid: str | None = None,
        field_metadata: Sequence[dict] | None = None,
        model_name: str | None = None,
    ) -> ExtractionRunResult:
        """Extract the requested fields from the provided documents."""
        active_model = model_name or self.model_name
        fields = self._normalize_fields(extraction_items, field_metadata, searchset_uuid)

        if not fields:
            warning = "No extraction fields provided."
            return ExtractionRunResult(entities=[], by_document=[], warnings=[warning])

        documents = self._load_documents(document_uuids, full_text=full_text)
        if not documents:
            error = "No documents resolved for extraction."
            return ExtractionRunResult(entities=[], by_document=[], errors=[error])

        context_hint = self._build_field_context(fields)
        doc_chunks = self._chunk_documents(documents)

        doc_results: dict[str, DocumentExtraction] = {
            doc["uuid"]: DocumentExtraction(
                document_uuid=doc["uuid"],
                document_title=doc.get("title"),
            )
            for doc in documents
        }

        warnings: list[str] = []
        errors: list[str] = []

        max_workers = min(self.max_workers, max(1, len(doc_chunks)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    self._extract_chunk,
                    chunk=chunk,
                    fields=fields,
                    context_hint=context_hint,
                    model_name=active_model,
                ): chunk
                for chunk in doc_chunks
            }

            for future, chunk in future_map.items():
                doc_uuid = chunk["document_uuid"]
                document_result = doc_results[doc_uuid]
                try:
                    chunk_entities = future.result()
                    if isinstance(chunk_entities, dict) and chunk_entities.get("error"):
                        document_result.chunk_errors.append(chunk_entities["error"])
                        errors.append(chunk_entities["error"])
                    else:
                        document_result.add_entities(chunk_entities)
                except Exception as exc:  # noqa: BLE001
                    message = f"Extraction failed for document {doc_uuid}: {exc}"
                    debug(message)
                    document_result.chunk_errors.append(message)
                    errors.append(message)
                finally:
                    document_result.chunks_processed += 1

        aggregated_entities: list[dict] = []
        seen_entities = set()
        for document_result in doc_results.values():
            for entity in document_result.entities:
                signature = json.dumps(entity, sort_keys=True)
                if signature in seen_entities:
                    continue
                seen_entities.add(signature)
                aggregated_entities.append(entity)

        return ExtractionRunResult(
            entities=aggregated_entities,
            by_document=list(doc_results.values()),
            warnings=warnings,
            errors=errors,
        )

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _normalize_fields(
        self,
        extraction_items: Sequence[str] | Sequence[SearchSetItem] | Sequence[dict],
        field_metadata: Sequence[dict] | None,
        searchset_uuid: str | None,
    ) -> list[ExtractionField]:
        """Normalize raw extraction items into ExtractionField objects."""
        fields: list[ExtractionField] = []

        if field_metadata:
            for item in field_metadata:
                name = item.get("name") or item.get("searchphrase")
                if not name:
                    continue
                fields.append(
                    ExtractionField(
                        name=name.strip(),
                        description=item.get("description"),
                        type_hint=item.get("type_hint"),
                    )
                )
            return fields

        if searchset_uuid:
            items = SearchSetItem.objects(
                searchset=searchset_uuid,
                searchphrase__in=[self._item_name(item) for item in extraction_items],
                searchtype="extraction",
            )
            for item in items:
                fields.append(
                    ExtractionField(
                        name=item.searchphrase.strip(),
                        description=item.title,
                    )
                )

        if not fields:
            for item in extraction_items:
                name = self._item_name(item)
                if not name:
                    continue
                fields.append(ExtractionField(name=name.strip()))

        # Deduplicate while preserving order
        seen = set()
        unique_fields: list[ExtractionField] = []
        for field in fields:
            if field.name in seen:
                continue
            seen.add(field.name)
            unique_fields.append(field)
        return unique_fields

    def _item_name(self, item) -> str | None:
        if isinstance(item, SearchSetItem):
            return item.searchphrase
        if isinstance(item, dict):
            return item.get("name") or item.get("searchphrase")
        if isinstance(item, str):
            return item
        return None

    def _load_documents(
        self,
        document_uuids: Sequence[str],
        *,
        full_text: str | None = None,
    ) -> list[dict]:
        """Fetch documents and return ordered metadata."""
        if full_text is not None:
            return [
                {
                    "uuid": "__provided_text__",
                    "title": "Provided Text",
                    "text": full_text,
                }
            ]

        if not document_uuids:
            return []

        docs = SmartDocument.objects(uuid__in=list(document_uuids))
        doc_map = {doc.uuid: doc for doc in docs}
        ordered_docs = []
        for uuid in document_uuids:
            doc = doc_map.get(uuid)
            if doc is None:
                debug(f"Document not found for extraction: {uuid}")
                continue
            ordered_docs.append(
                {
                    "uuid": doc.uuid,
                    "title": doc.title,
                    "text": doc.raw_text or "",
                }
            )
        return ordered_docs

    def _build_field_context(self, fields: Sequence[ExtractionField]) -> str:
        """Construct a context string describing the extraction fields."""
        lines = []
        for field in fields:
            description = field.description or "No additional description provided."
            type_hint = f" (Type hint: {field.type_hint})" if field.type_hint else ""
            lines.append(f"- {field.name}: {description}{type_hint}")
        return "Requested fields:\n" + "\n".join(lines)

    def _chunk_documents(self, documents: Sequence[dict]) -> list[dict]:
        """Break documents into manageable chunks for extraction."""
        chunks: list[dict] = []
        for doc in documents:
            text = doc["text"]
            if not text:
                chunks.append(
                    {
                        "document_uuid": doc["uuid"],
                        "document_title": doc.get("title"),
                        "text": "",
                        "index": 0,
                        "total": 1,
                    }
                )
                continue

            doc_chunks = list(self._split_text(text))
            total = len(doc_chunks)
            for index, chunk_text in enumerate(doc_chunks):
                chunks.append(
                    {
                        "document_uuid": doc["uuid"],
                        "document_title": doc.get("title"),
                        "text": chunk_text,
                        "index": index,
                        "total": total,
                    }
                )
        return chunks

    def _split_text(self, text: str) -> Iterable[str]:
        """Split text into overlapping chunks based on the configured size."""
        if len(text) <= self.chunk_size:
            yield text
            return

        start = 0
        text_length = len(text)
        while start < text_length:
            end = min(text_length, start + self.chunk_size)
            yield text[start:end]
            if end == text_length:
                break
            start = end - self.chunk_overlap
            if start < 0:
                start = 0

    def _extract_chunk(
        self,
        *,
        chunk: dict,
        fields: Sequence[ExtractionField],
        context_hint: str,
        model_name: str,
    ) -> list[dict] | dict:
        """Run extraction for a single chunk."""
        keys = [field.name for field in fields]
        doc_title = chunk.get("document_title") or "Untitled Document"
        chunk_context = textwrap.dedent(
            f"""\
            {context_hint}

            Document title: {doc_title}
            Document UUID: {chunk['document_uuid']}
            Chunk: {chunk['index'] + 1} of {chunk['total']}
            """
        )

        try:
            result = extract_entities_with_agent(
                text=chunk["text"],
                keys=keys,
                context=chunk_context,
                model_name=model_name,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            debug("Chunk extraction error", exc)
            return {"error": str(exc)}


__all__ = [
    "ExtractionManager4",
    "ExtractionRunResult",
    "DocumentExtraction",
    "ExtractionField",
]
