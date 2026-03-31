import { Navigate, Link } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { AuthLayout } from '../components/layout/AuthLayout'
import { RegisterForm } from '../components/auth/RegisterForm'

export function Register() {
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
    <AuthLayout title="Create your account">
      <RegisterForm />
      <p className="mt-4 text-center text-sm text-gray-400">
        Already have an account?{' '}
        <Link to="/login" className="font-bold text-white hover:text-[#f1b300]">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  )
}
