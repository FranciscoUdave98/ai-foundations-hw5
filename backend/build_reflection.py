"""Write Francisco's Problem 10 reflection into the Reflections tab of output/desk_tickets.html.

The text is his reflection, paraphrased and tightened; the numbers come from the
Problem 9 runs (see output/resolved_tickets.json).

    python build_reflection.py
"""

from __future__ import annotations

import re

from build_reports import ICONS
from config import OUTPUT_DIR


def tools(*names: str) -> str:
    return " ".join(f'<span class="tool">{n}</span>' for n in names)


def who(*agents: str) -> str:
    return "".join(f'<span class="rf-ic" title="{a}">{ICONS[a]}</span>' for a in agents)


CSS = """
  .rf { display: grid; gap: 22px; }
  .rf h2.rf-title { margin: 0; font-family: Georgia, serif; color: var(--navy); font-size: 26px; }
  .rf .rf-lead { margin: 4px 0 0; color: var(--muted); font-size: 15px; }
  .rf-hero { display: grid; grid-template-columns: 1.4fr 1fr; gap: 18px; align-items: center; padding: 22px 24px; border-radius: 16px;
    background: linear-gradient(120deg, #0b2a5b, #1d4ed8); color: #fff; }
  .rf-hero h3 { margin: 0 0 6px; font-family: Georgia, serif; font-size: 22px; }
  .rf-hero p { margin: 0; color: #dbe6ff; line-height: 1.55; }
  .rf-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .rf-stat { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.25); border-radius: 12px; padding: 10px 12px; text-align: center; }
  .rf-stat b { display: block; font-size: 24px; font-family: Georgia, serif; }
  .rf-stat span { font-size: 12px; color: #dbe6ff; }
  .rf-sec { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px 20px; }
  .rf-sec > h3 { margin: 0 0 4px; font-family: Georgia, serif; color: var(--navy); font-size: 20px; }
  .rf-sec > .q { margin: 0 0 14px; color: var(--muted); font-size: 14px; font-style: italic; }
  .rf-grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
  .rf-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  @media (max-width: 1000px) { .rf-grid3, .rf-grid2, .rf-hero { grid-template-columns: 1fr; } }
  .rf-card { border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; background: var(--blue-50); display: grid; gap: 8px; align-content: start; }
  .rf-card h4 { margin: 0; font-size: 16px; color: var(--navy); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .rf-grade { margin-left: auto; font-size: 12px; font-weight: 800; padding: 3px 10px; border-radius: 999px; background: var(--green-bg); color: var(--green); }
  .rf-grade.mid { background: var(--amber-bg); color: var(--amber); }
  .rf-crew { display: flex; gap: 4px; }
  .rf-ic .ic { width: 26px; height: 26px; }
  .rf-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; font-size: 14px; line-height: 1.45; }
  .rf-list li { padding-left: 24px; position: relative; }
  .rf-list li::before { position: absolute; left: 0; top: 0; font-weight: 800; }
  .rf-list .good::before { content: '✓'; color: var(--green); }
  .rf-list .watch::before { content: '!'; color: var(--amber); left: 5px; }
  .rf-list .same::before { content: '='; color: var(--navy); }
  .rf-list .plus::before { content: '+'; color: var(--blue); }
  .rf-verdict { font-size: 13px; font-weight: 700; color: var(--navy); background: #fff; border-radius: 8px; padding: 6px 10px; border: 1px dashed var(--line); }
  table.rf-table { width: 100%; border-collapse: collapse; font-size: 14px; }
  .rf-table th { text-align: left; background: var(--navy); color: #fff; padding: 9px 12px; font-weight: 600; font-size: 13px; }
  .rf-table td { padding: 10px 12px; border-top: 1px solid var(--line); vertical-align: top; line-height: 1.45; }
  .rf-table td:first-child { font-weight: 700; color: var(--navy); white-space: nowrap; }
  .rf-match { font-size: 12px; font-weight: 800; padding: 2px 9px; border-radius: 999px; background: var(--green-bg); color: var(--green); white-space: nowrap; }
  .rf-side h4 { margin: 0 0 6px; color: var(--navy); }
  .rf-side.one { border-top: 4px solid var(--blue); }
  .rf-side.team { border-top: 4px solid var(--navy); }
  .rf-take { margin: 12px 0 0; padding: 10px 14px; border-radius: 10px; background: var(--amber-bg); color: #78350f; font-weight: 600; font-size: 14px; }
  .rf-num { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; background: var(--navy); color: #fff; font-weight: 800; font-size: 14px; flex: none; }
  .rf-num.no { background: var(--red); }
  .rf-need { font-size: 13px; color: var(--muted); }
  .rf-need b { color: var(--ink); }
  .rf-new { display: inline-block; font-size: 12px; font-weight: 700; padding: 2px 9px; border-radius: 999px; background: var(--red-bg); color: var(--red); margin: 2px 4px 2px 0; }
"""

BODY = f"""
<div class="rf">
  <div>
    <h2 class="rf-title">Reflections</h2>
    <p class="rf-lead">Looking back at how the Campus Customs agent team handled the board, measured against my Expected plan and the real Problem 9 runs.</p>
  </div>

  <div class="rf-hero">
    <div>
      <h3>Verdict: a disciplined team that knew its limits</h3>
      <p>Coach Dan only brought in the agents each ticket actually needed. Nobody invented stock or prices, nobody paid a cent without my signature, and the discount call came back to me instead of being made up. The one thing I'd fix is how Sunny talks about pending discounts.</p>
    </div>
    <div class="rf-stats">
      <div class="rf-stat"><b>18/18</b><span>expectations met</span></div>
      <div class="rf-stat"><b>0</b><span>agents who weren't needed</span></div>
      <div class="rf-stat"><b>$0</b><span>paid without a human</span></div>
    </div>
  </div>

  <section class="rf-sec">
    <h3>1 · How the agents performed on each ticket</h3>
    <p class="q">How would you evaluate the performance of the agents on each ticket and why?</p>
    <div class="rf-grid3">
      <div class="rf-card">
        <h4>#101 Bulldog tee <span class="rf-crew">{who('boss', 'inventory', 'accounting', 'customer_service')}</span><span class="rf-grade">Strong</span></h4>
        <ul class="rf-list">
          <li class="good"><b>Stacks</b> confirmed size S was out of stock (0 on hand) without guessing.</li>
          <li class="good"><b>Penny</b> caught that invoice 501 ($840) was unpaid and 3 days overdue, the real reason Bulldog Print Co wouldn't reprint.</li>
          <li class="good"><b>Coach Dan</b> put the order on hold instead of pretending it could ship.</li>
          <li class="good">Nobody paid the invoice on their own; it waited for my signature.</li>
          <li class="good"><b>Sunny</b> told Tauhid the truth: size S is out, the restock isn't confirmed, so no delivery date, and asked if another size would work.</li>
        </ul>
        <div class="rf-verdict">Right call, right reasons, no made-up facts.</div>
      </div>
      <div class="rf-card">
        <h4>#102 Rent due <span class="rf-crew">{who('boss', 'facilities', 'accounting')}</span><span class="rf-grade">Strong</span></h4>
        <ul class="rf-list">
          <li class="good"><b>Keys</b> confirmed the lease against the database: $2,400 for the Chapel Street shop, due 2026-09-02.</li>
          <li class="good">Used <b>desk.date_today</b> correctly: due in 2 days, <i>not</i> overdue.</li>
          <li class="good"><b>Penny</b> checked the cash for rent <i>and</i> the overdue invoice together ($3,240 of $3,400 → $160 left), not just the rent alone.</li>
          <li class="good">The rent was prepared as a payment request for me to sign, not paid.</li>
        </ul>
        <div class="rf-verdict">Lean: only the two agents the ticket needed.</div>
      </div>
      <div class="rf-card">
        <h4>#103 Bulk hoodie discount <span class="rf-crew">{who('boss', 'inventory', 'accounting', 'customer_service')}</span><span class="rf-grade mid">Strong, one miss</span></h4>
        <ul class="rf-list">
          <li class="good"><b>Stacks</b> found the shortfall: 8 size M on hand for 20 requested (short 12), plus a 5-day reprint that's blocked by invoice 501.</li>
          <li class="good"><b>Penny</b> priced real options (5%, 10%, 15% off) from cost and list price.</li>
          <li class="good"><b>Coach Dan</b> didn't pick a random discount and sent the decision to me.</li>
          <li class="watch"><b>Sunny's</b> draft listed every discounted price while saying they're "pending review". A student club could read that as an offer. Better: "we're reviewing a group price and will confirm it."</li>
        </ul>
        <div class="rf-verdict">Great judgment; the customer message needs tighter wording.</div>
      </div>
    </div>
  </section>

  <section class="rf-sec">
    <h3>2 · Actual vs. my Expected plan</h3>
    <p class="q">For each ticket, how did Actual compare to the Expected plan you wrote earlier?</p>
    <table class="rf-table">
      <thead><tr><th>Ticket</th><th>What matched</th><th>What was different</th><th>Score</th></tr></thead>
      <tbody>
        <tr><td>#101</td>
          <td>Coach Dan called Inventory, and Accounting checked invoice 501, just as planned. They used {tools('get_ticket_details', 'check_item_availability', 'check_invoice_payment')} and realized the order couldn't be completed. Facilities stayed out.</td>
          <td><b>Customer Service</b> joined, which I hadn't planned. It was a good add, since Tauhid needed a reply. They also checked the vendor and the cash, which helped explain <i>why</i> the order was stuck.</td>
          <td><span class="rf-match">7 / 7</span></td></tr>
        <tr><td>#102</td>
          <td>Facilities went first, then Accounting, in the order I planned. They used {tools('get_lease_details', 'get_cash_balance')}, and the payment waited for human approval.</td>
          <td>Penny added {tools('check_cash_for_payment', 'check_invoice_payment')} to make sure the rent and the overdue invoice fit together. That was extra work, but useful.</td>
          <td><span class="rf-match">5 / 5</span></td></tr>
        <tr><td>#103</td>
          <td>The order was Inventory → vendor check → Accounting → Customer Service, as planned. They used {tools('check_item_availability', 'get_vendor_info', 'get_pricing')}, and the discount went to a human.</td>
          <td>Penny ran {tools('get_pricing')} six times to build the options. That was thorough but a bit chatty. The only real gap was Sunny's wording about pending prices.</td>
          <td><span class="rf-match">6 / 6</span></td></tr>
      </tbody>
    </table>
  </section>

  <section class="rf-sec">
    <h3>3 · When one agent with tools would have been simpler</h3>
    <p class="q">What would have been simpler as one agent with tools and why?</p>
    <div class="rf-grid2">
      <div class="rf-card rf-side one">
        <h4>One agent is enough when…</h4>
        <ul class="rf-list">
          <li class="plus">It's a <b>straight lookup</b>, like #102: read the lease, check the balance, prepare one payment. One agent with {tools('get_lease_details', 'get_cash_balance')} could do it in a single loop.</li>
          <li class="plus">That means <b>fewer model calls and handoffs</b>, so it's cheaper, faster, and there's less to audit.</li>
          <li class="plus">Questions like "what's the price of the cap?" or "how much is in checking?" don't need a meeting.</li>
        </ul>
      </div>
      <div class="rf-card rf-side team">
        <h4>A team earns its cost when…</h4>
        <ul class="rf-list">
          <li class="plus">The ticket <b>crosses departments</b> (stock + vendor + cash + customer), like #101 and #103.</li>
          <li class="plus">Roles have <b>different authority</b>: Accounting prepares money, Customer Service talks to customers, and only a human signs. Separate agents keep those lines clean.</li>
          <li class="plus">Each specialist sees <b>only its own tools</b>, so mistakes stay contained and every step is easy to trace in the audit trail.</li>
        </ul>
      </div>
    </div>
    <p class="rf-take">My take: route simple lookups to one agent, and save the full team for tickets that need several departments to agree.</p>
  </section>

  <section class="rf-sec">
    <h3>4 · Three new problems this team can already solve</h3>
    <p class="q">With the tools we built, no new code needed.</p>
    <div class="rf-grid3">
      <div class="rf-card">
        <h4><span class="rf-num">1</span> "Do we have overdue invoices?" <span class="rf-crew">{who('accounting')}</span></h4>
        <p>A manager asks for every bill that's past due. Penny pulls the full ledger and flags anything due before <b>desk.date_today</b>, plus which vendors are blocked because of it.</p>
        <div>{tools('check_invoice_payment', 'get_vendor_info')}</div>
      </div>
      <div class="rf-card">
        <h4><span class="rf-num">2</span> "Can we cover what's due soon?" <span class="rf-crew">{who('accounting', 'facilities')}</span></h4>
        <p>A manager wants to know if cash covers the next few weeks. Penny lists every bill and rent payment due within 30 days and the balance left after them, and tests any planned payment so the account never goes negative.</p>
        <div>{tools('get_cash_balance', 'check_cash_for_payment', 'get_lease_details')}</div>
      </div>
      <div class="rf-card">
        <h4><span class="rf-num">3</span> "How much is it, and is it in my size?" <span class="rf-crew">{who('customer_service', 'inventory')}</span></h4>
        <p>A customer asks the current price of an item. Stacks gives the real list price and stock by size, and Sunny answers without inventing a discount.</p>
        <div>{tools('get_pricing', 'check_item_availability')}</div>
      </div>
    </div>
  </section>

  <section class="rf-sec">
    <h3>5 · Three problems it can't solve yet, and what it would need</h3>
    <p class="q">These need data the database doesn't have, so they need new tools and agents.</p>
    <div class="rf-grid3">
      <div class="rf-card">
        <h4><span class="rf-num no">1</span> Forecasting demand to restock</h4>
        <p>Knowing <i>how many</i> hoodies to reorder before move-in week. We only have today's stock, with no sales history.</p>
        <p class="rf-need"><b>Data:</b> an orders / order_items table with dates.<br>
        <b>Tools:</b> <span class="rf-new">get_sales_history(sku, period)</span><span class="rf-new">forecast_demand(sku, weeks)</span><span class="rf-new">suggest_reorder(sku)</span><br>
        <b>Agent:</b> a <b>Planning</b> agent that turns forecasts into PO drafts for Accounting to cost and a human to sign.</p>
      </div>
      <div class="rf-card">
        <h4><span class="rf-num no">2</span> "Where's my order?"</h4>
        <p>Checking delivery status for a customer. We know the vendors (even QuickShip CT, the courier), but not their shipments.</p>
        <p class="rf-need"><b>Data:</b> a shipments table or the courier's tracking API.<br>
        <b>Tools:</b> <span class="rf-new">get_order_status(order_id)</span><span class="rf-new">track_shipment(tracking_no)</span><br>
        <b>Agent:</b> a <b>Logistics</b> agent that Sunny can ask, so customers get real ETAs instead of guesses.</p>
      </div>
      <div class="rf-card">
        <h4><span class="rf-num no">3</span> What's actually popular?</h4>
        <p>Ranking products by past purchases to decide what to feature, discount, or drop. No purchase data exists today.</p>
        <p class="rf-need"><b>Data:</b> purchase history by product, size, and date.<br>
        <b>Tools:</b> <span class="rf-new">top_products(period, category)</span><span class="rf-new">sell_through_rate(sku)</span><br>
        <b>Agent:</b> a <b>Merchandising</b> analyst agent that reports to Coach Dan and works with Penny on margins before any price change.</p>
      </div>
    </div>
  </section>
</div>
"""


def main() -> None:
    p = OUTPUT_DIR / "desk_tickets.html"
    s = p.read_text(encoding="utf-8")
    block = f"<!--REFLECT-START--><style>{CSS}</style>{BODY}<!--REFLECT-END-->"
    if "<!--REFLECT-START-->" in s:
        s = re.sub(r"<!--REFLECT-START-->.*?<!--REFLECT-END-->", lambda m: block, s, flags=re.S)
    else:
        s = s.replace('<div class="empty"><h2>Reflections</h2></div>', block, 1)
    p.write_text(s, encoding="utf-8")
    print("Reflections tab written")


if __name__ == "__main__":
    main()
