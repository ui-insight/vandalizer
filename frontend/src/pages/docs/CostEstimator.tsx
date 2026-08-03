import { useMemo, useState } from 'react'
import {
  MODEL_PRICES,
  OPERATIONS,
  WORKLOAD_PRESETS,
  estimate,
  formatTokens,
  formatUsd,
  type OperationCounts,
} from './costMath'

const FIELD =
  'w-full bg-[#1c1c1c] border border-white/15 rounded px-3 py-2 text-sm text-white ' +
  'focus:outline-none focus:border-[#f1b300] focus:ring-1 focus:ring-[#f1b300]'

const LABEL = 'block text-xs font-medium uppercase tracking-wide text-gray-400 mb-1.5'

/** Numeric fields are held as strings so a field can be cleared while typing. */
const toNumber = (raw: string) => {
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : 0
}

const countsToStrings = (counts: OperationCounts): Record<string, string> =>
  Object.fromEntries(Object.entries(counts).map(([k, v]) => [k, String(v)]))

export function CostEstimator() {
  const [presetId, setPresetId] = useState(WORKLOAD_PRESETS[1].id)
  const [counts, setCounts] = useState<Record<string, string>>(() =>
    countsToStrings(WORKLOAD_PRESETS[1].counts),
  )
  const [modelId, setModelId] = useState(MODEL_PRICES[0].id)
  const [inputRate, setInputRate] = useState(String(MODEL_PRICES[0].inputPerMTok))
  const [outputRate, setOutputRate] = useState(String(MODEL_PRICES[0].outputPerMTok))
  const [users, setUsers] = useState('25')
  const [cachePct, setCachePct] = useState(0)

  const model = MODEL_PRICES.find((m) => m.id === modelId) ?? MODEL_PRICES[0]

  // Switching preset or model overwrites the fields it owns; each is still
  // editable afterwards, which flips the selection into a "Custom" state.
  const applyPreset = (id: string) => {
    const preset = WORKLOAD_PRESETS.find((p) => p.id === id)
    if (!preset) return
    setPresetId(id)
    setCounts(countsToStrings(preset.counts))
  }

  const applyModel = (id: string) => {
    const next = MODEL_PRICES.find((m) => m.id === id)
    if (!next) return
    setModelId(id)
    setInputRate(String(next.inputPerMTok))
    setOutputRate(String(next.outputPerMTok))
  }

  const ratesOverridden =
    toNumber(inputRate) !== model.inputPerMTok || toNumber(outputRate) !== model.outputPerMTok

  const activePreset = WORKLOAD_PRESETS.find((p) => p.id === presetId)
  const countsMatchPreset =
    activePreset !== undefined &&
    OPERATIONS.every((op) => toNumber(counts[op.id] ?? '0') === (activePreset.counts[op.id] ?? 0))

  const result = useMemo(
    () =>
      estimate({
        counts: Object.fromEntries(OPERATIONS.map((op) => [op.id, toNumber(counts[op.id] ?? '0')])),
        inputPerMTok: toNumber(inputRate),
        outputPerMTok: toNumber(outputRate),
        users: toNumber(users),
        cacheHitRate: cachePct / 100,
      }),
    [counts, inputRate, outputRate, users, cachePct],
  )

  const providers = [...new Set(MODEL_PRICES.map((m) => m.provider))]

  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold text-white">Cost Estimator</h2>
      <p className="text-gray-300 text-lg leading-relaxed">
        Estimate what a Vandalizer deployment will spend on LLM API calls, per research
        administrator per month. Pick a workload level and a frontier model, adjust anything that
        does not match your office, and the estimate updates as you type.
      </p>

      <div className="bg-[#f1b300]/10 border border-[#f1b300]/30 rounded-lg p-4">
        <p className="text-sm text-gray-300 leading-relaxed">
          <strong className="text-white">These are starting assumptions, not measurements.</strong>{' '}
          Vandalizer meters every LLM call and records it with a feature label, so once your
          deployment has real traffic you should calibrate against your own numbers rather than
          these. See <em className="text-white">Calibrating against real usage</em> below.
        </p>
      </div>

      {/* ------------------------------------------------------------------ */}
      <h3 className="text-xl font-bold text-white mt-8">1. Workload level</h3>
      <div className="grid gap-3 sm:grid-cols-3">
        {WORKLOAD_PRESETS.map((preset) => {
          const selected = presetId === preset.id && countsMatchPreset
          return (
            <button
              key={preset.id}
              type="button"
              onClick={() => applyPreset(preset.id)}
              aria-pressed={selected}
              className={`text-left rounded-lg border p-4 transition-colors ${
                selected
                  ? 'border-[#f1b300] bg-[#f1b300]/10'
                  : 'border-white/15 bg-[#262626] hover:border-white/30'
              }`}
            >
              <div className="font-bold text-white">{preset.label}</div>
              <div className="text-xs text-gray-400 mt-1.5 leading-relaxed">
                {preset.description}
              </div>
            </button>
          )
        })}
      </div>

      <div className="bg-[#262626] rounded-lg p-4 space-y-3">
        <div className="flex items-baseline justify-between gap-4 flex-wrap">
          <span className={LABEL + ' mb-0'}>Per user, per month</span>
          {!countsMatchPreset && (
            <span className="text-xs text-[#f1b300]">Custom &mdash; edited from {activePreset?.label}</span>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {OPERATIONS.map((op) => (
            <div key={op.id}>
              <label className="block text-sm text-gray-300 mb-1.5" htmlFor={`count-${op.id}`}>
                {op.label} <span className="text-gray-500">({op.unit})</span>
              </label>
              <input
                id={`count-${op.id}`}
                type="number"
                min={0}
                inputMode="numeric"
                className={FIELD}
                value={counts[op.id] ?? '0'}
                onChange={(e) => setCounts({ ...counts, [op.id]: e.target.value })}
              />
            </div>
          ))}
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      <h3 className="text-xl font-bold text-white mt-8">2. Model &amp; deployment</h3>
      <div className="bg-[#262626] rounded-lg p-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="sm:col-span-2">
          <label className={LABEL} htmlFor="cost-model">
            Model
          </label>
          <select
            id="cost-model"
            className={FIELD}
            value={modelId}
            onChange={(e) => applyModel(e.target.value)}
          >
            {providers.map((provider) => (
              <optgroup key={provider} label={provider}>
                {MODEL_PRICES.filter((m) => m.provider === provider).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
        <div>
          <label className={LABEL} htmlFor="cost-input-rate">
            Input $ / 1M tokens
          </label>
          <input
            id="cost-input-rate"
            type="number"
            min={0}
            step="0.01"
            inputMode="decimal"
            className={FIELD}
            value={inputRate}
            onChange={(e) => setInputRate(e.target.value)}
          />
        </div>
        <div>
          <label className={LABEL} htmlFor="cost-output-rate">
            Output $ / 1M tokens
          </label>
          <input
            id="cost-output-rate"
            type="number"
            min={0}
            step="0.01"
            inputMode="decimal"
            className={FIELD}
            value={outputRate}
            onChange={(e) => setOutputRate(e.target.value)}
          />
        </div>
        <div>
          <label className={LABEL} htmlFor="cost-users">
            Users on the deployment
          </label>
          <input
            id="cost-users"
            type="number"
            min={0}
            inputMode="numeric"
            className={FIELD}
            value={users}
            onChange={(e) => setUsers(e.target.value)}
          />
        </div>
        <div className="sm:col-span-2 lg:col-span-3">
          <label className={LABEL} htmlFor="cost-cache">
            Prompt-cache hit rate &mdash; {cachePct}% of input tokens
          </label>
          <input
            id="cost-cache"
            type="range"
            min={0}
            max={90}
            step={5}
            className="w-full accent-[#f1b300]"
            value={cachePct}
            onChange={(e) => setCachePct(Number(e.target.value))}
          />
          <p className="text-xs text-gray-500 mt-1.5">
            Repeated document and knowledge-base context caches well; cached reads bill at roughly
            a tenth of the standard input rate. Leave at 0% for a worst-case figure.
          </p>
        </div>
        {(model.note || ratesOverridden) && (
          <p className="sm:col-span-2 lg:col-span-4 text-xs text-gray-400 leading-relaxed">
            {ratesOverridden ? (
              <span className="text-[#f1b300]">Using your overridden rates. </span>
            ) : null}
            {model.note}
          </p>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      <h3 className="text-xl font-bold text-white mt-8">3. Estimate</h3>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="bg-[#262626] rounded-lg p-6 border border-[#f1b300]/30">
          <div className={LABEL}>Per user / month</div>
          <div className="text-4xl font-bold text-[#f1b300]">{formatUsd(result.costPerUser)}</div>
          <div className="text-xs text-gray-500 mt-2">
            {formatUsd(result.costPerUser * 12)} per user / year
          </div>
        </div>
        <div className="bg-[#262626] rounded-lg p-6 border border-white/15">
          <div className={LABEL}>Deployment / month</div>
          <div className="text-4xl font-bold text-white">{formatUsd(result.costTotal)}</div>
          <div className="text-xs text-gray-500 mt-2">
            {formatUsd(result.costTotal * 12)} per year at {toNumber(users) || 0} users
          </div>
        </div>
      </div>

      <div className="bg-[#262626] rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10 text-left">
              <th className="p-3 font-medium text-gray-400">Operation</th>
              <th className="p-3 font-medium text-gray-400 text-right">Volume</th>
              <th className="p-3 font-medium text-gray-400 text-right">Input</th>
              <th className="p-3 font-medium text-gray-400 text-right">Output</th>
              <th className="p-3 font-medium text-gray-400 text-right">Cost / user</th>
            </tr>
          </thead>
          <tbody>
            {result.perOperation.map((row) => (
              <tr key={row.operation.id} className="border-b border-white/5">
                <td className="p-3">
                  <div className="text-white">{row.operation.label}</div>
                  <div className="text-xs text-gray-500 mt-0.5 max-w-md leading-relaxed">
                    {row.operation.description}
                  </div>
                </td>
                <td className="p-3 text-right text-gray-300 whitespace-nowrap">{row.count}</td>
                <td className="p-3 text-right text-gray-300 whitespace-nowrap">
                  {formatTokens(row.inputTokens)}
                </td>
                <td className="p-3 text-right text-gray-300 whitespace-nowrap">
                  {formatTokens(row.outputTokens)}
                </td>
                <td className="p-3 text-right text-white whitespace-nowrap">
                  {formatUsd(row.cost)}
                </td>
              </tr>
            ))}
            <tr className="font-bold">
              <td className="p-3 text-white">Total</td>
              <td className="p-3" />
              <td className="p-3 text-right text-gray-300 whitespace-nowrap">
                {formatTokens(result.inputTokens)}
              </td>
              <td className="p-3 text-right text-gray-300 whitespace-nowrap">
                {formatTokens(result.outputTokens)}
              </td>
              <td className="p-3 text-right text-[#f1b300] whitespace-nowrap">
                {formatUsd(result.costPerUser)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* ------------------------------------------------------------------ */}
      <h3 className="text-xl font-bold text-white mt-8">What the numbers assume</h3>
      <ul className="space-y-2 text-gray-300 text-sm">
        <li className="flex items-start gap-2">
          <span className="text-[#f1b300] mt-1">&#x2022;</span>
          <span>
            <strong className="text-white">Extraction is two-pass by default</strong>, so the
            document body goes through the model twice. Switching a workflow step to{' '}
            <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">
              one_pass
            </code>{' '}
            in extraction config roughly halves its input cost.
          </span>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-[#f1b300] mt-1">&#x2022;</span>
          <span>
            <strong className="text-white">Indexing documents costs nothing.</strong> Chunking and
            embedding run locally through ChromaDB&rsquo;s default embedding function, so uploads
            only incur the classification and title-generation pass.
          </span>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-[#f1b300] mt-1">&#x2022;</span>
          <span>
            <strong className="text-white">Input tokens dominate.</strong> Document context, not
            generated text, is where the money goes &mdash; which is why prompt caching and model
            choice for high-volume steps matter more than trimming output length.
          </span>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-[#f1b300] mt-1">&#x2022;</span>
          <span>
            <strong className="text-white">Rates are list prices captured 2026-07-31</strong> and go
            stale. Provider pricing pages are authoritative; override the rate fields above rather
            than trusting the defaults for a budget you have to defend.
          </span>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-[#f1b300] mt-1">&#x2022;</span>
          <span>
            <strong className="text-white">Self-hosted models cost $0 per token</strong> but shift
            spend to GPU infrastructure, which this estimator does not model. See{' '}
            <em className="text-white">Sizing your own cluster</em> below.
          </span>
        </li>
      </ul>

      {/* ------------------------------------------------------------------ */}
      <h3 className="text-xl font-bold text-white mt-8">Sizing your own cluster</h3>
      <p className="text-gray-300 leading-relaxed">
        The figures above price a hosted frontier model per token. If you are weighing that against
        running open-weight models on your own hardware, the cost shifts to capital and power, and
        the question becomes how many GPUs your user count and throughput actually demand.
      </p>
      <div className="bg-[#262626] rounded-lg p-5 border border-white/15">
        <div className="text-xs font-medium uppercase tracking-wide text-[#f1b300] mb-2">
          Interactive tool
        </div>
        <div className="text-lg font-bold text-white">Plan Your Inference Cluster</div>
        <p className="text-sm text-gray-300 mt-2 leading-relaxed">
          MindRouter&rsquo;s configurator takes users, throughput, budget, and a model-intelligence
          target calibrated against the open-weight frontier, and returns a concrete build:
          servers, GPUs, price range, and power draw &mdash; from a single NVIDIA DGX Spark up to a
          Supermicro HGX B300 node.
        </p>
        <a
          href="https://mindrouter.ai/configurator.html"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block mt-4 bg-[#f1b300] text-black font-bold text-sm px-4 py-2 rounded hover:bg-[#f1b300]/85 transition-colors"
        >
          Open the Configurator &rarr;
        </a>
        <p className="text-xs text-gray-500 mt-3 leading-relaxed">
          External tool, not affiliated with Vandalizer. It sizes hardware; it does not account for
          staff time, cooling, or rack space.
        </p>
      </div>

      <h3 className="text-xl font-bold text-white mt-8">Calibrating against real usage</h3>
      <p className="text-gray-300 leading-relaxed">
        Every LLM call flows through a single metering chokepoint and is written to the{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">llm_usage</code>{' '}
        ledger with its feature, model, user, team, and exact input/output token counts. The
        operation names in the table above match those feature labels, so after a month of real
        traffic you can divide each feature&rsquo;s token total by its operation count and replace
        the assumptions here with measurements. Rows flagged{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">estimated</code>{' '}
        are ones where the provider returned no usage data and tokens were counted locally.
      </p>
      <div className="bg-[#262626] rounded-lg p-4 font-mono text-sm text-gray-300 overflow-x-auto">
        <div className="text-gray-500"># Mean tokens per operation, by feature, last 30 days</div>
        <div>db.llm_usage.aggregate([</div>
        <div>&nbsp;&nbsp;{'{'} $match: {'{'} timestamp: {'{'} $gte: cutoff {'}'} {'}'} {'}'},</div>
        <div>
          &nbsp;&nbsp;{'{'} $group: {'{'} _id: &quot;$feature&quot;, calls: {'{'} $sum: 1 {'}'},
        </div>
        <div>
          &nbsp;&nbsp;&nbsp;&nbsp;avgIn: {'{'} $avg: &quot;$tokens_input&quot; {'}'}, avgOut: {'{'}{' '}
          $avg: &quot;$tokens_output&quot; {'}'} {'}'} {'}'}
        </div>
        <div>])</div>
      </div>
    </div>
  )
}

export default CostEstimator
