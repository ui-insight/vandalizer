import type { ReactNode } from 'react'
import { Link } from '@tanstack/react-router'

export function AuthLayout({ children, title }: { children: ReactNode; title: string }) {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-gray-200 antialiased relative">
      {/* Background glow */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-yellow-600/10 rounded-full blur-[120px] animate-pulse" />
        <div
          className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-gray-800/30 rounded-full blur-[120px] animate-pulse"
          style={{ animationDelay: '2s' }}
        />
      </div>

      {/* Top nav */}
      <nav className="relative z-10 border-b border-white/10 bg-[#0a0a0a]/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <Link to="/landing">
            <img src="/images/Vandalizer_Wordmark_Color_RGB+W.png" alt="Vandalizer" className="h-10" />
          </Link>
        </div>
      </nav>

      {/* Centered content */}
      <div className="relative z-10 flex items-center justify-center" style={{ minHeight: 'calc(100vh - 64px)' }}>
        <div className="w-full max-w-sm px-4">
          <h1 className="mb-8 text-center text-2xl font-bold text-white">{title}</h1>
          {children}
          <p className="mt-6 text-center text-sm text-gray-500">
            <Link to="/landing" className="text-gray-400 hover:text-[#f1b300] transition-colors">
              &larr; Back to home
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
