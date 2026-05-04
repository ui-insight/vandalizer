import { useEffect } from 'react'
import { X, Layers, Search, BookOpen, Sparkles, type LucideIcon } from 'lucide-react'
import { KnowledgeTutorial } from './KnowledgeTutorial'

export function KnowledgeExplainer({ onClose }: { onClose: () => void }) {
  useEffect(() => {
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
        style={{
          position: 'absolute', inset: 0, zIndex: 50,
          background: 'radial-gradient(ellipse at top, #1f2740 0%, #131628 55%, #0c1020 100%)',
          overflowY: 'auto',
        }}
      >
        {/* Ambient glow */}
        <div
          className="kb-explainer-glow"
          style={{
            position: 'absolute', top: -120, left: '50%', transform: 'translateX(-50%)',
            width: 520, height: 520, borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(96, 165, 250, 0.18) 0%, transparent 65%)',
            pointerEvents: 'none',
          }}
        />

        {/* Close button */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: 14, right: 14, zIndex: 10,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 32, height: 32, borderRadius: 8,
            background: 'rgba(255,255,255,0.06)',
            border: '1px solid rgba(255,255,255,0.1)',
            color: '#c0c7d6', cursor: 'pointer',
          }}
          aria-label="Close"
        >
          <X size={16} />
        </button>

        <div className="kb-explainer-content" style={{ padding: '48px 32px 56px', maxWidth: 720, margin: '0 auto', position: 'relative' }}>
          {/* Hero */}
          <div className="kb-explainer-section" style={{ animationDelay: '60ms', textAlign: 'center', marginBottom: 28 }}>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 14px',
              borderRadius: 999,
              background: 'rgba(96, 165, 250, 0.12)',
              border: '1px solid rgba(96, 165, 250, 0.3)',
              fontSize: 11, fontWeight: 700, color: '#93c5fd',
              textTransform: 'uppercase', letterSpacing: '0.1em',
              marginBottom: 18,
            }}>
              <Sparkles size={12} /> Knowledge Bases
            </div>
            <h1 style={{
              fontSize: 34, fontWeight: 700, color: '#fff', letterSpacing: '-0.025em',
              lineHeight: 1.1, margin: '0 0 14px',
            }}>
              Ask anything.<br />Get answers from your sources.
            </h1>
            <p style={{
              fontSize: 15, color: '#9aa3b8', maxWidth: 500, margin: '0 auto', lineHeight: 1.6,
            }}>
              A knowledge base turns a folder of documents, a stack of policies, or a website
              into something you can talk to — with citations back to the exact source.
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
              body="Find the passages most relevant to any question — even when the wording doesn't match."
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
              accent="#60a5fa"
              question="Is salary cap waivable on a K award?"
              answer="Federal regulations KB returns the answer with a citation to 2 CFR §200.305 and the relevant NIH NOT-OD notice."
            />
            <UseCase
              accent="#a78bfa"
              question="What's the F&A rate cap for the Gates Foundation?"
              answer="Sponsor policies KB pulls the matching clause from 200+ indexed funder pages — with the source URL."
            />
            <UseCase
              accent="#34d399"
              question="What's our process for closing out a fixed-price subaward?"
              answer="Internal SOPs KB answers from your office's playbook so new staff stop opening tickets for the same questions."
            />
            <UseCase
              accent="#f472b6"
              question="What did we tell DCAA about Q3 indirect costs?"
              answer="Audit response KB surfaces the exact correspondence and exhibits — searchable months after the fact."
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
          <div className="kb-explainer-section" style={{ animationDelay: '580ms', textAlign: 'center', marginTop: 36 }}>
            <button
              onClick={onClose}
              style={{
                padding: '11px 26px', fontSize: 14, fontWeight: 600,
                color: '#0c1020',
                background: 'linear-gradient(135deg, #93c5fd 0%, #60a5fa 100%)',
                border: 'none', borderRadius: 10, cursor: 'pointer', fontFamily: 'inherit',
                boxShadow: '0 6px 20px -6px rgba(96, 165, 250, 0.5)',
              }}
            >
              Got it — back to the knowledge base
            </button>
          </div>
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
        fontSize: 20, fontWeight: 700, color: '#fff', margin: '0 0 4px',
        letterSpacing: '-0.01em',
      }}>
        {title}
      </h2>
      {subtitle && (
        <p style={{ fontSize: 13, color: '#7a8499', margin: '0 0 14px' }}>{subtitle}</p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: subtitle ? 0 : 14 }}>
        {children}
      </div>
    </div>
  )
}

function Card({ icon: Icon, title, body }: { icon: LucideIcon; title: string; body: string }) {
  return (
    <div style={{
      display: 'flex', gap: 14, alignItems: 'flex-start',
      padding: 16, borderRadius: 12,
      background: 'rgba(255,255,255,0.03)',
      border: '1px solid rgba(255,255,255,0.07)',
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 10,
        background: 'rgba(96, 165, 250, 0.12)',
        border: '1px solid rgba(96, 165, 250, 0.28)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <Icon size={18} style={{ color: '#93c5fd' }} />
      </div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: '#e5e7eb', marginBottom: 4 }}>
          {title}
        </div>
        <div style={{ fontSize: 13, color: '#9aa3b8', lineHeight: 1.55 }}>{body}</div>
      </div>
    </div>
  )
}

function UseCase({ question, answer, accent }: { question: string; answer: string; accent: string }) {
  return (
    <div style={{
      padding: 16, borderRadius: 12,
      background: 'rgba(255,255,255,0.03)',
      border: '1px solid rgba(255,255,255,0.07)',
      borderLeft: `3px solid ${accent}`,
    }}>
      <div style={{
        display: 'inline-block', padding: '2px 8px', borderRadius: 6,
        background: `${accent}22`, color: accent,
        fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em',
        marginBottom: 8,
      }}>
        Ask
      </div>
      <div style={{ fontSize: 13.5, fontWeight: 600, color: '#e5e7eb', marginBottom: 8, lineHeight: 1.45, fontStyle: 'italic' }}>
        "{question}"
      </div>
      <div style={{ fontSize: 13, color: '#9aa3b8', lineHeight: 1.55 }}>
        <span style={{ color: accent, fontWeight: 600 }}>→ </span>{answer}
      </div>
    </div>
  )
}

function Step({ num, title, body }: { num: string; title: string; body: string }) {
  return (
    <div style={{
      display: 'flex', gap: 14, alignItems: 'flex-start',
      padding: 14, borderRadius: 12,
      background: 'rgba(255,255,255,0.03)',
      border: '1px solid rgba(255,255,255,0.07)',
    }}>
      <div style={{
        width: 28, height: 28, borderRadius: '50%',
        background: 'linear-gradient(135deg, #93c5fd 0%, #60a5fa 100%)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        fontSize: 13, fontWeight: 700, color: '#0c1020',
        boxShadow: '0 2px 10px -2px rgba(96, 165, 250, 0.4)',
      }}>
        {num}
      </div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: '#e5e7eb', marginBottom: 2 }}>
          {title}
        </div>
        <div style={{ fontSize: 13, color: '#9aa3b8', lineHeight: 1.55 }}>{body}</div>
      </div>
    </div>
  )
}
