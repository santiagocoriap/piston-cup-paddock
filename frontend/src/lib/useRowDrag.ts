import { useState, type DragEvent } from 'react'

/** Drag and drop for the rows of a list. onMove gets the old and the new place of a row. */
export function useRowDrag(onMove: (from: number, to: number) => void) {
  const [from, setFrom] = useState<number | null>(null)
  const [over, setOver] = useState<number | null>(null)
  const reset = () => {
    setFrom(null)
    setOver(null)
  }
  const rowProps = (index: number) => ({
    draggable: true,
    onDragStart: (event: DragEvent) => {
      setFrom(index)
      event.dataTransfer.effectAllowed = 'move'
      // Firefox needs data to start a drag.
      event.dataTransfer.setData('text/plain', String(index))
    },
    onDragOver: (event: DragEvent) => {
      event.preventDefault()
      setOver(index)
    },
    onDrop: (event: DragEvent) => {
      event.preventDefault()
      if (from !== null && from !== index) onMove(from, index)
      reset()
    },
    onDragEnd: reset,
  })
  return { from, over, rowProps }
}
