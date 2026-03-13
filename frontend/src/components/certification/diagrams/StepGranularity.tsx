export function StepGranularityDiagram() {
  return (
    <svg viewBox="0 0 480 130" className="w-full" aria-label="Step granularity comparison: too few steps, too many steps, and the right balance">
      {/* Too Few */}
      <text x="80" y="14" textAnchor="middle" className="text-[10px] font-bold fill-red-600">Too few steps</text>
      <rect x="20" y="20" width="120" height="40" rx="6" fill="#fef2f2" stroke="#fca5a5" strokeWidth="1.5" />
      <text x="80" y="44" textAnchor="middle" className="text-[9px] fill-red-700">Everything in one blob</text>
      <text x="80" y="75" textAnchor="middle" className="text-[9px] fill-gray-500">Hard to debug</text>

      {/* Too Many */}
      <text x="245" y="14" textAnchor="middle" className="text-[10px] font-bold fill-red-600">Too many steps</text>
      <g>
        {[0, 1, 2, 3, 4, 5].map(i => (
          <g key={i}>
            <rect x={175 + i * 22} y="22" width="18" height="36" rx="3" fill="#fef2f2" stroke="#fca5a5" strokeWidth="1" />
            {i < 5 && <line x1={195 + i * 22} y1="40" x2={197 + i * 22} y2="40" stroke="#d4d4d4" strokeWidth="1" />}
          </g>
        ))}
      </g>
      <text x="245" y="75" textAnchor="middle" className="text-[9px] fill-gray-500">Over-engineered</text>

      {/* Just Right */}
      <text x="405" y="14" textAnchor="middle" className="text-[10px] font-bold fill-green-600">Just right</text>
      <rect x="340" y="22" width="38" height="36" rx="5" fill="#dcfce7" stroke="#86efac" strokeWidth="1.5" />
      <line x1="382" y1="40" x2="392" y2="40" stroke="#86efac" strokeWidth="1.5" markerEnd="url(#arrow-sg)" />
      <rect x="396" y="22" width="38" height="36" rx="5" fill="#dcfce7" stroke="#86efac" strokeWidth="1.5" />
      <line x1="438" y1="40" x2="448" y2="40" stroke="#86efac" strokeWidth="1.5" markerEnd="url(#arrow-sg)" />
      <rect x="452" y="22" width="20" height="36" rx="5" fill="#dcfce7" stroke="#86efac" strokeWidth="1.5" />
      <text x="359" y="44" textAnchor="middle" className="text-[8px] fill-green-700">Extract</text>
      <text x="415" y="44" textAnchor="middle" className="text-[8px] fill-green-700">Reason</text>
      <text x="462" y="44" textAnchor="middle" className="text-[8px] fill-green-700">Out</text>
      <text x="405" y="75" textAnchor="middle" className="text-[9px] fill-gray-500">Each step has one job</text>

      <defs>
        <marker id="arrow-sg" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#86efac" />
        </marker>
      </defs>
    </svg>
  )
}
