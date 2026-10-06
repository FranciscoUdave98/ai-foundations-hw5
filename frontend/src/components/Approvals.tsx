import { useState } from 'react'
import type { Approval } from '../api'
import { ApiError, api, money } from '../api'
import Modal from './Modal'

const KIND: Record<string, string> = { invoice: 'Invoice payment', rent: 'Rent payment', purchase_order: 'Purchase order' }

/** One bill to sign. Several tickets can ask for the same bill (e.g. invoice 501). */
interface Bill {
  key: string
  first: Approval
  tickets: number[]
}

function groupBills(approvals: Approval[]): Bill[] {
  const bills = new Map<string, Bill>()
  for (const a of approvals) {
    const key = a.ref_id != null && (a.kind === 'invoice' || a.kind === 'rent') ? `${a.kind}:${a.ref_id}` : a.approval_id
    const bill = bills.get(key)
    if (bill) {
      if (!bill.tickets.includes(a.ticket_id)) bill.tickets.push(a.ticket_id)
    } else {
      bills.set(key, { key, first: a, tickets: [a.ticket_id] })
    }
  }
  return [...bills.values()]
}

interface Props {
  approvals: Approval[]
  selectedTicketId: number | null
  balance: number | null
  disabled: boolean
  onApproved: (message: string) => void
}

export default function Approvals({ approvals, selectedTicketId, balance, disabled, onApproved }: Props) {
  const [active, setActive] = useState<Bill | null>(null)
  const [name, setName] = useState('')
  const [agree, setAgree] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const bills = groupBills(approvals)
  const total = bills.reduce((s, b) => s + b.first.amount, 0)
  // Bills for the ticket you're looking at come first.
  bills.sort((a, b) => Number(b.tickets.includes(selectedTicketId ?? -1)) - Number(a.tickets.includes(selectedTicketId ?? -1)))

  async function approve() {
    if (!active) return
    setBusy(true)
    setError(null)
    try {
      const r = await api.approve(active.first.approval_id, name.trim())
      onApproved(`${name.trim()} approved ${money(active.first.amount)} to ${active.first.payee}. Checking is now ${money(r.balance_after)}.`)
      setActive(null)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const a = active?.first
  const after = a && balance != null ? balance - a.amount : null

  return (
    <section className="panel approvals" aria-labelledby="approvals-title">
      <header className="panel-head">
        <h2 id="approvals-title">Needs your signature</h2>
        <span className="muted">{bills.length ? `${bills.length} to sign · ${money(total)}` : 'all clear'}</span>
      </header>
      {bills.length === 0 ? (
        <p className="muted pad">Nothing waiting. Agents only <em>prepare</em> payments; a human signs.</p>
      ) : (
        <ul className="approval-list">
          {bills.map((b) => (
            <li key={b.key} className={`approval ${b.tickets.includes(selectedTicketId ?? -1) ? 'mine' : ''}`}>
              <div className="approval-row">
                <div className="approval-main">
                  <span className="approval-kind">{KIND[b.first.kind] ?? b.first.kind} · {b.tickets.map((t) => `#${t}`).join(' · ')}</span>
                  <span className="approval-amount">{money(b.first.amount)}</span>
                  <span className="approval-payee">to {b.first.payee}</span>
                </div>
                <button className="btn btn-sign" onClick={() => { setActive(b); setAgree(false); setError(null) }} disabled={disabled}>Sign</button>
              </div>
              {b.tickets.length > 1 && <p className="approval-shared">One bill, asked for by {b.tickets.length} tickets. Signing once covers all of them.</p>}
            </li>
          ))}
        </ul>
      )}

      {active && a && (
        <Modal title={`Approve ${KIND[a.kind]?.toLowerCase() ?? 'payment'}`} onClose={() => !busy && setActive(null)}>
          <div className="sign-sheet">
            <div className="sign-amount">{money(a.amount)}</div>
            <p>to <strong>{a.payee}</strong> from {a.account} · ticket {active.tickets.map((t) => `#${t}`).join(' & ')}</p>
            <p className="muted">{a.reason}</p>
            <div className="sign-balance">
              <span>Checking now <b>{money(balance)}</b></span>
              <span>After <b className={after != null && after < 0 ? 'neg' : ''}>{money(after)}</b></span>
            </div>
            {after != null && after < 0 && <p className="sign-warn">This would overdraw checking. The backend will refuse it.</p>}
            <label className="field">
              <span>Your name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Who is signing?" autoFocus />
            </label>
            <label className="check">
              <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
              <span>I’m a human and I approve paying {money(a.amount)} to {a.payee}.</span>
            </label>
            {error && <p className="sign-error" role="alert">Refused: {error}</p>}
            <div className="modal-actions">
              <button className="btn btn-ghost-dark" onClick={() => setActive(null)} disabled={busy}>Not now</button>
              <button className="btn btn-primary" onClick={approve} disabled={busy || !agree || !name.trim()}>
                {busy ? 'Signing…' : `Approve ${money(a.amount)}`}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </section>
  )
}
