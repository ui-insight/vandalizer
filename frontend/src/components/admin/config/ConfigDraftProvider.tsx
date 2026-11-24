import { useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useBlocker, useRouter } from '@tanstack/react-router'
import { useConfirm } from '../../shared/useConfirm'
import { ConfigDraftContext } from './configDrafts'

function NavigationGuard({ names }: { names: string[] }) {
  const confirm = useConfirm()
  useBlocker({
    disabled: names.length === 0,
    enableBeforeUnload: false,
    shouldBlockFn: async ({ current, next }) => {
      if (current.pathname === next.pathname && JSON.stringify(current.search) === JSON.stringify(next.search)) return false
      return !await confirm({
        title: 'Discard unsaved configuration?',
        message: `Unsaved changes in ${names.join(', ')} will be lost. Keep editing to save each section before leaving.`,
        confirmLabel: 'Discard and leave',
        cancelLabel: 'Keep editing',
        destructive: true,
      })
    },
  })
  return null
}

export function ConfigDraftProvider({ children }: { children: ReactNode }) {
  const [names, setNames] = useState<string[]>([])
  const router = useRouter({ warn: false })
  const report = useCallback((name: string, dirty: boolean) => {
    setNames(previous => {
      if (previous.includes(name) === dirty) return previous
      return dirty ? [...previous, name] : previous.filter(item => item !== name)
    })
  }, [])
  useEffect(() => {
    if (!names.length) return
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [names.length])
  const value = useMemo(() => ({ names, report }), [names, report])
  return <ConfigDraftContext.Provider value={value}>
    {router && <NavigationGuard names={names} />}
    {children}
  </ConfigDraftContext.Provider>
}

export function ConfigDraftStatus() {
  const names = useContext(ConfigDraftContext)?.names ?? []
  return names.length > 0
    ? <p role="status" style={{ flexBasis: '100%', margin: 0, fontSize: 13, color: '#92400e' }}>Unsaved changes: {names.join(', ')}. Save each section separately.</p>
    : null
}
