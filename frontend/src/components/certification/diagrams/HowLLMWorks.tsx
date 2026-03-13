export function HowLLMWorksDiagram() {
  return (
    <svg viewBox="0 0 480 100" className="w-full" aria-label="How an LLM works: Training Data flows to Pattern Learning flows to Text Generation">
      {/* Training Data box */}
      <rect x="10" y="25" width="120" height="50" rx="8" fill="#dbeafe" stroke="#93c5fd" strokeWidth="1.5" />
      <text x="70" y="47" textAnchor="middle" className="text-[11px] font-semibold fill-blue-800">Training</text>
      <text x="70" y="62" textAnchor="middle" className="text-[11px] font-semibold fill-blue-800">Data</text>

      {/* Arrow 1 */}
      <line x1="135" y1="50" x2="170" y2="50" stroke="#94a3b8" strokeWidth="2" markerEnd="url(#arrow-llm)" />

      {/* Pattern Learning box */}
      <rect x="175" y="25" width="120" height="50" rx="8" fill="#e0e7ff" stroke="#a5b4fc" strokeWidth="1.5" />
      <text x="235" y="47" textAnchor="middle" className="text-[11px] font-semibold fill-indigo-800">Pattern</text>
      <text x="235" y="62" textAnchor="middle" className="text-[11px] font-semibold fill-indigo-800">Learning</text>

      {/* Arrow 2 */}
      <line x1="300" y1="50" x2="335" y2="50" stroke="#94a3b8" strokeWidth="2" markerEnd="url(#arrow-llm)" />

      {/* Text Generation box */}
      <rect x="340" y="25" width="130" height="50" rx="8" fill="#dcfce7" stroke="#86efac" strokeWidth="1.5" />
      <text x="405" y="47" textAnchor="middle" className="text-[11px] font-semibold fill-green-800">Text</text>
      <text x="405" y="62" textAnchor="middle" className="text-[11px] font-semibold fill-green-800">Generation</text>

      {/* Arrow marker definition */}
      <defs>
        <marker id="arrow-llm" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
        </marker>
      </defs>
    </svg>
  )
}
