import { createRoot } from 'react-dom/client'
import { ChatPageCard } from '../../src/components/artifacts/ChatPageCard'
import '@fontsource-variable/public-sans'
import '../../src/index.css'

createRoot(document.getElementById('root')!).render(<main style={{ maxWidth: 1000, margin: '30px auto' }}>
  <ChatPageCard title="New award budget" html="<h1>New award budget</h1><p>Personnel $250</p>" previewId="page-preview" needsApproval decision={null} decisionError={null} onDecide={() => {}} revising={false}
    templateCheck={{ filled: 24, missing: 2, retained: 0, source_title: 'New budget.xlsx', template_name: 'Budget dashboard' }} />
</main>)
