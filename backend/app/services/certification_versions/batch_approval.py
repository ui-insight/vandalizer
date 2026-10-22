"""Phase-bound explicit learner approval using the saved-plan protocol."""
from typing import Literal

from .connected_workflow_approval import ConnectedScopeRepository, ConnectedScopeRequest
from .batch_preparation import BatchPreparation


class BatchScopeRequest(ConnectedScopeRequest):
    consent: Literal['save_bounded_batch_scope_decision']


class BatchScopeRepository(ConnectedScopeRepository):
    request_model = BatchScopeRequest
    preparation_type = BatchPreparation
    module_id = 'batch_processing'
    record_kind = 'bounded_batch_scope'
    scope_prompt_id = 'batch_scope_approval'
