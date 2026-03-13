export function ExtractReasonDeliverDiagram() {
  return (
    <svg viewBox="0 0 480 90" className="w-full" aria-label="Extract-Reason-Deliver pipeline: Extract structured data, Reason over it, Deliver results">
      {/* Extract */}
      <rect x="10" y="20" width="130" height="50" rx="8" fill="#dbeafe" stroke="#93c5fd" strokeWidth="1.5" />
      <text x="75" y="40" textAnchor="middle" className="text-[12px] font-bold fill-blue-800">Extract</text>
      <text x="75" y="55" textAnchor="middle" className="text-[9px] fill-blue-600">Structured data</text>

      {/* Arrow */}
      <line x1="145" y1="45" x2="175" y2="45" stroke="#94a3b8" strokeWidth="2" markerEnd="url(#arrow-erd)" />

      {/* Reason */}
      <rect x="180" y="20" width="130" height="50" rx="8" fill="#e0e7ff" stroke="#a5b4fc" strokeWidth="1.5" />
      <text x="245" y="40" textAnchor="middle" className="text-[12px] font-bold fill-indigo-800">Reason</text>
      <text x="245" y="55" textAnchor="middle" className="text-[9px] fill-indigo-600">Analysis & logic</text>

      {/* Arrow */}
      <line x1="315" y1="45" x2="345" y2="45" stroke="#94a3b8" strokeWidth="2" markerEnd="url(#arrow-erd)" />

      {/* Deliver */}
      <rect x="350" y="20" width="120" height="50" rx="8" fill="#dcfce7" stroke="#86efac" strokeWidth="1.5" />
      <text x="410" y="40" textAnchor="middle" className="text-[12px] font-bold fill-green-800">Deliver</text>
      <text x="410" y="55" textAnchor="middle" className="text-[9px] fill-green-600">Useful output</text>

      <defs>
        <marker id="arrow-erd" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
        </marker>
      </defs>
    </svg>
  )
}
