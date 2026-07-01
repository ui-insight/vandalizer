import { useState, type FormEvent } from 'react'
import { Link, useSearch } from '@tanstack/react-router'
import { AuthLayout } from '../components/layout/AuthLayout'
import { forgotPassword, resetPassword } from '../api/auth'

function ForgotPasswordForm() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await forgotPassword(email)
      setSubmitted(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  if (submitted) {
    return (
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[#f1b300]/20">
          <svg className="h-6 w-6 text-[#f1b300]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-white">Check your email</h2>
        <p className="mt-2 text-sm text-gray-400">
          If an account exists for <strong className="text-white">{email}</strong>, we've sent a password reset link.
        </p>
        <Link to="/login" className="mt-6 inline-block text-sm font-bold text-[#f1b300] hover:text-[#d49e00]">
          Back to sign in
        </Link>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <p className="text-sm text-gray-400 mb-4">
        Enter your email address and we'll send you a link to reset your password.
      </p>
      {error && (
        <div className="rounded-md bg-red-500/20 border border-red-500/30 p-3 text-sm text-red-300">
          {error}
        </div>
      )}
      <input
        type="email"
        aria-label="Email address"
        autoComplete="email"
        placeholder="Email address"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
      />
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-lg bg-[#f1b300] px-4 py-3 font-bold text-black transition-all hover:bg-[#d49e00] disabled:opacity-50"
      >
        {loading ? 'Sending...' : 'Send Reset Link'}
      </button>
      <p className="text-center text-sm text-gray-500">
        <Link to="/login" className="text-gray-400 hover:text-[#f1b300]">
          Back to sign in
        </Link>
      </p>
    </form>
  )
}

function ResetPasswordForm({ token }: { token: string }) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')

    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      await resetPassword(token, password)
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed')
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-500/20">
          <svg className="h-6 w-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-white">Password reset!</h2>
        <p className="mt-2 text-sm text-gray-400">Your password has been updated. You can now sign in.</p>
        <Link
          to="/login"
          className="mt-6 inline-block rounded-lg bg-[#f1b300] px-6 py-3 font-bold text-black transition-all hover:bg-[#d49e00]"
        >
          Sign In
        </Link>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && (
        <div className="rounded-md bg-red-500/20 border border-red-500/30 p-3 text-sm text-red-300">
          {error}
        </div>
      )}
      <input
        type="password"
        aria-label="New password"
        autoComplete="new-password"
        placeholder="New password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
      />
      <input
        type="password"
        aria-label="Confirm new password"
        autoComplete="new-password"
        placeholder="Confirm new password"
        required
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
      />
      <p className="text-xs text-gray-500">
        Must be at least 8 characters with uppercase, lowercase, and a digit.
      </p>
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-lg bg-[#f1b300] px-4 py-3 font-bold text-black transition-all hover:bg-[#d49e00] disabled:opacity-50"
      >
        {loading ? 'Resetting...' : 'Reset Password'}
      </button>
    </form>
  )
}

export default function ResetPassword() {
  const search = useSearch({ strict: false }) as Record<string, string | undefined>
  const token = search?.token

  return (
    <AuthLayout title={token ? 'Set new password' : 'Forgot password?'}>
      {token ? <ResetPasswordForm token={token} /> : <ForgotPasswordForm />}
    </AuthLayout>
  )
}
