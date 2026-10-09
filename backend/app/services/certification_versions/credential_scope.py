"""The same authored credential scope for course reading and future issuance."""
from pydantic import BaseModel, ConfigDict, Field

from .outcomes import package_outcomes


class CredentialScope(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    contract_id: str = Field(min_length=1)
    contract_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    promise: str = Field(min_length=1)
    agent_assistance: str = Field(min_length=1)
    exclusions: tuple[str, ...] = Field(min_length=1)


def scope_from_contract(package, contract):
    return CredentialScope(contract_id=contract.contract_id,
        contract_sha256=package.manifest.artifacts['outcomes.json'],
        promise=contract.credential_promise, agent_assistance=contract.agent_assistance,
        exclusions=contract.exclusions)


def public_credential_scope(package):
    contract = package_outcomes(package)
    if contract is None:
        return None  # Never infer newer competencies from a legacy course.
    return {**scope_from_contract(package, contract).model_dump(mode='json'), 'state': contract.state}
