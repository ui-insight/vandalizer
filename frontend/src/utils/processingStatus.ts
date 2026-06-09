// Mapping from backend `task_status` pipeline stages to user-facing copy.
// Backend stages: layout → extracting → security → readying → complete | error.
// Keep these in sync with backend/app/tasks/document_tasks.py and
// backend/app/tasks/upload_validation_tasks.py.

export interface StageCopy {
  short: string   // tight cells (e.g. file browser row)
  title: string   // banner/overlay headline
  message: string // banner/overlay subtitle
  progress: number // 0..1, for progress bars
}

export const PROCESSING_STAGES: Record<string, StageCopy> = {
  layout: {
    short: 'Preparing…',
    title: 'Converting & Preparing Your Document…',
    message: "We're converting your document so it can be read and analyzed accurately.",
    progress: 0.2,
  },
  extracting: {
    short: 'Reading text…',
    title: 'Reading Your Document…',
    message: 'Extracting text from each page.',
    progress: 0.4,
  },
  ocr: {
    short: 'Running OCR…',
    title: 'Extracting Text From Your Document…',
    message: 'Running OCR to extract text content from your document.',
    progress: 0.5,
  },
  security: {
    short: 'Scanning…',
    title: 'Scanning Your Document…',
    message: "Checking for any sensitive information in your document.",
    progress: 0.65,
  },
  readying: {
    short: 'Indexing…',
    title: 'Almost Ready…',
    message: 'Indexing your document for search and analysis.',
    progress: 0.85,
  },
}

const FALLBACK: StageCopy = {
  short: 'Processing…',
  title: 'Processing Your Document…',
  message: 'Please wait while we prepare your document.',
  progress: 0.1,
}

export function stageCopy(taskStatus: string | null | undefined): StageCopy {
  if (!taskStatus) return FALLBACK
  return PROCESSING_STAGES[taskStatus] ?? FALLBACK
}

// A doc is fully ready when its background processing has finished AND
// retrieval indexing has too. `processing` flips off after text extraction,
// but `task_status` continues through "readying" while RAG indexing runs.
export function isDocReady(doc: { processing?: boolean; task_status?: string | null }): boolean {
  if (doc.processing) return false
  const status = doc.task_status
  return !status || status === 'complete' || status === 'error'
}
