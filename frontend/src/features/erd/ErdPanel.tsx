import { useCallback, useEffect, useState } from 'react'

import { apiFetch } from '../../lib/api'
import type { ErdResponse } from '../../lib/types'
import { ErdCanvas } from './ErdCanvas'

interface ErdPanelProps {
  projectId: number
}

/** Loads the diagram, then hands it to the canvas. */
export function ErdPanel({ projectId }: ErdPanelProps) {
  const [erd, setErd] = useState<ErdResponse | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setErd(await apiFetch<ErdResponse>(`/projects/${projectId}/erd`))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load the diagram.')
    }
  }, [projectId])

  useEffect(() => {
    void load()
  }, [load])

  if (error) {
    return (
      <p role="alert" className="text-small text-text-primary">
        {error}
      </p>
    )
  }
  if (!erd) return null

  return <ErdCanvas projectId={projectId} erd={erd} />
}
