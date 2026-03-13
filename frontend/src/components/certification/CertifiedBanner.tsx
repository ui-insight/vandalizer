import { Award } from 'lucide-react'

export function CertifiedBanner() {
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
      </div>
    </div>
  )
}
