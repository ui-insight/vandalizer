import './browser-setup.css'
import { browserSkillTemplate } from '../../lib/browserSkillTemplates'
export function BrowserSkillHelp({ onStart }: { onStart?: (instructions: string) => void }) {
  return <details className="browser-panel my-3 rounded border p-3 text-sm">
    <summary className="cursor-pointer font-medium">Writing a Skill that reads websites</summary>
    <ul className="mt-2 list-disc space-y-1 pl-5">
      <li>Name exact URLs and the field, button and tab labels you see.</li>
      <li>Ask for one <code>record_value</code> per figure, exactly as shown. Use <code>calculate</code> for math.</li>
      <li>Stop at sign-in. Ask the person to use the working tab, then continue. Never ask for passwords.</li>
      <li>The tools refuse to submit or change anything. Only read sites the person allows.</li>
      <li>Finish with a table linking every figure to its source. Mark missing figures “Not found”.</li>
    </ul>
    {onStart && <button type="button" className="mt-2 underline" onClick={() => onStart(browserSkillTemplate().instructions)}>Use “Collect figures from websites” starter</button>}
  </details>
}
