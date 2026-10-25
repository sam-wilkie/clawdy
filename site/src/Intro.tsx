import { useEffect } from 'react'

/** The dark intro screen: typed wordmark, then the iris (red ring, then snow) that opens the desk. */
export function Intro({ text, lit, frame, skip }: { text: string; lit: boolean; frame: string; skip: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (!['Shift', 'Control', 'Alt', 'Meta'].includes(e.key)) skip() }
    window.addEventListener('pointerdown', skip, true)
    window.addEventListener('keydown', onKey, true)
    return () => { window.removeEventListener('pointerdown', skip, true); window.removeEventListener('keydown', onKey, true) }
  }, [skip])

  return (
    <div className="intro" data-frame={frame} aria-hidden="true">
      <div className="iris"><i /><i /></div>
      <div className="brand" style={{ opacity: lit ? 1 : 0 }}>
        <span>{text}</span><span className="brand-cursor">▌</span>
      </div>
    </div>
  )
}
