import type { SurveyField } from '../../types/demo'

export const PRE_SURVEY_FIELDS: SurveyField[] = [
  // --- Demographics ---
  {
    key: 'ra_department',
    label: 'Department you work in (select all that apply)',
    type: 'multiselect',
    required: true,
    section: 'Demographics',
    options: [
      'Pre-Award',
      'Post-Award',
      'Contracts',
      'Cost Accounting/Cost Compliance',
      'Financial/Invoicing',
      'Departmental Support',
      'Compliance (IACUC, IRB, etc.)',
      'IT Support',
      'Other',
      "I'm not in research administration",
    ],
  },
  {
    key: 'carnegie_classification',
    label: 'Institution Carnegie Classification (select all that apply)',
    type: 'multiselect',
    required: true,
    section: 'Demographics',
    options: [
      'Carnegie R1',
      'Carnegie R2',
      'Primarily Undergraduate Institution',
      'Community College',
      'Minority Serving Institution',
      'Academic Medical Center',
      'Independent Research Institute',
      'Emerging Research Institution',
      'Historically Black College / University',
      'Other',
    ],
  },

  // --- Where did you come from? ---
  {
    key: 'process_obstacles',
    label:
      'Please describe some of the process-based, technological obstacles or bottlenecks which you feel could be reduced or automated using AI.',
    type: 'textarea',
    required: true,
    section: 'Where did you come from?',
    placeholder: 'Describe current pain points in your workflow...',
  },
  {
    key: 'intended_use',
    label: 'How do you intend on using Vandalizer in your daily tasks?',
    type: 'textarea',
    required: true,
    section: 'Where did you come from?',
    placeholder: 'e.g., Grant proposal review, compliance checking, document extraction...',
  },

  // --- Task Time Estimates ---
  // We collect baseline time estimates so we can measure how much time
  // Vandalizer saves you. After the pilot we'll compare your "before"
  // estimates here with your actual experience in the post-survey.
  {
    key: 'task_time_intro',
    label: 'For each task below, estimate how long it takes you today without AI assistance. This helps us measure time savings during the pilot so we can demonstrate the value of AI-assisted workflows to your institution.\n\nIf you do not know how long this takes, leave it blank.',
    type: 'info',
    required: false,
    section: 'Task Time Estimates',
  },
  {
    key: 'time_foa_checklist',
    label: 'Review a funding opportunity (RFA/FOA/NOFO) and build a checklist of requirements for PIs',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },
  {
    key: 'time_compliance_framework',
    label: 'Read an award notice and compile the compliance obligations and reporting requirements',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },
  {
    key: 'time_effort_compliance',
    label: 'Prepare effort certification or time-and-effort compliance documentation for a project',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },
  {
    key: 'time_management_plan',
    label: 'Review an SF-425 (Federal Financial Report) and build a financial management summary',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },
  {
    key: 'time_prior_approval',
    label: 'Read through award terms and extract the list of actions requiring prior sponsor approval',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },
  {
    key: 'time_subaward_extraction',
    label: 'Extract key data (parties, amounts, period of performance, terms) from a subaward agreement',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },

  // --- AI Experience ---
  {
    key: 'ai_experience_level',
    label: 'What is your experience level with AI tools?',
    type: 'select',
    required: true,
    section: 'AI Experience',
    options: [
      'I have no experience with AI',
      'Less than a year',
      '1 - 2 years',
      '3 - 4 years',
      '5+ years',
    ],
  },
  {
    key: 'ai_tools_used',
    label: 'Which AI tools have you used? (select all that apply)',
    type: 'multiselect',
    required: false,
    section: 'AI Experience',
    options: [
      'ChatGPT',
      'Claude',
      'Microsoft Co-Pilot',
      'Google Gemini',
      'Perplexity',
      'Institution Specific Internal Tools',
      'Other',
    ],
  },
  {
    key: 'ai_work_frequency',
    label: 'How often do you use AI tools in your work?',
    type: 'select',
    required: true,
    section: 'AI Experience',
    options: [
      'Never',
      'Rarely (less than once weekly)',
      'Occasionally (a few times weekly)',
      'Moderately (once daily)',
      'Often (multiple times daily)',
    ],
  },

  // --- Pre-Experience Assessment ---
  {
    key: 'pre_assessment',
    label: 'Please rate your agreement with the following statements:',
    type: 'likert_group',
    required: false,
    section: 'Pre-Experience Assessment',
    statements: [
      { key: 'trust_ai', label: 'I trust AI outputs' },
      { key: 'want_ai', label: 'I want to use AI in my work life' },
      { key: 'not_worried_job', label: "I'm not worried AI will take my job" },
      { key: 'easy_to_use', label: 'I find AI easy to use' },
      { key: 'safe_use', label: 'I can use AI safely in my work' },
      { key: 'understand_models', label: 'I understand how AI models work' },
      {
        key: 'ethics_transparency',
        label:
          'It is unethical to utilize AI without being transparent about its use and explicitly disclosing it to the recipients',
      },
      {
        key: 'environmental_ethics',
        label:
          'I am worried that I am ethically complicit in environmental harms when using energy-intensive AI systems',
      },
      {
        key: 'comfortable_learning',
        label:
          'I am comfortable learning technical skills, even when there is a learning curve',
      },
    ],
  },

  // --- Excitement & Discovery ---
  {
    key: 'excitement_level',
    label: 'How excited are you to try Vandalizer?',
    type: 'select',
    required: true,
    section: 'Pre-Experience Assessment',
    options: ['1', '2', '3', '4', '5'],
  },
  {
    key: 'how_heard',
    label: 'How did you hear about Vandalizer?',
    type: 'textarea',
    required: false,
    section: 'Pre-Experience Assessment',
    placeholder: 'e.g., Conference, colleague, social media...',
  },
]
