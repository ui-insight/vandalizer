import type { ReactNode } from 'react'

export function AuthLayout({ children, title }: { children: ReactNode; title: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md">
        <h1 className="mb-6 text-center text-2xl font-bold text-gray-900">{title}</h1>
        <div className="rounded-lg bg-white p-6 shadow-md">{children}</div>
      </div>
    </div>
  )
}
