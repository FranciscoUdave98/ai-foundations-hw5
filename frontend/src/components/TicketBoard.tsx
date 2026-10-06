import type { Ticket } from '../api'

const TYPE_INFO: Record<string, { label: string; icon: string }> = {
  customer_order: { label: 'Customer order', icon: 'tee' },
  rent_notice: { label: 'Rent notice', icon: 'house' },
  price_override: { label: 'Discount request', icon: 'tag' },
}

function TypeIcon({ kind }: { kind: string }) {
  const common = { width: 26, height: 26, viewBox: '0 0 32 32', fill: 'none', stroke: 'currentColor', strokeWidth: 2.2, strokeLinejoin: 'round' as const, strokeLinecap: 'round' as const, 'aria-hidden': true }
  if (kind === 'house') return <svg {...common}><path d="M4 15 L16 5 L28 15" /><path d="M8 13 V27 H24 V13" /><path d="M13 27 V19 H19 V27" /></svg>
  if (kind === 'tag') return <svg {...common}><path d="M4 16 V5 H15 L28 18 L18 28 Z" /><circle cx="10" cy="11" r="2" /></svg>
  return <svg {...common}><path d="M10 4 L4 8 L7 13 L9 12 V28 H23 V12 L25 13 L28 8 L22 4 Q16 9 10 4 Z" /></svg>
}

interface Props {
  tickets: Ticket[]
  selectedId: number | null
  runningTicketId: number | null
  starting: boolean
  onSelect: (id: number) => void
  onRun: (id: number) => void
}

export default function TicketBoard({ tickets, selectedId, runningTicketId, starting, onSelect, onRun }: Props) {
  const busy = runningTicketId !== null || starting
  return (
    <section className="panel board" aria-labelledby="board-title">
      <header className="panel-head">
        <h2 id="board-title">Ticket board</h2>
        <span className="muted">{tickets.filter((t) => t.is_open).length} open · {tickets.filter((t) => t.is_resolved).length} resolved</span>
      </header>
      <ul className="ticket-list">
        {tickets.map((t, i) => {
          const info = TYPE_INFO[t.type] ?? { label: t.type, icon: 'tee' }
          const selected = t.id === selectedId
          const running = t.id === runningTicketId
          return (
            <li key={t.id} style={{ animationDelay: `${i * 80}ms` }}>
              <div
                className={`ticket ${selected ? 'selected' : ''} ${running ? 'running' : ''} ${t.is_resolved ? 'resolved' : ''}`}
                role="button"
                tabIndex={0}
                aria-pressed={selected}
                onClick={() => onSelect(t.id)}
                onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onSelect(t.id))}
              >
                <div className="ticket-top">
                  <span className="ticket-type"><TypeIcon kind={info.icon} /></span>
                  <div className="ticket-title">
                    <span className="ticket-id">#{t.id}</span>
                    <strong>{t.subject}</strong>
                  </div>
                  <span className={`status-pill ${running ? 'is-running' : t.is_resolved ? 'is-resolved' : 'is-open'}`}>
                    {running ? 'On it…' : t.is_resolved ? 'Resolved' : 'Open'}
                  </span>
                </div>
                <div className="ticket-meta">
                  <span>{info.label}</span>
                  <span>from {t.requester}</span>
                </div>
                {t.last_run && (
                  <p className="ticket-call">“{t.last_run.final_call}”</p>
                )}
                <div className="ticket-foot">
                  {t.pending_approvals > 0 && (
                    <span className="sign-badge">✍ {t.pending_approvals} to approve</span>
                  )}
                  {selected && (
                    <button
                      className="btn btn-primary btn-run"
                      disabled={busy}
                      onClick={(e) => { e.stopPropagation(); onRun(t.id) }}
                      title={busy && !running ? 'Another ticket is running. One play at a time.' : undefined}
                    >
                      {running || (starting && selected) ? 'Team on the field…' : t.last_run ? 'Run the team again' : 'Send in the team ▸'}
                    </button>
                  )}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
