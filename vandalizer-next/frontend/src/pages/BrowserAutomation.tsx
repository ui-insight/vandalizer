import { useState } from 'react'
import {
  Globe,
  Chrome,
  MonitorPlay,
  Circle,
  Play,
  Square,
  MousePointer,
  FormInput,
  ScanSearch,
  Sparkles,
  CheckSquare,
  Pause,
} from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'

type Tab = 'overview' | 'recordings' | 'actions'

const ACTION_TYPES = [
  {
    name: 'Navigate',
    icon: Globe,
    description: 'Go to a URL',
    color: 'text-blue-600 bg-blue-50',
  },
  {
    name: 'Click',
    icon: MousePointer,
    description: 'Click an element on the page',
    color: 'text-purple-600 bg-purple-50',
  },
  {
    name: 'Fill Form',
    icon: FormInput,
    description: 'Enter text into form fields',
    color: 'text-green-600 bg-green-50',
  },
  {
    name: 'Extract',
    icon: ScanSearch,
    description: 'Extract data from the page',
    color: 'text-orange-600 bg-orange-50',
  },
  {
    name: 'Smart Action',
    icon: Sparkles,
    description: 'Natural language instruction executed by AI',
    color: 'text-pink-600 bg-pink-50',
  },
  {
    name: 'Verify',
    icon: CheckSquare,
    description: 'Assert that a condition is met',
    color: 'text-teal-600 bg-teal-50',
  },
  {
    name: 'Login Pause',
    icon: Pause,
    description: 'Wait for user to log in manually',
    color: 'text-yellow-600 bg-yellow-50',
  },
]

export default function BrowserAutomation() {
  const [tab, setTab] = useState<Tab>('overview')

  return (
    <PageLayout>
      <div className="mx-auto max-w-5xl space-y-6">
        {/* Header */}
        <div className="flex items-center gap-2">
          <Globe className="h-5 w-5 text-gray-400" />
          <h2 className="text-xl font-semibold text-gray-900">Browser Automation</h2>
        </div>

        {/* Tab bar */}
        <div className="flex gap-0 border-b border-gray-200">
          {([
            { key: 'overview' as const, label: 'Overview' },
            { key: 'recordings' as const, label: 'Recordings' },
            { key: 'actions' as const, label: 'Action Reference' },
          ]).map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-3 text-sm font-semibold transition-colors ${
                tab === t.key
                  ? 'border-b-2 border-gray-900 text-gray-900'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Overview */}
        {tab === 'overview' && (
          <div className="space-y-6">
            {/* Extension status */}
            <div className="rounded-lg border border-gray-200 bg-white p-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100">
                    <Chrome className="h-5 w-5 text-gray-600" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-gray-900">Chrome Extension</div>
                    <div className="text-xs text-gray-500">
                      Required for browser automation workflows
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 text-sm text-gray-400">
                  <Circle className="h-2.5 w-2.5 fill-gray-300" />
                  Not connected
                </div>
              </div>
              <div className="mt-4 rounded-md bg-gray-50 p-3 text-xs text-gray-600 leading-relaxed">
                Install the Vandalizer Chrome Extension and configure it with your backend URL
                and authentication token. The extension enables browser recording, element
                picking, and automated action execution.
              </div>
            </div>

            {/* How it works */}
            <div className="rounded-lg border border-gray-200 bg-white">
              <div className="border-b border-gray-200 px-4 py-3">
                <h3 className="font-medium text-gray-900">How It Works</h3>
              </div>
              <div className="p-4 space-y-4">
                <Step
                  num={1}
                  title="Record or Build"
                  description="Use the Chrome extension to record your browser actions, or manually build an action sequence in the workflow editor."
                />
                <Step
                  num={2}
                  title="Add to Workflow"
                  description="Add a Browser Automation task to any workflow step. Configure the target URL, allowed domains, and action sequence."
                />
                <Step
                  num={3}
                  title="Execute"
                  description="When the workflow runs, the automation engine connects to the Chrome extension and executes each action in sequence, extracting data along the way."
                />
                <Step
                  num={4}
                  title="Self-Healing"
                  description="If an element can't be found, the system uses fallback locator strategies and can prompt the user to re-select the target element."
                />
              </div>
            </div>

            {/* Capabilities */}
            <div className="grid grid-cols-3 gap-4">
              <CapabilityCard
                icon={MonitorPlay}
                title="Recording"
                description="Record browser interactions and convert them into reusable automation steps."
              />
              <CapabilityCard
                icon={Sparkles}
                title="Smart Actions"
                description="Use natural language instructions that AI translates into browser actions."
              />
              <CapabilityCard
                icon={ScanSearch}
                title="Data Extraction"
                description="Extract structured data from web pages using CSS selectors or AI-powered extraction."
              />
            </div>
          </div>
        )}

        {/* Recordings */}
        {tab === 'recordings' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-500">
                Browser recordings from the Chrome extension appear here.
              </div>
              <button className="flex items-center gap-1.5 rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800">
                <Play className="h-3.5 w-3.5" />
                Start Recording
              </button>
            </div>

            <div className="rounded-lg border border-gray-200 bg-white p-8 text-center">
              <MonitorPlay className="mx-auto h-8 w-8 text-gray-300 mb-3" />
              <p className="text-sm text-gray-500">
                No recordings yet. Connect the Chrome extension and start recording to create
                browser automation workflows.
              </p>
              <p className="text-xs text-gray-400 mt-2">
                Recordings capture clicks, form fills, navigation, and data extraction.
              </p>
            </div>
          </div>
        )}

        {/* Action Reference */}
        {tab === 'actions' && (
          <div className="space-y-4">
            <p className="text-sm text-gray-500">
              Available action types for browser automation workflows.
            </p>
            <div className="grid grid-cols-2 gap-3">
              {ACTION_TYPES.map((action) => {
                const Icon = action.icon
                return (
                  <div
                    key={action.name}
                    className="flex items-start gap-3 rounded-lg border border-gray-200 bg-white p-4"
                  >
                    <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${action.color}`}>
                      <Icon className="h-4.5 w-4.5" />
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-gray-900">{action.name}</div>
                      <div className="text-xs text-gray-500 mt-0.5">{action.description}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </PageLayout>
  )
}

function Step({
  num,
  title,
  description,
}: {
  num: number
  title: string
  description: string
}) {
  return (
    <div className="flex gap-3">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-900 text-xs font-bold text-white">
        {num}
      </div>
      <div>
        <div className="text-sm font-medium text-gray-900">{title}</div>
        <div className="text-xs text-gray-500 mt-0.5">{description}</div>
      </div>
    </div>
  )
}

function CapabilityCard({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof Globe
  title: string
  description: string
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <Icon className="h-5 w-5 text-gray-400 mb-2" />
      <div className="text-sm font-semibold text-gray-900">{title}</div>
      <div className="text-xs text-gray-500 mt-1 leading-relaxed">{description}</div>
    </div>
  )
}
