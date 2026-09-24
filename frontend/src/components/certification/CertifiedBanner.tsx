import { useState } from 'react'
import { Award, Download, Loader2 } from 'lucide-react'
import { downloadCertificate } from '../../api/certification'

export function CertifiedBanner() {
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleDownload = async () => {
    setDownloading(true)
    setError(null)
    try {
      await downloadCertificate()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div
      className="relative overflow-hidden p-8 text-center"
      style={{
        borderRadius: 'var(--ui-radius, 12px)',
        background: 'linear-gradient(135deg, #191919, #2d2d2d)',
      }}
    >
      {/* Shimmer sweep */}
      <div className="absolute inset-0 cert-banner-shimmer" />

      <div className="relative">
        <div className="flex items-center justify-center gap-3 mb-1">
          <Award size={32} className="text-yellow-400" />
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-0.5">
              University of Idaho &middot; Certified
            </p>
            <h2 className="text-2xl font-bold text-white title-shimmer">
              Vandal Workflow Architect
            </h2>
          </div>
          <Award size={32} className="text-yellow-400" />
        </div>
        <p className="text-gray-400 text-sm mt-2">
          All 11 modules completed &middot; 1850 XP &middot; Architect level
        </p>
        <p className="text-gray-500 text-xs mt-1">
          Recognized for mastery in AI-powered document workflow design for research administration
        </p>
        <button
          type="button"
          onClick={handleDownload}
          disabled={downloading}
          title="A one-page PDF with your name, certification date and level, ready to print"
          className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-highlight text-highlight-text text-sm font-bold hover:brightness-90 transition-all disabled:opacity-60"
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          {downloading ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
          Download certificate (PDF)
        </button>
        {error && <p className="text-red-400 text-xs mt-2" role="alert">{error}</p>}
      </div>
    </div>
  )
}
