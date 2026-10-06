import { useEffect, useRef, useState } from 'react'
import type { BoardEvent } from '../api'
import { AGENTS, AgentIcon, agentName, funLine, isAgent } from '../agents'
import { HandsomeDan, PawTrail } from './Brand'

function clock(t: string | null): string {
  if (!t) return ''
  const d = new Date(t)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' })
}

function argsText(args: unknown): string {
  if (!args || typeof args !== 'object') return ''
  return Object.entries(args as Record<string, unknown>).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')
}

type FeedItem = BoardEvent & { result?: unknown }

/** Drop rows the team room already shows and fold each tool's result into its call. */
function tidy(events: BoardEvent[]): FeedItem[] {
  const out: FeedItem[] = []
  for (const e of events) {
    if (e.kind === 'finished' || e.kind === 'run_started' || (e.kind === 'started' && e.depth !== 0)) continue
    if (e.kind === 'tool_result') {
      const call = [...out].reverse().find((x) => x.kind === 'tool' && x.agent === e.agent && x.detail?.tool === e.detail?.tool && x.result === undefined)
      if (call) {
        call.result = e.detail?.result ?? null
        continue
      }
    }
    out.push({ ...e })
  }
  return out
}

function Row({ e }: { e: FeedItem }) {
  const [open, setOpen] = useState(false)
  const agent = isAgent(e.agent) ? e.agent : null
  const who = agentName(e.agent)
  const to = e.detail?.to as string | undefined
  const said = e.kind === 'said' ? String(e.detail?.final_call ?? e.detail?.answer ?? e.detail?.text ?? e.text) : null

  return (
    <li className={`feed-row kind-${e.kind}`} style={agent ? { ['--accent' as string]: AGENTS[agent].accent } : undefined}>
      <span className="feed-avatar">
        {agent ? <AgentIcon agent={agent} size={34} /> : e.agent === 'human' ? <span className="human-dot">✍</span> : <HandsomeDan size={30} />}
      </span>
      <div className="feed-body">
        <div className="feed-line">
          <strong>{who}</strong>
          <span className="fun">{funLine(e)}</span>
          <time>{clock(e.time)}</time>
        </div>
        {e.kind === 'delegated' && (
          <div className="msg delegated">
            <span className="msg-to">→ {agentName(to)}</span>
            {String(e.detail?.request ?? '')}
          </div>
        )}
        {e.kind === 'tool' && (
          <div className="tool-line">
            <code className="tool-chip">{String(e.detail?.tool)}({argsText(e.detail?.args)})</code>
            {e.result !== undefined && (
              <button className="result-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
                {open ? '▾ hide result' : '▸ result'}
              </button>
            )}
          </div>
        )}
        {e.kind === 'tool' && open && (
          <pre className="result-json">{JSON.stringify(e.result, null, 2)}</pre>
        )}
        {said && <div className="msg said">{said}</div>}
        {['refused', 'retry', 'safety', 'run_started', 'run_finished', 'run_failed', 'approval_needed', 'payment_approved', 'payment_covered', 'payment_refused', 'reset', 'error'].includes(e.kind) && (
          <div className={`msg note note-${e.kind}`}>{e.text}</div>
        )}
      </div>
    </li>
  )
}

export default function LiveFeed({ events, running }: { events: BoardEvent[]; running: boolean }) {
  const listRef = useRef<HTMLOListElement>(null)
  const stick = useRef(true)
  const items = tidy(events)

  useEffect(() => {
    const el = listRef.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [items.length])

  return (
    <section className="panel feed" aria-labelledby="feed-title">
      <header className="panel-head">
        <h2 id="feed-title">Play-by-play</h2>
        <span className="muted">{items.length} moves</span>
      </header>
      {items.length === 0 ? (
        <div className="feed-empty">
          <HandsomeDan size={60} className="dan-bounce" />
          <p>Quiet in here. Every message, tool, and handoff will show up live.</p>
        </div>
      ) : (
        <ol
          className="feed-list"
          ref={listRef}
          onScroll={(ev) => {
            const el = ev.currentTarget
            stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
          }}
        >
          {items.map((e) => <Row key={e.seq} e={e} />)}
          {running && (
            <li className="feed-row typing">
              <PawTrail count={4} />
              <span>the team is working…</span>
            </li>
          )}
        </ol>
      )}
    </section>
  )
}
