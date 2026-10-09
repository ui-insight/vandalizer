"""Budget-specific consent using the shared saved-plan approval protocol."""
from typing import Literal

from .advanced_workflow_preparation import AdvancedWorkflowPreparation
from .connected_workflow_approval import ConnectedScopeRepository, ConnectedScopeRequest


class AdvancedScopeRequest(ConnectedScopeRequest):
    consent: Literal['save_budget_workflow_scope_decision']


class AdvancedScopeRepository(ConnectedScopeRepository):
    request_model = AdvancedScopeRequest
    preparation_type = AdvancedWorkflowPreparation
    module_id = 'advanced_nodes'
    record_kind = 'budget_workflow_scope'
    scope_prompt_id = 'budget_scope_approval'
