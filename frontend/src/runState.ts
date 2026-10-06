// Replays a run's events into live state for the board: what each agent is
// doing right now, who is waiting on whom, and a short summary of their work.

import type { AgentName, BoardEvent } from './api'
import { AGENT_ORDER, funLine, isAgent } from './agents'

export type AgentStatus = 'idle' | 'working' | 'waiting' | 'done' | 'error'

export interface AgentLive {
  status: AgentStatus
  line: string
  tools: string[]
  toolCalls: number
  asked: AgentName[]
  askedBy: AgentName[]
  said: string | null
  runs: number
  seconds: number
}

export interface Wire {
  key: string
  from: AgentName
  to: AgentName
  request: string
  active: boolean
  count: number
}

export interface RunView {
  agents: Record<AgentName, AgentLive>
  wires: Wire[]
  started: boolean
  finished: boolean
  failed: boolean
}

const blank = (): AgentLive => ({
  status: 'idle', line: 'Napping by the register', tools: [], toolCalls: 0,
  asked: [], askedBy: [], said: null, runs: 0, seconds: 0,
})

function saidText(e: BoardEvent): string {
  const d = e.detail ?? {}
  const v = (d.final_call ?? d.answer ?? d.text) as string | undefined
  return v ?? e.text.replace(/^[^:]+:\s*/, '')
}

export function deriveRun(events: BoardEvent[]): RunView {
  const agents = Object.fromEntries(AGENT_ORDER.map((a) => [a, blank()])) as Record<AgentName, AgentLive>
  const wires = new Map<string, Wire>()
  const open: { from: AgentName; to: AgentName }[] = []
  let started = false
  let finished = false
  let failed = false

  for (const e of [...events].sort((a, b) => a.seq - b.seq)) {
    if (e.kind === 'run_started') started = true
    if (e.kind === 'run_finished') finished = true
    if (e.kind === 'run_failed') failed = true
    if (!isAgent(e.agent)) continue
    const a = agents[e.agent]
    switch (e.kind) {
      case 'started':
        started = true
        a.status = 'working'
        a.runs += 1
        a.line = funLine(e)
        break
      case 'delegated': {
        const to = e.detail?.to as string
        if (!isAgent(to)) break
        const key = `${e.agent}->${to}`
        const w = wires.get(key) ?? { key, from: e.agent, to, request: '', active: false, count: 0 }
        w.count += 1
        w.active = true
        w.request = String(e.detail?.request ?? '')
        wires.set(key, w)
        open.push({ from: e.agent, to })
        if (!a.asked.includes(to)) a.asked.push(to)
        if (!agents[to].askedBy.includes(e.agent)) agents[to].askedBy.push(e.agent)
        a.status = 'waiting'
        a.line = funLine(e)
        break
      }
      case 'tool': {
        const tool = String(e.detail?.tool ?? '')
        a.status = 'working'
        a.toolCalls += 1
        if (tool && !a.tools.includes(tool)) a.tools.push(tool)
        a.line = funLine(e)
        break
      }
      case 'said':
        a.said = saidText(e)
        a.line = funLine(e)
        break
      case 'finished': {
        a.status = 'done'
        a.line = funLine(e)
        const m = e.text.match(/in ([\d.]+)s/)
        if (m) a.seconds += Number(m[1])
        const i = open.findIndex((o) => o.to === e.agent)
        if (i >= 0) {
          const { from } = open.splice(i, 1)[0]
          const w = wires.get(`${from}->${e.agent}`)
          if (w && !open.some((o) => o.from === from && o.to === e.agent)) w.active = false
          if (!open.some((o) => o.from === from) && agents[from].status === 'waiting') {
            agents[from].status = 'working'
            agents[from].line = 'Got the report, thinking it over'
          }
        }
        break
      }
      case 'error':
        a.status = 'error'
        a.line = funLine(e)
        break
      case 'refused':
      case 'retry':
        a.line = funLine(e)
        break
    }
  }
  if (finished || failed) {
    for (const w of wires.values()) w.active = false
  }
  return { agents, wires: [...wires.values()], started, finished, failed }
}
