"""Authored method/calculation/dependency case, never learner execution evidence."""
from decimal import Decimal
import hashlib
from typing import Literal

from pydantic import Field, model_validator

from .attempts import encode
from .outcomes import ContractModel
from .process_case import ProcessReviewGuidance
from .repair_case import SourceAnchor

EVIDENCE = {
    'advanced_nodes.appropriate_method': {'learner_decision', 'design_snapshot'},
    'advanced_nodes.checked_computation': {'assigned_document_snapshot', 'intermediate_snapshot', 'calculation_record', 'learner_decision'},
    'advanced_nodes.parallel_safety': {'artifact_revision', 'design_snapshot', 'execution_receipt', 'learner_decision'},
}
QUESTIONS = {
    'method_choice': ('advanced_nodes.appropriate_method', 'method_and_availability', 'before_execution'),
    'calculation_review': ('advanced_nodes.checked_computation', 'source_bound_calculation_review', 'after_execution'),
    'dependency_review': ('advanced_nodes.parallel_safety', 'dependencies_and_actual_results', 'after_execution'),
}
DIRECT_INPUTS = ('senior_personnel', 'other_personnel', 'fringe', 'equipment', 'travel', 'supplies', 'subaward')
CALCULATIONS = {
    'equipment_subtotal': ('weather_station', 'soil_system', 'drone'),
    'listed_direct_subtotal': DIRECT_INPUTS,
    'listed_summary_total': (*DIRECT_INPUTS, 'estimated_indirect'),
}
AMOUNT_PATTERN = r'^(0|[1-9][0-9]{0,8})\.[0-9]{2}$'


class BudgetAmount(ContractModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,99}$')
    label: str = Field(min_length=3, max_length=200)
    value: str = Field(pattern=AMOUNT_PATTERN)
    unit: Literal['USD']
    basis: str = Field(min_length=30, max_length=1000)
    anchor: SourceAnchor


class BudgetCalculation(ContractModel):
    id: Literal['equipment_subtotal', 'listed_direct_subtotal', 'listed_summary_total']
    operation: Literal['sum']
    inputs: tuple[str, ...] = Field(min_length=2, max_length=10)
    unit: Literal['USD']
    expected_value: str = Field(pattern=AMOUNT_PATTERN)
    interpretation_limit: str = Field(min_length=50, max_length=2000)


class BudgetSourceIssue(ContractModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,99}$')
    meaning: str = Field(min_length=50, max_length=2000)
    anchors: tuple[SourceAnchor, ...] = Field(min_length=1, max_length=5)


class AdvancedQuestion(ContractModel):
    id: Literal['method_choice', 'calculation_review', 'dependency_review']
    outcome_id: str
    response_kind: Literal['method_and_availability', 'source_bound_calculation_review', 'dependencies_and_actual_results']
    phase: Literal['before_execution', 'after_execution']
    prompt: str = Field(min_length=60, max_length=3000)


class AdvancedNodesCase(ContractModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,99}$')
    revision: int = Field(ge=1, strict=True)
    module_id: Literal['advanced_nodes']
    provenance: Literal['authored_budget_method_case_not_execution']
    source_filename: Literal['budget-justification.pdf']
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    notice: str = Field(min_length=60, max_length=1000)
    task: str = Field(min_length=100, max_length=4000)
    intended_output: str = Field(min_length=60, max_length=2000)
    instructions: tuple[str, ...] = Field(min_length=5, max_length=12)
    exclusions: tuple[str, ...] = Field(min_length=3, max_length=10)
    flawed_proposal: str = Field(min_length=100, max_length=4000)
    questions: tuple[AdvancedQuestion, ...] = Field(min_length=3, max_length=3)
    calculation_methods: tuple[Literal['recorded_deterministic_arithmetic', 'explicit_learner_arithmetic'], ...]
    execution_rule: Literal['owned_revision_assigned_source_actual_task_inputs_results_and_order_not_node_counts']
    arithmetic_rule: Literal['exact_named_source_inputs_units_formula_result_and_limits_not_model_assurance']
    availability_rule: Literal['use_available_permitted_operations_no_code_enablement_or_staff_requirement']
    parallel_rule: Literal['independent_reads_may_overlap_dependent_synthesis_waits_for_all_required_results']
    scope_policy: Literal['assigned_source_internal_draft_no_external_actions_or_staff_queue']
    assessment_policy: Literal['automatic_structured_review_with_checked_arithmetic_no_presence_credit']
    review_guidance: tuple[ProcessReviewGuidance, ...] = Field(min_length=3, max_length=3)
    amounts: tuple[BudgetAmount, ...] = Field(min_length=11, max_length=11)
    calculations: tuple[BudgetCalculation, ...] = Field(min_length=3, max_length=3)
    source_issues: tuple[BudgetSourceIssue, ...] = Field(min_length=2, max_length=6)

    @model_validator(mode='after')
    def coherent_case(self):
        if ({q.id for q in self.questions} != set(QUESTIONS)
                or {g.outcome_id for g in self.review_guidance} != set(EVIDENCE)):
            raise ValueError('Every Advanced Nodes outcome needs its own question and review guidance')
        if any((q.outcome_id, q.response_kind, q.phase) != QUESTIONS[q.id] for q in self.questions):
            raise ValueError('Method choice precedes execution; calculation and dependency reviews inspect actual results')
        if (len(self.calculation_methods) != 2
                or set(self.calculation_methods) != {'recorded_deterministic_arithmetic', 'explicit_learner_arithmetic'}):
            raise ValueError('Arithmetic must permit an explicit learner check without restricted tools or staff')
        amounts = {amount.id: amount for amount in self.amounts}
        required = {name for names in CALCULATIONS.values() for name in names}
        if set(amounts) != required or len(amounts) != len(self.amounts):
            raise ValueError('The case requires each exact named source input once')
        if {calculation.id for calculation in self.calculations} != set(CALCULATIONS):
            raise ValueError('All three distinct calculation checks are required')
        for calculation in self.calculations:
            if (calculation.inputs != CALCULATIONS[calculation.id]
                    or sum((Decimal(amounts[name].value) for name in calculation.inputs), Decimal(0))
                    != Decimal(calculation.expected_value)):
                raise ValueError('Authored calculation operands and expected arithmetic must agree exactly')
        if len({issue.id for issue in self.source_issues}) != len(self.source_issues):
            raise ValueError('Source issues require unique identities')
        return self

    @property
    def digest(self):
        return encode(self.model_dump(mode='json'))[1]

    def public_definition(self):
        return {**self.model_dump(mode='json', exclude={'review_guidance', 'amounts', 'calculations', 'source_issues'}), 'case_sha256': self.digest}

    def verify_contract(self, contract):
        module = next((m for m in contract.modules if m.module_id == self.module_id), None)
        if module is None or {o.id for o in module.outcomes} != set(EVIDENCE):
            raise ValueError('The case must bind the exact Advanced Nodes outcomes')
        guidance = {g.outcome_id: g for g in self.review_guidance}
        for outcome in module.outcomes:
            if (outcome.method != 'structured_review' or set(outcome.evidence) != EVIDENCE[outcome.id]
                    or guidance[outcome.id].passing_conditions != outcome.passing_conditions
                    or guidance[outcome.id].critical_failures != outcome.critical_failures):
                raise ValueError('Authored guidance cannot replace evidence or weaken the outcome rubric')

    def verify_source(self, source_bytes, page_texts):
        if hashlib.sha256(source_bytes).hexdigest() != self.source_sha256:
            raise ValueError('The assigned budget source changed')
        anchors = [amount.anchor for amount in self.amounts] + [a for issue in self.source_issues for a in issue.anchors]
        for anchor in anchors:
            if anchor.page > len(page_texts) or ' '.join(anchor.quote.split()) not in ' '.join(page_texts[anchor.page - 1].split()):
                raise ValueError('A private budget expectation has no matching source anchor')
        for amount in self.amounts:
            display = f'${Decimal(amount.value):,.2f}'
            if display.endswith('.00'):
                display = display[:-3]
            if display not in amount.anchor.quote:
                raise ValueError('A named arithmetic input differs from its quoted source amount')

    def verify_exercise(self, exercise):
        if (exercise.get('documents') != [self.source_filename] or exercise.get('expected_fields') != []
                or exercise.get('expected_values') != {} or exercise.get('star_criteria') != {}
                or exercise.get('assessment_case_id') != self.id or exercise.get('advanced_case_sha256') != self.digest
                or exercise.get('instructions') != list(self.instructions)
                or exercise.get('assessment_method') != 'authenticated_method_calculation_dependency_review'):
            raise ValueError('The exercise must bind the exact case without node-count or reflection-presence credit')


def load_advanced_case(package):
    from .catalog import CourseCatalogError
    from .outcomes import package_outcomes
    path = 'advanced-cases/advanced_nodes.json'
    if path not in package.manifest.artifacts:
        raise CourseCatalogError('This course has no Advanced Nodes case')
    try:
        case = AdvancedNodesCase.model_validate(package.json(path))
        case.verify_contract(package_outcomes(package))
        case.verify_exercise(package.json('exercises.json')['advanced_nodes'])
        if package.manifest.artifacts.get('documents/' + case.source_filename) != case.source_sha256:
            raise ValueError('The case must bind its exact packaged source')
        return case
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CourseCatalogError('The packaged Advanced Nodes case is invalid') from exc
