import { PageLayout } from '../components/layout/PageLayout'
import { OptimizerInbox } from '../components/shared/OptimizerInbox'

/**
 * Tuning suggestions — the user-facing home for automatically generated
 * optimizer candidates and failed tuning runs.
 *
 * The per-item "Validate & improve" tabs stay the place you *launch* tuning
 * from; this page answers the question those tabs can't: "did anything the
 * system tuned on its own need me?"
 *
 * Deliberately unlinked from the main nav. It used to have an always-on
 * account-menu item and an activity-rail badge, which put a power-user surface
 * in front of every research administrator — nearly all of whom own nothing
 * the optimizer tunes. The route stays live for bookmarks and notification
 * links, and Admin → Optimizer activity links here.
 */
export default function TuningSuggestions() {
  return (
    <PageLayout>
      <div style={{ maxWidth: 980, margin: '0 auto' }}>
        <header style={{ marginBottom: 20 }}>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: '#111827', margin: 0 }}>
            Tuning suggestions
          </h1>
          <p style={{ fontSize: 13, color: '#4b5563', margin: '6px 0 0', maxWidth: 640 }}>
            When quality slips on one of your workflows, extraction sets, or knowledge
            bases, the system re-tunes it in the background and proposes a better
            configuration. Nothing is changed until you apply it here.
          </p>
        </header>
        <OptimizerInbox />
      </div>
    </PageLayout>
  )
}
