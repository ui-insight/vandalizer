import { describe, expect, it } from 'vitest'
import { prettyJson, readGroundingDraft, readKbQueryDraft, splitLines, taskKnowledgeBaseCount } from './WorkflowEditorPanel'

describe('readGroundingDraft', () => {
  it('reads per-base entries, each with its own queries', () => {
    const draft = readGroundingDraft({
      knowledge_bases: [
        { kb_uuid: 'ug', queries: ['cost sharing 200.306', 'indirect costs 200.414'] },
        { kb_uuid: 'osp', queries: ['approval routing'] },
      ],
      k: 3, max_passages: 6, min_similarity: 0.2,
    })
    expect(draft.targets).toEqual([
      { kb_uuid: 'ug', queries: 'cost sharing 200.306\nindirect costs 200.414' },
      { kb_uuid: 'osp', queries: 'approval routing' },
    ])
    expect(draft.k).toBe('3')
    expect(draft.max_passages).toBe('6')
    expect(draft.min_similarity).toBe('0.2')
  })

  it('gives every base the shared queries of the older flat form', () => {
    const draft = readGroundingDraft({ knowledge_bases: ['ug', 'osp'], queries: ['cost sharing'] })
    expect(draft.targets).toEqual([
      { kb_uuid: 'ug', queries: 'cost sharing' },
      { kb_uuid: 'osp', queries: 'cost sharing' },
    ])
    expect(draft.k).toBe('4')
  })

  it('reads the legacy single kb_uuid / query and drops blanks and duplicates', () => {
    expect(readGroundingDraft({ kb_uuid: 'ug', query: 'one' }).targets).toEqual([{ kb_uuid: 'ug', queries: 'one' }])
    const draft = readGroundingDraft({ knowledge_bases: [{ kb_uuid: 'ug', queries: ['a'] }, { kb_uuid: 'ug' }, '', 3, null] })
    expect(draft.targets).toEqual([{ kb_uuid: 'ug', queries: 'a' }])
  })

  it('is empty for anything that is not a grounding block', () => {
    expect(readGroundingDraft(undefined).targets).toEqual([])
    expect(readGroundingDraft('ug').targets).toEqual([])
    expect(readGroundingDraft({ queries: ['q'] }).targets).toEqual([])
  })
})

describe('splitLines', () => {
  it('keeps non-empty trimmed lines', () => {
    expect(splitLines(' a \n\n b\n')).toEqual(['a', 'b'])
    expect(splitLines('')).toEqual([])
  })
})

describe('taskKnowledgeBaseCount', () => {
  it('counts a grounded task from its own config, whatever the step input is', () => {
    const data = {
      input_sources: ['workflow_documents'],
      kb_grounding: { knowledge_bases: [{ kb_uuid: 'ug', queries: ['q'] }, { kb_uuid: 'osp', queries: ['q'] }] },
    }
    expect(taskKnowledgeBaseCount('Prompt', data)).toBe(2)
    expect(taskKnowledgeBaseCount('Extraction', { kb_grounding: { knowledge_bases: ['ug'], queries: ['q'] } })).toBe(1)
  })

  it('reads a Knowledge Base Query step from its list, then the legacy single field', () => {
    expect(taskKnowledgeBaseCount('KnowledgeBaseQuery', { knowledge_bases: ['a', 'b', 'c'] })).toBe(3)
    expect(taskKnowledgeBaseCount('KnowledgeBaseQuery', { kb_uuid: 'a' })).toBe(1)
    expect(taskKnowledgeBaseCount('KnowledgeBaseQuery', { kb_uuid: '' })).toBe(0)
    expect(taskKnowledgeBaseCount('KnowledgeBaseQuery', {})).toBe(0)
  })

  it('is zero for tasks that cannot be grounded or have no config', () => {
    expect(taskKnowledgeBaseCount('APINode', { kb_grounding: { knowledge_bases: [{ kb_uuid: 'ug', queries: ['q'] }] } })).toBe(0)
    expect(taskKnowledgeBaseCount('Prompt', {})).toBe(0)
    expect(taskKnowledgeBaseCount('Prompt', { kb_grounding: { knowledge_bases: [] } })).toBe(0)
  })
})

describe('readKbQueryDraft', () => {
  it('reads the lists, else the legacy single base and query', () => {
    expect(readKbQueryDraft({ knowledge_bases: ['a', '', 'b'], queries: ['q1', 'q2'] })).toEqual({ kbs: ['a', 'b'], queries: 'q1\nq2' })
    expect(readKbQueryDraft({ kb_uuid: 'a', query: 'q' })).toEqual({ kbs: ['a'], queries: 'q' })
    expect(readKbQueryDraft({ knowledge_bases: [], kb_uuid: 'a', queries: [], query: 'q' })).toEqual({ kbs: ['a'], queries: 'q' })
    expect(readKbQueryDraft({})).toEqual({ kbs: [], queries: '' })
  })
})

describe('prettyJson', () => {
  it('re-indents a JSON object or array and ignores anything else', () => {
    expect(prettyJson('{"a":1}')).toBe('{\n  "a": 1\n}')
    expect(prettyJson(' [1] ')).toBe('[\n  1\n]')
    expect(prettyJson('"text"')).toBeNull()
    expect(prettyJson('{ not json')).toBeNull()
    expect(prettyJson('Allowable [UG · p. 4]')).toBeNull()
  })
})
