export function AISuitabilityDiagram() {
  return (
    <svg viewBox="0 0 420 180" className="w-full" aria-label="Decision tree: Is it repetitive? Is it document-based? Is it rule-based? Then it's a good candidate for AI.">
      {/* Question 1 */}
      <rect x="130" y="5" width="160" height="32" rx="6" fill="#e0e7ff" stroke="#a5b4fc" strokeWidth="1.5" />
      <text x="210" y="26" textAnchor="middle" className="text-[11px] font-semibold fill-indigo-800">Is it repetitive?</text>

      {/* Yes arrow down */}
      <line x1="210" y1="37" x2="210" y2="55" stroke="#22c55e" strokeWidth="1.5" markerEnd="url(#arrow-ai)" />
      <text x="222" y="50" className="text-[9px] font-bold fill-green-600">YES</text>

      {/* No arrow right */}
      <line x1="290" y1="21" x2="320" y2="21" stroke="#ef4444" strokeWidth="1.5" markerEnd="url(#arrow-ai)" />
      <text x="330" y="25" className="text-[9px] font-bold fill-red-500">NO</text>
      <rect x="325" y="8" width="85" height="26" rx="6" fill="#fef2f2" stroke="#fca5a5" strokeWidth="1" />
      <text x="367" y="25" textAnchor="middle" className="text-[9px] fill-red-700">Keep manual</text>

      {/* Question 2 */}
      <rect x="120" y="58" width="180" height="32" rx="6" fill="#e0e7ff" stroke="#a5b4fc" strokeWidth="1.5" />
      <text x="210" y="79" textAnchor="middle" className="text-[11px] font-semibold fill-indigo-800">Is it document-based?</text>

      {/* Yes arrow down */}
      <line x1="210" y1="90" x2="210" y2="108" stroke="#22c55e" strokeWidth="1.5" markerEnd="url(#arrow-ai)" />
      <text x="222" y="103" className="text-[9px] font-bold fill-green-600">YES</text>

      {/* No arrow right */}
      <line x1="300" y1="74" x2="320" y2="74" stroke="#ef4444" strokeWidth="1.5" markerEnd="url(#arrow-ai)" />
      <text x="330" y="78" className="text-[9px] font-bold fill-red-500">NO</text>
      <rect x="325" y="61" width="85" height="26" rx="6" fill="#fef2f2" stroke="#fca5a5" strokeWidth="1" />
      <text x="367" y="78" textAnchor="middle" className="text-[9px] fill-red-700">Keep manual</text>

      {/* Question 3 */}
      <rect x="125" y="111" width="170" height="32" rx="6" fill="#e0e7ff" stroke="#a5b4fc" strokeWidth="1.5" />
      <text x="210" y="132" textAnchor="middle" className="text-[11px] font-semibold fill-indigo-800">Is it rule-based?</text>

      {/* Yes arrow down */}
      <line x1="210" y1="143" x2="210" y2="155" stroke="#22c55e" strokeWidth="1.5" markerEnd="url(#arrow-ai)" />
      <text x="222" y="153" className="text-[9px] font-bold fill-green-600">YES</text>

      {/* Result */}
      <rect x="130" y="158" width="160" height="20" rx="6" fill="#dcfce7" stroke="#86efac" strokeWidth="1.5" />
      <text x="210" y="172" textAnchor="middle" className="text-[10px] font-bold fill-green-800">Good AI candidate!</text>

      <defs>
        <marker id="arrow-ai" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
        </marker>
      </defs>
    </svg>
  )
}
