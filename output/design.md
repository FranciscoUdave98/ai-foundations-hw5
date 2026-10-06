# Design: Campus Customs Agent Desk (Problem 8)

The React + Vite + TypeScript dashboard in `frontend/` (`npm run dev` → http://localhost:5173, talking to the FastAPI backend at http://localhost:8000). These are Francisco's choices for the look and the reasons behind them.

## What Francisco asked for, and why

| Choice | What it looks like | Why Francisco wanted it |
|---|---|---|
| **Same colors and vibe as the HW4 Campus Customs site** | Yale navy `#00356B` on white, with navy tints only. Same Graduate + Fraunces type, same rounded cards, and the same Handsome Dan art (splash, header badge, empty states). | The desk should feel like part of the same shop. In HW4 he chose "white Yale navy colors" so the site looked like official Yale gear and built trust. The staff board keeps that identity instead of looking like a generic admin tool. |
| **"Awesome and personable"** | Every agent is a character with a nickname, icon, and voice: **Coach Dan** (Boss, Dan with a coach's whistle), **Stacks** (Inventory, a box tower with a tee), **Penny** (Accounting, ledger and coin), **Keys** (Facilities, the shop front and key), **Sunny** (Customer Service, a smiling speech bubble). | Five agents named "inventory" and "accounting" blur together. Named characters make it obvious who is talking, and make watching a run fun instead of reading logs. |
| **Fun phrases based on personality** | Each tool call becomes a line in that agent's voice: Stacks is "Counting size S in the stockroom", Penny is "Running the numbers twice: $3,240", Keys is "Pulling the Chapel Street lease", Coach Dan is "Calling a play: Penny, you're up!" and "Final whistle!". Idle agents are "Napping by the register". | His example for this problem. It's the same idea as HW4's "Sniffing out every hoodie…" loaders: a friendly voice keeps waits from feeling broken, and the line still says what is happening. |
| **Show what each agent says and does while it runs, and how they communicate** | **The team room:** Coach Dan sits at the top with the four specialists below, and dashed lines connect them. When someone delegates, the line between them lights up and flows, and a chip says who asked whom ("Coach Dan → Penny ×2"). Teammate-to-teammate requests arc between the two. Each avatar hops while working, tilts with a dashed ring while waiting on a teammate, and gets a green ✓ when done. A speech bubble shows its current line. **The play-by-play:** a live, auto-scrolling feed of every handoff (with the full request), every tool call (with its arguments), every tool result (click to expand), and what each agent said. | He wanted to see the multi-agent conversation itself, not just the final answer. The diagram shows the shape of the work at a glance (who's involved, who's waiting on whom), and the feed has the detail to audit it. |
| **Mark a ticket resolved when the run finishes** | The backend sets the ticket to `resolved` when the run ends. The card's pill turns green and a "RESOLVED" varsity stamp lands on it, with a toast. | A board needs a clear done state. The stamp reuses HW4's "stamp" headline motion. |
| **Short summary of what each agent did** | "The call" panel: Coach Dan's decision chip (Approved / With conditions / On hold…), the final call, blockers in red, Sunny's draft to the customer as a note card, and the safety check. Under "What each agent did", one row per agent: tools used, who they asked or answered, seconds spent, and their last words. | So he doesn't need to replay the feed to know the outcome. It also matches the "Actual" section of `desk_tickets.html`. |
| **Humans approve a payment or purchase when asked** | "Needs your signature" sits at the top of the right column. Each prepared payment or PO is a card that gently nudges, showing amount → payee, reason, and ticket. **Review & sign** opens a sheet with the amount, checking now vs. after, a warning if it would overdraw, a required **name** field, and an "I'm a human and I approve…" checkbox. A backend refusal (e.g. the vendor still has an unpaid invoice) shows the reason. | Human approval is the core safety rule. The UI makes it deliberate: nothing is pre-filled, nothing is automatic, and the agents can only prepare. |
| **Live checking balance** | A white card in the navy header: "Checking · live" with a pulsing green dot. It updates every few seconds and after every approval. The number rolls to its new value and flashes red when cash goes out. It also shows bills waiting and what's left after them. | Cash is the constraint behind every decision (only $160 left once rent and invoice 501 are paid), so it stays visible at all times. |
| **Uses `desk.date_today`** | A dashed "desk.date_today 2026-08-31" badge in the header. | The rule he gave for the whole homework. Showing it keeps "overdue" and "due in 2 days" honest on screen. |
| **Personal greeting** | "Hey Francisco! 3 open tickets on the desk today." It changes to "Every ticket is resolved. Go Bulldogs!" when the board is clear. | He asked to be called Francisco. It makes it his desk. |

## Carried over from HW4

- **Palette and type:** navy/white only. *Graduate* varsity lettering for names, amounts, and stamps; *Fraunces* for headings and quotes. Both are bundled locally with `@fontsource`, so there are no external requests.
- **Handsome Dan:** the original illustrations from HW4 (inspired by Yale's mascot, not Yale's trademarked logo). He appears on the splash ("Rounding up the team…"), in the header (wiggling while idle, ears flapping and nose sniffing during a run, like the HW4 chat's waiting state), in empty states, and as Coach Dan.
- **Motion that explains:** a paw-print progress bar trots across the top during a run, cards slide in one after another, and the "RESOLVED" stamp lands. As in HW4, **all motion turns off** for anyone who asks their device for reduced motion.
- **Friendly waiting states:** "Quiet in here. Every message, tool, and handoff will show up live", and "the team is working…" with walking paws.

## Layout

```
┌ navy header: Dan · Campus Customs Agent Desk · "Hey Francisco!" · desk.date_today · Checking (live) · ↺ Fresh run ┐
│ Ticket board        │ The team room (live diagram + speech bubbles)     │ Needs your signature          │
│  #101 #102 #103     │ Play-by-play (handoffs, tools, results, quotes)   │ The call + what each agent did│
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Left to right follows the work: pick a ticket → watch the team → sign and read the call. On narrower screens the right column moves below.

## Guardrails in the UI

- **Fresh run (reset)** asks for confirmation first and is disabled while a run is going.
- **One run at a time:** the other tickets' run buttons are disabled while the team is on the field, matching the backend's 409.
- **Approvals:** a name and the checkbox are required, and the backend still re-checks every rule (human approver, balance, unpaid-invoice block) before any money moves.

## Follow-up: less clutter, one bill per signature

Francisco flagged that invoice 501 appeared twice (requested by #101 and #103), and that the page wasted space and felt cluttered. Changes:

- **One card per bill.** Requests for the same bill are merged into one card ("Invoice payment · #101 · #103") with a single **Sign** button. Signing it closes the other request as *covered*, so no one is asked to pay twice. The backend enforces the same rule.
- **"What each agent did" moved to the center** as compact cards (four across), out of the narrow right column where text was cut off. The right column now holds only what needs action: signatures and the call.
- **A shorter play-by-play.** Each tool's result folds into its call row ("▸ result"). The "finished" and "picked up the request" rows are gone because the team room already shows them with ✓ and the wires. The feed is now about half as long and fills the empty space.
- **Clearer room.** Handoff labels sit right above the agent being asked ("from Coach Dan ×2") instead of stacking up under the Boss. LIVE only shows during a real run. Resolved tickets get a green edge instead of an overlapping stamp. A negative "leaves" amount in the cash card turns red.
