import { useEffect, useRef, useState } from 'react'
import type { Cash } from '../api'
import { money } from '../api'

/** Live checking balance; the number rolls to its new value and flashes when it changes. */
export default function CashWidget({ cash }: { cash: Cash | null }) {
  const [shown, setShown] = useState<number | null>(cash?.balance ?? null)
  const [flash, setFlash] = useState<'' | 'down' | 'up'>('')
  const prev = useRef<number | null>(null)

  useEffect(() => {
    if (!cash) return
    const target = cash.balance
    const from = prev.current
    prev.current = target
    if (from == null || from === target) {
      setShown(target)
      return
    }
    setFlash(target < from ? 'down' : 'up')
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) {
      setShown(target)
      return
    }
    const start = performance.now()
    let raf = 0
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / 900)
      setShown(from + (target - from) * (1 - Math.pow(1 - k, 3)))
      if (k < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    const timer = setTimeout(() => setFlash(''), 1600)
    return () => { cancelAnimationFrame(raf); clearTimeout(timer) }
  }, [cash])

  const owed = cash?.upcoming_obligations.reduce((s, o) => s + o.amount, 0) ?? 0
  return (
    <div className={`cash ${flash}`} aria-live="polite">
      <span className="cash-label">Checking · live</span>
      <span className="cash-amount">{money(shown)}</span>
      <span className="cash-sub">
        {cash ? (owed > 0 ? <>bills waiting {money(owed)} · leaves <b className={cash.balance_after_obligations < 0 ? 'neg' : ''}>{money(cash.balance_after_obligations)}</b></> : 'no bills waiting') : 'connecting…'}
      </span>
    </div>
  )
}
