import type { TFunction } from 'i18next'
import { api } from '../api/client'
import { errorMessage } from './errors'

/** Draw the conditions of a round. A second draw asks for a reason. */
export async function drawConditions(roundId: number, t: TFunction): Promise<string | null> {
  const path = { params: { path: { round_id: roundId } } }
  let { error } = await api.POST('/api/rounds/{round_id}/draw-conditions', { ...path, body: {} })
  if ((error as { detail?: string } | undefined)?.detail === 'reason_required') {
    const reason = window.prompt(t('draw.reasonPrompt'))
    if (!reason) return null
    ;({ error } = await api.POST('/api/rounds/{round_id}/draw-conditions', { ...path, body: { reason } }))
  }
  return error ? errorMessage(t, error) : null
}
