import type { ModuleDefinition } from '../types/certification'

export function hasOutcomeAssessment(module: ModuleDefinition | undefined): boolean {
  return !!module && !!(module.scenarioAssessment || module.processAssessment || module.workflowDesignAssessment
    || module.connectedWorkflowAssessment || module.budgetWorkflowAssessment || module.outputWorkflowAssessment
    || module.validationAssessment || module.batchAssessment || module.governanceAssessment || module.decisionPrompts?.length)
}
