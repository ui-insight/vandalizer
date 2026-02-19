import { apiFetch } from './client'
import type { User } from '../types/user'

export function login(user_id: string, password: string) {
  return apiFetch<User>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ user_id, password }),
  })
}

export function register(user_id: string, email: string, password: string, name?: string) {
  return apiFetch<User>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ user_id, email, password, name }),
  })
}

export function logout() {
  return apiFetch<{ ok: boolean }>('/api/auth/logout', { method: 'POST' })
}

export function getMe() {
  return apiFetch<User>('/api/auth/me')
}
