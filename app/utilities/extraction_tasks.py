"""Celery tasks for extraction operations."""

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from devtools import debug
from pypdf import PdfReader, PdfWriter

from app.celery_worker import celery_app
from app.models import (
    ActivityEvent,
    ActivityStatus,
    SearchSet,
    SearchSetItem,
    SmartDocument,
)
from app.utilities.analytics_helper import activity_finish
from app.utilities.config import get_user_model_name
from app.utilities.extraction_manager_nontyped import ExtractionManagerNonTyped
from app.utilities.semantic_recommender import SemanticRecommender


def _build_extraction_ingestion_text(documents: list[SmartDocument], keys: list) -> str:
    ingestion_text = "# Documents selected:"
    for document in documents:
        # Include document title and first part of raw_text for better semantic matching
        ingestion_text += f"\n- {document.title}"
        if document.raw_text:
            text_preview = (
                document.raw_text[:500]
                if len(document.raw_text) > 500
                else document.raw_text
            )
            ingestion_text += f"\n{text_preview}"
    if keys:
        ingestion_text += "\n\n# Extraction performed:\n"
        for key in keys:
            ingestion_text += f"- {key}\n"
    return ingestion_text


def normalize_results(results, expected_keys: List[str] = None) -> Dict[str, Any]:
    """Normalize a list of dicts into a single dict of unique values (comma-joined),
    or return the dict as-is. Non-list/dict inputs yield {}.
    
    Args:
        results: The extraction results (dict or list of dicts)
        expected_keys: Optional list of keys that should be present in the output.
                      If provided, all keys will be included even if None/empty.
    """
    normalized = {}
    
    if isinstance(results, dict):
        normalized = results.copy()
    elif isinstance(results, list):
        collected: Dict[str, List[Any]] = defaultdict(list)
        seen: Dict[str, set] = defaultdict(set)

        for item in results:
            if not isinstance(item, dict):
                continue
            for k, v in item.items():
                # Skip empty values when collecting, but we'll include all keys later
                if v in (None, "", [], {}):
                    continue
                if v in seen[k]:
                    continue
                seen[k].add(v)
                collected[k].append(v)

        normalized = {
            k: vals[0] if len(vals) == 1 else ", ".join(map(str, vals))
            for k, vals in collected.items()
        }
    else:
        normalized = {}
    
    # If expected_keys is provided, ensure all keys are present
    if expected_keys:
        for key in expected_keys:
            if key not in normalized:
                normalized[key] = None
    
    return normalized


@celery_app.task(
    name="tasks.extraction.run",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def perform_extraction_task(
    activity_id: str,
    searchset_uuid: str,
    document_uuids: list,
    keys: list,
    root_path: str,
    fillable_pdf_url: str = None,
    extraction_config_override: dict = None,
):
    """
    Perform extraction task asynchronously.

    Args:
        activity_id: Activity ID for tracking
        searchset_uuid: SearchSet UUID
        document_uuids: List of document UUIDs to extract from
        keys: List of extraction keys/fields
        root_path: Application root path
        fillable_pdf_url: Optional URL to fillable PDF template

    Returns:
        dict: Results including template and activity_id
    """
    try:
        # Update activity status to running
        activity = ActivityEvent.objects(id=activity_id).first()
        if activity:
            activity.status = "running"
            activity.save()

        # Get a valid user model, auto-falling back if their saved model is stale.
        user_id = activity.user_id if activity else None
        model_name = get_user_model_name(user_id)

        # Perform extraction
        em = ExtractionManagerNonTyped()
        em.root_path = root_path
        results = em.extract(
            keys, document_uuids, model=model_name,
            extraction_config_override=extraction_config_override,
            activity_id=activity_id,
        )
        raw_results = deepcopy(results)

        result_count = (
            len(results)
            if isinstance(results, list)
            else (1 if isinstance(results, dict) else 0)
        )
        debug(f"Extraction produced {result_count} result(s)")

        if len(results) == 1:
            results = results[0]

        # Get search set and documents
        search_set = SearchSet.objects(uuid=searchset_uuid).first()
        documents = []
        for doc_uuid in document_uuids:
            document = SmartDocument.objects(uuid=doc_uuid).first()
            if document:
                documents.append(document)

        # Handle fillable PDF if present
        if fillable_pdf_url and fillable_pdf_url != "":
            bindings = {}
            # results might be a dict or list, handle both
            if isinstance(results, dict):
                for key in results:
                    search_set_item = SearchSetItem.objects(searchphrase=key).first()
                    if search_set_item and search_set_item.pdf_binding:
                        bindings[search_set_item.pdf_binding] = results[key]
            elif isinstance(results, list) and len(results) > 0:
                # If results is a list, use the first item
                first_result = results[0] if isinstance(results[0], dict) else {}
                for key in first_result:
                    search_set_item = SearchSetItem.objects(searchphrase=key).first()
                    if search_set_item and search_set_item.pdf_binding:
                        bindings[search_set_item.pdf_binding] = first_result[key]

            pdf_path = Path(root_path) / "static" / "uploads" / fillable_pdf_url
            reader = PdfReader(pdf_path)
            reader.get_fields()
            writer = PdfWriter()
            writer.append(reader)

            writer.update_page_form_field_values(
                writer.pages[0],
                bindings,
                auto_regenerate=False,
            )

            output_pdf_path = Path(root_path) / "static" / "fillable_form.pdf"
            with Path.open(output_pdf_path, "wb") as f:
                writer.write(f)

        # Normalize and save results - pass keys to ensure all are included
        normalized_results = normalize_results(results, expected_keys=keys)
        if isinstance(normalized_results, dict):
            debug(
                f"Normalized results contains {len(normalized_results)} fields"
            )

        # Finish activity
        if activity:
            activity_finish(activity)
            activity.result_snapshot = {
                "raw": raw_results,
                "normalized": normalized_results,
                "document_uuids": document_uuids,
                "search_set_uuid": searchset_uuid,
            }
            activity.save()
            
            # Trigger description generation now that we have results
            # This will generate a better title based on actual extraction results
            try:
                from app.utilities.activity_description import generate_activity_description_task
                debug(f"Triggering description generation for completed extraction {activity.id}")
                generate_activity_description_task.delay(str(activity.id), activity.type, document_uuids)
            except Exception as e:
                debug(f"Error triggering description generation after extraction: {e}")

        # Ingest extraction into vector database for recommendations asynchronously
        try:
            if search_set:
                ingest_extraction_recommendation_task.delay(
                    str(search_set.uuid), document_uuids, keys
                )
        except Exception as e:
            debug(f"Error scheduling extraction recommendation ingestion: {e}")

        return {
            "status": "completed",
            "activity_id": str(activity_id),
            "results": normalized_results,
        }

    except Exception as e:
        debug(f"Error in extraction task: {e}")
        # Update activity status to failed
        if activity:
            activity.status = "failed"
            activity.error = str(e)
            activity_finish(activity, status=ActivityStatus.FAILED, error=str(e))
        raise


@celery_app.task(
    name="tasks.extraction.ingest_recommendation",
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
)
def ingest_extraction_recommendation_task(
    searchset_uuid: str, document_uuids: list, keys: list
):
    """Build and ingest extraction recommendations without blocking extraction results."""
    try:
        search_set = SearchSet.objects(uuid=searchset_uuid).first()
        if not search_set:
            debug(f"Recommendation ingest skipped: search set not found {searchset_uuid}")
            return

        documents = []
        for doc_uuid in document_uuids:
            document = SmartDocument.objects(uuid=doc_uuid).first()
            if document:
                documents.append(document)

        if not documents:
            debug(
                f"Recommendation ingest skipped: no documents found for {searchset_uuid}"
            )
            return

        ingestion_text = _build_extraction_ingestion_text(documents, keys)

        # Ingest into semantic recommender - use singleton to avoid expensive re-initialization
        try:
            from app.blueprints.workflows.routes import get_recommendation_manager

            recommendation_manager = get_recommendation_manager()
            recommendation_manager.ingest_recommendation_item(
                identifier=str(search_set.uuid),
                ingestion_text=ingestion_text,
                recommendation_type="Extraction",
            )

            debug(
                f"Successfully ingested Extraction: {str(search_set.uuid)} with text length {len(ingestion_text)}"
            )

            # Clear recommendations cache so new extraction appears immediately
            try:
                from app.blueprints.workflows.routes import clear_recommendations_cache

                clear_recommendations_cache()
            except Exception as cache_error:
                debug(f"Error clearing recommendations cache: {cache_error}")
        except ImportError:
            # Fallback if singleton not available (shouldn't happen in normal flow)
            persist_directory = "data/recommendations_vectordb"
            recommendation_manager = SemanticRecommender(
                persist_directory=persist_directory
            )
            recommendation_manager.ingest_recommendation_item(
                identifier=str(search_set.uuid),
                ingestion_text=ingestion_text,
                recommendation_type="Extraction",
            )
    except Exception as e:
        debug(f"Error ingesting extraction recommendation: {e}")
