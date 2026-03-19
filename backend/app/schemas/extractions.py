"""Request/response models for extraction endpoints."""

from typing import Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# SearchSet
# ---------------------------------------------------------------------------

class CreateSearchSetRequest(BaseModel):
    title: str
    space: Optional[str] = None
    set_type: str = "extraction"
    extraction_config: Optional[dict] = None


class UpdateSearchSetRequest(BaseModel):
    title: Optional[str] = None
    extraction_config: Optional[dict] = None


class SearchSetItemRequest(BaseModel):
    searchphrase: str
    searchtype: str = "extraction"
    title: Optional[str] = None
    is_optional: bool = False
    enum_values: list[str] = []


class UpdateSearchSetItemRequest(BaseModel):
    searchphrase: Optional[str] = None
    title: Optional[str] = None
    is_optional: Optional[bool] = None
    enum_values: Optional[list[str]] = None


class ReorderItemsRequest(BaseModel):
    item_ids: list[str]


class BuildFromDocumentRequest(BaseModel):
    document_uuids: list[str]
    model: Optional[str] = None


class SearchSetResponse(BaseModel):
    id: str
    title: str
    uuid: str
    space: str
    status: str
    set_type: str
    user_id: Optional[str] = None
    is_global: bool = False
    verified: bool = False
    item_count: int = 0
    extraction_config: dict = {}
    fillable_pdf_url: Optional[str] = None
    quality_score: Optional[float] = None
    quality_tier: Optional[str] = None
    last_validated_at: Optional[str] = None
    validation_run_count: int = 0


class SearchSetItemResponse(BaseModel):
    id: str
    searchphrase: str
    searchset: Optional[str] = None
    searchtype: str
    title: Optional[str] = None
    is_optional: bool = False
    enum_values: list[str] = []
    pdf_binding: Optional[str] = None


class ExportPDFRequest(BaseModel):
    results: dict[str, str]
    document_names: list[str] = []


# ---------------------------------------------------------------------------
# Extraction execution
# ---------------------------------------------------------------------------

class RunExtractionRequest(BaseModel):
    search_set_uuid: str
    document_uuids: list[str]
    model: Optional[str] = None
    extraction_config_override: Optional[dict] = None


class RunExtractionSyncRequest(BaseModel):
    search_set_uuid: str
    document_uuids: list[str]
    model: Optional[str] = None
    extraction_config_override: Optional[dict] = None


class ExtractionStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[list] = None


# ---------------------------------------------------------------------------
# Extraction test cases & validation
# ---------------------------------------------------------------------------

class CreateTestCaseRequest(BaseModel):
    search_set_uuid: str
    label: str
    source_type: str  # "text" | "document"
    source_text: Optional[str] = None
    document_uuid: Optional[str] = None
    expected_values: dict[str, str] = {}


class UpdateTestCaseRequest(BaseModel):
    label: Optional[str] = None
    source_type: Optional[str] = None
    source_text: Optional[str] = None
    document_uuid: Optional[str] = None
    expected_values: Optional[dict[str, str]] = None


class TestCaseResponse(BaseModel):
    id: str
    uuid: str
    search_set_uuid: str
    label: str
    source_type: str
    source_text: Optional[str] = None
    document_uuid: Optional[str] = None
    expected_values: dict[str, str] = {}
    user_id: str
    created_at: str


class RunValidationRequest(BaseModel):
    search_set_uuid: str
    test_case_uuids: list[str] = []
    num_runs: int = 3
    model: Optional[str] = None


class ValidationSource(BaseModel):
    source_type: str  # "document" | "text"
    document_uuid: Optional[str] = None
    label: Optional[str] = None
    source_text: Optional[str] = None
    expected_values: dict[str, str] = {}


class RunValidationV2Request(BaseModel):
    search_set_uuid: str
    sources: list[ValidationSource]
    num_runs: int = 3
    model: Optional[str] = None


class FieldValidationResult(BaseModel):
    field_name: str
    expected: Optional[str] = None
    extracted_values: list[Optional[str]] = []
    most_common_value: Optional[str] = None
    consistency: float = 0.0
    accuracy: Optional[float] = None
    accuracy_method: Optional[str] = None
    enum_compliance: Optional[float] = None


class TestCaseValidationResult(BaseModel):
    test_case_uuid: str
    label: str
    fields: list[FieldValidationResult] = []
    overall_accuracy: Optional[float] = None
    overall_consistency: float = 0.0


class ValidationResponse(BaseModel):
    search_set_uuid: str
    num_runs: int
    test_cases: list[TestCaseValidationResult] = []
    aggregate_accuracy: Optional[float] = None
    aggregate_consistency: float = 0.0
