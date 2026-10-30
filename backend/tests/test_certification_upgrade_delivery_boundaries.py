"""Upgrade dispatch keeps feature gates and error mapping around lazy services."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.routers import certification_upgrades as routes
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.upgrade_comparison import UpgradeUnavailable


@pytest.mark.asyncio
@pytest.mark.parametrize('deliver', [routes.deliver, routes.transfer_delivery])
async def test_disabled_rollout_does_not_construct_service(monkeypatch, deliver):
    monkeypatch.setattr(routes, 'versioning_enabled', lambda: False)

    def unavailable_service():
        pytest.fail('Disabled rollout must reject before constructing a service')

    with pytest.raises(HTTPException) as error:
        await deliver(SimpleNamespace(user_id='learner'), unavailable_service, True, 'request')
    assert error.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize('deliver', [routes.deliver, routes.transfer_delivery])
async def test_saved_reads_keep_original_identity_when_rollout_is_disabled(monkeypatch, deliver):
    monkeypatch.setattr(routes, 'versioning_enabled', lambda: False)

    async def saved(user_id, request_id, *, cursor):
        return {'user_id': user_id, 'request_id': request_id, 'cursor': cursor}

    result = await deliver(SimpleNamespace(user_id='learner'), lambda: saved, False, 'original', cursor='page')
    assert result == {'user_id': 'learner', 'request_id': 'original', 'cursor': 'page'}


@pytest.mark.asyncio
@pytest.mark.parametrize('deliver', [routes.deliver, routes.transfer_delivery])
@pytest.mark.parametrize('failure,status', [
    (EnrollmentConflict, 409), (CourseCatalogError, 503), (UpgradeUnavailable, 404),
])
async def test_service_construction_errors_keep_http_mapping(monkeypatch, deliver, failure, status):
    monkeypatch.setattr(routes, 'versioning_enabled', lambda: True)

    def unavailable_service():
        raise failure('Original choice needs attention')

    with pytest.raises(HTTPException) as error:
        await deliver(SimpleNamespace(user_id='learner'), unavailable_service, True, 'original')
    assert error.value.status_code == status
    assert error.value.detail == 'Original choice needs attention'


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint,method', [
    (routes.preview_credit_transfer, 'preview'),
    (routes.apply_credit_transfer, 'apply'),
    (routes.saved_credit_transfer, 'saved'),
])
async def test_credit_transfer_routes_dispatch_the_authenticated_request(monkeypatch, endpoint, method):
    monkeypatch.setattr(routes, 'versioning_enabled', lambda: True)
    operation = AsyncMock(return_value={'original_receipt': 'saved'})
    service = Mock(return_value=SimpleNamespace(**{method: operation}))
    monkeypatch.setattr(routes, 'CreditTransfer', service)
    payload = {'request_id': 'original'} if method == 'apply' else 'original'
    result = await endpoint(payload, user=SimpleNamespace(user_id='learner'))
    assert result == {'original_receipt': 'saved'}
    operation.assert_awaited_once_with('learner', payload)
    service.assert_called_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', [routes.preview_credit_transfer, routes.apply_credit_transfer])
async def test_credit_transfer_routes_gate_before_constructing_service(monkeypatch, endpoint):
    monkeypatch.setattr(routes, 'versioning_enabled', lambda: False)
    service = Mock(side_effect=AssertionError('Service must remain unconstructed'))
    monkeypatch.setattr(routes, 'CreditTransfer', service)
    with pytest.raises(HTTPException) as error:
        await endpoint('original', user=SimpleNamespace(user_id='learner'))
    assert error.value.status_code == 404
    service.assert_not_called()
