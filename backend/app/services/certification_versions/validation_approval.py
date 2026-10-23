"""Explicit suite-specific consent using the shared saved-plan approval protocol."""
from typing import Literal

from .connected_workflow_approval import ConnectedScopeRepository, ConnectedScopeRequest
from .validation_preparation import ValidationPreparation


class ValidationScopeRequest(ConnectedScopeRequest):
    consent: Literal['save_validation_suite_scope_decision']


class ValidationScopeRepository(ConnectedScopeRepository):
    request_model = ValidationScopeRequest
    preparation_type = ValidationPreparation
    module_id = 'validation_qa'
    record_kind = 'validation_suite_scope'
    scope_prompt_id = 'validation_scope_approval'
