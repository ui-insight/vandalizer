import { PageLayout } from '../components/layout/PageLayout'
import { VerificationQueue } from '../components/library/VerificationQueue'
import { useAuth } from '../hooks/useAuth'

export default function Verification() {
  const { user } = useAuth()

  if (!user?.is_examiner) {
    return (
      <PageLayout>
        <div className="text-center py-12 text-gray-500">
          You do not have examiner access.
        </div>
      </PageLayout>
    )
  }

  return (
    <PageLayout>
      <div className="mx-auto max-w-5xl">
        <h2 className="text-xl font-semibold text-gray-900 mb-6">Verification Management</h2>
        <VerificationQueue />
      </div>
    </PageLayout>
  )
}
