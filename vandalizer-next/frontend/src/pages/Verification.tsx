import { useState } from 'react'
import { ShieldCheck, BookOpen, FolderOpen, Users, Tag } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { VerificationQueue } from '../components/library/VerificationQueue'
import { VerifiedCatalog } from '../components/library/VerifiedCatalog'
import { CollectionsManager } from '../components/library/CollectionsManager'
import { ExaminerManager } from '../components/library/ExaminerManager'
import { GroupManager } from '../components/library/GroupManager'
import { useAuth } from '../hooks/useAuth'

type Tab = 'queue' | 'catalog' | 'collections' | 'groups' | 'examiners'

const TABS: { key: Tab; label: string; icon: typeof ShieldCheck; adminOnly?: boolean }[] = [
  { key: 'queue', label: 'Queue', icon: ShieldCheck },
  { key: 'catalog', label: 'Catalog', icon: BookOpen },
  { key: 'collections', label: 'Collections', icon: FolderOpen },
  { key: 'groups', label: 'Groups', icon: Tag },
  { key: 'examiners', label: 'Examiners', icon: Users, adminOnly: true },
]

export default function Verification() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<Tab>('queue')

  if (!user?.is_examiner) {
    return (
      <PageLayout>
        <div className="text-center py-12 text-gray-500">
          You do not have examiner access.
        </div>
      </PageLayout>
    )
  }

  const isAdmin = !!user.is_admin
  const visibleTabs = isAdmin ? TABS : TABS.filter(t => !t.adminOnly)

  return (
    <PageLayout>
      <div style={{ display: 'flex', gap: 0, minHeight: 'calc(100vh - 130px)' }}>
        {/* Sidebar */}
        <nav style={{
          width: 220, flexShrink: 0,
          borderRight: '1px solid #e5e7eb',
          backgroundColor: '#fff',
          padding: '20px 0',
          borderRadius: 'var(--ui-radius, 12px) 0 0 var(--ui-radius, 12px)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 20px', marginBottom: 20 }}>
            <ShieldCheck size={20} color="#6b7280" />
            <h1 style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>Verification</h1>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '0 8px' }}>
            {visibleTabs.map(tab => {
              const Icon = tab.icon
              const isActive = activeTab === tab.key
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 14px', border: 'none', cursor: 'pointer',
                    fontSize: 14, fontWeight: isActive ? 600 : 400,
                    color: isActive ? '#111827' : '#6b7280',
                    backgroundColor: isActive ? '#f3f4f6' : 'transparent',
                    borderRadius: 8, fontFamily: 'inherit',
                    transition: 'background-color 0.15s, color 0.15s',
                    width: '100%', textAlign: 'left',
                    borderLeft: isActive ? '3px solid var(--highlight-color, #eab308)' : '3px solid transparent',
                  }}
                >
                  <Icon size={18} style={{ flexShrink: 0 }} />
                  {tab.label}
                </button>
              )
            })}
          </div>
        </nav>

        {/* Content */}
        <div style={{ flex: 1, padding: '20px 32px', minWidth: 0 }}>
          {activeTab === 'queue' && <VerificationQueue />}
          {activeTab === 'catalog' && <VerifiedCatalog />}
          {activeTab === 'collections' && <CollectionsManager />}
          {activeTab === 'groups' && <GroupManager />}
          {activeTab === 'examiners' && isAdmin && <ExaminerManager />}
        </div>
      </div>
    </PageLayout>
  )
}
