import { apiFetch } from './client'
import type { User } from '../types/user'

// ---------------------------------------------------------------------------
// Auth config (public, pre-login)
// ---------------------------------------------------------------------------

export interface OAuthProvider {
  provider: string
  display_name: string
  configured: boolean
}

export interface AuthConfig {
  auth_methods: string[]
  oauth_providers: OAuthProvider[]
  demo_login_enabled?: boolean
  trial_system_enabled?: boolean
}

export async function getAuthConfig(): Promise<AuthConfig> {
  const res = await fetch('/api/auth/config')
  if (!res.ok) {
    return { auth_methods: ['password'], oauth_providers: [] }
  }
  return res.json()
}

// ---------------------------------------------------------------------------
// Password auth
// ---------------------------------------------------------------------------

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

export function forgotPassword(email: string) {
  return apiFetch<{ ok: boolean }>('/api/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function resetPassword(token: string, password: string) {
  return apiFetch<{ ok: boolean }>('/api/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ token, password }),
  })
}

export function logout() {
  return apiFetch<{ ok: boolean }>('/api/auth/logout', { method: 'POST' })
}

export function getMe() {
  return apiFetch<User>('/api/auth/me')
}

// Profile update

export function updateProfile(data: { name?: string; email?: string }) {
  return apiFetch<User>('/api/auth/profile', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
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

// Account deletion

export interface DeleteAccountPreflight {
  can_delete: boolean
  blocking_reason: string | null
  has_password: boolean
  data_summary: {
    documents: number
    folders: number
    chat_conversations: number
    workflows: number
    search_sets: number
    knowledge_bases: number
    teams_owned: number
    teams_member: number
  }
  owned_teams_with_members: Array<{ uuid: string; name: string; member_count: number }>
}

export function deleteAccountPreflight() {
  return apiFetch<DeleteAccountPreflight>('/api/auth/account/delete/preflight', { method: 'POST' })
}

export function deleteAccount(data: { password?: string; confirmation: string }) {
  return apiFetch<{ ok: boolean }>('/api/auth/account/delete', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
