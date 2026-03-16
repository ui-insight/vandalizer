import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function jsonResponse(data: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

beforeEach(() => {
  mockFetch.mockReset()
  document.cookie = 'csrf_token=; max-age=0'
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('organizations API', () => {
  it('getOrgTree calls /api/organizations/tree', async () => {
    const tree = [{ uuid: 'org1', name: 'College of Engineering', org_type: 'college', parent_id: null }]
    mockFetch.mockResolvedValueOnce(jsonResponse({ tree }))

    const { getOrgTree } = await import('./organizations')
    const result = await getOrgTree()

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/organizations/tree',
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(result.tree).toEqual(tree)
  })

  it('listOrganizations sends query params', async () => {
    const orgs = [{ uuid: 'org1', name: 'Dept CS', org_type: 'department', parent_id: 'org0' }]
    mockFetch.mockResolvedValueOnce(jsonResponse({ organizations: orgs }))

    const { listOrganizations } = await import('./organizations')
    const result = await listOrganizations({ org_type: 'department', parent_id: 'org0' })

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/organizations/')
    expect(calledUrl).toContain('org_type=department')
    expect(calledUrl).toContain('parent_id=org0')
    expect(result.organizations).toEqual(orgs)
  })

  it('createOrganization sends POST with body', async () => {
    const newOrg = { uuid: 'org-new', name: 'New Dept', org_type: 'department', parent_id: 'org0' }
    mockFetch.mockResolvedValueOnce(jsonResponse(newOrg))

    const { createOrganization } = await import('./organizations')
    const result = await createOrganization({
      name: 'New Dept',
      org_type: 'department',
      parent_id: 'org0',
    })

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/organizations/')
    expect(call[1].method).toBe('POST')
    const body = JSON.parse(call[1].body as string)
    expect(body.name).toBe('New Dept')
    expect(body.org_type).toBe('department')
    expect(body.parent_id).toBe('org0')
    expect(result.uuid).toBe('org-new')
  })

  it('deleteOrganization sends DELETE', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'Deleted' }))

    const { deleteOrganization } = await import('./organizations')
    const result = await deleteOrganization('org-to-delete')

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/organizations/org-to-delete')
    expect(call[1].method).toBe('DELETE')
    expect(result.detail).toBe('Deleted')
  })

  it('assignUserToOrg sends POST to correct URL', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'Assigned' }))

    const { assignUserToOrg } = await import('./organizations')
    const result = await assignUserToOrg('org-uuid-1', 'user-id-1')

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/organizations/org-uuid-1/assign-user/user-id-1')
    expect(call[1].method).toBe('POST')
    expect(result.detail).toBe('Assigned')
  })
})
