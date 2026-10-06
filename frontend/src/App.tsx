import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Approval, BoardEvent, Cash, TicketsResponse } from './api'
import { API_BASE, ApiError, api } from './api'
import { deriveRun } from './runState'
import AgentSummary from './components/AgentSummary'
import Approvals from './components/Approvals'
import { HandsomeDan, PawTrail } from './components/Brand'
import CashWidget from './components/CashWidget'
import LiveFeed from './components/LiveFeed'
import Modal from './components/Modal'
import RunSummary from './components/RunSummary'
import TeamRoom from './components/TeamRoom'
import TicketBoard from './components/TicketBoard'

interface Toast { id: number; text: string; tone: 'good' | 'info' | 'bad' }

const REFRESH_KINDS = new Set(['run_finished', 'run_failed', 'payment_approved', 'payment_refused', 'reset', 'approval_needed'])

export default function App() {
  const [board, setBoard] = useState<TicketsResponse | null>(null)
  const [cash, setCash] = useState<Cash | null>(null)
  const [pending, setPending] = useState<Approval[]>([])
  const [events, setEvents] = useState<BoardEvent[]>([])
  // ?ticket=103 opens the board on that ticket (handy for links and screenshots).
  const [selectedId, setSelectedId] = useState<number | null>(() => Number(new URLSearchParams(location.search).get('ticket')) || null)
  const [starting, setStarting] = useState<{ ticketId: number; runId: string | null } | null>(null)
  const [offline, setOffline] = useState<string | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [confirmReset, setConfirmReset] = useState(false)
  const lastSeq = useRef(0)
  const loaded = useRef(false)

  const toast = useCallback((text: string, tone: Toast['tone'] = 'info') => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, text, tone }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000)
  }, [])

  const refresh = useCallback(async () => {
    try {
      const [b, c, p] = await Promise.all([api.tickets(), api.cash(), api.pending()])
      setBoard(b)
      setCash(c)
      setPending(p.payments)
      setOffline(null)
      setSelectedId((cur) => cur ?? b.tickets.find((t) => t.is_open)?.id ?? b.tickets[0]?.id ?? null)
    } catch (e) {
      setOffline(e instanceof ApiError ? e.message : String(e))
    }
  }, [])

  const pollEvents = useCallback(async () => {
    try {
      const r = await api.events(lastSeq.current)
      if (r.events.length) {
        lastSeq.current = r.last_seq
        setEvents((prev) => [...prev, ...r.events].slice(-3000))
        if (loaded.current) {
          for (const e of r.events) {
            if (e.kind === 'run_finished') toast(`Ticket #${e.ticket_id} resolved! ${String(e.detail?.decision ?? '').replace(/_/g, ' ')}`, 'good')
            if (e.kind === 'run_failed') toast(e.text, 'bad')
            if (e.kind === 'approval_needed') toast(`✍ ${e.text}`, 'info')
          }
        }
        if (r.events.some((e) => REFRESH_KINDS.has(e.kind))) refresh()
      } else if (r.last_seq < lastSeq.current) {
        // backend restarted: start the feed over
        lastSeq.current = 0
        setEvents([])
      }
      loaded.current = true
    } catch {
      /* the main refresh reports connection problems */
    }
  }, [refresh, toast])

  useEffect(() => {
    refresh()
    pollEvents()
    const fast = setInterval(pollEvents, 1000)
    const slow = setInterval(refresh, 2500)
    return () => { clearInterval(fast); clearInterval(slow) }
  }, [refresh, pollEvents])

  const tickets = board?.tickets ?? []
  const runningTicket = tickets.find((t) => t.running) ?? null
  const runningTicketId = runningTicket?.id ?? starting?.ticketId ?? null
  const runningRunId = board?.running_run_id ?? starting?.runId ?? null
  const selected = tickets.find((t) => t.id === selectedId) ?? null

  // Clear the "starting" flag once the board shows the run finished.
  useEffect(() => {
    if (starting?.runId && selected?.last_run?.run_id === starting.runId && !runningTicket) setStarting(null)
  }, [starting, selected, runningTicket])

  const displayRunId =
    (runningTicketId === selectedId ? runningRunId : null) ?? selected?.last_run?.run_id ?? null
  const runEvents = useMemo(() => events.filter((e) => displayRunId && e.run_id === displayRunId), [events, displayRunId])
  const view = useMemo(() => deriveRun(runEvents), [runEvents])
  const isLive = !!displayRunId && displayRunId === runningRunId && !view.finished && !view.failed

  async function runTeam(id: number) {
    setStarting({ ticketId: id, runId: null })
    try {
      const r = await api.runTicket(id)
      setStarting({ ticketId: id, runId: r.run_id })
      toast(`Team huddle on ticket #${id}. Coach Dan has the ball!`, 'info')
      refresh()
    } catch (e) {
      setStarting(null)
      toast(e instanceof ApiError ? e.message : String(e), 'bad')
    }
  }

  async function doReset() {
    setConfirmReset(false)
    try {
      await api.reset()
      setStarting(null)
      toast('Fresh start! The database is back to its original values.', 'good')
      refresh()
    } catch (e) {
      toast(e instanceof ApiError ? e.message : String(e), 'bad')
    }
  }

  const openCount = tickets.filter((t) => t.is_open).length
  const greeting = !board ? 'Warming up the desk…'
    : openCount === 0 ? 'Hey Francisco! Every ticket is resolved. Go Bulldogs!'
    : `Hey Francisco! ${openCount} open ticket${openCount === 1 ? '' : 's'} on the desk today.`

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark"><HandsomeDan size={40} className={isLive ? 'dan-thinking' : 'dan-wiggle'} /></span>
          <span className="brand-text">
            <strong>Campus Customs</strong>
            <small>Agent Desk · the bulldogs who run the shop</small>
          </span>
        </div>
        <p className="greeting">{greeting}</p>
        <div className="desk-date" title="Every overdue check uses desk.date_today, not the real calendar">
          <small>desk.date_today</small>
          <b>{board?.date_today ?? '…'}</b>
        </div>
        <CashWidget cash={cash} />
        <button className="btn btn-reset" onClick={() => setConfirmReset(true)} disabled={!!runningTicketId}
          title={runningTicketId ? 'Wait for the run to finish' : 'Reset the database for a fresh run'}>
          ↺ Fresh run
        </button>
      </header>
      {isLive && <div className="run-progress" aria-hidden="true"><span /><PawTrail count={6} color="#ffffff" /></div>}

      {offline && (
        <div className="offline" role="alert">
          <HandsomeDan size={36} /> {offline} Start it from <code>backend/</code> with <code>uvicorn main:app --reload --port 8000</code> ({API_BASE}).
        </div>
      )}

      <main className="layout">
        <TicketBoard
          tickets={tickets}
          selectedId={selectedId}
          runningTicketId={runningTicketId}
          starting={!!starting && !starting.runId}
          onSelect={setSelectedId}
          onRun={runTeam}
        />
        <div className="center">
          <TeamRoom view={view} ticketId={selectedId} live={isLive}
            emptyHint={selected?.is_resolved ? 'This ticket was resolved before the last restart. Run it again to watch the team.' : `Ticket #${selectedId} is waiting. Hit “Send in the team”.`} />
          <AgentSummary view={view} />
          <LiveFeed events={runEvents} running={isLive} />
        </div>
        <aside className="side">
          <Approvals
            approvals={pending}
            selectedTicketId={selectedId}
            balance={cash?.balance ?? null}
            disabled={!!runningTicketId}
            onApproved={(m) => { toast(m, 'good'); refresh() }}
          />
          <RunSummary ticket={selected} />
        </aside>
      </main>

      <footer className="foot">
        <PawTrail count={3} /> Campus Customs · HW5 agent team on gpt-6-luna · facts via the MCP server · humans sign every payment
      </footer>

      <div className="toasts" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`toast tone-${t.tone}`}>{t.text}</div>)}
      </div>

      {confirmReset && (
        <Modal title="Start fresh?" onClose={() => setConfirmReset(false)}>
          <div className="sign-sheet">
            <p>This copies the original <code>campus_customs.db</code> over the working copy. All tickets go back to <b>open</b>, payments are cleared, checking goes back to its starting balance, and waiting approvals are dropped.</p>
            <div className="modal-actions">
              <button className="btn btn-ghost-dark" onClick={() => setConfirmReset(false)}>Keep things as they are</button>
              <button className="btn btn-primary" onClick={doReset}>Reset the database</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
