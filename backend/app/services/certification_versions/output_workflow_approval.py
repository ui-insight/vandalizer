"""Output-generation-specific consent using the shared saved-plan approval protocol."""
from typing import Literal

from .output_workflow_preparation import OutputWorkflowPreparation
from .connected_workflow_approval import ConnectedScopeRepository, ConnectedScopeRequest


class OutputScopeRequest(ConnectedScopeRequest):
    consent: Literal['save_output_workflow_scope_decision']


class OutputScopeRepository(ConnectedScopeRepository):
    request_model = OutputScopeRequest
    preparation_type = OutputWorkflowPreparation
    module_id = 'output_delivery'
    record_kind = 'output_generation_scope'
    scope_prompt_id = 'output_scope_approval'
