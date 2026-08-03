import { describe, it, expect } from 'vitest'

import { getModelIdentityError } from './modelIdentity'

const models = (...pairs: [string, string][]) => pairs.map(([name, tag]) => ({ name, tag }))

describe('getModelIdentityError', () => {
  it('allows a name and tag that collide with nothing', () => {
    expect(getModelIdentityError('gpt-oss', 'fast', models(['qwen-large', 'local']))).toBeNull()
  })

  it('rejects a duplicate name and says which model holds it', () => {
    const error = getModelIdentityError('qwen-large', 'fast', models(['qwen-large', 'local']))
    expect(error).toContain('qwen-large')
  })

  it('rejects a duplicate tag and says which model holds it', () => {
    const error = getModelIdentityError('gpt-oss', 'local', models(['qwen-large', 'local']))
    expect(error).toContain('local')
    expect(error).toContain('qwen-large')
  })

  it('treats case-only differences as collisions', () => {
    expect(getModelIdentityError('QWEN-Large', 'fast', models(['qwen-large', 'local']))).not.toBeNull()
    expect(getModelIdentityError('gpt-oss', 'LOCAL', models(['qwen-large', 'local']))).not.toBeNull()
  })

  it('rejects a name that matches another model tag', () => {
    // Resolution tries names before tags, so this would hijack the other
    // model's tag.
    expect(getModelIdentityError('local', 'reasoning', models(['qwen-large', 'local']))).not.toBeNull()
  })

  it('rejects a tag that matches another model name', () => {
    expect(getModelIdentityError('gpt-oss', 'qwen-large', models(['qwen-large', 'local']))).not.toBeNull()
  })

  it('ignores whitespace around the submitted value', () => {
    expect(getModelIdentityError('  qwen-large  ', 'fast', models(['qwen-large', 'local']))).not.toBeNull()
  })

  it('ignores whitespace around an already stored value', () => {
    expect(getModelIdentityError('gpt-oss', 'local', models(['qwen-large', '  local  ']))).not.toBeNull()
  })

  it('lets a model use the same string for its own name and tag', () => {
    expect(getModelIdentityError('local', 'local', models(['qwen-large', 'fast']))).toBeNull()
  })

  it('excludes the model being edited', () => {
    const existing = models(['qwen-large', 'local'], ['gpt-oss', 'fast'])
    expect(getModelIdentityError('qwen-large', 'local', existing, 0)).toBeNull()
  })

  it('still reports a collision with a different model while editing', () => {
    const existing = models(['qwen-large', 'local'], ['gpt-oss', 'fast'])
    expect(getModelIdentityError('gpt-oss', 'local', existing, 0)).toContain('gpt-oss')
  })

  it('ignores empty values rather than matching them against each other', () => {
    expect(getModelIdentityError('gpt-oss', '', models(['qwen-large', '']))).toBeNull()
  })
})
