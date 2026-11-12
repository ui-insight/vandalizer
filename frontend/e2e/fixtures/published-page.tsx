import { createRoot } from 'react-dom/client'
import ArtifactPage from '../../src/pages/Artifacts'
import '../../src/index.css'

// The browser regression intercepts this synthetic token's public API reads.
createRoot(document.getElementById('root')!).render(<ArtifactPage publicToken="phone-fixture" />)
