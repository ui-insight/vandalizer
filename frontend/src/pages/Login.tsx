import { Navigate, Link } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { AuthLayout } from '../components/layout/AuthLayout'
import { LoginForm } from '../components/auth/LoginForm'

export function Login() {
  const { user, loading } = useAuth()

  if (loading) return null
  if (user) return <Navigate to="/" />

  return (
    <AuthLayout title="Sign in to Vandalizer">
      <LoginForm />
      <p className="mt-4 text-center text-sm text-gray-600">
        Don't have an account?{' '}
        <Link to="/register" className="font-medium text-highlight hover:brightness-75">
          Register
        </Link>
      </p>
    </AuthLayout>
  )
}
