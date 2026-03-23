import type { SurveyField } from '../../types/demo'

export const POST_SURVEY_FIELDS: SurveyField[] = [
  // --- Overall Experience ---
  {
    key: 'satisfaction',
    label: 'How satisfied were you with your overall experience?',
    type: 'select',
    required: true,
    section: 'Overall Experience',
    options: [
      'Extremely Dissatisfied',
      'Somewhat Dissatisfied',
      'Neither Satisfied nor Dissatisfied',
      'Somewhat Satisfied',
      'Extremely Satisfied',
    ],
  },
  {
    key: 'ease_of_use',
    label: 'How would you rate Vandalizer\'s ease of use?',
    type: 'select',
    required: true,
    section: 'Overall Experience',
    options: [
      'Very easy to use',
      'Somewhat easy to use',
      'Neither easy nor difficult to use',
      'Somewhat difficult to use',
      'Very difficult to use',
    ],
  },
  {
    key: 'saved_time',
    label:
      'If given enough time to learn this tool, would Vandalizer workflows or tasks save you time?',
    type: 'select',
    required: true,
    section: 'Overall Experience',
    options: ['Yes', 'No'],
  },
  {
    key: 'time_saved_description',
    label: 'How much time did using Vandalizer save you? Describe task and time savings.',
    type: 'textarea',
    required: false,
    section: 'Overall Experience',
    placeholder: 'Describe how Vandalizer saved you time...',
  },

  // --- Feature Usage ---
  {
    key: 'built_own_workflows',
    label: 'Did you build your own workflows? If so, what did you create?',
    type: 'textarea',
    required: false,
    section: 'Feature Usage',
    placeholder: 'Describe any custom workflows you built...',
  },
  {
    key: 'pre_vetted_tasks_used',
    label: 'Which pre-vetted tasks did you use? (select all that apply)',
    type: 'multiselect',
    required: false,
    section: 'Feature Usage',
    options: [
      'RFA Checklist Builder',
      'FOA Checklist Maker',
      'Award Compliance Analysis',
      'Effort and Reporting Compliance',
      'FFR Management Analysis',
      'Prior Approval Requirements',
      'Subaward Extraction',
      'Other',
      'I did not use pre-vetted tasks or workflows',
    ],
  },
  {
    key: 'other_features_used',
    label: 'Which other features did you use? (select all that apply)',
    type: 'multiselect',
    required: false,
    section: 'Feature Usage',
    options: [
      'Chat assistant',
      'Teams',
      'Submit workflow for verification',
      'Support button',
    ],
  },

  // --- Feedback ---
  {
    key: 'constructive_criticism',
    label:
      'Please provide any constructive criticism you have for the Vandalizer workflows or features you used.',
    type: 'textarea',
    required: false,
    section: 'Feedback',
    placeholder: 'We welcome all feedback — what could we improve?',
  },
  {
    key: 'what_worked_well',
    label: 'What worked well and what can be improved?',
    type: 'textarea',
    required: false,
    section: 'Feedback',
  },
  {
    key: 'additional_capabilities',
    label: 'Which additional capabilities would you like to see incorporated?',
    type: 'textarea',
    required: false,
    section: 'Feedback',
  },
  {
    key: 'estimated_usage_frequency',
    label: 'How often do you estimate you would use Vandalizer in the future?',
    type: 'select',
    required: true,
    section: 'Feedback',
    options: [
      'Never',
      'Rarely (less than once weekly)',
      'Occasionally (a few times weekly)',
      'Moderately (once daily)',
      'Often (multiple times daily)',
    ],
  },

  // --- Post-Experience Assessment ---
  {
    key: 'post_assessment',
    label: 'Please rate your agreement with the following statements:',
    type: 'likert_group',
    required: false,
    section: 'Post-Experience Assessment',
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
]
