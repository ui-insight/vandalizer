import type { ReactNode } from 'react'
import { ArrowLeft } from 'lucide-react'
import { Header } from './Header'

interface PageLayoutProps {
  children: ReactNode
}

export function PageLayout({ children }: PageLayoutProps) {
  return (
    <div className="flex h-screen flex-col">
      <Header />
      <div className="flex-1 overflow-auto bg-gray-50">
        <div className="px-6 pt-4 pb-2">
          <a
            href="/"
            className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to workspace
          </a>
        </div>
        <main className="px-6 pb-6">{children}</main>
      </div>
    </div>
  )
}
