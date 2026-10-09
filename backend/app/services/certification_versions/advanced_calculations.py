"""Check explicit learner arithmetic against the exact authored PDF.

This pure checker does not authenticate, save a receipt, run a workflow, call a
model or award credit. A trusted collector must bind its result to owned work.
"""
from decimal import Decimal
import hashlib
from typing import Literal

from pydantic import Field, model_validator

from .advanced_case import AMOUNT_PATTERN, AdvancedNodesCase, CALCULATIONS
from .outcomes import ContractModel


class CalculationOperand(ContractModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,99}$')
    value: str | None = Field(pattern=AMOUNT_PATTERN)
    unit: Literal['USD']
    source_page: int = Field(ge=1, strict=True)
    source_quote: str = Field(max_length=2000)
    status: Literal['supported', 'unresolved']
    explanation: str = Field(min_length=10, max_length=2000)

    @model_validator(mode='after')
    def explicit_source_check(self):
        if len(self.explanation.strip()) < 10:
            raise ValueError('Explain the source check or unresolved input')
        if self.status == 'supported' and (self.value is None or not self.source_quote.strip()):
            raise ValueError('A supported input requires its amount and source quote')
        return self


class CalculationRecord(ContractModel):
    id: Literal['equipment_subtotal', 'listed_direct_subtotal', 'listed_summary_total']
    operation: Literal['sum']
    method: Literal['recorded_deterministic_arithmetic', 'explicit_learner_arithmetic']
    inputs: tuple[CalculationOperand, ...] = Field(min_length=2, max_length=10)
    result: str | None = Field(pattern=AMOUNT_PATTERN)
    unit: Literal['USD']
    interpretation: str = Field(min_length=20, max_length=4000)

    @model_validator(mode='after')
    def exact_named_inputs(self):
        if tuple(item.id for item in self.inputs) != CALCULATIONS[self.id]:
            raise ValueError('Preserve every named calculation input once in its source order')
        if len(self.interpretation.strip()) < 20:
            raise ValueError('Explain the calculation meaning and limits')
        return self


def check_budget_calculations(case: AdvancedNodesCase, records, *, source_bytes: bytes):
    import fitz
    records = tuple(CalculationRecord.model_validate(record) for record in records)
    if len(records) != 3 or {record.id for record in records} != set(CALCULATIONS):
        raise ValueError('Preserve all three distinct checks, including unresolved inputs')
    if hashlib.sha256(source_bytes).hexdigest() != case.source_sha256:
        raise ValueError('Calculations must use the exact assigned budget PDF')
    with fitz.open(stream=source_bytes, filetype='pdf') as pdf:
        pages = [page.get_text() for page in pdf]
    case.verify_source(source_bytes, pages)
    def normalize(text):
        return ' '.join(text.split())
    expected = {amount.id: amount for amount in case.amounts}
    checks = []
    for record in records:
        input_checks = []
        for operand in record.inputs:
            source = expected[operand.id]
            quote = normalize(operand.source_quote)
            page = pages[operand.source_page - 1] if operand.source_page <= len(pages) else ''
            quoted_row = bool(quote) and normalize(source.anchor.quote) in quote and quote in normalize(page)
            input_checks.append({'id': operand.id, 'resolved': operand.status == 'supported',
                                 'source_matches': operand.value == source.value
                                     and operand.source_page == source.anchor.page and quoted_row})
        resolved = all(item['resolved'] for item in input_checks)
        computed = format(sum((Decimal(item.value) for item in record.inputs), Decimal(0)), '.2f') if resolved else None
        arithmetic_matches = record.result == computed if computed is not None and record.result is not None else None
        source_matches = all(item['source_matches'] for item in input_checks)
        state = ('unresolved' if not resolved or record.result is None else
                 'supported' if arithmetic_matches and source_matches else 'revision_required')
        checks.append({'id': record.id, 'state': state, 'input_checks': input_checks,
                       'source_matches': source_matches, 'arithmetic_matches': arithmetic_matches,
                       'computed_value': computed, 'recorded_value': record.result, 'unit': record.unit,
                       'expression': ' + '.join(item.value if item.value is not None else '[unresolved]' for item in record.inputs),
                       'method': record.method, 'method_provenance': 'learner_reported',
                       'check_provenance': 'server_recomputed_decimal_sum',
                       'interpretation': record.interpretation})
    return {'checker_id': 'budget-source-addition.1', 'case_sha256': case.digest, 'source_sha256': case.source_sha256,
            'checks': checks, 'all_arithmetic_supported': all(check['state'] == 'supported' for check in checks),
            'interpretation_review_required': True, 'credit_awarded': False, 'module_completion_eligible': False,
            'notice': 'These checks establish source-row addition only. They do not verify period compatibility, policy, workflow execution or the learner interpretation.'}
