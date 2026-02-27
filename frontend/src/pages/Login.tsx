import { useState, useEffect } from 'react'
import { Navigate, Link } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { AuthLayout } from '../components/layout/AuthLayout'
import { LoginForm } from '../components/auth/LoginForm'
import { getAuthConfig } from '../api/auth'

export function Login() {
  const { user, loading } = useAuth()
  const [recaptchaSiteKey, setRecaptchaSiteKey] = useState<string | null>(null)

  useEffect(() => {
    getAuthConfig().then((c) => setRecaptchaSiteKey(c.recaptcha_site_key))
  }, [])

  if (loading) return null
  if (user) return <Navigate to="/" />

  return (
    <AuthLayout title="Sign in to Vandalizer">
      <LoginForm recaptchaSiteKey={recaptchaSiteKey} />
      <p className="mt-4 text-center text-sm text-gray-600">
        Don't have an account?{' '}
        <Link to="/register" className="font-medium text-highlight hover:brightness-75">
          Register
        </Link>
      </p>
    </AuthLayout>
  )
}
