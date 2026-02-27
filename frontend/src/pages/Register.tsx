import { useState, useEffect } from 'react'
import { Navigate, Link } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { AuthLayout } from '../components/layout/AuthLayout'
import { RegisterForm } from '../components/auth/RegisterForm'
import { getAuthConfig } from '../api/auth'

export function Register() {
  const { user, loading } = useAuth()
  const [recaptchaSiteKey, setRecaptchaSiteKey] = useState<string | null>(null)

  useEffect(() => {
    getAuthConfig().then((c) => setRecaptchaSiteKey(c.recaptcha_site_key))
  }, [])

  if (loading) return null
  if (user) return <Navigate to="/" />

  return (
    <AuthLayout title="Create your account">
      <RegisterForm recaptchaSiteKey={recaptchaSiteKey} />
      <p className="mt-4 text-center text-sm text-gray-600">
        Already have an account?{' '}
        <Link to="/login" className="font-medium text-highlight hover:brightness-75">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  )
}
