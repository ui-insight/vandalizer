import type { SurveyField } from '../../types/demo'

// Short, low-friction notes collected from engaged trial users in exchange for
// another two weeks. Kept deliberately brief — the goal is a quick signal on
// what to build next, not a full post-experience survey.
export const RENEWAL_NOTES_FIELDS: SurveyField[] = [
  {
    key: 'using_for',
    label: 'What are you using Vandalizer for?',
    type: 'textarea',
    required: true,
    section: 'Quick notes',
    placeholder: 'e.g. extracting deadlines and budgets from NIH grant announcements',
  },
  {
    key: 'would_make_useful',
    label: 'What would make Vandalizer more useful for your office?',
    type: 'textarea',
    required: true,
    section: 'Quick notes',
    placeholder: 'The one thing that would make this a no-brainer to keep using',
  },
  {
    key: 'anything_blocking',
    label: 'Anything getting in your way? (optional)',
    type: 'textarea',
    required: false,
    section: 'Quick notes',
    placeholder: 'Bugs, confusing bits, missing features…',
  },
]
