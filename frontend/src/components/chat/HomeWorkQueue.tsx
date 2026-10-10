import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { listMyReviews } from '../../api/reviews'
import { RAInbox } from './RAInbox'
import { useAuth } from '../../hooks/useAuth'

/** Real obligations and assigned approval work; never inferred from tool scores. */
export function HomeWorkQueue() {
  const { user } = useAuth()
  const reviews = useQuery({ queryKey: ['home-pending-reviews', user?.id, user?.current_team], enabled: !!user, queryFn: () => listMyReviews('pending'), staleTime: 30_000, refetchInterval: 60_000, retry: false })
  return <div className="home-work-queue">
    <RAInbox />
    {reviews.isError && <p role="status" className="home-meta">Pending approvals could not be loaded. <button type="button" className="home-text-action" onClick={() => void reviews.refetch()}>Retry approvals</button></p>}
    {!!reviews.data?.reviews.length && <section className="home-approvals" aria-label="Pending approvals">
      <h3>Awaiting your review</h3>
      <ul>{reviews.data.reviews.slice(0, 3).map(review => <li key={review.uuid}>
        <div><strong>{review.workflow_name || 'Workflow review'}</strong><p>{review.step_name} · Pending approval</p></div>
        <Link to="/reviews/$uuid" params={{ uuid: review.uuid }}>Review submission</Link>
      </li>)}</ul>
      {reviews.data.reviews.length > 3 && <Link to="/reviews">View all {reviews.data.reviews.length} approvals</Link>}
    </section>}
  </div>
}
