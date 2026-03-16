import { useEffect, useState } from 'react'
import { Building2, ChevronRight, Plus, Trash2, Edit2, Users, FolderTree } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useAuth } from '../hooks/useAuth'
import * as api from '../api/organizations'
import type { Organization } from '../api/organizations'

const ORG_TYPE_LABELS: Record<string, string> = {
  university: 'University',
  college: 'College',
  central_office: 'Central Office',
  department: 'Department',
  unit: 'Unit',
}

const ORG_TYPE_COLORS: Record<string, string> = {
  university: 'bg-purple-100 text-purple-800',
  college: 'bg-blue-100 text-blue-800',
  central_office: 'bg-amber-100 text-amber-800',
  department: 'bg-green-100 text-green-800',
  unit: 'bg-gray-100 text-gray-800',
}

function OrgNode({
  org,
  depth = 0,
  onEdit,
  onDelete,
  onAddChild,
}: {
  org: Organization
  depth?: number
  onEdit: (org: Organization) => void
  onDelete: (org: Organization) => void
  onAddChild: (parentId: string) => void
}) {
  const [expanded, setExpanded] = useState(depth < 2)
  const hasChildren = org.children && org.children.length > 0

  return (
    <div>
      <div
        className="flex items-center gap-2 rounded-lg px-3 py-2 hover:bg-gray-50"
        style={{ paddingLeft: `${depth * 24 + 12}px` }}
      >
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex h-5 w-5 items-center justify-center"
        >
          {hasChildren && (
            <ChevronRight
              className={`h-4 w-4 text-gray-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
            />
          )}
        </button>

        <Building2 className="h-4 w-4 text-gray-500" />
        <span className="font-medium text-gray-900">{org.name}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${ORG_TYPE_COLORS[org.org_type] || 'bg-gray-100 text-gray-600'}`}
        >
          {ORG_TYPE_LABELS[org.org_type] || org.org_type}
        </span>

        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={() => onAddChild(org.uuid)}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            title="Add child"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => onEdit(org)}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            title="Edit"
          >
            <Edit2 className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => onDelete(org)}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-red-600"
            title="Delete"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {expanded && hasChildren && (
        <div>
          {org.children!.map((child) => (
            <OrgNode
              key={child.uuid}
              org={child}
              depth={depth + 1}
              onEdit={onEdit}
              onDelete={onDelete}
              onAddChild={onAddChild}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default function Organizations() {
  const { user } = useAuth()
  const [tree, setTree] = useState<Organization[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [createParentId, setCreateParentId] = useState<string | undefined>()
  const [editOrg, setEditOrg] = useState<Organization | null>(null)
  const [formName, setFormName] = useState('')
  const [formType, setFormType] = useState('department')

  const loadTree = async () => {
    try {
      const data = await api.getOrgTree()
      setTree(data.tree)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTree()
  }, [])

  const handleCreate = async () => {
    if (!formName.trim()) return
    try {
      await api.createOrganization({
        name: formName.trim(),
        org_type: formType,
        parent_id: createParentId,
      })
      setShowCreate(false)
      setFormName('')
      setCreateParentId(undefined)
      loadTree()
    } catch {
      // ignore
    }
  }

  const handleUpdate = async () => {
    if (!editOrg || !formName.trim()) return
    try {
      await api.updateOrganization(editOrg.uuid, { name: formName.trim() })
      setEditOrg(null)
      setFormName('')
      loadTree()
    } catch {
      // ignore
    }
  }

  const handleDelete = async (org: Organization) => {
    if (!confirm(`Delete "${org.name}"? Children will be re-parented.`)) return
    try {
      await api.deleteOrganization(org.uuid)
      loadTree()
    } catch {
      // ignore
    }
  }

  if (!user?.is_admin) {
    return (
      <PageLayout>
        <div className="text-center text-gray-500">Admin access required</div>
      </PageLayout>
    )
  }

  return (
    <PageLayout>
      <div className="mx-auto max-w-4xl">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <FolderTree className="h-6 w-6 text-gray-700" />
            <h1 className="text-2xl font-bold text-gray-900">Organization Hierarchy</h1>
          </div>
          <button
            onClick={() => {
              setShowCreate(true)
              setCreateParentId(undefined)
              setFormName('')
              setFormType('university')
            }}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Add Organization
          </button>
        </div>

        {/* Create/Edit Modal */}
        {(showCreate || editOrg) && (
          <div className="mb-4 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <h3 className="mb-3 font-medium">
              {editOrg ? `Edit: ${editOrg.name}` : 'Create Organization'}
            </h3>
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="mb-1 block text-sm text-gray-600">Name</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  placeholder="e.g., College of Science"
                />
              </div>
              {!editOrg && (
                <div>
                  <label className="mb-1 block text-sm text-gray-600">Type</label>
                  <select
                    value={formType}
                    onChange={(e) => setFormType(e.target.value)}
                    className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  >
                    {Object.entries(ORG_TYPE_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <button
                onClick={editOrg ? handleUpdate : handleCreate}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                {editOrg ? 'Update' : 'Create'}
              </button>
              <button
                onClick={() => {
                  setShowCreate(false)
                  setEditOrg(null)
                  setFormName('')
                }}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Tree */}
        <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
          {loading ? (
            <div className="p-8 text-center text-gray-500">Loading...</div>
          ) : tree.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <Users className="mx-auto mb-2 h-8 w-8 text-gray-300" />
              <p>No organizations yet. Create a root organization to get started.</p>
            </div>
          ) : (
            <div className="py-2">
              {tree.map((org) => (
                <OrgNode
                  key={org.uuid}
                  org={org}
                  onEdit={(o) => {
                    setEditOrg(o)
                    setFormName(o.name)
                  }}
                  onDelete={handleDelete}
                  onAddChild={(parentId) => {
                    setShowCreate(true)
                    setCreateParentId(parentId)
                    setFormName('')
                    setFormType('department')
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </PageLayout>
  )
}
