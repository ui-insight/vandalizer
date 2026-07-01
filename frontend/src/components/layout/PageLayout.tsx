import type { ReactNode } from 'react'
import { ArrowLeft } from 'lucide-react'
import { Header } from './Header'

interface PageLayoutProps {
  children: ReactNode
}

export function PageLayout({ children }: PageLayoutProps) {
  return (
    <div className="flex h-screen flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[1000] focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:shadow-lg focus:ring-2 focus:ring-highlight"
      >
        Skip to main content
      </a>
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
        <main id="main-content" className="px-6 pb-6">{children}</main>
      </div>
    </div>
  )
}
