import { Link } from '@tanstack/react-router'
import { ExternalLink } from 'lucide-react'

export function Footer() {
  return (
    <footer className="bg-[#0a0a0a] border-t border-white/10 text-gray-400">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
          {/* Col 1: Brand */}
          <div>
            <h3 className="text-xl font-bold text-white mb-3">Vandalizer</h3>
            <p className="text-sm leading-relaxed mb-4">
              AI-powered document intelligence for research administration. Built at the University
              of Idaho.
            </p>
            <p className="text-sm text-gray-500">&copy; 2024&ndash;2026 University of Idaho</p>
          </div>

          {/* Col 2: Links */}
          <div>
            <h4 className="text-sm font-bold text-white uppercase tracking-wider mb-4">Links</h4>
            <ul className="space-y-3 text-sm">
              <li>
                <Link to="/docs" className="hover:text-[#f1b300] transition-colors">
                  Documentation
                </Link>
              </li>
              <li>
                <a
                  href="https://github.com/ui-insight/vandalizer"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 hover:text-[#f1b300] transition-colors"
                >
                  GitHub <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li>
                <a
                  href="https://ai4ra.uidaho.edu"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 hover:text-[#f1b300] transition-colors"
                >
                  AI4RA <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li>
                <a
                  href="https://ai4ra.uidaho.edu/contact/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 hover:text-[#f1b300] transition-colors"
                >
                  Contact <ExternalLink className="w-3 h-3" />
                </a>
              </li>
            </ul>
          </div>

          {/* Col 3: License & Funding */}
          <div>
            <h4 className="text-sm font-bold text-white uppercase tracking-wider mb-4">
              Open Source
            </h4>
            <p className="text-sm leading-relaxed mb-3">
              Licensed under the{' '}
              <a
                href="https://www.gnu.org/licenses/gpl-3.0.html"
                target="_blank"
                rel="noopener noreferrer"
                className="text-white hover:text-[#f1b300] transition-colors underline"
              >
                GNU General Public License v3.0
              </a>
            </p>
            <p className="text-sm leading-relaxed">
              Supported by the NSF GRANTED program (Award #2427549).
            </p>
          </div>
        </div>
      </div>

      {/* NSF Disclaimer */}
      <div className="border-t border-white/5 py-6">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-xs text-gray-500 leading-relaxed">
            This material is based upon work supported by the National Science Foundation under
            Award No. 2427549. Any opinions, findings, and conclusions or recommendations expressed
            in this material are those of the author(s) and do not necessarily reflect the views of
            the National Science Foundation.
          </p>
        </div>
      </div>
    </footer>
  )
}
