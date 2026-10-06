import type { Ticket } from '../api'
import { money } from '../api'

const DECISION: Record<string, { label: string; tone: string }> = {
  approve: { label: 'Approved', tone: 'good' },
  approve_with_conditions: { label: 'Approved with conditions', tone: 'warn' },
  hold: { label: 'On hold', tone: 'warn' },
  decline: { label: 'Declined', tone: 'bad' },
  escalate_to_human: { label: 'Needs a human call', tone: 'warn' },
}

export default function RunSummary({ ticket }: { ticket: Ticket | null }) {
  const run = ticket?.last_run

  return (
    <section className="panel summary" aria-labelledby="summary-title">
      <header className="panel-head">
        <h2 id="summary-title">The call</h2>
        {run && <span className={`decision-chip tone-${DECISION[run.decision]?.tone ?? 'warn'}`}>{DECISION[run.decision]?.label ?? run.decision}</span>}
      </header>

      {!run ? (
        <p className="muted pad">{ticket ? 'No call yet. Run the team and Coach Dan’s decision lands here.' : 'Pick a ticket to see its call.'}</p>
      ) : (
        <div className="pad">
          <p className="final-call">{run.final_call}</p>
          {run.blockers.length > 0 && (
            <ul className="blockers">
              {run.blockers.map((b) => <li key={b}>{b}</li>)}
            </ul>
          )}
          {run.customer_message && (
            <figure className="note-card">
              <figcaption>Sunny’s draft to {ticket?.requester}</figcaption>
              <p>{run.customer_message}</p>
            </figure>
          )}
          <p className={`safety ${run.safety.within_balance ? 'ok' : 'flag'}`}>
            {run.safety.within_balance ? '🛡 Safety check passed: ' : '⚠ Safety check: '}
            requested {money(run.safety.payment_total)} vs {money(run.safety.cash_balance)} in checking.
            Nothing is paid until a human approves.
          </p>
        </div>
      )}

    </section>
  )
}
