export function SavedScopeHint({ scope, kind, dark = false }: { scope: string; kind: 'tools' | 'knowledge bases'; dark?: boolean }) {
  const label = kind === 'tools' ? 'Tools' : 'Knowledge bases'
  const text = scope === 'mine'
    ? `${label} you own or have saved.`
    : scope === 'team'
      ? `${label} owned by or shared with your team.`
      : 'Shared with everyone. Save an item to Mine.'
  return <p className="saved-scope-hint" data-dark={dark}>{text}</p>
}
