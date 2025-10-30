"""Celery tasks for extraction operations."""

from copy import deepcopy
from pathlib import Path

from devtools import debug
from flask import current_app, render_template
from pypdf import PdfReader, PdfWriter

from app.celery_worker import celery_app
from app.models import ActivityEvent, SearchSet, SearchSetItem, SmartDocument
from app.utilities.analytics_helper import activity_finish
from app.utilities.extraction_manager3 import ExtractionManager3
from app.utilities.semantic_recommender import SemanticRecommender


def normalize_results(results):
    """Normalize extraction results for display."""
    if isinstance(results, dict):
        # Single document result - convert to list format
        return [results]
    elif isinstance(results, list):
        # Already a list
        return results
    else:
        return []


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

        # Perform extraction
        em = ExtractionManager3()
        em.root_path = root_path
        results = em.extract(keys, document_uuids)
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

            # Ingest into semantic recommender
            persist_directory = Path(root_path) / "chroma_db"
            recommendation_manager = SemanticRecommender(
                persist_directory=str(persist_directory)
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
            activity.save()
        raise
