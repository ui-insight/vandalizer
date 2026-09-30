import { usePanelEffect } from '../shared/usePanelEffect'
import { X, Layers, Search, BookOpen, Sparkles, type LucideIcon } from 'lucide-react'
import { KnowledgeTutorial } from './KnowledgeTutorial'

export function KnowledgeExplainer({ onClose }: { onClose?: () => void }) {
  usePanelEffect(() => {
    if (!onClose) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <>
      <style>{`
        @keyframes kbExplainerFadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes kbExplainerScaleIn {
          from { opacity: 0; transform: translateY(16px) scale(0.985); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes kbExplainerSectionIn {
          from { opacity: 0; transform: translateY(14px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes kbExplainerGlow {
          0%, 100% { opacity: 0.45; }
          50% { opacity: 0.85; }
        }
        .kb-explainer-root { animation: kbExplainerFadeIn 220ms ease-out; }
        .kb-explainer-content { animation: kbExplainerScaleIn 420ms cubic-bezier(0.2, 0.8, 0.2, 1); }
        .kb-explainer-section { opacity: 0; animation: kbExplainerSectionIn 520ms cubic-bezier(0.2, 0.8, 0.2, 1) forwards; }
        .kb-explainer-glow { animation: kbExplainerGlow 4s ease-in-out infinite; }
      `}</style>

      <div
        className="kb-explainer-root"
        tabIndex={0}
        style={{
          // As a modal (onClose set) it must sit above the panel header/search
          // chrome (zIndex 300), or that header bleeds through over the top.
          // As an inline empty-state it stays in flow below the header.
          position: 'absolute', inset: 0, zIndex: onClose ? 400 : 50,
          background: 'var(--workspace-canvas)',
          overflowY: 'auto',
        }}
      >
        {/* Close button */}
        {onClose && (
          <button
            onClick={onClose}
            style={{
              position: 'absolute', top: 14, right: 14, zIndex: 10,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 32, height: 32, borderRadius: 'var(--workspace-radius-medium)',
              background: 'var(--workspace-canvas)',
              border: '1px solid var(--workspace-border)',
              color: 'var(--workspace-muted)', cursor: 'pointer',
            }}
            aria-label="Close"
          >
            <X size={16} />
          </button>
        )}

        <div className="kb-explainer-content" style={{ padding: "48px var(--workspace-space-32) 56px", maxWidth: 720, margin: '0 auto', position: 'relative' }}>
          {/* Hero */}
          <div className="kb-explainer-section" style={{ animationDelay: '60ms', textAlign: 'center', marginBottom: 28 }}>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-6)', padding: "var(--workspace-space-6) var(--workspace-space-16)",
              borderRadius: 999,
              background: 'rgba(96, 165, 250, 0.12)',
              border: '1px solid rgba(96, 165, 250, 0.3)',
              fontSize: 'var(--workspace-font-meta)', fontWeight: 700, color: 'var(--workspace-info)',
              textTransform: 'uppercase', letterSpacing: '0.1em',
              marginBottom: 'var(--workspace-space-20)',
            }}>
              <Sparkles size={12} /> Knowledge Bases
            </div>
            <h1 style={{
              fontSize: 34, fontWeight: 700, color: 'var(--workspace-text)', letterSpacing: '-0.025em',
              lineHeight: 1.1, margin: "0 0 var(--workspace-space-16)",
            }}>
              Ask anything.<br />Get answers from your sources.
            </h1>
            <p style={{
              fontSize: 'var(--workspace-font-card-title)', color: 'var(--workspace-muted)', maxWidth: 500, margin: '0 auto', lineHeight: 1.6,
            }}>
              A knowledge base turns a folder of documents, a stack of policies, or a website
              into something you can talk to, with citations back to the exact source.
            </p>
          </div>

          {/* Animation */}
          <div className="kb-explainer-section" style={{ animationDelay: '180ms', marginBottom: 44 }}>
            <KnowledgeTutorial />
          </div>

          {/* What they do */}
          <Section title="What they do for you" delay="280ms">
            <Card
              icon={Layers}
              title="Index"
              body="Pull text out of your documents, websites, and uploads, and split it into searchable chunks."
            />
            <Card
              icon={Search}
              title="Search"
              body="Find the passages most relevant to any question, even when the wording doesn't match."
            />
            <Card
              icon={BookOpen}
              title="Cite"
              body="Every answer points back to the exact document and page it came from. No black boxes."
            />
          </Section>

          {/* Research admin examples */}
          <Section
            title="Built for research administration"
            subtitle="Patterns we see across grants, contracts, and compliance offices."
            delay="380ms"
          >
            <UseCase
              accent="var(--workspace-info)"
              question="Is salary cap waivable on a K award?"
              answer="Federal regulations KB returns the answer with a citation to 2 CFR §200.305 and the relevant NIH NOT-OD notice."
            />
            <UseCase
              accent="var(--workspace-info)"
              question="What's the F&A rate cap for the Gates Foundation?"
              answer="Sponsor policies KB pulls the matching clause from 200+ indexed funder pages, with the source URL."
            />
            <UseCase
              accent="var(--workspace-success)"
              question="What's our process for closing out a fixed-price subaward?"
              answer="Internal SOPs KB answers from your office's playbook so new staff stop opening tickets for the same questions."
            />
            <UseCase
              accent="#f472b6"
              question="What did we tell DCAA about Q3 indirect costs?"
              answer="Audit response KB surfaces the exact correspondence and exhibits, searchable months after the fact."
            />
          </Section>

          {/* How to use */}
          <Section title="How you'd build one" delay="480ms">
            <Step num="1" title="Create a knowledge base" body="Name it after the question you want answered (e.g. 'NIH grant policies')." />
            <Step num="2" title="Add sources" body="Pick documents from your library, paste URLs, or point it at a website to crawl." />
            <Step num="3" title="Wait for it to build" body="Sources are chunked and indexed in the background. Status updates live." />
            <Step num="4" title="Open chat and ask" body="Ask in plain English. You'll get answers with citations to the source documents." />
          </Section>

          {/* CTA */}
          {onClose && (
            <div className="kb-explainer-section" style={{ animationDelay: '580ms', textAlign: 'center', marginTop: 36 }}>
              <button
                onClick={onClose}
                style={{
                  padding: '11px 26px', fontSize: 'var(--workspace-font-body)', fontWeight: 600,
                  color: '#0c1020',
                  background: 'var(--workspace-canvas)',
                  border: 'none', borderRadius: 'var(--workspace-radius-large)', cursor: 'pointer', fontFamily: 'inherit',
                  boxShadow: '0 6px 20px -6px rgba(96, 165, 250, 0.5)',
                }}
              >
                Got it, back to the knowledge base
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

function Section({
  title, subtitle, delay, children,
}: {
  title: string; subtitle?: string; delay: string; children: React.ReactNode
}) {
  return (
    <div className="kb-explainer-section" style={{ animationDelay: delay, marginBottom: 36 }}>
      <h2 style={{
        fontSize: 'var(--workspace-font-page-title)', fontWeight: 700, color: 'var(--workspace-text)', margin: "0 0 var(--workspace-space-4)",
        letterSpacing: '-0.01em',
      }}>
        {title}
      </h2>
      {subtitle && (
        <p style={{ fontSize: 'var(--workspace-font-control)', color: '#aeb7c9', margin: "0 0 var(--workspace-space-16)" }}>{subtitle}</p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-12)', marginTop: subtitle ? 0 : 14 }}>
        {children}
      </div>
    </div>
  )
}

function Card({ icon: Icon, title, body }: { icon: LucideIcon; title: string; body: string }) {
  return (
    <div style={{
      display: 'flex', gap: 'var(--workspace-space-16)', alignItems: 'flex-start',
      padding: 'var(--workspace-space-16)', borderRadius: 'var(--workspace-radius-large)',
      background: 'var(--workspace-canvas)',
      border: '1px solid var(--workspace-border)',
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 'var(--workspace-radius-large)',
        background: 'rgba(96, 165, 250, 0.12)',
        border: '1px solid rgba(96, 165, 250, 0.28)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <Icon size={18} style={{ color: 'var(--workspace-info)' }} />
      </div>
      <div>
        <div style={{ fontSize: 'var(--workspace-font-body)', fontWeight: 600, color: 'var(--workspace-text)', marginBottom: 'var(--workspace-space-4)' }}>
          {title}
        </div>
        <div style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-muted)', lineHeight: 1.55 }}>{body}</div>
      </div>
    </div>
  )
}

function UseCase({ question, answer, accent }: { question: string; answer: string; accent: string }) {
  return (
    <div style={{
      padding: 'var(--workspace-space-16)', borderRadius: 'var(--workspace-radius-large)',
      background: 'var(--workspace-canvas)',
      border: '1px solid var(--workspace-border)',
      borderLeft: `3px solid ${accent}`,
    }}>
      <div style={{
        display: 'inline-block', padding: "var(--workspace-space-2) var(--workspace-space-8)", borderRadius: 'var(--workspace-radius-small)',
        background: `color-mix(in srgb, ${accent} 13.33%, transparent)`, color: accent,
        fontSize: 'var(--workspace-font-meta)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em',
        marginBottom: 'var(--workspace-space-8)',
      }}>
        Ask
      </div>
      <div style={{ fontSize: 'var(--workspace-font-body)', fontWeight: 600, color: 'var(--workspace-text)', marginBottom: 'var(--workspace-space-8)', lineHeight: 1.45, fontStyle: 'italic' }}>
        "{question}"
      </div>
      <div style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-muted)', lineHeight: 1.55 }}>
        <span style={{ color: accent, fontWeight: 600 }}>→ </span>{answer}
      </div>
    </div>
  )
}

function Step({ num, title, body }: { num: string; title: string; body: string }) {
  return (
    <div style={{
      display: 'flex', gap: 'var(--workspace-space-16)', alignItems: 'flex-start',
      padding: 'var(--workspace-space-16)', borderRadius: 'var(--workspace-radius-large)',
      background: 'var(--workspace-canvas)',
      border: '1px solid var(--workspace-border)',
    }}>
      <div style={{
        width: 28, height: 28, borderRadius: '50%',
        background: 'var(--workspace-canvas)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        fontSize: 'var(--workspace-font-control)', fontWeight: 700, color: '#0c1020',
        boxShadow: '0 2px 10px -2px rgba(96, 165, 250, 0.4)',
      }}>
        {num}
      </div>
      <div>
        <div style={{ fontSize: 'var(--workspace-font-body)', fontWeight: 600, color: 'var(--workspace-text)', marginBottom: 'var(--workspace-space-2)' }}>
          {title}
        </div>
        <div style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-muted)', lineHeight: 1.55 }}>{body}</div>
      </div>
    </div>
  )
}
