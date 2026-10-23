"""Every automatic assessment route retains the original owned receipt reference."""
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services.certification_versions.review_attempts import ReviewAlreadyExists


@pytest.mark.parametrize(('suffix', 'service_name'), [
    ('connected', 'ConnectedWorkflowAssessment'), ('advanced', 'AdvancedWorkflowAssessment'),
    ('output', 'OutputWorkflowAssessment'), ('validation', 'ValidationAssessment'),
    ('batch', 'BatchAssessment'), ('governance', 'GovernanceAssessment'),
])
async def test_module_review_conflict_keeps_owned_reference(monkeypatch, suffix, service_name):
    routes = importlib.import_module('app.routers.certification_' + suffix)
    monkeypatch.setattr(routes.runtime, 'versioning_enabled', lambda: True)
    conflict = ReviewAlreadyExists('a' * 32)
    service = SimpleNamespace(request=AsyncMock(side_effect=conflict), retry=AsyncMock(side_effect=conflict))
    monkeypatch.setattr(routes, service_name, lambda: service)
    for kind in ('assess', 'retry'):
        with pytest.raises(HTTPException) as caught:
            await routes.action(SimpleNamespace(user_id='owner'), 'enrollment', payload=object(), reference='saved', kind=kind)
        assert caught.value.status_code == 409
        assert caught.value.detail == conflict.detail

@pytest.mark.parametrize('kind', ['process', 'workflow'])
async def test_design_review_conflict_keeps_owned_reference(monkeypatch, kind):
    from app.routers import certification as routes
    from app.services.certification_versions import runtime
    module_name, service_name = ('process_delivery', 'ProcessAssessment') if kind == 'process' else ('workflow_design_delivery', 'WorkflowDesignAssessment')
    service_module = importlib.import_module('app.services.certification_versions.' + module_name)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    conflict = ReviewAlreadyExists('a' * 32)
    service = SimpleNamespace(request=AsyncMock(side_effect=conflict), retry=AsyncMock(side_effect=conflict))
    monkeypatch.setattr(service_module, service_name, lambda: service)
    for retry in (False, True):
        with pytest.raises(HTTPException) as caught:
            if kind == 'process':
                await routes._process_design_action(SimpleNamespace(user_id='owner'), 'enrollment',
                    payload=object(), submission_id='saved', assessment=True, parent_id='parent' if retry else None)
            else:
                await routes._workflow_design_action(SimpleNamespace(user_id='owner'), 'enrollment',
                    payload=object(), reference='saved', action='retry' if retry else 'assess')
        assert caught.value.status_code == 409
        assert caught.value.detail == conflict.detail
