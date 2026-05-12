# Habit-Formation Plan: 14-Day Trial → Daily Ritual

Turn a curious, "I-don't-really-know-what-this-is" research administrator into a daily Vandalizer user before the trial expires.

## 1. What ritual we're actually building

Name it. Without a name, every team builds something different.

**The ritual: "Morning Intake."** Every weekday morning, the research admin opens Vandalizer first thing, looks at a short briefing of what changed and what needs them, triages 1–3 items in chat, and closes. Three to five minutes minimum, expandable to thirty.

This is the only ritual that fits a research admin's actual workday — they already triage email, awards portals, and sponsor sites every morning. We're inserting Vandalizer into a slot they already have, not creating a new one.

Everything else (cert, workflows, KB, team) is a **deepening** of this ritual, not a competitor to it.

## 2. The habit loop

- **Cue**: 8am email + (eventually) calendar event + browser pin. Email is the wedge for week 1; we want them to stop needing it.
- **Action**: Click the briefing → land in chat → triage. Single-click.
- **Reward**: Variable. Some days new KB matches, some days a quality alert, some days a teammate's published workflow, some days "you saved 47 minutes this week." Variability matters more than magnitude.
- **Investment**: Each session adds to their personal KB, conversation history, saved searches, certification XP, and team library. By day 10 they shouldn't want to abandon the corpus.

## 3. Trial day-by-day

| Day | Mechanic | Purpose |
|-----|----------|---------|
| 0 | Role-tailored chat opener + "first real task in <5 min" guided flow ending with quality badge | One real win, not a tour |
| 1 | First 8am Morning Briefing (seeded if needed); "Day N of 14" trial orientation visible | Establish the cue |
| 2 | Briefing #2; chat continuity ("yesterday you asked about X…") | Prove the system remembers |
| 3 | If silent: day-3 nudge tied to *what they missed in their briefing*, not generic | Catch the first drop-off |
| 4–6 | Daily briefing, variable reward categories rotate; team activity introduced | Build the rhythm |
| 7 | "Saved-time counter" reveal + Cert Module 1 framed as "graduate from helper to power user" | First identity shift |
| 8–10 | Suggested workflows from their actual usage; personal templates surface as artifacts they own | Investment |
| 11 | T-3 expiry warning framed by what they'd lose (corpus, streak, saved time) | Loss aversion |
| 12 | "Your 12 days" recap card in chat | Status snapshot |
| 14 | Conversion path + 14-day extension offer for cert-active users | Soft landing |

The shape: **value in day 0, cue by day 1, recovery on day 3, investment by day 7, conversion-ready by day 11.**

## 4. Mechanics to build

In rough impact-to-effort order.

### 4.1 Morning Briefing Engine *(linchpin)*

New `engagement_service.compute_daily_briefing(user)` aggregating, for the last 24h:

- The user's own `ActivityEvent`s (workflow runs, KB queries, extractions)
- Due items / deadlines from their documents and folders
- Team activity (teammates publishing workflows, KB approvals, quality alerts on shared docs)
- New validated KB items relevant to their `role_segment`
- Suggested next actions based on prior usage

Two surfaces:

- **8am email** sent by Celery beat (new task `engagement-morning-briefing`, daily at 08:00 user-local where possible, else org-default)
- **Chat-injected assistant card** on next login (`chat_service` checks for an unread briefing for today and prepends it)

Variable categories so consecutive days don't feel identical. Briefings are never empty — see §7.

### 4.2 Demo-aware re-engagement

The existing 30-day inactivity nudge is useless inside a 14-day trial. Add:

- **Day-3 silent nudge**: if `demo_status=active` and no login since day 1, send a nudge that *quotes the missed briefing's actual content*. The nudge IS the briefing.
- **Day-7 silent nudge**: same pattern, escalated copy ("you're halfway through your trial — here's what's been piling up").
- Cooldown: max one nudge per 48h.
- Driven by a new Celery task `engagement-demo-silent-nudges` (daily at 09:30).

### 4.3 Role-tailored chat opener

`role_segment` is already captured at registration. Gate:

- First-session **system prompt addendum** by role (compliance posture vs. PI posture vs. sponsored-programs posture).
- The 3–4 **suggested-task pills** on empty chat (e.g., compliance officer sees "Check an IRB protocol for missing required elements" / PI sees "Extract budget categories from an NIH proposal").

Persist a `first_session_completed` boolean on `User` (the field already exists but is never set — wire it on first successful chat interaction).

### 4.4 Trial-day orientation UI *(not a streak)*

- Persistent header element on workspace pages: "Day N of 14" + next briefing time.
- **No streak, no point total, no daily-login reward.** University research administrators on workday tasks find gamification patronizing; see [[feedback_audience_mechanics]]. Return-pull comes from briefing content quality and continuity, not from behavioral coercion.
- Engagement-day data (`User.briefing_opened_dates`) is still collected for analytics + retention cohorts, but not surfaced as a streak number to the user.
- Certification keeps its own XP/levels — that's a credentialing track and the audience expects mastery mechanics there. The main workday surface does not.

### 4.5 In-app notification surface

The `notifications` router exists; wire frontend.

- Bell icon with unread count in workspace nav.
- Triggers: teammate publishes workflow, KB approval lands, quality alert fires on user's doc, user's workflow completes (long-running).
- Each notification is a deep-link into chat with the relevant artifact already loaded.

### 4.6 Continuity memory in chat

- At end of each session, agent writes a 1-line "next time, you could…" hint to the conversation.
- Next session, agent leads with that open thread (e.g., "Yesterday you asked about NIH F&A rates — want me to pull the latest from your award letter?").
- Trivial to implement on top of existing `chat_service` + conversation storage. Outsized perceived-intelligence payoff.

### 4.7 Variable-reward rotation

Briefing engine selects 1–3 categories per day from:

`{ my-activity, team-activity, kb-news, deadline, suggested-action, time-saved, achievement }`

Constraint: never the same single category two days in a row. Pure scheduling logic on top of §4.1.

### 4.8 Time-saved counter

- Per `ActivityEvent` kind, attach a minutes-saved estimate (extraction ≈ 6 min, workflow run ≈ 15 min, KB answer ≈ 3 min — calibrate later).
- Sum visible daily on the workspace header; cumulative across trial.
- Frame the day-12 recap card around this number.

### 4.9 First-task scaffold replaces tour step 3

Drop the cert-plug slide from `FirstRunTour.tsx`. Replace with a one-shot guided real-document upload → extraction → quality-badge reveal. Cert offer moves to the day-7 email and the workspace nav.

## 5. Sequencing

- **Sprint 1 — Foundation.** Briefing engine v0 → 8am email job → role-tailored opener → "Day N of 14" trial orientation. Without these, nothing else matters.
- **Sprint 2 — Pull.** Demo-aware day-3 + day-7 nudges → in-app notifications wired → continuity memory → suggested-task pills.
- **Sprint 3 — Reward + investment.** Variable-reward rotation → time-saved counter → team activity in briefing → achievement drops.
- **Sprint 4 — Instrument + tune.** Day-N retention dashboard → A/B briefing variants → optimize the day-11–14 conversion path.

## 6. Instrumentation

Wire the existing `first_session_completed` flag (currently dead).

New fields on `User`:

- `daily_briefing_opened_dates: set[date]`
- `time_saved_minutes_total: int`
- `last_briefing_sent_at: datetime`

Admin dashboard additions:

- Per-trial-day retention cohort (day-0, day-1, … day-14 active)
- Briefing email open rate and in-app open rate, separately
- Day-3 nudge recovery rate (% of day-3-silent users who returned within 48h of nudge)
- Conversion-by-cohort (trial → paid, by number of briefings opened during trial)

**North-star metric:** % of trial users active on ≥7 of 14 days.
**Secondary:** % active on day 14 (the conversion-ready cohort).
**Counter-metric:** unsubscribe rate on Morning Briefing — if this climbs above 8%, the briefing content is bad.

## 7. What we deliberately don't do

- **No leaderboards or public point totals** outside certification. Research admins find game mechanics patronizing for their actual job.
- **No notifications outside business hours.** Cue must respect the workday.
- **No empty briefings.** If the system has nothing real, surface a curated KB highlight or a "did you know" — never silence.
- **Certification stays a parallel track**, not the on-ramp. The on-ramp is one real task in chat, day 0.
- **Don't ship the briefing email without the in-app surface.** They reinforce each other; either alone trains the wrong habit (email-only = inbox tool; in-app-only = forgettable).
- **Don't replace the existing agentic drip wholesale.** The drip teaches the product's surface area; the briefing builds the habit. Run them in parallel and measure whether the drip can be slimmed down later.

## 8. The bet

If the Morning Briefing is good enough that **≥60% of trial users open at least one within 48 hours of the first send**, this plan works. If it isn't, no amount of streaks, nudges, or counters will rescue it.

Spend disproportionate effort on briefing content quality and first-day seeding. That is the linchpin.

---

## Appendix A — Briefing content guardrails

A good briefing answers three questions for the user, in order:

1. **What changed since I was last here?** (team activity, KB updates, your workflow completions)
2. **What needs me today?** (deadlines, quality alerts, approvals, pending reviews)
3. **What's one thing I could try?** (suggested-action, calibrated to their role and prior usage)

Length cap: ~5 items total. If we have more, rank by relevance and cut. A briefing that takes more than 60 seconds to read fails.

## Appendix B — Why the existing 5-step agentic drip is not enough

The drip explains the product's surface area (chat, KB, extraction, workflow, verification) over 14 days. It does not build a daily return habit because:

- It pulls 5 times in 14 days — far below daily cadence.
- It teaches *features*, not *moments*. A user can finish the drip and still have no reason to open the app on day 8.
- It cannot reference the user's actual content, only generic capabilities.

The Morning Briefing complements the drip: drip = "what can this do," briefing = "what does this have for me today." Both should ship.

## Appendix C — Open questions for v2

- Calendar integration (.ics for the morning slot) — opt-in?
- Slack/Teams briefing delivery for orgs that don't want another email?
- Briefing personalization beyond `role_segment` — should we cluster on actual usage patterns by week 2?
- Should streak survive weekends or treat M–F as the unit?
