import { useEffect, useRef, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { Sparkles, X } from 'lucide-react'

interface Props {
  onConfirm: (coverage: 'quick' | 'standard' | 'exhaustive') => void
  onClose: () => void
}
const OPTIONS = [
  { id: 'quick', label: 'Quick', count: 5, cost: '~10 model calls' },
  { id: 'standard', label: 'Standard', count: 10, cost: '~20 model calls' },
  { id: 'exhaustive', label: 'Exhaustive', count: 25, cost: '~50 model calls' },
] as const

export function GenerateTestQueriesModal({ onConfirm, onClose }: Props) {
  const [choice, setChoice] = useState<'quick' | 'standard' | 'exhaustive'>('standard')
  const submitted = useRef(false)
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.stopPropagation(); onClose() } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div style={{ position:'fixed', inset:0, backgroundColor:'rgba(0,0,0,0.6)', display:'flex', alignItems:'center', justifyContent:'center', zIndex:1000, padding:12 }}>
      <FocusTrap focusTrapOptions={{ initialFocus:'#generate-coverage-standard', escapeDeactivates:false, tabbableOptions:{displayCheck:import.meta.env.MODE === 'test' ? 'none' : 'full'} }}>
        <div role="dialog" aria-modal="true" aria-label="Auto-generate test queries" style={{ width:440, maxWidth:'100%', maxHeight:'calc(100dvh - 24px)', display:'flex', flexDirection:'column', overflow:'hidden', backgroundColor:'#1f1f1f', border:'1px solid #444', borderRadius:10, color:'#e5e7eb', fontSize:14 }}>
          <header style={{ display:'flex', alignItems:'center', gap:8, padding:'12px 16px', flexShrink:0, borderBottom:'1px solid #444' }}>
            <Sparkles size={18} aria-hidden="true" style={{flexShrink:0}} />
            <h3 style={{margin:0,fontSize:18,color:'#fff'}}>Auto-generate test queries</h3>
            <button type="button" aria-label="Close" onClick={onClose} style={{marginLeft:'auto',flexShrink:0,display:'grid',placeItems:'center',width:36,height:36,background:'transparent',border:0,cursor:'pointer',color:'#d1d5db'}}><X size={20} aria-hidden="true" /></button>
          </header>
          <div style={{minHeight:0,overflowY:'auto',padding:16,lineHeight:1.5}}>
            <p style={{margin:'0 0 16px'}}>Create draft questions from your indexed sources. Review the expected answers before using them to check answer quality.</p>
            <fieldset style={{border:0,padding:0,margin:0,minWidth:0}}>
              <legend style={{fontWeight:600,marginBottom:8}}>Question coverage</legend>
              {OPTIONS.map(option => <label key={option.id} htmlFor={`generate-coverage-${option.id}`} style={{display:'flex',alignItems:'center',gap:10,padding:12,marginBottom:8,borderRadius:6,background:'#262626',border:`1px solid ${choice===option.id ? 'var(--highlight-color, #eab308)' : '#555'}`,cursor:'pointer'}}>
                <input id={`generate-coverage-${option.id}`} type="radio" name="question-coverage" value={option.id} checked={choice===option.id} onChange={()=>setChoice(option.id)} style={{accentColor:'var(--highlight-color, #eab308)',flexShrink:0}} />
                <span style={{minWidth:0,flex:1}}><strong>{option.label}</strong><span style={{display:'block',fontSize:12,color:'#d1d5db'}}>Up to {option.count} questions</span></span>
                <span style={{fontSize:12,color:'#d1d5db',maxWidth:90}}>{option.cost}</span>
              </label>)}
            </fieldset>
            <p style={{fontSize:12,color:'#d1d5db'}}>Estimates; actual model usage may vary.</p>
            <details style={{fontSize:12,color:'#d1d5db',marginTop:12}}>
              <summary style={{cursor:'pointer',padding:'8px 0'}}>How question IDs work</summary>
              <p>Each question gets an expected answer, category, source, notes and a stable ID. Generating again creates new IDs; imported IDs are kept as provided.</p>
            </details>
          </div>
          <footer style={{display:'flex',justifyContent:'flex-end',flexWrap:'wrap',gap:8,padding:'12px 16px',borderTop:'1px solid #444',flexShrink:0}}>
            <button type="button" onClick={onClose} style={{minHeight:36,padding:'6px 14px',fontSize:14,fontFamily:'inherit',color:'#e5e7eb',background:'transparent',border:'1px solid #666',borderRadius:6,cursor:'pointer'}}>Cancel</button>
            <button type="button" onClick={()=>{if(!submitted.current){submitted.current=true;onConfirm(choice)}}} style={{minHeight:36,padding:'6px 14px',fontSize:14,fontWeight:600,fontFamily:'inherit',color:'var(--highlight-text-color, #000)',background:'var(--highlight-color, #eab308)',border:0,borderRadius:6,cursor:'pointer'}}>Generate</button>
          </footer>
        </div>
      </FocusTrap>
    </div>
  )
}
