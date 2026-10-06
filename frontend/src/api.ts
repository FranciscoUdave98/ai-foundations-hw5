// Talks to the FastAPI backend (backend/main.py). The backend allows this page's
// origin (http://localhost:5173) through CORS, so the browser can call it directly.

export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface PurchaseOrder {
  vendor_id: number
  vendor_name: string
  sku: string
  size: string
  qty: number
  unit_cost: number
  total_cost: number
  lead_days: number
  earliest_delivery: string | null
  blocked_by: string[]
}

export interface Safety {
  payment_total: number
  cash_balance: number | null
  balance_after: number | null
  within_balance: boolean
  all_payments_need_human_approval: boolean
  payments_recorded_in_db: number
  notes: string[]
}

export interface LastRun {
  run_id: string
  finished_at: string
  decision: string
  final_call: string
  assigned_agents: AgentName[]
  customer_message: string | null
  blockers: string[]
  purchase_orders: PurchaseOrder[]
  safety: Safety
  approval_ids: string[]
}

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  status: string
  created_at: string
  is_open: boolean
  is_resolved: boolean
  running: boolean
  pending_approvals: number
  last_run: LastRun | null
}

export interface TicketsResponse {
  date_today: string
  count: number
  open: number
  resolved: number
  running_run_id: string | null
  tickets: Ticket[]
}

export interface BoardEvent {
  seq: number
  time: string | null
  run_id: string | null
  ticket_id: number | null
  agent: string | null
  depth: number | null
  loop_step: number | null
  kind: string
  text: string
  detail: Record<string, unknown> | null
}

export interface EventsResponse {
  last_seq: number
  running_run_id: string | null
  count: number
  events: BoardEvent[]
}

export interface Approval {
  approval_id: string
  ticket_id: number
  run_id: string
  kind: 'invoice' | 'rent' | 'purchase_order'
  ref_id: number | null
  payee: string
  amount: number
  account: string
  reason: string
  status: string
  created_at: string
  purchase_order?: PurchaseOrder
}

export interface PendingResponse {
  count: number
  total: number
  payments: Approval[]
}

export interface Obligation {
  kind: string
  ref_id: number
  payee: string
  amount: number
  due_date: string
  is_overdue: boolean
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  date_today: string
  upcoming_obligations: Obligation[]
  balance_after_obligations: number
}

export interface ApproveResult {
  approval: Approval
  balance_after: number
  effects: string[]
  ticket_pending_approvals: number
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(0, `Can't reach the backend at ${API_BASE}. Is uvicorn running?`)
  }
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = body?.detail
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join('; ') : res.statusText
    throw new ApiError(res.status, message)
  }
  return body as T
}

export const api = {
  tickets: () => request<TicketsResponse>('/api/tickets'),
  runTicket: (id: number) => request<{ run_id: string; ticket_id: number; status: string }>(`/api/tickets/${id}/run`, { method: 'POST' }),
  events: (since: number) => request<EventsResponse>(`/api/events?since=${since}&limit=1000`),
  pending: () => request<PendingResponse>('/api/payments/pending'),
  approve: (approvalId: string, approvedBy: string) =>
    request<ApproveResult>(`/api/payments/${encodeURIComponent(approvalId)}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy, confirm: true }),
    }),
  cash: () => request<Cash>('/api/cash'),
  reset: () => request<{ ok: boolean; checking_balance: number }>('/api/reset', { method: 'POST' }),
}

export const money = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
