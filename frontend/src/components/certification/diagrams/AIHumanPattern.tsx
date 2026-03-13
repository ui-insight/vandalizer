export function AIHumanPatternDiagram() {
  return (
    <svg viewBox="0 0 480 120" className="w-full" aria-label="AI does extraction, then Human does verification">
      {/* AI Lane */}
      <rect x="10" y="10" width="220" height="45" rx="8" fill="#dbeafe" stroke="#93c5fd" strokeWidth="1.5" />
      <text x="20" y="28" className="text-[10px] font-bold fill-blue-500">AI</text>
      <text x="120" y="38" textAnchor="middle" className="text-[12px] font-semibold fill-blue-800">Extraction & Analysis</text>

      {/* Arrow */}
      <line x1="235" y1="32" x2="255" y2="32" stroke="#94a3b8" strokeWidth="2" markerEnd="url(#arrow-aih)" />

      {/* Human Lane */}
      <rect x="260" y="10" width="210" height="45" rx="8" fill="#fef3c7" stroke="#fbbf24" strokeWidth="1.5" />
      <text x="270" y="28" className="text-[10px] font-bold fill-amber-600">HUMAN</text>
      <text x="365" y="38" textAnchor="middle" className="text-[12px] font-semibold fill-amber-800">Verification & Judgment</text>

      {/* Labels underneath */}
      <text x="120" y="78" textAnchor="middle" className="text-[10px] fill-gray-500">Reads documents</text>
      <text x="120" y="92" textAnchor="middle" className="text-[10px] fill-gray-500">Extracts data</text>
      <text x="120" y="106" textAnchor="middle" className="text-[10px] fill-gray-500">Produces structured output</text>

      <text x="365" y="78" textAnchor="middle" className="text-[10px] fill-gray-500">Reviews results</text>
      <text x="365" y="92" textAnchor="middle" className="text-[10px] fill-gray-500">Applies judgment</text>
      <text x="365" y="106" textAnchor="middle" className="text-[10px] fill-gray-500">Makes decisions</text>

      <defs>
        <marker id="arrow-aih" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
        </marker>
      </defs>
    </svg>
  )
}
