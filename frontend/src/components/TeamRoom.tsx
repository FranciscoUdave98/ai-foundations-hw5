import type { AgentName } from '../api'
import { AGENTS, AGENT_ORDER, AgentIcon } from '../agents'
import type { RunView } from '../runState'

// Where each agent sits in the room (percent of the stage).
const SEATS: Record<AgentName, { x: number; y: number }> = {
  boss: { x: 50, y: 22 },
  inventory: { x: 11, y: 74 },
  accounting: { x: 37, y: 74 },
  facilities: { x: 63, y: 74 },
  customer_service: { x: 89, y: 74 },
}

const STATUS_TEXT = { idle: 'Idle', working: 'Working', waiting: 'Waiting on a teammate', done: 'Done', error: 'Trouble' }

function wirePath(from: AgentName, to: AgentName): string {
  const a = SEATS[from]
  const b = SEATS[to]
  if (Math.abs(a.y - b.y) < 1) {
    // teammate-to-teammate: arc below the row
    const mid = (a.x + b.x) / 2
    return `M ${a.x} ${a.y + 6} Q ${mid} ${a.y + 26} ${b.x} ${b.y + 6}`
  }
  return `M ${a.x} ${a.y + 8} C ${a.x} ${(a.y + b.y) / 2 + 4}, ${b.x} ${(a.y + b.y) / 2 - 4}, ${b.x} ${b.y - 9}`
}

export default function TeamRoom({ view, ticketId, emptyHint, live }: { view: RunView; ticketId: number | null; emptyHint: string; live: boolean }) {
  const { agents, wires } = view
  return (
    <section className="panel team-room" aria-labelledby="room-title">
      <header className="panel-head">
        <h2 id="room-title">The team room</h2>
        <span className={`live-dot ${live ? 'on' : ''}`}>{live ? 'LIVE' : view.failed ? 'Run failed' : view.started ? 'Final whistle' : 'Waiting for kickoff'}</span>
      </header>
      <div className="stage">
        <svg className="wires" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          {AGENT_ORDER.filter((a) => a !== 'boss').map((a) => (
            <path key={`base-${a}`} d={wirePath('boss', a)} className="wire base" vectorEffect="non-scaling-stroke" />
          ))}
          {wires.map((w) => (
            <path key={w.key} d={wirePath(w.from, w.to)} className={`wire talk ${w.active ? 'active' : 'used'}`} vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
        {wires.map((w) => {
          // Label each handoff right above the agent being asked; stack if several people asked them.
          const b = SEATS[w.to]
          const stack = wires.filter((x) => x.to === w.to).indexOf(w)
          return (
            <span key={`chip-${w.key}`} className={`wire-chip ${w.active ? 'active' : ''}`}
              style={{ left: `${b.x}%`, top: `${b.y - (w.to === 'boss' ? -14 : 19) - stack * 6}%` }} title={w.request}>
              from {AGENTS[w.from].name}{w.count > 1 ? ` ×${w.count}` : ''}
            </span>
          )
        })}
        {AGENT_ORDER.map((name) => {
          const p = AGENTS[name]
          const s = agents[name]
          const seat = SEATS[name]
          return (
            <div key={name} className={`seat status-${s.status} ${name === 'boss' ? 'seat-boss' : ''}`}
              style={{ left: `${seat.x}%`, top: `${seat.y}%`, ['--accent' as string]: p.accent }}>
              <div className="avatar-ring" title={`${p.name} · ${p.role}: ${STATUS_TEXT[s.status]}`}>
                <AgentIcon agent={name} size={name === 'boss' ? 64 : 54} />
                {s.status === 'done' && <span className="done-check" aria-label="done">✓</span>}
              </div>
              <div className="seat-name"><strong>{p.name}</strong><small>{p.role}</small></div>
              <div className={`bubble ${s.status}`} aria-live="polite">
                {s.status === 'idle' && !view.started ? <em>{p.tagline}</em> : s.line}
                {(s.status === 'working' || s.status === 'waiting') && <span className="dots" aria-hidden="true"><i /><i /><i /></span>}
              </div>
            </div>
          )
        })}
        {!view.started && (
          <p className="stage-hint">{ticketId ? emptyHint : 'Pick a ticket on the left, then send in the team.'}</p>
        )}
      </div>
    </section>
  )
}
