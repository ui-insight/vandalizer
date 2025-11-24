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
    UserModelConfig,
)
from app.utilities.analytics_helper import activity_finish
from app.utilities.config import settings
from app.utilities.extraction_manager_nontyped import ExtractionManagerNonTyped
from app.utilities.semantic_recommender import SemanticRecommender


def normalize_results(results) -> Dict[str, Any]:
    """Normalize a list of dicts into a single dict of unique values (comma-joined),
    or return the dict as-is. Non-list/dict inputs yield {}."""
    if isinstance(results, dict):
        return results
    if not isinstance(results, list):
        return {}

    collected: Dict[str, List[Any]] = defaultdict(list)
    seen: Dict[str, set] = defaultdict(set)

    for item in results:
        if not isinstance(item, dict):
            continue
        for k, v in item.items():
            if v in (None, "", [], {}):
                continue
            if v in seen[k]:
                continue
            seen[k].add(v)
            collected[k].append(v)

    return {
        k: vals[0] if len(vals) == 1 else ", ".join(map(str, vals))
        for k, vals in collected.items()
    }


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

        # get user model config
        user_id = activity.user_id if activity else None
        user_model_config = UserModelConfig.objects(user_id=user_id).first()
        model_name = (
            user_model_config.name
            if user_model_config and user_model_config.name
            else settings.base_model
        )

        # Perform extraction
        em = ExtractionManagerNonTyped()
        em.root_path = root_path
        results = em.extract(keys, document_uuids, model_name)
        raw_results = deepcopy(results)

        if len(results) == 1:
            results = results[0]

        debug(results)

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
            for key in results:
                search_set_item = SearchSetItem.objects(searchphrase=key).first()
                if search_set_item and search_set_item.pdf_binding:
                    bindings[search_set_item.pdf_binding] = results[key]

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

        # Normalize and save results
        normalized_results = normalize_results(results)
        debug(normalized_results)

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

        # Ingest extraction into vector database for recommendations
        try:
            ingestion_text = ""
            ingestion_text += "# Documents selected:"
            for document in documents:
                ingestion_text += f"\n- {document.title}"
            ingestion_text += "\n\n# Extraction performed:\n"
            for key in keys:
                ingestion_text += f"- {key}\n"

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
                    f"Successfully ingested Extrxtion: {str(search_set.uuid)} with text length {len(ingestion_text)}"
                )

                # Clear recommendations cache so new extraction appears immediately
                try:
                    from app.blueprints.workflows.routes import (
                        clear_recommendations_cache,
                    )

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
