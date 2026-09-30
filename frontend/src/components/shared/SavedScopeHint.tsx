export function SavedScopeHint({ scope, kind, dark = false }: { scope: string; kind: 'tools' | 'knowledge bases'; dark?: boolean }) {
  const text = scope === 'mine'
    ? `Mine contains ${kind} you own or have saved.`
    : scope === 'team'
      ? `Team contains ${kind} owned by or shared with your current team.`
      : `Explore contains ${kind} shared with everyone here. Add an item to keep it in Mine.`
  return <p className="saved-scope-hint" data-dark={dark}>{text}</p>
}
