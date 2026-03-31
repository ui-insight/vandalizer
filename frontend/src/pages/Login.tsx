import { Navigate } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { AuthLayout } from '../components/layout/AuthLayout'
import { LoginForm } from '../components/auth/LoginForm'

export default function Login() {
  const { user, loading } = useAuth()

  if (loading) return null
  if (user) {
    return (
      <Navigate
        to="/"
        search={{
          mode: undefined,
          tab: undefined,
          workflow: undefined,
          extraction: undefined,
          automation: undefined,
          kb: undefined,
        }}
      />
    )
  }

  return (
    <AuthLayout title="Sign in">
      <LoginForm />
    </AuthLayout>
  )
}
