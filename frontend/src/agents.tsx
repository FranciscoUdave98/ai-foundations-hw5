// The five agents as characters: a name, a personality, an icon, and the fun
// lines they "say" on the board while they work.

import type { ReactNode } from 'react'
import type { AgentName, BoardEvent } from './api'
import { HandsomeDan } from './components/Brand'

export interface AgentProfile {
  id: AgentName
  name: string
  role: string
  tagline: string
  accent: string
}

export const AGENTS: Record<AgentName, AgentProfile> = {
  boss: { id: 'boss', name: 'Coach Dan', role: 'Boss', tagline: 'Calls the plays, makes the final call', accent: '#00356b' },
  inventory: { id: 'inventory', name: 'Stacks', role: 'Inventory', tagline: 'Knows every hoodie by size', accent: '#1f4f8a' },
  accounting: { id: 'accounting', name: 'Penny', role: 'Accounting', tagline: 'Counts every cent twice', accent: '#2b6cb0' },
  facilities: { id: 'facilities', name: 'Keys', role: 'Facilities', tagline: 'Keeps the Chapel St. lights on', accent: '#3d5a80' },
  customer_service: { id: 'customer_service', name: 'Sunny', role: 'Customer Service', tagline: 'Turns facts into friendly notes', accent: '#4a7fc1' },
}

export const AGENT_ORDER: AgentName[] = ['boss', 'inventory', 'accounting', 'facilities', 'customer_service']

export function isAgent(name: string | null | undefined): name is AgentName {
  return !!name && name in AGENTS
}

export function agentName(name: string | null | undefined): string {
  if (isAgent(name)) return AGENTS[name].name
  if (name === 'human') return 'You'
  return 'Desk'
}

// ---- icons ---------------------------------------------------------------

const NAVY = '#00356b'

function Badge({ size, children, title }: { size: number; children: ReactNode; title: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label={title}>
      <circle cx="32" cy="32" r="30" fill="#fff" stroke={NAVY} strokeWidth="3" />
      {children}
    </svg>
  )
}

/** Coach Dan: Handsome Dan with a coach's whistle. */
function BossIcon({ size }: { size: number }) {
  return (
    <span className="agent-icon-boss" style={{ width: size, height: size }}>
      <HandsomeDan size={size} />
      <svg className="whistle" width={size * 0.42} height={size * 0.42} viewBox="0 0 30 30" aria-hidden="true">
        <path d="M3 4 Q9 14 13 16" stroke={NAVY} strokeWidth="2" fill="none" />
        <rect x="11" y="13" width="14" height="10" rx="5" fill="#fff" stroke={NAVY} strokeWidth="2.4" />
        <rect x="21" y="12" width="7" height="5" rx="1.5" fill={NAVY} />
      </svg>
    </span>
  )
}

/** Stacks: a tower of boxes with a tee on top. */
function InventoryIcon({ size }: { size: number }) {
  return (
    <Badge size={size} title="Stacks, Inventory">
      <g stroke={NAVY} strokeWidth="2.4" strokeLinejoin="round">
        <rect x="16" y="36" width="15" height="13" fill="#e8eef6" />
        <rect x="33" y="36" width="15" height="13" fill="#e8eef6" />
        <rect x="24" y="23" width="16" height="13" fill="#fff" />
        <path d="M21 36 h5 M38 36 h5 M29 23 h6" />
        <path d="M24 13 l5 -3 h6 l5 3 l-3 4 l-2 -1 v7 h-6 v-7 l-2 1 Z" fill={NAVY} />
      </g>
    </Badge>
  )
}

/** Penny: a coin and ledger. */
function AccountingIcon({ size }: { size: number }) {
  return (
    <Badge size={size} title="Penny, Accounting">
      <g stroke={NAVY} strokeWidth="2.4" strokeLinejoin="round">
        <rect x="14" y="16" width="24" height="32" rx="3" fill="#e8eef6" />
        <path d="M19 24 h14 M19 30 h14 M19 36 h9" strokeLinecap="round" />
        <circle cx="41" cy="40" r="10" fill={NAVY} />
        <text x="41" y="45" textAnchor="middle" fontSize="14" fontWeight="700" fill="#fff" stroke="none" fontFamily="Graduate, Georgia, serif">$</text>
      </g>
    </Badge>
  )
}

/** Keys: the shop front with a key. */
function FacilitiesIcon({ size }: { size: number }) {
  return (
    <Badge size={size} title="Keys, Facilities">
      <g stroke={NAVY} strokeWidth="2.4" strokeLinejoin="round">
        <path d="M14 28 L32 15 L50 28" fill="none" strokeLinecap="round" />
        <rect x="18" y="27" width="28" height="21" fill="#e8eef6" />
        <rect x="28" y="35" width="8" height="13" fill={NAVY} />
        <circle cx="45" cy="44" r="5" fill="#fff" />
        <path d="M45 39 V30 M45 33 h3 M45 36 h2" strokeLinecap="round" />
      </g>
    </Badge>
  )
}

/** Sunny: a speech bubble with a smile. */
function ServiceIcon({ size }: { size: number }) {
  return (
    <Badge size={size} title="Sunny, Customer Service">
      <g stroke={NAVY} strokeWidth="2.4" strokeLinejoin="round">
        <path d="M14 20 Q14 15 19 15 H45 Q50 15 50 20 V36 Q50 41 45 41 H28 L20 49 V41 H19 Q14 41 14 36 Z" fill="#e8eef6" />
        <circle cx="25" cy="26" r="2" fill={NAVY} stroke="none" />
        <circle cx="39" cy="26" r="2" fill={NAVY} stroke="none" />
        <path d="M24 32 Q32 38 40 32" fill="none" strokeLinecap="round" />
      </g>
    </Badge>
  )
}

export function AgentIcon({ agent, size = 48 }: { agent: AgentName; size?: number }) {
  switch (agent) {
    case 'boss': return <BossIcon size={size} />
    case 'inventory': return <InventoryIcon size={size} />
    case 'accounting': return <AccountingIcon size={size} />
    case 'facilities': return <FacilitiesIcon size={size} />
    case 'customer_service': return <ServiceIcon size={size} />
  }
}

// ---- personality lines ---------------------------------------------------

const START_LINES: Record<AgentName, string> = {
  boss: "Whistle's blown! Reading the ticket",
  inventory: 'Lacing up and heading to the stockroom',
  accounting: 'Sharpening pencils, opening the ledger',
  facilities: 'Grabbing the big key ring',
  customer_service: 'Warming up my friendliest voice',
}

const DONE_LINES: Record<AgentName, string> = {
  boss: 'Final whistle! The call is made',
  inventory: 'Stockroom report filed',
  accounting: 'Ledger balanced, every cent counted',
  facilities: 'Lease checked and locked up',
  customer_service: 'Note drafted with a smile',
}

function arg(detail: Record<string, unknown> | null, key: string): unknown {
  const args = (detail?.args ?? {}) as Record<string, unknown>
  return args[key]
}

function toolLine(agent: AgentName, tool: string, detail: Record<string, unknown> | null): string {
  switch (tool) {
    case 'get_ticket_details':
      return agent === 'boss' ? 'Reading the play sheet' : agent === 'customer_service' ? "Re-reading what the customer asked" : 'Skimming the ticket'
    case 'list_tickets':
      return 'Scanning the whole board'
    case 'check_item_availability': {
      const size = arg(detail, 'size')
      return size ? `Counting size ${size} in the stockroom` : 'Counting every size on the shelf'
    }
    case 'get_vendor_info':
      return 'Ringing up the print shop'
    case 'get_pricing': {
      const pct = arg(detail, 'discount_pct')
      if (agent === 'accounting') return pct ? `Crunching margins at ${pct}% off` : 'Crunching the margins'
      return 'Checking the price tags'
    }
    case 'check_invoice_payment':
      return 'Flipping through the invoices'
    case 'get_cash_balance':
      return 'Peeking at the checking account'
    case 'check_cash_for_payment': {
      const amount = Number(arg(detail, 'amount'))
      return Number.isFinite(amount) ? `Running the numbers twice: $${amount.toLocaleString()}` : 'Running the numbers twice'
    }
    case 'get_lease_details':
      return 'Pulling the Chapel Street lease'
    default:
      return `Using ${tool}`
  }
}

/** The fun one-liner shown for an event, in the agent's voice. */
export function funLine(e: BoardEvent): string {
  const agent = isAgent(e.agent) ? e.agent : null
  switch (e.kind) {
    case 'started':
      return agent ? START_LINES[agent] : 'Getting started'
    case 'delegated': {
      const to = agentName(e.detail?.to as string)
      return agent === 'boss' ? `Calling a play: ${to}, you're up!` : `Quick question for ${to}`
    }
    case 'tool':
      return agent ? toolLine(agent, String(e.detail?.tool ?? ''), e.detail) : 'Using a tool'
    case 'tool_result':
      return 'Got the facts back'
    case 'said':
      return agent === 'boss' ? 'Here\'s the call' : 'Reporting back'
    case 'finished':
      return agent ? DONE_LINES[agent] : 'Done'
    case 'refused':
      return 'Hit a guardrail, staying in my lane'
    case 'retry':
      return 'Fixing my homework and trying again'
    case 'safety':
      return 'Safety check on the money'
    case 'run_started':
      return 'Team huddle!'
    case 'run_finished':
      return 'Ticket resolved'
    case 'run_failed':
      return 'Fumble! The run failed'
    case 'approval_needed':
      return 'Needs a human signature'
    case 'payment_covered':
      return 'Same bill, already paid'
    case 'payment_approved':
      return 'Approved by a human'
    case 'payment_refused':
      return 'Payment refused by the rules'
    case 'reset':
      return 'Fresh start'
    case 'error':
      return 'Ran into trouble'
    default:
      return e.kind
  }
}
