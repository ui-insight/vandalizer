import { useEffect } from 'react'
import { useParams, useNavigate } from '@tanstack/react-router'

/**
 * Redirect /workflows/:id to the workspace with the workflow open in-panel.
 * The query param is picked up by Workspace to call openWorkflow().
 */
export default function WorkflowEditor() {
  const { id } = useParams({ strict: false })
  const navigate = useNavigate()

  useEffect(() => {
    if (id) {
      navigate({
        to: '/',
        search: {
          mode: undefined,
          tab: undefined,
          workflow: id,
          extraction: undefined,
          automation: undefined,
          kb: undefined,
        },
        replace: true,
      })
    } else {
      navigate({ to: '/workflows', replace: true })
    }
  }, [id, navigate])

  return null
}
