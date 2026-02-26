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
      'Dissatisfied',
      'Neutral',
      'Satisfied',
      'Extremely Satisfied',
    ],
  },
  {
    key: 'ease_of_use',
    label: 'How easy was Vandalizer to use?',
    type: 'select',
    required: true,
    section: 'Overall Experience',
    options: [
      'Very Difficult',
      'Difficult',
      'Neutral',
      'Easy',
      'Very Easy',
    ],
  },
  {
    key: 'saved_time',
    label: 'Did Vandalizer save you time?',
    type: 'select',
    required: true,
    section: 'Overall Experience',
    options: ['Yes', 'No'],
  },
  {
    key: 'time_saved_description',
    label: 'If yes, please describe how it saved you time',
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
      'I did not use pre-vetted tasks',
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
    label: 'What constructive criticism do you have for us?',
    type: 'textarea',
    required: false,
    section: 'Feedback',
    placeholder: 'We welcome all feedback — what could we improve?',
  },
  {
    key: 'estimated_usage_frequency',
    label: 'How often do you estimate you would use Vandalizer in the future?',
    type: 'select',
    required: true,
    section: 'Feedback',
    options: ['Never', 'Rarely', 'Sometimes', 'Often'],
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
          'I believe AI tools should be transparent about their limitations and potential biases',
      },
      {
        key: 'environmental_ethics',
        label:
          'I believe the environmental impact of AI (energy use, carbon footprint) should be considered when adopting AI tools',
      },
    ],
  },

  // --- Looking Forward ---
  {
    key: 'new_features_desired',
    label: 'What new features would you like to see in Vandalizer?',
    type: 'textarea',
    required: false,
    section: 'Looking Forward',
    placeholder: 'Describe features or capabilities you wish existed...',
  },
  {
    key: 'training_types_desired',
    label: 'What types of training would be helpful for using Vandalizer?',
    type: 'textarea',
    required: false,
    section: 'Looking Forward',
    placeholder: 'e.g., Video tutorials, live webinars, written guides...',
  },
]
