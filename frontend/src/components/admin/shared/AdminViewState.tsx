import { createContext, useContext, useEffect, useCallback, useRef, useMemo, useState, type Dispatch, type SetStateAction, type ReactNode } from 'react'

// Only explicitly opted-in filters, positions, and accepted job references live
// here. Never retain form values, credentials, records, or consent decisions.
const scopes = new Map<string, Map<string, unknown>>()
const Context = createContext<Map<string, unknown> | null>(null)
export function AdminViewState({ scope, children }: { scope: string; children: ReactNode }) {
  const values = useMemo(() => {
    if (!scopes.has(scope)) scopes.set(scope, new Map())
    if (scopes.size > 20) scopes.delete(scopes.keys().next().value!)
    return scopes.get(scope)!
  }, [scope])
  return <Context.Provider value={values}>{children}</Context.Provider>
}
export function useAdminViewState<T>(key: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const values = useContext(Context)
  const [value, setValue] = useState<T>(() => values?.has(key) ? values.get(key) as T : initial)
  useEffect(() => { values?.set(key, value) }, [values, key, value])
  const current = useRef(value)
  const update: Dispatch<SetStateAction<T>> = useCallback(next => {
    const resolved = typeof next === 'function' ? (next as (value: T) => T)(current.current) : next
    current.current = resolved
    values?.set(key, resolved)
    setValue(resolved)
  }, [values, key])
  return [value, update]
}
