import { useState, type FormEvent } from 'react'
import { Link } from '@tanstack/react-router'
import { useAuth } from '../../hooks/useAuth'

export function LoginForm() {
  const { login } = useAuth()
  const [userId, setUserId] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(userId, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && (
        <div
          role="alert"
          id="login-error"
          className="rounded-md bg-red-500/20 border border-red-500/30 p-3 text-sm text-red-300"
        >
          {error}
        </div>
      )}
      <label htmlFor="login-email" className="sr-only">Email</label>
      <input
        id="login-email"
        type="email"
        autoComplete="username"
        placeholder="Email"
        required
        aria-invalid={!!error}
        aria-describedby={error ? 'login-error' : undefined}
        value={userId}
        onChange={(e) => setUserId(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50"
      />
      <label htmlFor="login-password" className="sr-only">Password</label>
      <input
        id="login-password"
        type="password"
        autoComplete="current-password"
        placeholder="Password"
        required
        aria-invalid={!!error}
        aria-describedby={error ? 'login-error' : undefined}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50"
      />
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-lg bg-highlight px-4 py-3 font-bold text-highlight-text transition-all hover:bg-highlight-hover disabled:opacity-50"
      >
        {loading ? 'Signing in...' : 'SIGN IN'}
      </button>
      <p className="text-center text-sm">
        <Link to="/reset-password" search={{ token: undefined }} className="text-gray-400 hover:text-highlight-on-dark transition-colors">
          Forgot password?
        </Link>
      </p>
      <p className="text-center text-sm text-gray-400">
        Don&apos;t have an account?{' '}
        <Link to="/register" className="font-bold text-white hover:text-highlight-on-dark">
          Create one
        </Link>
      </p>
    </form>
  )
}
