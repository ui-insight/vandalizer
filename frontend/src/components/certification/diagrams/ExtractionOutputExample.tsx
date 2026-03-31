export function ExtractionOutputExample() {
  return (
    <div className="rounded-lg overflow-hidden border border-gray-200 text-xs mt-2">
      <div className="grid grid-cols-2 divide-x divide-gray-200">
        <div className="p-3 bg-blue-50">
          <div className="text-[10px] font-bold uppercase tracking-wider text-blue-600 mb-2">Document Excerpt</div>
          <div className="space-y-0.5 text-blue-900 leading-relaxed">
            <p><span className="font-semibold">PI:</span> Dr. Sarah Chen, University of Idaho</p>
            <p><span className="font-semibold">Budget:</span> $485,000</p>
            <p><span className="font-semibold">Period:</span> 09/01/2024 – 08/31/2029</p>
            <p><span className="font-semibold">Agency:</span> National Science Foundation</p>
          </div>
        </div>
        <div className="p-3 bg-gray-50">
          <div className="text-[10px] font-bold uppercase tracking-wider text-gray-500 mb-2">Extracted Output (JSON)</div>
          <pre className="text-gray-700 font-mono text-[10px] leading-relaxed whitespace-pre">{`{
  "pi_name": "Dr. Sarah Chen",
  "total_budget": "$485,000",
  "project_period": "5 years",
  "agency": "NSF"
}`}</pre>
        </div>
      </div>
    </div>
  )
}
