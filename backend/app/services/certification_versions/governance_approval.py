"""Approve or hold only the exact saved original diagnostic capstone plan."""
from typing import Literal

from .connected_workflow_approval import ConnectedScopeRepository, ConnectedScopeRequest
from .governance_preparation import GovernancePreparation


class GovernanceApprovalRequest(ConnectedScopeRequest):
    consent: Literal['save_bounded_governance_execution_decision']


class GovernanceApprovalRepository(ConnectedScopeRepository):
    request_model = GovernanceApprovalRequest
    preparation_type = GovernancePreparation
    module_id = 'governance'
    record_kind = 'bounded_governance_execution'
    scope_prompt_id = 'governance_execution_approval'
