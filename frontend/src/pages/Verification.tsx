import { SectionPage } from '../components/layout/SectionPage'
import { useState } from 'react'
import { useSearch } from '@tanstack/react-router'
import { ShieldCheck, BookOpen, FolderOpen, Users, Pin } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { VerificationQueue } from '../components/library/VerificationQueue'
import { VerifiedCatalog } from '../components/library/VerifiedCatalog'
import { CollectionsManager } from '../components/library/CollectionsManager'
import { ExaminerManager } from '../components/library/ExaminerManager'
import { CatalogCoverageTab } from '../components/library/CatalogCoverageTab'
import { useAuth } from '../hooks/useAuth'

type Tab = 'queue' | 'catalog' | 'coverage' | 'collections' | 'examiners'

const TABS: { key: Tab; label: string; icon: typeof ShieldCheck; adminOnly?: boolean }[] = [
  { key: 'queue', label: 'Requests', icon: ShieldCheck },
  { key: 'catalog', label: 'Catalog', icon: BookOpen },
  { key: 'coverage', label: 'Coverage', icon: Pin },
  { key: 'collections', label: 'Collections', icon: FolderOpen },
  { key: 'examiners', label: 'Examiners', icon: Users, adminOnly: true },
]

export default function Verification() {
  const { user } = useAuth()
  const search = useSearch({ strict: false }) as { request?: string }
  // A notification links to the submission it is about, so open on the queue
  // with that row in view rather than making the reviewer find it.
  const [activeTab, setActiveTab] = useState<Tab>('queue')

  if (!user?.is_examiner) {
    return (
      <PageLayout>
        <div className="mx-auto max-w-5xl">
          <h1 className="mb-2 text-xl font-semibold text-gray-900">My sharing requests</h1>
          <p className="mb-5 text-sm text-gray-600">See the examiner’s feedback on your submissions. Open the item to make changes and submit it again from its sharing menu.</p>
          <VerificationQueue focusRequestUuid={search.request} />
        </div>
      </PageLayout>
    )
  }

  const isAdmin = !!user.is_admin
  const visibleTabs = isAdmin ? TABS : TABS.filter(t => !t.adminOnly)

  return (
    <PageLayout>
      <SectionPage title="Shared items" icon={ShieldCheck} label="Shared item sections" sections={visibleTabs} active={activeTab} onSelect={setActiveTab}>
          {activeTab === 'queue' && <VerificationQueue focusRequestUuid={search.request} />}
          {activeTab === 'catalog' && <VerifiedCatalog />}
          {activeTab === 'coverage' && <CatalogCoverageTab />}
          {activeTab === 'collections' && <CollectionsManager />}
          {activeTab === 'examiners' && isAdmin && <ExaminerManager />}
      </SectionPage>
    </PageLayout>
  )
}
