// Model names and tags form a single identifier namespace. The backend resolver
// (get_llm_model_by_name) scans names first and tags second, returning the first
// match either way, so two models sharing a tag - or one model whose name is
// another's tag - make a selector ambiguous and let list order decide the
// winner. User model preferences are stored as that selector.
//
// Mirrors backend/app/services/name_conflicts.py:ensure_model_identity_available
// - keep the two in sync. The backend rejects collisions with an HTTP 409; this
// lets the admin form warn before submitting.

type ModelIdentity = { name?: string; tag?: string }

/** Normalize a model name or tag for comparison. Mirrors _model_identifier. */
function identifier(value: string | undefined): string {
  return (value ?? '').trim().toLowerCase()
}

/**
 * Check a proposed model name and tag against the models already configured.
 * Returns a human-readable error message if either collides, or null if the
 * identity is free. Pass `excludeIndex` when editing so a model does not
 * collide with itself.
 */
export function getModelIdentityError(
  name: string,
  tag: string,
  models: readonly ModelIdentity[],
  excludeIndex: number | null = null,
): string | null {
  const candidates: [string, string][] = [
    ['name', (name ?? '').trim()],
    ['tag', (tag ?? '').trim()],
  ]

  for (let index = 0; index < models.length; index++) {
    if (index === excludeIndex) continue
    const existing = models[index]
    if (!existing) continue

    const owner = (existing.name ?? '').trim() || `at index ${index}`
    const taken: [string, string][] = [
      ['name', identifier(existing.name)],
      ['tag', identifier(existing.tag)],
    ]

    for (const [field, value] of candidates) {
      if (!value) continue
      for (const [takenField, takenValue] of taken) {
        if (takenValue && identifier(value) === takenValue) {
          return `Model ${field} "${value}" is already used as the ${takenField} of model "${owner}". Model names and tags must be unique.`
        }
      }
    }
  }

  return null
}
