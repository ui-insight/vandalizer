import { useEffect, useRef, useState, useCallback, type DragEvent } from 'react'
import { Loader2, BookOpen, X, ArrowDown, ChevronRight, Shield, CheckCircle2, Upload, Zap, Link2, Sparkles, FolderKanban } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { AttachmentList } from './AttachmentList'
import { toolResultToText } from './ToolCallDisplay'
import { WorkspaceBriefing } from './WorkspaceBriefing'
import { OnboardingStepper } from './WelcomeExperience'
import { ConceptStrip } from './ConceptTip'
import { ContextMeter } from './ContextMeter'
import { ContextLimitDialog } from './ContextLimitDialog'
import { MemoryPanel } from './MemoryPanel'
import { ProjectChatBadge } from './ProjectChatBadge'
import { ProjectSuggestedActions } from '../projects/ProjectSuggestedActions'
import { useChat } from '../../hooks/useChat'
import { useProject } from '../../hooks/useProjects'
import { useOnboarding } from '../../hooks/useOnboarding'
import { useWorkspace, type PendingChatMessage } from '../../contexts/WorkspaceContext'
import { useToast } from '../../contexts/ToastContext'
import { useBranding } from '../../contexts/BrandingContext'
import { useShareLink } from '../../lib/shareLink'
import { addLink, removeDocument, removeLink, truncateContext, compactContext, clearContext } from '../../api/chat'
import { uploadFile } from '../../api/files'
import { pollStatus } from '../../api/documents'
import { convertDocumentsToKB } from '../../api/knowledge'
import { getUserConfig, updateUserConfig, markFirstSessionComplete } from '../../api/config'
import type { FileAttachment, UrlAttachment } from '../../types/chat'
import type { ModelInfo } from '../../types/workflow'
import { stageCopy, isDocReady } from '../../utils/processingStatus'
import { partitionNewFiles } from './attachmentDedup'

const LOADING_WORDS = [
  'Thinking', 'Vandalizing', 'Pondering', 'Analyzing',
  'Processing', 'Brewing', 'Crunching', 'Conjuring',
]

function StreamingLabel() {
  const { isCustomized } = useBranding()
  // 'Vandalizing' is a Joe Vandal in-joke — keep it off white-labeled deployments.
  const words = isCustomized ? LOADING_WORDS.filter(w => w !== 'Vandalizing') : LOADING_WORDS
  const [index, setIndex] = useState(0)
  const [fade, setFade] = useState(true)

  useEffect(() => {
    const interval = setInterval(() => {
      setFade(false)
      setTimeout(() => {
        setIndex(i => (i + 1) % words.length)
        setFade(true)
      }, 200)
    }, 2000)
    return () => clearInterval(interval)
  }, [words.length])

  return (
    // role=status announces "working" to assistive tech ONCE when streaming
    // begins; the rotating word itself is decorative (aria-hidden) so screen
    // readers aren't spammed with "Thinking… Pondering… Analyzing…" every 2s.
    <span role="status" aria-live="polite">
      <span
        aria-hidden="true"
        style={{
          opacity: fade ? 1 : 0,
          transition: 'opacity 0.2s ease',
          fontSize: 13,
          color: '#9ca3af',
        }}
      >
        {words[index % words.length]}&hellip;
      </span>
      <span className="sr-only">The assistant is working…</span>
    </span>
  )
}

const VALUE_TAGLINES: Array<{
  icon: typeof Shield
  title: string
  detail: string
}> = [
  { icon: Shield, title: 'Your documents stay private', detail: 'Files never leave your institution; you choose the model.' },
  { icon: CheckCircle2, title: 'Workflows you can trust', detail: 'Every extraction template has documented accuracy metrics.' },
  { icon: Upload, title: 'Built for research administration', detail: 'Purpose-built for grants, compliance, and institutional docs.' },
]

/** Single-line rotator that fades between the three value props inside the first-session banner. */
function ValueTaglineRotator() {
  const [index, setIndex] = useState(0)
  const [fade, setFade] = useState(true)

  useEffect(() => {
    const interval = setInterval(() => {
      setFade(false)
      setTimeout(() => {
        setIndex(i => (i + 1) % VALUE_TAGLINES.length)
        setFade(true)
      }, 380)
    }, 4200)
    return () => clearInterval(interval)
  }, [])

  const { icon: Icon, title, detail } = VALUE_TAGLINES[index]

  return (
    <div
      aria-live="polite"
      style={{
        marginTop: 14,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '8px 12px',
        borderRadius: 10,
        background: 'rgba(255,255,255,0.12)',
        backdropFilter: 'blur(4px)',
        opacity: fade ? 1 : 0,
        transition: 'opacity 0.38s ease',
        minHeight: 38,
      }}
    >
      <Icon size={15} style={{ flexShrink: 0, opacity: 0.95 }} />
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: '4px 8px', lineHeight: 1.35 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{title}</span>
        <span style={{ fontSize: 12, opacity: 0.82 }}>{detail}</span>
      </div>
    </div>
  )
}

interface ChatPanelProps {
  conversationToLoad?: string | null
  pendingMessage?: PendingChatMessage | null
  onPendingMessageConsumed?: () => void
}

export function ChatPanel({ conversationToLoad, pendingMessage, onPendingMessageConsumed }: ChatPanelProps) {
  const branding = useBranding()
  const brandIcon = branding.iconUrl
  const {
    messages,
    setMessages,
    streamingContent,
    thinkingContent,
    thinkingDuration,
    isStreaming,
    activityId,
    conversationUuid,
    error,
    activeToolCalls,
    toolResults,
    segments,
    errorDetails,
    clearError,
    retry,
    contextTokens,
    contextMode,
    contextCutoffIndex,
    contextNotices,
    setContextTokens,
    setContextMode,
    setContextCutoffIndex,
    send,
    stop,
    loadHistory,
    setActivity,
  } = useChat()

  const { bumpActivitySignal, processingDoc, selectedDocsProcessing, selectedDocUuids, setSelectedDocUuids, selectedDocNames, setSelectedDocNames, selectedFolderUuids, activeKBUuid, activeKBTitle, activateKB, deactivateKB, activeProjectUuid, activeProjectTitle, activeProjectRole, deactivateProject, setCurrentConversationUuid, focusChatSignal } = useWorkspace()

  // When scoped to a project, surface its file/index status so the empty state
  // reflects the project (not a generic assistant) and sets honest expectations.
  const { project: scopedProject } = useProject(activeProjectUuid ?? '')
  const projectFileCount = scopedProject?.capabilities?.files.count ?? 0
  const projectIndexed = scopedProject?.capabilities?.knowledge.documents ?? 0
  const projectEmpty = !!activeProjectUuid && projectFileCount === 0
  const projectIndexing = !!activeProjectUuid && projectFileCount > 0 && projectIndexed < projectFileCount
  const [convertingToKB, setConvertingToKB] = useState(false)
  const { toast } = useToast()
  const shareLink = useShareLink()
  const { pills: onboardingPills, isFirstSession, loading: onboardingLoading, status: onboardingStatus } = useOnboarding()
  // Lock the first-session flag once it's set so remounts/refetches can't
  // flip it mid-conversation (markFirstSessionComplete fires early).
  const lockedFirstSession = useRef<boolean | null>(null)
  if (lockedFirstSession.current === null && !onboardingLoading) {
    lockedFirstSession.current = isFirstSession
  }
  const effectiveFirstSession = lockedFirstSession.current ?? isFirstSession
  const firstSessionSeeded = useRef(false)
  const firstSessionMarked = useRef(false)
  const demoTriggered = useRef(false)
  const [fileAttachments, setFileAttachments] = useState<FileAttachment[]>([])
  const [urlAttachments, setUrlAttachments] = useState<UrlAttachment[]>([])
  const [attachLoading, setAttachLoading] = useState(false)
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [modelsList, setModelsList] = useState<ModelInfo[]>([])
  const [showContextDialog, setShowContextDialog] = useState(false)
  const [showContextNudge, setShowContextNudge] = useState(false)
  const contextNudgeShownRef = useRef(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)
  // Docs dropped this session — shown as "processing…" until the docs poll
  // confirms readiness, so a freshly dropped file's chip reflects state at once.
  const [justDroppedUuids, setJustDroppedUuids] = useState<Set<string>>(new Set())
  // A message sent while attached docs are still processing; auto-fires once ready.
  const [heldMessage, setHeldMessage] = useState<{ message: string; includeOnboardingContext?: boolean } | null>(null)
  const lastLoadedConvo = useRef<string | null>(null)
  const prevStreamingRef = useRef(false)
  const [showScrollDown, setShowScrollDown] = useState(false)
  const prevScrollInfo = useRef({ scrollHeight: 0, scrollTop: 0, clientHeight: 0 })
  const [dragOver, setDragOver] = useState(false)
  const dragCounter = useRef(0)


  // Load saved model preference on mount
  useEffect(() => {
    getUserConfig().then(cfg => {
      if (cfg.available_models?.length) {
        setModelsList(cfg.available_models)
      }
      if (cfg.model) {
        setSelectedModel(cfg.model)
      } else if (cfg.available_models?.length) {
        const first = cfg.available_models[0].tag || cfg.available_models[0].name
        setSelectedModel(first)
        updateUserConfig({ model: first }).catch(() => {})
      }
    }).catch(() => {})
  }, [])

  // Derive the context window size for the currently selected model
  const contextWindow = (() => {
    const match = modelsList.find(
      m => m.tag === selectedModel || m.name === selectedModel,
    )
    return match?.context_window ?? 128000
  })()

  // When usage crosses 90%, show a dismissible inline nudge rather than a
  // blocking modal — far less jarring for a first-time user mid-conversation.
  useEffect(() => {
    if (contextTokens > 0 && contextWindow > 0) {
      const ratio = contextTokens / contextWindow
      if (ratio >= 0.9 && !contextNudgeShownRef.current) {
        contextNudgeShownRef.current = true
        setShowContextNudge(true)
      } else if (ratio < 0.9) {
        contextNudgeShownRef.current = false
        setShowContextNudge(false)
      }
    }
  }, [contextTokens, contextWindow])

  // Seed the first-session conversation with an opening assistant message
  useEffect(() => {
    if (effectiveFirstSession && !onboardingLoading && messages.length === 0 && !firstSessionSeeded.current && !conversationToLoad) {
      firstSessionSeeded.current = true
      setMessages([{
        role: 'assistant',
        content:
          `Hi! I'm your ${branding.orgName} assistant.\n\n` +
          "I specialize in document intelligence for research administration: " +
          "extraction with **measured accuracy**, not guesses.\n\n" +
          "Want a quick demo? Say **\"show me\"** and I'll run one live against a sample grant proposal.\n\n" +
          "Or just ask me about your own documents.",
      }])
    }
  }, [effectiveFirstSession, onboardingLoading, messages.length, setMessages, conversationToLoad])

  const handleModelChange = (model: string) => {
    setSelectedModel(model)
    updateUserConfig({ model }).catch(() => {})
  }

  const handleTruncate = async () => {
    if (!conversationUuid) return
    const result = await truncateContext(conversationUuid)
    setContextMode('truncated')
    setContextCutoffIndex(result.context_cutoff_index)
    setContextTokens(0)
  }

  const handleCompact = async () => {
    if (!conversationUuid) return
    const result = await compactContext(conversationUuid)
    setContextMode('compacted')
    setContextCutoffIndex(result.context_cutoff_index)
    setContextTokens(0)
  }

  const handleClearContext = async () => {
    if (!conversationUuid) return
    const result = await clearContext(conversationUuid)
    setContextMode('truncated')
    setContextCutoffIndex(result.context_cutoff_index)
    setContextTokens(0)
  }

  const handleConvertToKB = async () => {
    const docs = errorDetails?.oversizeDocuments ?? []
    if (!docs.length) return
    setConvertingToKB(true)
    try {
      const kb = await convertDocumentsToKB(docs.map(d => d.uuid))
      // Detach the now-oversized docs from the message so retrying with the KB
      // doesn't immediately re-trigger the same error.
      const oversizeUuids = new Set(docs.map(d => d.uuid))
      setSelectedDocUuids(selectedDocUuids.filter(u => !oversizeUuids.has(u)))
      const remainingNames: Record<string, string> = {}
      for (const [uuid, name] of Object.entries(selectedDocNames)) {
        if (!oversizeUuids.has(uuid)) remainingNames[uuid] = name
      }
      setSelectedDocNames(remainingNames)
      activateKB(kb.uuid, kb.title)
      clearError()
      toast('Converted to Knowledge Base. Ask your question again.', 'success')
    } catch (e) {
      toast(
        e instanceof Error ? e.message : 'Could not convert the documents to a Knowledge Base.',
        'error',
      )
    } finally {
      setConvertingToKB(false)
    }
  }

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return
    prevScrollInfo.current = {
      scrollHeight: el.scrollHeight,
      scrollTop: el.scrollTop,
      clientHeight: el.clientHeight,
    }
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    // Stay "pinned" while near the bottom; if the user scrolls up, stop
    // auto-following the stream so they can read back without being yanked down.
    stickToBottomRef.current = distFromBottom < 80
    setShowScrollDown(distFromBottom > 80)
  }, [])

  // Follow the assistant's streaming output while the user is pinned to the
  // bottom — otherwise long answers scroll off-screen with no auto-scroll.
  useEffect(() => {
    if (!isStreaming || !stickToBottomRef.current) return
    const el = scrollContainerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [isStreaming, streamingContent, thinkingContent, segments])

  useEffect(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    if (distFromBottom > 80) {
      setShowScrollDown(true)
    }
  }, [messages, streamingContent])

  const prevConvoRef = useRef(conversationUuid)
  useEffect(() => {
    if (conversationUuid !== prevConvoRef.current) {
      prevConvoRef.current = conversationUuid
      prevScrollInfo.current = { scrollHeight: 0, scrollTop: 0, clientHeight: 0 }
      setShowScrollDown(false)
    }
  }, [conversationUuid])

  // Mirror the active conversation into workspace context so ActivityRail
  // can clear the chat when the user deletes the currently-open activity.
  useEffect(() => {
    setCurrentConversationUuid(conversationUuid)
    return () => setCurrentConversationUuid(null)
  }, [conversationUuid, setCurrentConversationUuid])

  const prevMsgCount = useRef(messages.length)
  useEffect(() => {
    if (messages.length > prevMsgCount.current) {
      const lastMsg = messages[messages.length - 1]
      if (lastMsg?.role === 'user') {
        prevScrollInfo.current = { scrollHeight: 0, scrollTop: 0, clientHeight: 0 }
        setShowScrollDown(false)
        stickToBottomRef.current = true
        const el = scrollContainerRef.current
        if (el) el.scrollTop = el.scrollHeight
      }
    }
    prevMsgCount.current = messages.length
  }, [messages])

  const scrollToBottom = useCallback(() => {
    setShowScrollDown(false)
    stickToBottomRef.current = true
    const el = scrollContainerRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [])

  useEffect(() => {
    if (isStreaming !== prevStreamingRef.current) {
      prevStreamingRef.current = isStreaming
      bumpActivitySignal()
    }
  }, [isStreaming, bumpActivitySignal])

  useEffect(() => {
    if (conversationToLoad && conversationToLoad !== lastLoadedConvo.current) {
      lastLoadedConvo.current = conversationToLoad
      loadHistory(conversationToLoad).then(() => {
        setTimeout(() => {
          const el = scrollContainerRef.current
          if (el) el.scrollTop = el.scrollHeight
        }, 50)
      }).catch(() => {
        // loadHistory sets its own error state; swallow here so a failed
        // history fetch doesn't surface as an unhandled promise rejection.
      })
    }
  }, [conversationToLoad, loadHistory])

  const pendingHandled = useRef<PendingChatMessage | null>(null)
  useEffect(() => {
    if (pendingMessage && pendingMessage !== pendingHandled.current && !isStreaming) {
      pendingHandled.current = pendingMessage
      const docs = pendingMessage.documentUuids ?? selectedDocUuids
      const folders = pendingMessage.folderUuids ?? selectedFolderUuids
      send(pendingMessage.message, docs, undefined, undefined, undefined, folders)
      onPendingMessageConsumed?.()
    }
  }, [pendingMessage, isStreaming, send, onPendingMessageConsumed])

  const hasDocContext = fileAttachments.length > 0 || urlAttachments.length > 0 || selectedDocUuids.length > 0 || selectedFolderUuids.length > 0

  // For the banner / pills: prefer the doc the user is actively viewing, but
  // fall back to any selected-but-still-processing doc so the chat doesn't
  // claim "ready for analysis" while OCR/indexing is still in flight.
  const bannerProcessingDoc = processingDoc ?? (selectedDocsProcessing.length > 0
    ? { title: selectedDocsProcessing[0].title, status: selectedDocsProcessing[0].status }
    : null)
  const processingCount = processingDoc ? 1 : selectedDocsProcessing.length

  // Per-document readiness: a selected doc is "processing" if FileBrowser
  // reports it not-ready, or it was just dropped and hasn't been reported yet.
  // Drives the live chip state and the send gate (Phase 4).
  const processingByUuid: Record<string, boolean> = {}
  for (const d of selectedDocsProcessing) {
    processingByUuid[d.uuid] = !isDocReady({ task_status: d.status })
  }
  for (const uuid of justDroppedUuids) {
    if (!(uuid in processingByUuid)) processingByUuid[uuid] = true
  }
  const anySelectedProcessing = selectedDocUuids.some(u => processingByUuid[u])

  // Poll just-dropped docs to authoritative readiness. FileBrowser only reports
  // status for docs selected *in the browser*, so a chat-dropped doc may never
  // appear in selectedDocsProcessing — poll_status is the source of truth here.
  // Clears each uuid once text extraction completes (or fails), which both
  // stops its chip spinning and releases any held message.
  useEffect(() => {
    if (justDroppedUuids.size === 0) return
    let cancelled = false
    const tick = async () => {
      const uuids = [...justDroppedUuids]
      const results = await Promise.all(
        uuids.map(u => pollStatus(u).then(r => ({ u, r })).catch(() => null)),
      )
      if (cancelled) return
      const done = results
        .filter((x): x is { u: string; r: Awaited<ReturnType<typeof pollStatus>> } => x !== null)
        .filter(({ r }) => r.complete || !!r.raw_text || !!r.error_message)
        .map(({ u }) => u)
      if (done.length) {
        setJustDroppedUuids(prev => {
          const next = new Set(prev)
          done.forEach(u => next.delete(u))
          return next
        })
      }
    }
    tick()
    const id = setInterval(tick, 2500)
    return () => { cancelled = true; clearInterval(id) }
  }, [justDroppedUuids])

  const handleSend = (message: string, includeOnboardingContext?: boolean) => {
    // Auto-hold: if the user attached document(s) that aren't readable yet,
    // don't fire a question at a file the model can't see. Queue it and let the
    // readiness effect below auto-send once text extraction finishes.
    if (anySelectedProcessing) {
      setHeldMessage({ message, includeOnboardingContext })
      return
    }
    // Use the locked ref so remounts / refetches can't flip this mid-conversation.
    const firstSession = effectiveFirstSession && !hasDocContext && !activeKBUuid && !activeProjectUuid
    // Detect "show me" to track demo trigger (backend does the real routing)
    if (firstSession && /^show\s*me/i.test(message.trim())) {
      demoTriggered.current = true
    }
    send(message, selectedDocUuids, selectedModel || undefined, activeKBUuid || undefined, includeOnboardingContext, selectedFolderUuids, firstSession || undefined, undefined, activeProjectUuid || undefined)
    // Defer markFirstSessionComplete until the user has had enough exchanges
    // to experience the value discovery (at least 3 user messages).
    // messages.length counts both user + assistant; 4 = 2 full exchanges done.
    if (firstSession && !firstSessionMarked.current && messages.length >= 4) {
      firstSessionMarked.current = true
      markFirstSessionComplete().catch(() => {})
    }
  }

  // Keep the latest handleSend in a ref so the auto-fire effect can call it
  // without re-subscribing on every render (handleSend isn't memoized).
  const handleSendRef = useRef(handleSend)
  handleSendRef.current = handleSend

  // Auto-fire a held message once all attached docs are readable. A doc that
  // errored out counts as "ready" (isDocReady), so the turn fires and the
  // backend explains the failure rather than the message hanging forever.
  useEffect(() => {
    if (!heldMessage || anySelectedProcessing || isStreaming) return
    const { message, includeOnboardingContext } = heldMessage
    setHeldMessage(null)
    handleSendRef.current(message, includeOnboardingContext)
  }, [heldMessage, anySelectedProcessing, isStreaming])

  const handleRunDemo = () => {
    demoTriggered.current = true
    send(
      `Show me what ${branding.orgName} can do`,
      selectedDocUuids,
      selectedModel || undefined,
      undefined, // knowledgeBaseUuid
      undefined, // includeOnboardingContext
      undefined, // folderUuids
      undefined, // isFirstSession
      true, // runDemo
    )
  }


  const queryClient = useQueryClient()

  const handleAttachFile = async (files: File[]) => {
    // Dedup by filename against what's already attached so a second drop of the
    // same file doesn't silently create a duplicate document (and OCR job).
    const { toUpload: uploadNames, dupes } = partitionNewFiles(
      files.map(f => f.name),
      Object.values(selectedDocNames),
    )
    const uploadSet = new Set(uploadNames)
    const seen = new Set<string>()
    const toUpload = files.filter(f => {
      if (!uploadSet.has(f.name) || seen.has(f.name)) return false
      seen.add(f.name)
      return true
    })
    if (dupes.length > 0) {
      toast(`${dupes[0]}${dupes.length > 1 ? ` and ${dupes.length - 1} more` : ''} already attached`, 'info')
    }
    if (toUpload.length === 0) return

    setAttachLoading(true)
    try {
      // Upload to the file browser (single source of truth) and auto-select
      const newNames: Record<string, string> = {}
      const newUuids: string[] = []
      for (const file of toUpload) {
        const ext = file.name.split('.').pop() || ''
        const base64 = await fileToBase64(file)
        const result = await uploadFile({ contentAsBase64String: base64, fileName: file.name, extension: ext })
        if (result.uuid) {
          newUuids.push(result.uuid)
          newNames[result.uuid] = file.name
        }
      }
      if (newUuids.length > 0) {
        setSelectedDocUuids([...selectedDocUuids, ...newUuids])
        setSelectedDocNames({ ...selectedDocNames, ...newNames })
        // Mark as just-dropped so the chip shows "processing…" immediately,
        // before the documents poll has a chance to report status.
        setJustDroppedUuids(prev => {
          const next = new Set(prev)
          newUuids.forEach(u => next.add(u))
          return next
        })
        queryClient.invalidateQueries({ queryKey: ['documents'] })
        const label = newUuids.length === 1 ? newNames[newUuids[0]] : `${newUuids.length} files`
        toast(`Added ${label}, processing…`, 'success')
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to upload file', 'error')
    } finally {
      setAttachLoading(false)
    }
  }

  const handleAttachLink = async (url: string) => {
    setAttachLoading(true)
    try {
      const result = await addLink(url, activityId)
      setUrlAttachments((prev) => [
        ...prev,
        {
          id: result.attachment_id,
          url,
          title: result.title,
          created_at: new Date().toISOString(),
        },
      ])
      if (result.activity_id && result.conversation_uuid) {
        setActivity(result.activity_id, result.conversation_uuid)
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to add website', 'error')
    } finally {
      setAttachLoading(false)
    }
  }

  const handleRemoveFile = async (id: string) => {
    try {
      await removeDocument(id)
      setFileAttachments((prev) => prev.filter((a) => a.id !== id))
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to remove file', 'error')
    }
  }

  const handleRemoveUrl = async (id: string) => {
    try {
      await removeLink(id)
      setUrlAttachments((prev) => prev.filter((a) => a.id !== id))
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to remove link', 'error')
    }
  }

  const handleDragEnter = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current++
    if (e.dataTransfer.types.includes('Files')) setDragOver(true)
  }, [])

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
  }, [])

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current--
    if (dragCounter.current <= 0) {
      dragCounter.current = 0
      setDragOver(false)
    }
  }, [])

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current = 0
    setDragOver(false)
    if (e.dataTransfer.files.length > 0) {
      const files = Array.from(e.dataTransfer.files)
      handleAttachFile(files)
    }
  }

  const handleExport = (format: string) => {
    /** Serialize a single message including any tool results from its segments. */
    const messageToText = (m: typeof messages[number]): string => {
      const role = m.role === 'user' ? 'User' : 'Assistant'
      const segs = m.segments
      if (segs && segs.length > 0) {
        const parts: string[] = []
        for (const seg of segs) {
          if (seg.kind === 'text') {
            const cleaned = seg.content.trim()
            if (cleaned) parts.push(cleaned)
          } else if (seg.kind === 'tool_result') {
            const body = toolResultToText(seg.result.tool_name, seg.result.content)
            if (body) parts.push(`[${seg.result.tool_name}]\n${body}`)
          }
        }
        return `${role}:\n${parts.join('\n\n')}`
      }
      // Fallback: content + tool results
      const parts = [m.content]
      if (m.tool_results) {
        for (const r of m.tool_results) {
          const body = toolResultToText(r.tool_name, r.content)
          if (body) parts.push(`[${r.tool_name}]\n${body}`)
        }
      }
      return `${role}:\n${parts.join('\n\n')}`
    }

    const fullText = messages.map(messageToText).join('\n\n---\n\n')

    if (format === 'text') {
      const blob = new Blob([fullText], { type: 'text/plain' })
      downloadBlob(blob, 'conversation.txt')
    } else if (format === 'csv') {
      const csvEscape = (s: string) => `"${s.replace(/"/g, '""')}"`
      const rows = [['Role', 'Content']]
      messages.forEach(m => {
        const segs = m.segments
        let content = m.content
        if (segs && segs.length > 0) {
          const parts: string[] = []
          for (const seg of segs) {
            if (seg.kind === 'text') {
              const cleaned = seg.content.trim()
              if (cleaned) parts.push(cleaned)
            } else if (seg.kind === 'tool_result') {
              const body = toolResultToText(seg.result.tool_name, seg.result.content)
              if (body) parts.push(`[${seg.result.tool_name}] ${body}`)
            }
          }
          content = parts.join('\n')
        } else if (m.tool_results) {
          const extras = m.tool_results
            .map(r => toolResultToText(r.tool_name, r.content))
            .filter(Boolean)
          if (extras.length) content += '\n' + extras.join('\n')
        }
        rows.push([m.role, content])
      })
      const csv = rows.map(r => r.map(csvEscape).join(',')).join('\n')
      const blob = new Blob([csv], { type: 'text/csv' })
      downloadBlob(blob, 'conversation.csv')
    } else if (format === 'pdf') {
      const escHtml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>')
      const html = `<html><head><title>Conversation</title><style>body{font-family:sans-serif;padding:40px;max-width:800px;margin:0 auto}
      .msg{margin-bottom:20px;padding:12px;border-radius:8px}.user{background:#f3f4f6;border-left:4px solid #eab308}
      .assistant{background:#fafafa}.role{font-weight:bold;margin-bottom:4px;font-size:12px;text-transform:uppercase;color:#666}
      .tool-data{background:#f0f4f8;padding:8px 12px;border-radius:4px;font-size:12px;margin:8px 0;white-space:pre-wrap;font-family:monospace}</style></head>
      <body>${messages.map(m => {
        const parts = [escHtml(m.content)]
        const segs = m.segments
        if (segs) {
          for (const seg of segs) {
            if (seg.kind === 'tool_result') {
              const body = toolResultToText(seg.result.tool_name, seg.result.content)
              if (body) parts.push(`<div class="tool-data"><strong>${seg.result.tool_name}</strong><br>${escHtml(body)}</div>`)
            }
          }
        } else if (m.tool_results) {
          for (const r of m.tool_results) {
            const body = toolResultToText(r.tool_name, r.content)
            if (body) parts.push(`<div class="tool-data"><strong>${r.tool_name}</strong><br>${escHtml(body)}</div>`)
          }
        }
        return `<div class="msg ${m.role}"><div class="role">${m.role}</div><div>${parts.join('')}</div></div>`
      }).join('')}</body></html>`
      const win = window.open('', '_blank')
      if (win) { win.document.write(html); win.document.close(); win.print() }
    }
  }

  return (
    <div
      className="flex h-full flex-col"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      style={{ position: 'relative' }}
    >
      {/* Drop overlay */}
      {dragOver && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 6%, rgba(255,255,255,0.95))',
            border: '2px dashed var(--highlight-color, #eab308)',
            borderRadius: 'var(--ui-radius, 12px)',
            pointerEvents: 'none',
          }}
        >
          <Upload size={32} style={{ color: 'var(--highlight-color, #eab308)' }} />
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--highlight-color, #eab308)' }}>
            Drop files to add to chat &amp; files
          </div>
          <div style={{ fontSize: 12, color: '#6b7280' }}>
            pdf, doc, docx, xls, xlsx, csv
          </div>
        </div>
      )}

      {/* Attachments bar */}
      <AttachmentList
        fileAttachments={fileAttachments}
        urlAttachments={urlAttachments}
        selectedDocUuids={selectedDocUuids}
        selectedDocNames={selectedDocNames}
        processingByUuid={processingByUuid}
        onRemoveFile={handleRemoveFile}
        onRemoveUrl={handleRemoveUrl}
        onDeselectDoc={(uuid) => {
          setSelectedDocUuids(selectedDocUuids.filter(u => u !== uuid))
          const next = { ...selectedDocNames }
          delete next[uuid]
          setSelectedDocNames(next)
        }}
      />

      {attachLoading && (
        <div className="flex items-center gap-2 border-b border-gray-200 bg-[color-mix(in_srgb,var(--highlight-color),white_90%)] px-4 py-2 text-xs text-highlight">
          <div className="chat-loader" style={{ width: 30 }} />
          Processing document... This may take a moment for PDFs and scanned files.
        </div>
      )}

      {/* Messages area */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto hide-scrollbar"
        style={{ padding: '20px 20px 180px 20px', position: 'relative' }}
      >
        {/* First-session: compact value-prop banner with rotating taglines */}
        {effectiveFirstSession && !onboardingLoading && (
          <div style={{ maxWidth: 640, margin: '0 auto 16px' }}>
            <div
              className="relative overflow-hidden text-white"
              style={{
                padding: '20px 22px',
                borderRadius: 'var(--ui-radius, 12px)',
                background: 'linear-gradient(135deg, var(--highlight-complement, #6a11cb), color-mix(in srgb, var(--highlight-color, #f1b300) 70%, #ffffff 30%))',
              }}
            >
              <div
                style={{
                  position: 'absolute', top: '-50%', left: '-50%',
                  width: '200%', height: '200%',
                  background: 'radial-gradient(circle at center, rgba(255,255,255,0.15), transparent 70%)',
                  animation: 'rotateBG 32s linear infinite',
                }}
              />
              <div className="relative z-[1]">
                <div className="flex items-center gap-4">
                  {brandIcon && (
                    <div style={{ animation: 'float 3s ease-in-out infinite' }} className="shrink-0">
                      <img src={brandIcon} alt={branding.orgName} style={{ width: 22, height: 35, objectFit: 'contain' }} className="opacity-90" />
                    </div>
                  )}
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.3 }}>
                      Welcome to {branding.orgName}
                    </div>
                    <div style={{ fontSize: 13, opacity: 0.8, marginTop: 2, fontWeight: 400 }}>
                      AI-powered document intelligence. Watch it in action below.
                    </div>
                  </div>
                </div>
                <ValueTaglineRotator />
              </div>
            </div>
          </div>
        )}

        {/* Empty state: banner + contextual pills (non-first-session users) */}
        {!effectiveFirstSession && messages.length === 0 && !isStreaming && !onboardingLoading && (
          <div style={{ maxWidth: 640, margin: '0 auto' }}>
            <div
              className="relative overflow-hidden text-white"
              style={{
                padding: '28px 24px',
                borderRadius: 'var(--ui-radius, 12px)',
                background: 'linear-gradient(135deg, var(--highlight-complement, #6a11cb), color-mix(in srgb, var(--highlight-color, #f1b300) 70%, #ffffff 30%))',
                transition: 'filter 0.3s ease',
              }}
            >
              <div
                style={{
                  position: 'absolute', top: '-50%', left: '-50%',
                  width: '200%', height: '200%',
                  background: 'radial-gradient(circle at center, rgba(255,255,255,0.15), transparent 70%)',
                  animation: 'rotateBG 32s linear infinite',
                }}
              />
              <div className="relative z-[1] flex items-center gap-4">
                <div style={{ animation: 'float 3s ease-in-out infinite' }} className="shrink-0">
                  {bannerProcessingDoc ? (
                    <Loader2 className="h-7 w-7 opacity-90 animate-spin" />
                  ) : activeProjectUuid ? (
                    <FolderKanban className="h-7 w-7 opacity-90" />
                  ) : activeKBUuid ? (
                    <BookOpen className="h-7 w-7 opacity-90" />
                  ) : brandIcon ? (
                    <img src={brandIcon} alt={branding.orgName} style={{ width: 22, height: 35, objectFit: 'contain' }} className="opacity-90" />
                  ) : (
                    <Sparkles className="h-7 w-7 opacity-90" />
                  )}
                </div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.3 }}>
                    {bannerProcessingDoc
                      ? processingCount > 1
                        ? `Preparing ${processingCount} documents…`
                        : stageCopy(bannerProcessingDoc.status).title
                      : activeProjectUuid
                        ? `Chat with ${activeProjectTitle ?? 'this project'}`
                        : activeKBUuid
                          ? `Knowledge Base: ${activeKBTitle}`
                          : hasDocContext
                            ? 'Documents ready for analysis'
                            : onboardingStatus?.maturity_stage && onboardingStatus.maturity_stage !== 'newcomer'
                              ? 'Welcome back'
                              : 'What would you like to work on?'}
                  </div>
                  <div style={{ fontSize: 13, opacity: 0.8, marginTop: 2, fontWeight: 400 }}>
                    {bannerProcessingDoc
                      ? processingCount > 1
                        ? "We'll be ready as soon as each document finishes processing."
                        : stageCopy(bannerProcessingDoc.status).message
                      : activeProjectUuid
                        ? projectEmpty
                          ? 'No files in this project yet. Add files in the Files tab and I’ll answer from them. You can still ask me anything.'
                          : projectIndexing
                            ? 'Indexing this project’s files. You can chat now; answers get better as indexing finishes.'
                            : `Ask questions across every file in this project (${projectFileCount} ${projectFileCount === 1 ? 'file' : 'files'}).`
                        : activeKBUuid
                          ? 'Ask questions grounded in your indexed documents and sources.'
                          : hasDocContext
                            ? 'Summarize, extract data, compare, or ask anything about your selected documents.'
                            : (onboardingStatus?.recent_activity?.length ?? 0) > 0
                              ? 'Here\'s what\'s been happening in your workspace.'
                              : 'Select documents to analyze, activate a knowledge base, or ask me anything.'}
                  </div>
                </div>
              </div>
              {bannerProcessingDoc && (
                <div className="relative z-[1]" style={{ marginTop: 16, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.2)', overflow: 'hidden' }}>
                  <div
                    className="animate-pulse"
                    style={{
                      height: '100%', borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.7)',
                      width: `${Math.round(stageCopy(bannerProcessingDoc.status).progress * 100)}%`,
                      transition: 'width 0.5s ease',
                    }}
                  />
                </div>
              )}
            </div>

            {/* Workspace briefing for returning users with data, guidance, or post-demo state */}
            {((onboardingStatus?.recent_activity?.length ?? 0) > 0 || onboardingStatus?.daily_guidance || onboardingStatus?.has_only_onboarding_docs) && (
              <div style={{ marginTop: 12 }}>
                <WorkspaceBriefing
                  recentActivity={onboardingStatus!.recent_activity}
                  activeAlerts={onboardingStatus!.active_alerts ?? []}
                  maturityStage={onboardingStatus!.maturity_stage ?? 'newcomer'}
                  unprocessedDocCount={onboardingStatus!.unprocessed_doc_count ?? 0}
                  dailyGuidance={onboardingStatus!.daily_guidance}
                  sinceLastVisit={onboardingStatus!.since_last_visit}
                  hasOnlyOnboardingDocs={onboardingStatus!.has_only_onboarding_docs}
                  onSendMessage={(msg) => handleSend(msg)}
                />
              </div>
            )}

            <div style={{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {/* Inside a project, surface project-specific actions (run pinned
                  tools, summarize, gaps) instead of generic onboarding/demo. */}
              {activeProjectUuid && (
                <ProjectSuggestedActions
                  projectUuid={activeProjectUuid}
                  role={activeProjectRole}
                  disabled={!!bannerProcessingDoc}
                  onSend={(msg) => handleSend(msg)}
                />
              )}
              {/* Demo pill — hidden once user reaches practitioner stage or has deeply engaged */}
              {!activeProjectUuid && !(onboardingStatus?.has_run_workflow || onboardingStatus?.is_certified || (onboardingStatus?.has_extraction_sets && onboardingStatus?.has_workflows) || (onboardingStatus?.maturity_stage && ['practitioner', 'builder', 'architect'].includes(onboardingStatus.maturity_stage))) && (
              <button
                disabled={!!processingDoc}
                onClick={handleRunDemo}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '8px 14px',
                  fontSize: 13,
                  fontWeight: 500,
                  fontFamily: 'inherit',
                  border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 40%, #e5e7eb)',
                  borderRadius: 20,
                  backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 6%, white)',
                  color: '#374151',
                  cursor: processingDoc ? 'default' : 'pointer',
                  transition: 'all 0.15s',
                  opacity: processingDoc ? 0.5 : 1,
                }}
                onMouseEnter={e => {
                  if (processingDoc) return
                  e.currentTarget.style.borderColor = 'var(--highlight-color, #eab308)'
                  e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 12%, white)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 40%, #e5e7eb)'
                  e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 6%, white)'
                }}
              >
                <Zap size={13} style={{ color: 'var(--highlight-color, #eab308)' }} />
                Show me what you can do
              </button>
              )}
              {/* Contextual suggestion pills (suppressed inside a project — the
                  project actions above take their place) */}
              {!activeProjectUuid && (activeKBUuid ? [
                'Summarize the key points across all sources',
                'What are the most important facts and figures?',
                'List every topic covered',
              ] : hasDocContext ? [
                'Summarize this in 5 bullet points',
                ...(onboardingStatus?.top_extraction_set_name
                  ? [`Run ${onboardingStatus.top_extraction_set_name} on selected documents`]
                  : ['Extract all names, dates, and numbers']),
                ...(onboardingStatus?.top_workflow_name
                  ? [`Run ${onboardingStatus.top_workflow_name} on selected documents`]
                  : ['List every action item and deadline']),
              ] : onboardingPills).map(suggestion => (
                <button
                  key={suggestion}
                  disabled={!!bannerProcessingDoc}
                  onClick={() => {
                    // Server-generated action pills don't need onboarding context injection —
                    // the workspace inventory in the system prompt provides the context.
                    const hasServerPills = (onboardingStatus?.suggestion_pills?.length ?? 0) > 0
                    const needsOnboardingContext = !activeKBUuid && !hasDocContext && !hasServerPills
                    handleSend(suggestion, needsOnboardingContext)
                  }}
                  style={{
                    padding: '8px 14px',
                    fontSize: 13,
                    fontWeight: 500,
                    fontFamily: 'inherit',
                    border: '1px solid #e5e7eb',
                    borderRadius: 20,
                    backgroundColor: '#fff',
                    color: '#374151',
                    cursor: bannerProcessingDoc ? 'default' : 'pointer',
                    transition: 'all 0.15s',
                    opacity: bannerProcessingDoc ? 0.5 : 1,
                  }}
                  onMouseEnter={e => {
                    if (bannerProcessingDoc) return
                    e.currentTarget.style.borderColor = 'var(--highlight-color, #eab308)'
                    e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, white)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.borderColor = '#e5e7eb'
                    e.currentTarget.style.backgroundColor = '#fff'
                  }}
                >
                  {suggestion}
                </button>
              ))}
            </div>

            {/* Concept glossary — teach the core nouns on the generic "ask me
                anything" surface, where a user new to the platform's vocabulary
                lands. Suppressed once they're working in a doc/KB/project. */}
            {!activeProjectUuid && !activeKBUuid && !hasDocContext && (
              <div style={{ marginTop: 16 }}>
                <ConceptStrip />
              </div>
            )}

            {/* Getting-started stepper for returning users who haven't finished basics */}
            {onboardingStatus && (
              <div style={{ marginTop: 12 }}>
                <OnboardingStepper
                  status={onboardingStatus}
                  hasChatAboutDocs={onboardingStatus.has_chatted_with_docs}
                />
              </div>
            )}
          </div>
        )}

        {/* Chat messages — centered column for readability */}
        <div style={{ maxWidth: 640, margin: '0 auto' }}>
          {messages.map((msg, i) => {
            const isExcluded = contextMode !== 'full' && contextCutoffIndex > 0 && i < contextCutoffIndex
            const showBoundary = contextMode !== 'full' && contextCutoffIndex > 0 && i === contextCutoffIndex
            return (
              <div key={i}>
                {showBoundary && (
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    margin: '12px 0',
                    fontSize: 11,
                    color: '#9ca3af',
                    userSelect: 'none',
                  }}>
                    <div style={{ flex: 1, height: 1, background: '#e5e7eb' }} />
                    <span>{contextMode === 'compacted' ? 'Context compacted above' : 'Context starts here'}</span>
                    <div style={{ flex: 1, height: 1, background: '#e5e7eb' }} />
                  </div>
                )}
                <div style={isExcluded ? { opacity: 0.5 } : undefined}>
                  <ChatMessage
                    message={msg}
                    messageIndex={i}
                    conversationUuid={conversationUuid || undefined}
                    onSendMessage={msg.role === 'assistant' && i === messages.length - 1 && !isStreaming ? (m) => handleSend(m) : undefined}
                  />
                </div>
              </div>
            )
          })}

        {/* Streaming: thinking-only phase (no text or tools yet) */}
        {isStreaming && thinkingContent && !streamingContent && segments.length === 0 && (
          <ChatMessage
            message={{ role: 'assistant', content: '' }}
            streamingThinking={thinkingContent}
            activeToolCalls={activeToolCalls}
            toolResults={toolResults}
            streamSegments={segments}
            isStreaming
          />
        )}

        {/* Streaming: segments have started (text and/or tools) */}
        {isStreaming && segments.length > 0 && (
          <ChatMessage
            message={{ role: 'assistant', content: streamingContent }}
            streamingThinking={thinkingContent || undefined}
            thinkingDuration={thinkingDuration}
            activeToolCalls={activeToolCalls}
            toolResults={toolResults}
            streamSegments={segments}
            isStreaming
          />
        )}

        {/* Loading indicator */}
        {isStreaming && !streamingContent && !thinkingContent && activeToolCalls.length === 0 && toolResults.length === 0 && segments.length === 0 && (
          <div style={{ padding: 15, marginBottom: 15, backgroundColor: '#00000008', borderRadius: 'var(--ui-radius, 12px)' }}>
            <div className="thinking-shimmer" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#9ca3af' }}>
              <ChevronRight size={14} />
              <StreamingLabel />
            </div>
          </div>
        )}

        {/* Held message: queued while attached docs finish processing. Renders
            as the user's bubble with a waiting note; auto-sends when ready. */}
        {heldMessage && !isStreaming && (() => {
          const names = selectedDocUuids
            .filter(u => processingByUuid[u])
            .map(u => selectedDocNames[u] || 'document')
          const joined = names.slice(0, 2).join(', ') + (names.length > 2 ? `, +${names.length - 2}` : '')
          return (
            <div style={{
              padding: 15, marginBottom: 10, color: 'white', backgroundColor: '#191919',
              borderLeft: '7px solid var(--highlight-color, #f1b300)', borderRadius: 'var(--ui-radius, 12px)',
              opacity: 0.85,
            }}>
              <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">{heldMessage.message}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, fontSize: 12, color: '#d1d5db' }}>
                <Loader2 size={13} className="animate-spin" style={{ color: 'var(--highlight-color, #f1b300)' }} />
                <span style={{ flex: 1 }}>Waiting for {joined || 'your file'} to finish processing…</span>
                <button
                  onClick={() => setHeldMessage(null)}
                  className="rounded px-2 py-0.5 text-xs text-gray-300 hover:text-white"
                  style={{ border: '1px solid #4b5563', background: 'transparent' }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )
        })()}

        {error && (
          <div className="mt-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 border border-red-200">
            <div className="flex items-start gap-2">
              <div className="flex-1">{error}</div>
              <button
                onClick={clearError}
                aria-label="Dismiss error"
                className="flex shrink-0 items-center justify-center rounded p-0.5 text-red-400 hover:text-red-600"
              >
                <X size={14} />
              </button>
            </div>
            {errorDetails?.suggestedAction === 'convert_to_kb' && (errorDetails.oversizeDocuments?.length ?? 0) > 0 ? (
              <div className="mt-2 flex items-center gap-2">
                <button
                  onClick={handleConvertToKB}
                  disabled={convertingToKB}
                  className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {convertingToKB ? (
                    <>
                      <Loader2 size={12} className="animate-spin" />
                      Converting…
                    </>
                  ) : (
                    <>
                      <BookOpen size={12} />
                      Convert to Knowledge Base
                    </>
                  )}
                </button>
                <span className="text-xs text-red-600/80">
                  Builds a searchable index so chat can read the document a chunk at a time.
                </span>
              </div>
            ) : (
              <div className="mt-2">
                <button
                  onClick={retry}
                  className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700"
                >
                  Retry
                </button>
              </div>
            )}
          </div>
        )}

        {showContextNudge && (
          <div className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 border border-amber-200">
            <div className="flex items-start gap-2">
              <div className="flex-1">
                This conversation is getting long and is close to the model's memory limit.
                You can trim or summarize older messages so replies stay sharp.
              </div>
              <button
                onClick={() => setShowContextNudge(false)}
                aria-label="Dismiss"
                className="flex shrink-0 items-center justify-center rounded p-0.5 text-amber-500 hover:text-amber-700"
              >
                <X size={14} />
              </button>
            </div>
            <div className="mt-2">
              <button
                onClick={() => { setShowContextNudge(false); setShowContextDialog(true) }}
                className="inline-flex items-center gap-1.5 rounded-md bg-amber-500 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-600"
              >
                Manage memory
              </button>
            </div>
          </div>
        )}

        {/* Notices are keyed by `action` so a "document still processing"
            warning never wears the "Context was compacted" label. */}
        {(() => {
          const notReady = contextNotices.filter(n => n.action === 'documents_not_ready')
          const failed = contextNotices.filter(n => n.action === 'documents_extraction_failed')
          const compacted = contextNotices.filter(
            n => n.action !== 'documents_not_ready' && n.action !== 'documents_extraction_failed',
          )
          return (
            <>
              {notReady.length > 0 && (
                <div className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 border border-amber-200">
                  <div className="font-medium mb-1">Still processing</div>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {notReady.map((n, i) => <li key={i}>{n.detail}</li>)}
                  </ul>
                  <div className="mt-2">
                    <button
                      onClick={retry}
                      className="inline-flex items-center gap-1.5 rounded-md bg-amber-500 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-600"
                    >
                      Resend now
                    </button>
                  </div>
                </div>
              )}
              {failed.length > 0 && (
                <div className="mt-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 border border-red-200">
                  <div className="font-medium mb-1">Couldn't read these files</div>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {failed.map((n, i) => <li key={i}>{n.detail}</li>)}
                  </ul>
                  <div className="mt-2 text-red-600/80">
                    This usually means the file is scanned/image-only, password-protected,
                    or in an unsupported format. Try re-saving it as a text-based PDF or
                    DOCX and re-uploading from the Files tab — or paste the relevant text
                    here directly.
                  </div>
                </div>
              )}
              {compacted.length > 0 && (
                <div className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 border border-amber-200">
                  <div className="font-medium mb-1">Context was compacted to fit the model:</div>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {compacted.map((n, i) => <li key={i}>{n.detail}</li>)}
                  </ul>
                </div>
              )}
            </>
          )
        })()}
        </div>{/* end centering wrapper */}

      </div>

      {/* Scroll to bottom button */}
      {showScrollDown && (
        <div style={{ display: 'flex', justifyContent: 'center', position: 'relative' }}>
          <button
            onClick={scrollToBottom}
            style={{
              position: 'absolute',
              bottom: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 36,
              height: 36,
              borderRadius: '50%',
              border: '1px solid #d1d5db',
              backgroundColor: '#fff',
              color: '#374151',
              cursor: 'pointer',
              boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
              zIndex: 10,
              transition: 'background-color 0.15s, box-shadow 0.15s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.backgroundColor = '#f3f4f6'
              e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.18)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.backgroundColor = '#fff'
              e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.12)'
            }}
            aria-label="Scroll to bottom"
          >
            <ArrowDown size={18} />
          </button>
        </div>
      )}



      {/* Project active badge — entering a project clears the KB, so normally
          only one of these shows; render project-first for deterministic order. */}
      {activeProjectUuid && (
        <ProjectChatBadge
          projectUuid={activeProjectUuid}
          fallbackTitle={activeProjectTitle}
          onExit={deactivateProject}
        />
      )}

      {/* KB active badge */}
      {activeKBUuid && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 16px',
            fontSize: 12,
            fontWeight: 600,
            color: 'var(--highlight-color, #eab308)',
            backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 10%, white)',
            borderTop: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 30%, white)',
          }}
        >
          <BookOpen size={14} />
          <span style={{ flex: 1 }}>Knowledge Base: {activeKBTitle}</span>
          <button
            onClick={() => shareLink('kb', activeKBUuid, activeKBTitle || undefined)}
            title="Copy share link"
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: 2,
              display: 'flex',
              color: 'inherit',
              opacity: 0.7,
            }}
          >
            <Link2 size={14} />
          </button>
          <button
            onClick={deactivateKB}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: 2,
              display: 'flex',
              color: 'inherit',
              opacity: 0.7,
            }}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        onAttachFile={handleAttachFile}
        onAttachLink={handleAttachLink}
        disabled={isStreaming}
        isStreaming={isStreaming}
        onStop={stop}
        selectedModel={selectedModel}
        onModelChange={handleModelChange}
        onExport={handleExport}
        hasMessages={messages.length > 0}
        hasDocuments={fileAttachments.length > 0 || urlAttachments.length > 0 || selectedDocUuids.length > 0 || selectedFolderUuids.length > 0}
        memoryControl={<MemoryPanel />}
        focusSignal={focusChatSignal}
        contextMeter={
          messages.length > 0 && contextTokens > 0 ? (
            <ContextMeter
              tokensUsed={contextTokens}
              contextWindow={contextWindow}
              onClick={() => setShowContextDialog(true)}
            />
          ) : null
        }
      />

      {/* Context limit dialog */}
      <ContextLimitDialog
        open={showContextDialog}
        onClose={() => setShowContextDialog(false)}
        onTruncate={handleTruncate}
        onCompact={handleCompact}
        onClear={handleClearContext}
        percent={contextWindow > 0 ? Math.round((contextTokens / contextWindow) * 100) : 0}
      />
    </div>
  )
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      resolve(result.split(',')[1])
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}
