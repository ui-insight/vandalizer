import { useEffect } from 'react'
import { X, FolderSearch, Zap, FileCheck, Sparkles, type LucideIcon } from 'lucide-react'
import { AutomationsTutorial } from './AutomationsTutorial'

export function AutomationsExplainer({ onClose }: { onClose: () => void }) {
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
        @keyframes explainerFadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes explainerScaleIn {
          from { opacity: 0; transform: translateY(16px) scale(0.985); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes explainerSectionIn {
          from { opacity: 0; transform: translateY(14px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes explainerGlow {
          0%, 100% { opacity: 0.45; }
          50% { opacity: 0.85; }
        }
        .explainer-root { animation: explainerFadeIn 220ms ease-out; }
        .explainer-content { animation: explainerScaleIn 420ms cubic-bezier(0.2, 0.8, 0.2, 1); }
        .explainer-section { opacity: 0; animation: explainerSectionIn 520ms cubic-bezier(0.2, 0.8, 0.2, 1) forwards; }
        .explainer-glow { animation: explainerGlow 4s ease-in-out infinite; }
      `}</style>

      <div
        className="explainer-root"
        style={{
          position: 'absolute', inset: 0, zIndex: 50,
          background: 'radial-gradient(ellipse at top, #232a3d 0%, #141826 55%, #0d111c 100%)',
          overflowY: 'auto',
        }}
      >
        {/* Ambient glow */}
        <div
          className="explainer-glow"
          style={{
            position: 'absolute', top: -120, left: '50%', transform: 'translateX(-50%)',
            width: 520, height: 520, borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(234, 179, 8, 0.15) 0%, transparent 65%)',
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

        <div className="explainer-content" style={{ padding: '48px 32px 56px', maxWidth: 720, margin: '0 auto', position: 'relative' }}>
          {/* Hero */}
          <div className="explainer-section" style={{ animationDelay: '60ms', textAlign: 'center', marginBottom: 28 }}>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 14px',
              borderRadius: 999,
              background: 'rgba(234, 179, 8, 0.12)',
              border: '1px solid rgba(234, 179, 8, 0.3)',
              fontSize: 11, fontWeight: 700, color: '#fbbf24',
              textTransform: 'uppercase', letterSpacing: '0.1em',
              marginBottom: 18,
            }}>
              <Sparkles size={12} /> Automations
            </div>
            <h1 style={{
              fontSize: 34, fontWeight: 700, color: '#fff', letterSpacing: '-0.025em',
              lineHeight: 1.1, margin: '0 0 14px',
            }}>
              Work that runs<br />while you don't have to.
            </h1>
            <p style={{
              fontSize: 15, color: '#9aa3b8', maxWidth: 500, margin: '0 auto', lineHeight: 1.6,
            }}>
              Automations watch for new files, run the right workflow on them, and put the
              results wherever you need. Set one up once — then forget it exists.
            </p>
          </div>

          {/* Animation */}
          <div className="explainer-section" style={{ animationDelay: '180ms', marginBottom: 44 }}>
            <AutomationsTutorial />
          </div>

          {/* What they do */}
          <Section title="What they do for you" delay="280ms">
            <Card
              icon={FolderSearch}
              title="Watch"
              body="Monitor a folder, an inbox, or an API endpoint for new documents."
            />
            <Card
              icon={Zap}
              title="Trigger"
              body="The moment a file arrives, run an extraction, workflow, or task on it."
            />
            <Card
              icon={FileCheck}
              title="Deliver"
              body="Save the results to a folder, email your team, or push them to downstream systems."
            />
          </Section>

          {/* Research admin examples */}
          <Section
            title="Built for research administration"
            subtitle="Patterns we see across grants, contracts, and compliance offices."
            delay="380ms"
          >
            <UseCase
              accent="#f59e0b"
              trigger="New NIH award letter lands in /Awards/2026"
              action="Extract sponsor terms, period dates, and budget — route a summary to compliance and the PI."
            />
            <UseCase
              accent="#3b82f6"
              trigger="Contract uploaded to /Legal/Subawards"
              action="Pull obligation amounts, key dates, and termination clauses. Email the findings to the pre-award analyst."
            />
            <UseCase
              accent="#8b5cf6"
              trigger="IRB protocol submitted via API"
              action="Validate required sections, flag missing approvals, and create a coordinator checklist."
            />
            <UseCase
              accent="#10b981"
              trigger="Cost-share commitment letter received"
              action="Extract committed amounts and matching periods, append a row to the cost-share log."
            />
          </Section>

          {/* How to use */}
          <Section title="How you'd set one up" delay="480ms">
            <Step num="1" title="Pick a trigger" body="Watch a folder, expose an API endpoint, or connect an M365 inbox." />
            <Step num="2" title="Pick what to run" body="Choose a workflow, an extraction template, or a single task." />
            <Step num="3" title="Choose where results go" body="Save to a folder, email a recipient list, or both." />
            <Step num="4" title="Enable it" body="That's the whole job. Files arrive, work happens, results land where you need them." />
          </Section>

          {/* CTA */}
          <div className="explainer-section" style={{ animationDelay: '580ms', textAlign: 'center', marginTop: 36 }}>
            <button
              onClick={onClose}
              style={{
                padding: '11px 26px', fontSize: 14, fontWeight: 600,
                color: '#1a1f2e',
                background: 'linear-gradient(135deg, #fbbf24 0%, #eab308 100%)',
                border: 'none', borderRadius: 10, cursor: 'pointer', fontFamily: 'inherit',
                boxShadow: '0 6px 20px -6px rgba(234, 179, 8, 0.5)',
              }}
            >
              Got it — back to the automation
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
    <div className="explainer-section" style={{ animationDelay: delay, marginBottom: 36 }}>
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
        background: 'rgba(234, 179, 8, 0.12)',
        border: '1px solid rgba(234, 179, 8, 0.28)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <Icon size={18} style={{ color: '#fbbf24' }} />
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

function UseCase({ trigger, action, accent }: { trigger: string; action: string; accent: string }) {
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
        When
      </div>
      <div style={{ fontSize: 13.5, fontWeight: 600, color: '#e5e7eb', marginBottom: 8, lineHeight: 1.45 }}>
        {trigger}
      </div>
      <div style={{ fontSize: 13, color: '#9aa3b8', lineHeight: 1.55 }}>
        <span style={{ color: accent, fontWeight: 600 }}>→ </span>{action}
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
        background: 'linear-gradient(135deg, #fbbf24 0%, #eab308 100%)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        fontSize: 13, fontWeight: 700, color: '#1a1f2e',
        boxShadow: '0 2px 10px -2px rgba(234, 179, 8, 0.4)',
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
