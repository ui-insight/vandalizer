#!/usr/bin/env python3
"""Check the unpublished 5.0 competency design without modifying any course."""
import json
import hashlib
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.services.certification_versions.outcomes import OutcomeContract  # noqa: E402
from app.services.certification_versions.scenario_assessment import ScenarioBank  # noqa: E402
from app.services.certification_versions.learner_decisions import DecisionPrompt  # noqa: E402
from app.services.certification_versions.scope_proposal import ScopeProposalCase  # noqa: E402
from app.services.certification_versions.repair_case import ExtractionRepairCase  # noqa: E402
from app.services.certification_versions.process_case import ProcessMappingCase  # noqa: E402
from app.services.certification_versions.workflow_design_case import WorkflowDesignCase  # noqa: E402
from app.services.certification_versions.multi_step_case import MultiStepCase  # noqa: E402
from app.services.certification_versions.advanced_case import AdvancedNodesCase  # noqa: E402
from app.services.certification_versions.output_case import OutputDeliveryCase  # noqa: E402
from app.services.certification_versions.validation_case import ValidationCase  # noqa: E402
from app.services.certification_versions.batch_case import BatchCase  # noqa: E402
from app.services.certification_versions.governance_case import GovernanceCase  # noqa: E402


def main():
    path = ROOT / 'backend/certification-data/drafts/v5.0/outcomes.json'
    contract = OutcomeContract.model_validate_json(path.read_bytes())
    lessons = json.loads((ROOT / 'backend/certification-data/lessons.json').read_text())
    contract.verify_teaching_references(lessons)
    teaching = [json.loads(asset.read_text()) for asset in sorted(path.parent.glob('*-teaching.json'))]
    by_module = {draft['module_id']: draft for draft in teaching}
    if len(by_module) != len(teaching):
        raise ValueError('Teaching drafts must have unique module identities')
    for module in contract.modules:
        replacements = {lesson['id'] for lesson in by_module.get(module.module_id, {}).get('replacements', [])}
        for outcome in module.outcomes:
            if outcome.teaching_status == 'authored' and not set(outcome.lesson_ids) <= replacements:
                raise ValueError(f'Authored teaching is missing a referenced replacement for {outcome.id}')
    scenarios = [ScenarioBank.model_validate_json(asset.read_bytes())
                 for asset in sorted(path.parent.glob('*-scenarios.json'))]
    expected_modules = {module.module_id for module in contract.modules
                        if any(outcome.method == 'scenario_choice' for outcome in module.outcomes)}
    if len(scenarios) != len(expected_modules) or {bank.module_id for bank in scenarios} != expected_modules:
        raise ValueError('Each module with recognition outcomes requires exactly one scenario bank')
    for bank in scenarios:
        bank.verify_contract(contract)
    decision_prompts = [DecisionPrompt.model_validate(item) for item in json.loads((path.parent / 'foundations-decisions.json').read_text())]
    proposal = ScopeProposalCase.model_validate_json((path.parent / 'foundations-proposal.json').read_bytes())
    proposal.verify_exercise(json.loads((path.parent / 'foundations-exercise.json').read_text()))
    if proposal.prompt_id not in {item.id for item in decision_prompts if item.execution_choice is not None}:
        raise ValueError('The Foundations proposal must bind an explicit scope approval prompt')
    foundations = next(module for module in contract.modules if module.module_id == 'foundations')
    if {item.outcome_id for item in decision_prompts} != {item.id for item in foundations.outcomes if item.method == 'structured_review'}:
        raise ValueError('Foundations decision prompts must cover its structured review outcomes')
    repair = ExtractionRepairCase.model_validate_json((path.parent / 'extraction-engine-repair.json').read_bytes())
    repair_prompts = [DecisionPrompt.model_validate(item) for item in json.loads((path.parent / 'extraction-engine-decisions.json').read_text())]
    repair.verify_contract(contract, repair_prompts)
    repair.verify_exercise(json.loads((path.parent / 'extraction-engine-exercise.json').read_text()))
    process = ProcessMappingCase.model_validate_json((path.parent / 'process-mapping-case.json').read_bytes())
    process.verify_contract(contract)
    process.verify_exercise(json.loads((path.parent / 'process-mapping-exercise.json').read_text()))
    workflow = WorkflowDesignCase.model_validate_json((path.parent / 'workflow-design-case.json').read_bytes())
    workflow.verify_contract(contract)
    workflow.verify_process_case(process)
    workflow.verify_exercise(json.loads((path.parent / 'workflow-design-exercise.json').read_text()))
    connected = MultiStepCase.model_validate_json((path.parent / 'multi-step-case.json').read_bytes())
    connected.verify_contract(contract)
    connected.verify_exercise(json.loads((path.parent / 'multi-step-exercise.json').read_text()))
    output = OutputDeliveryCase.model_validate_json((path.parent / 'output-delivery-case.json').read_bytes())
    output.verify_contract(contract)
    output.verify_exercise(json.loads((path.parent / 'output-delivery-exercise.json').read_text()))
    validation = ValidationCase.model_validate_json((path.parent / 'validation-qa-case.json').read_bytes())
    validation.verify_contract(contract)
    validation.verify_exercise(json.loads((path.parent / 'validation-qa-exercise.json').read_text()))
    governance = GovernanceCase.model_validate_json((path.parent / 'governance-capstone-case.json').read_bytes())
    governance.verify_contract(contract)
    governance.verify_exercise(json.loads((path.parent / 'governance-exercise.json').read_text()))
    batch = BatchCase.model_validate_json((path.parent / 'batch-processing-case.json').read_bytes())
    batch.verify_contract(contract)
    batch.verify_exercise(json.loads((path.parent / 'batch-processing-exercise.json').read_text()))
    advanced = AdvancedNodesCase.model_validate_json((path.parent / 'advanced-nodes-case.json').read_bytes())
    advanced.verify_contract(contract)
    advanced.verify_exercise(json.loads((path.parent / 'advanced-nodes-exercise.json').read_text()))
    import fitz
    for assigned in governance.sources:
        source = (path.parent / 'documents' / assigned.filename).read_bytes()
        with fitz.open(stream=source, filetype='pdf') as pdf:
            governance.verify_source(assigned.id, source, [page.get_text() for page in pdf])
    for assigned in batch.sources:
        source = (path.parent / 'documents' / assigned.filename).read_bytes()
        with fitz.open(stream=source, filetype='pdf') as pdf:
            batch.verify_source(assigned.id, source, [page.get_text() for page in pdf])
    for assigned in validation.sources:
        source = (path.parent / 'documents' / assigned.filename).read_bytes()
        with fitz.open(stream=source, filetype='pdf') as pdf:
            validation.verify_source(assigned.id, source, [page.get_text() for page in pdf])
    source = (path.parent / 'documents' / repair.source_filename).read_bytes()
    with fitz.open(stream=source, filetype='pdf') as pdf:
        repair.verify_source(source, [page.get_text() for page in pdf])
    connected_source = (path.parent / 'documents' / connected.source_filename).read_bytes()
    with fitz.open(stream=connected_source, filetype='pdf') as pdf:
        connected.verify_source(connected_source, [page.get_text() for page in pdf])
    output_source = (path.parent / 'documents' / output.source_filename).read_bytes()
    with fitz.open(stream=output_source, filetype='pdf') as pdf:
        output.verify_source(output_source, [page.get_text() for page in pdf])
    advanced_source = (path.parent / 'documents' / advanced.source_filename).read_bytes()
    with fitz.open(stream=advanced_source, filetype='pdf') as pdf:
        advanced.verify_source(advanced_source, [page.get_text() for page in pdf])
    print(json.dumps({
        'contract_id': contract.contract_id,
        'contract_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'rubric_id': contract.rubric_id,
        'state': contract.state,
        'modules': len(contract.modules),
        'required_outcomes': len(contract.required_outcomes()),
        'calibration_examples': sum(len(outcome.calibration) for module in contract.modules for outcome in module.outcomes),
        'assessment_status': sorted({outcome.assessment_status for module in contract.modules for outcome in module.outcomes}),
        'teaching_status_counts': dict(Counter(outcome.teaching_status for module in contract.modules for outcome in module.outcomes)),
        'assessment_status_counts': dict(Counter(outcome.assessment_status for module in contract.modules for outcome in module.outcomes)),
        'implemented_is_release_verified': False,
        'coverage_rule': 'Every outcome has its own passing conditions. Shared lessons or evidence packets support distinct criteria; no practice answer, other passed outcome or extra XP compensates for a required failure.',
        'outcome_matrix': [
            {'module_id': module.module_id, 'outcome_id': outcome.id, 'statement': outcome.statement,
             'lessons': [{'id': lesson['id'], 'title': lesson['title'], 'revision': lesson['revision'],
                          'source': f'backend/certification-data/drafts/v5.0/{module.module_id.replace("_", "-")}-teaching.json'}
                         for lesson in by_module[module.module_id]['replacements'] if lesson['id'] in outcome.lesson_ids],
             'practice': outcome.practice, 'assessment': outcome.assessment, 'method': outcome.method,
             'assessed_home': 'selected_saved_scenario' if outcome.method == 'scenario_choice' else 'selected_saved_automatic_review',
             'evidence_types': list(outcome.evidence), 'passing_conditions': list(outcome.passing_conditions),
             'critical_failures': list(outcome.critical_failures), 'rubric_id': contract.rubric_id,
             'teaching_status': outcome.teaching_status, 'assessment_status': outcome.assessment_status,
             'scenario_ids': [question.id for bank in scenarios if bank.module_id == module.module_id
                              for question in bank.questions if question.outcome_id == outcome.id]}
            for module in contract.modules for outcome in module.outcomes
        ],
        'outcomes_needing_assessment_implementation': [outcome.id for module in contract.modules for outcome in module.outcomes if outcome.assessment_status == 'not_implemented'],
        'outcomes_needing_release_verification': [outcome.id for module in contract.modules for outcome in module.outcomes if outcome.assessment_status != 'verified'],
        'enrollable': False,
        'scenario_questions': sum(len(bank.questions) for bank in scenarios),
        'scenario_banks': [{'module_id': bank.module_id, 'questions': len(bank.questions),
                            'assessed_outcome_ids': bank.outcome_ids} for bank in scenarios],
        'scenario_delivery_and_credit_enabled': False,
        'practical_decision_prompts': len(decision_prompts) + len(repair_prompts),
        'scope_proposal_cases': 1,
        'authored_repair_cases': 1,
        'repair_case_delivery_enabled': False,
        'repair_case_sha256': repair.digest,
        'authored_process_cases': 1,
        'process_case_sha256': process.digest,
        'process_case_delivery_implemented': True,
        'process_case_delivery_enabled': False,
        'authored_workflow_design_cases': 1,
        'workflow_design_case_sha256': workflow.digest,
        'workflow_design_delivery_implemented': True,
        'authored_connected_workflow_cases': 1,
        'connected_workflow_case_sha256': connected.digest,
        'connected_workflow_delivery_implemented': True,
        'authored_output_delivery_cases': 1,
        'output_delivery_case_sha256': output.digest,
        'output_delivery_implemented': True,
        'authored_validation_cases': 1,
        'validation_case_sha256': validation.digest,
        'validation_practical_implemented': True,
        'authored_batch_cases': 1,
        'batch_case_sha256': batch.digest,
        'batch_practical_implemented': True,
        'authored_governance_cases': 1,
        'governance_case_sha256': governance.digest,
        'governance_practical_implemented': True,
        'authored_advanced_nodes_cases': 1,
        'advanced_nodes_case_sha256': advanced.digest,
        'advanced_nodes_delivery_implemented': True,
        'practical_decision_ui_enabled': False,
        'teaching_drafts': [
            {'module_id': draft['module_id'], 'lesson_replacements': len(draft['replacements'])}
            for draft in teaching
        ],
    }, indent=2))


if __name__ == '__main__':
    main()
