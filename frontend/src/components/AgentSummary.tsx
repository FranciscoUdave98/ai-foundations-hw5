import { AGENTS, AGENT_ORDER, AgentIcon } from '../agents'
import type { RunView } from '../runState'

/** One compact card per agent that worked the ticket: tools, handoffs, time, and last words. */
export default function AgentSummary({ view }: { view: RunView }) {
  const helpers = AGENT_ORDER.filter((a) => view.agents[a].runs > 0)
  if (helpers.length === 0) return null
  return (
    <section className="panel agent-summary" aria-labelledby="who-title">
      <header className="panel-head">
        <h2 id="who-title">What each agent did</h2>
        <span className="muted">{helpers.length} of 5 agents worked this ticket</span>
      </header>
      <ul className="who-grid">
        {helpers.map((a) => {
          const s = view.agents[a]
          const handoff = a === 'boss'
            ? s.asked.length ? `asked ${s.asked.map((x) => AGENTS[x].name).join(', ')}` : 'worked alone'
            : [s.askedBy.length && `for ${s.askedBy.map((x) => AGENTS[x].name).join(', ')}`, s.asked.length && `asked ${s.asked.map((x) => AGENTS[x].name).join(', ')}`].filter(Boolean).join(' · ')
          return (
            <li key={a} style={{ ['--accent' as string]: AGENTS[a].accent }}>
              <div className="who-head">
                <AgentIcon agent={a} size={34} />
                <div>
                  <strong>{AGENTS[a].name}</strong>
                  <small>{AGENTS[a].role}{s.seconds ? ` · ${s.seconds.toFixed(0)}s` : ''}{handoff ? ` · ${handoff}` : ''}</small>
                </div>
              </div>
              {s.tools.length > 0 && (
                <div className="who-tools">{s.tools.map((t) => <code key={t}>{t}</code>)}</div>
              )}
              {s.said && <p className="who-said" title={s.said}>“{s.said}”</p>}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
