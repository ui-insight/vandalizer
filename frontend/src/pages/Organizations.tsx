import { useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'

/**
 * The /organizations route now redirects to the Admin panel's Organizations tab.
 * All org management lives in Admin > Organizations.
 */
export default function Organizations() {
  const navigate = useNavigate()
  useEffect(() => {
    navigate({ to: '/admin', replace: true })
  }, [navigate])
  return null
}
