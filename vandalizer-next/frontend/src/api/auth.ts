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

// API Token management

export function generateApiToken() {
  return apiFetch<{ api_token: string; created_at: string }>('/api/auth/api-token/generate', { method: 'POST' })
}

export function revokeApiToken() {
  return apiFetch<{ ok: boolean }>('/api/auth/api-token/revoke', { method: 'POST' })
}

export function getApiTokenStatus() {
  return apiFetch<{ has_token: boolean; created_at: string | null }>('/api/auth/api-token/status')
}
