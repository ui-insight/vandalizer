import { describe, it, expect } from 'vitest'
import { parseCSV } from './OrganizationsTab'

describe('parseCSV — quoting', () => {
  it('keeps a quoted field with an embedded comma intact', () => {
    const csv = 'name,parent\n"College of Engineering, Mines and Sciences",University of Idaho'
    const rows = parseCSV(csv)
    expect(rows).toHaveLength(1)
    expect(rows[0].name).toBe('College of Engineering, Mines and Sciences')
    expect(rows[0].parent_name).toBe('University of Idaho')
  })

  it('unescapes a doubled quote inside a quoted field to a single literal quote', () => {
    const csv = 'name,parent\n"Dept of ""Special"" Studies",'
    const rows = parseCSV(csv)
    expect(rows).toHaveLength(1)
    expect(rows[0].name).toBe('Dept of "Special" Studies')
  })

  it('parses an ordinary unquoted row as before', () => {
    const csv = 'name,parent\nCollege of Science,University of Idaho'
    const rows = parseCSV(csv)
    expect(rows).toHaveLength(1)
    expect(rows[0]).toEqual({ name: 'College of Science', parent_name: 'University of Idaho', org_type: 'college' })
  })
})

describe('parseCSV — order independence', () => {
  it('gives a child row the correct depth-derived org_type even when it precedes its parent (and grandparent)', () => {
    // Fully reversed order: Department appears before College, which appears before University.
    const csv = [
      'name,parent',
      'Department of Computer Science,College of Engineering',
      'College of Engineering,University of Idaho',
      'University of Idaho,',
    ].join('\n')
    const rows = parseCSV(csv)
    const byName = Object.fromEntries(rows.map(r => [r.name, r]))
    expect(byName['University of Idaho'].org_type).toBe('university')
    expect(byName['College of Engineering'].org_type).toBe('college')
    expect(byName['Department of Computer Science'].org_type).toBe('department')
  })

  it('produces the same output regardless of whether the parent comes first or last', () => {
    const parentFirst = [
      'name,parent',
      'University of Idaho,',
      'College of Engineering,University of Idaho',
    ].join('\n')
    const childFirst = [
      'name,parent',
      'College of Engineering,University of Idaho',
      'University of Idaho,',
    ].join('\n')
    const rowsParentFirst = parseCSV(parentFirst)
    const rowsChildFirst = parseCSV(childFirst)
    const collegeParentFirst = rowsParentFirst.find(r => r.name === 'College of Engineering')
    const collegeChildFirst = rowsChildFirst.find(r => r.name === 'College of Engineering')
    expect(collegeChildFirst?.org_type).toBe(collegeParentFirst?.org_type)
    expect(collegeChildFirst?.org_type).toBe('college')
  })

  it('treats a dangling parent reference as depth 0, giving the child depth 1, without crashing', () => {
    const csv = 'name,parent\nSome Unit,Nonexistent Parent'
    const rows = parseCSV(csv)
    expect(rows).toHaveLength(1)
    expect(rows[0].org_type).toBe('college')
  })

  it('terminates and returns rows for a cyclic parent reference (A -> B -> A)', () => {
    const csv = [
      'name,parent',
      'A,B',
      'B,A',
    ].join('\n')
    const rows = parseCSV(csv)
    expect(rows).toHaveLength(2)
    expect(rows.map(r => r.name).sort()).toEqual(['A', 'B'])
  })
})

describe('parseCSV — parent-before-child ordering (import compatibility)', () => {
  it('reorders an out-of-order 3-level file so every parent precedes its child', () => {
    // Fully reversed order: Department appears before College, which appears before University.
    const csv = [
      'name,parent',
      'Department of Computer Science,College of Engineering',
      'College of Engineering,University of Idaho',
      'University of Idaho,',
    ].join('\n')
    const rows = parseCSV(csv)
    const idx = (name: string) => rows.findIndex(r => r.name === name)
    expect(idx('University of Idaho')).toBeGreaterThanOrEqual(0)
    expect(idx('University of Idaho')).toBeLessThan(idx('College of Engineering'))
    expect(idx('College of Engineering')).toBeLessThan(idx('Department of Computer Science'))
  })

  it('leaves an already parent-before-child file in exactly the same order (stability)', () => {
    const csv = [
      'name,parent',
      'University of Idaho,',
      'College of Engineering,University of Idaho',
      'College of Science,University of Idaho',
      'Department of Computer Science,College of Engineering',
      'Department of Physics,College of Science',
    ].join('\n')
    const rows = parseCSV(csv)
    expect(rows.map(r => r.name)).toEqual([
      'University of Idaho',
      'College of Engineering',
      'College of Science',
      'Department of Computer Science',
      'Department of Physics',
    ])
  })

  it('terminates on a cyclic parent reference (A -> B -> A) and returns every row', () => {
    const csv = [
      'name,parent',
      'A,B',
      'B,A',
    ].join('\n')
    const rows = parseCSV(csv)
    expect(rows).toHaveLength(2)
    expect(rows.map(r => r.name).sort()).toEqual(['A', 'B'])
  })

  it('still returns a row whose parent reference is dangling (not present in the file)', () => {
    const csv = 'name,parent\nSome Unit,Nonexistent Parent'
    const rows = parseCSV(csv)
    expect(rows).toHaveLength(1)
    expect(rows[0].name).toBe('Some Unit')
  })
})

describe('parseCSV — structural cases', () => {
  it('returns [] for a header-only file', () => {
    expect(parseCSV('name,parent')).toEqual([])
  })

  it('returns [] when there is no name column', () => {
    expect(parseCSV('foo,bar\nCollege of Science,University of Idaho')).toEqual([])
  })

  it('parses CRLF line endings identically to LF', () => {
    const lf = 'name,parent\nUniversity of Idaho,\nCollege of Engineering,University of Idaho'
    const crlf = lf.replace(/\n/g, '\r\n')
    expect(parseCSV(crlf)).toEqual(parseCSV(lf))
  })

  it('skips rows with an empty name', () => {
    const csv = 'name,parent\n,University of Idaho\nCollege of Science,University of Idaho'
    const rows = parseCSV(csv)
    expect(rows).toHaveLength(1)
    expect(rows[0].name).toBe('College of Science')
  })
})
