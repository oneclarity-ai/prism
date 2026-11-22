# 25 — Set Up the QA Agent for Any Website (Step by Step)

Use this checklist every time you want the QA agent to test a new website. Section 25.8 shows the exact setup already created for **www.oneclarity.ai**.

## 25.1 Before you start (5 minutes)

| Check | Why | How |
| --- | --- | --- |
| Which environment? | The agent really clicks and submits | Prefer **staging / UAT**. Use production only for read-only checks (25.6) |
| Test account (if the site has login) | The agent signs in like a user | A dedicated account; **no MFA / OTP / CAPTCHA / email codes** |
| Network access | The browser runs on the worker machine (your Mac today) | Connect VPN if the site is internal |
| Model | Quality of testing | `gpt-5-mini` (default). gpt-5-nano is too weak (see [23](23-testing-oneclarity-ai.md)) |
| Worker running | Runs stay "Queued" otherwise | `./scripts/dev.sh` (red banner in the console if not) |

## 25.2 Find the pages and outside domains

1. Open the site in Chrome. Note the main pages from the header and footer menus (e.g. `/pricing`, `/login`).
2. Open **DevTools → Network**, tick "Preserve log", reload, click around.
3. Note every **other domain** the site loads, grouped by need:

| Group | Examples | Add to extra domains? |
| --- | --- | --- |
| Site's own API / subdomains | `api.example.com`, `app.example.com` | **Yes** (the site breaks without them) |
| Fonts / CDN | `fonts.googleapis.com`, `fonts.gstatic.com`, `cdn.jsdelivr.net` | **Yes** (layout and icons) |
| Login provider (SSO) | `accounts.google.com`, `login.microsoftonline.com`, `*.auth0.com` | Yes, if the agent must sign in through it |
| Analytics / tracking | `googletagmanager.com`, `google-analytics.com`, `hotjar.com` | **No**: keeps test traffic out of your analytics |
| Chat widgets, ads | `intercom.io`, `doubleclick.net` | No, unless you test them |

Tip: put `*` as the only extra domain to allow everything (fast first try, less safe).

## 25.3 Add the target app (console → Target apps → Add target)

| Field | What to enter |
| --- | --- |
| Name | e.g. `Acme portal (staging)` |
| Base URL | Home page, e.g. `https://staging.acme.com` |
| Environment | Local / Dev / Staging / **Production** (production shows a warning) |
| Test login | Username + password of the test account (stored encrypted) |
| Extra allowed domains | The "Yes" domains from 25.2, one chip each |
| Repository | GitHub repo URL, only if approved bugs should become GitHub issues (also add secret `github-token`) |
| Notes for the agent | House rules, test data and things to avoid (template below) |

Notes template:

```
Environment: STAGING. Safe to submit forms with test data.
Test data: use company "QA Test Co", email qa+<anything>@example.com, card 4242 4242 4242 4242.
Never: delete existing records, change account settings, send real emails, invite users.
Known issues (do not report): the chart on /reports loads slowly.
```

## 25.4 Create the first task (console → Tasks → New task)

Start **small**: one flow, 2–5 acceptance criteria. Good first tasks:

| Task | Pages | Acceptance criteria (Given / When / Then) |
| --- | --- | --- |
| Smoke: pages load | `/`, 3–6 main pages | Every page loads without error or 404; no console errors |
| Login | `/login` | Wrong password shows an error and stays logged out; correct login reaches the dashboard; log out works |
| One form | `/contact` | Empty required fields show errors; invalid email is rejected; valid data shows success (staging only) |

Keep **Allow filing bugs** off for the first runs. Turn it on when results are trustworthy.

## 25.5 Check the agent (console → Agents → QA Agent)

| Setting | Recommended |
| --- | --- |
| Agent runtime | OpenAI Agents SDK · Azure |
| Azure deployment | empty (= default `gpt-5-mini`) or a specific deployment |
| Max turns per run | 150 (a turn = one model call; each click counts) |
| Budget per run | $3 (gpt-5-mini runs cost ~$0.10–0.50) |
| Tools | Browser, test plan, results, bugs: Allowed. `file_bug`: Ask first |

## 25.6 Production sites: read-only rules

When the base URL is production (like www.oneclarity.ai):

- Notes must say: **never submit forms with valid-looking data**, only test validation with empty fields or `not-an-email`.
- No real names, emails or phone numbers. No "Sign in with Google". No demo bookings or trials.
- Leave analytics domains out of the extra domains (25.2) so runs do not count as visitors.
- Bug filing off.

## 25.7 Run, watch, improve

1. Task page → **Run now** → you land on the live run page.
2. Watch **Live log** and **What the agent sees**. **Cancel run** if it goes off track.
3. When it finishes, review **Test results** (check screenshots) and **Bugs**. Reject false bugs with a comment.
4. Improve and repeat:
   - wrong assumptions about the site → add facts to the target's **Notes**
   - missed checks → add **acceptance criteria**
   - repeated bad habits → edit the agent's **Instructions**
   - stopped at max turns → narrow the task or raise **Max turns**
5. Follow details in the worker log: `tail -f backend/var/logs/worker.log` (see [21](21-logging-and-debugging.md)).

## 25.8 Example: www.oneclarity.ai (already set up for you)

**Target app: "OneClarity.ai (public site)"**

| Field | Value |
| --- | --- |
| Base URL | `https://www.oneclarity.ai` |
| Environment | Production |
| Test login | none |
| Extra allowed domains | `https://api.oneclarity.ai`, `https://trust.oneclarity.ai`, `https://fonts.googleapis.com`, `https://fonts.gstatic.com`, `https://api.fontshare.com`, `https://cdn.fontshare.com`, `https://www.gstatic.com`, `https://ssl.gstatic.com`, `https://accounts.google.com`, `https://www.google.com` |
| Left out on purpose | `googletagmanager.com`, `google-analytics.com`, Google Translate domains |
| Notes | Production rules: never submit Book demo / Contact / Sign up with valid data; validation only with empty or `not-an-email`; log in only with a fake account; no "Sign in with Google"; otherwise read-only |

How the domains were found: the site is a single-page app, so it was loaded in a headless browser and every network request was recorded (16 domains, 2026-10-13).

**Task: "Smoke test: oneclarity.ai public website"**

- Pages: `/`, `/how-it-works`, `/solutions`, `/use-cases`, `/pricing`, `/book-demo`, `/contact`, `/login`, `/signup`, `/documentation`, `/security`, `/status`
- Features: header navigation, footer links, pricing page, Book demo / Contact / Sign up form validation, login error message
- Acceptance criteria:
  1. Every header or footer link opens without an error or 404
  2. Book demo, Contact and Sign up show validation errors when required fields are empty
  3. `not-an-email` is rejected
  4. A wrong email and password show a clear error and stay logged out
  5. Main pages load without console errors
- Bug filing: off

To run it: **Tasks → Smoke test: oneclarity.ai public website → Run now**. Expect several minutes and roughly $0.10–0.50 with gpt-5-mini (estimate).

For a deeper test of the logged-in product, repeat 25.3–25.5 with your **staging app URL** and a **test account**, and use forms freely there.

## 25.9 Test one page, or choose pages per run

Three ways, from quickest to most permanent:

| Way | How | When |
| --- | --- | --- |
| **Run with options** (per run) | Task → **Run with options** → untick all pages except the one you want (or "Select none" and add a page such as `/pricing`) → **One agent** → **Start run** | Try one page now without changing the task |
| **Edit the task** (permanent) | Task → **Edit** → **Pages or URLs**: keep only the page(s) you want | The task should always test the same few pages |
| **One task per page** | Tasks → **New task** for each page or flow, e.g. "Pricing page", "Book demo form" | Run, schedule and track pages separately |

The agent tests **only** the pages of the run. It opens other pages only when needed to reach them (for example the login page first).

Example: only the oneclarity.ai pricing page:

1. Tasks → **Smoke test: oneclarity.ai public website** → **Run with options**.
2. **Select none**, then tick `/pricing`.
3. **One agent**, Max turns `30`, Budget `0.50`.
4. **Start run**. Expect a few minutes and a few cents.

The run page shows "This run tests only: /pricing". **Run again** on that page repeats the same choice.

All pages at once, faster: same dialog, keep all pages ticked, choose **Parallel agents** (see [26](26-parallel-agents-orchestration.md)). Example for oneclarity.ai's 12 pages: Agents at once `3`, Pages per agent `2` → 6 sub-agents, 3 working at a time, worst case 6 × $1.

Pages can be paths (`/pricing`, joined to the target's base URL) or full URLs on an allowed domain.


## 25.10 Who decides the scope and the test cases?

| What | Who decides | Where to change it |
| --- | --- | --- |
| **Scope** (pages, features, acceptance criteria) | **You**, when you create the task. The agent never changes it. | Task → **Edit scope** (or Edit) |
| **Test cases** | **The agent**, at the start of each run, from the scope + its instructions. Acceptance criteria become cases almost one to one. | Write more specific acceptance criteria; or edit the agent's Instructions |
| **House rules of a website** (test data, never-do list, known issues) | You, once per website | Target apps → **Notes for the agent** |
| **How the agent tests in general** (negative cases, evidence, bug format) | You, once per agent | Agents → QA Agent → **Instructions** |
| Pages for one run only | You, per run | Task → **Run with options** |

Every company tests differently. Put your own way of working in these four places:

1. **Acceptance criteria** for the must-pass checks of a page or flow ("Given a wrong password, when I log in, then an error shows and I stay logged out").
2. **Target notes** for site-wide rules ("use company 'QA Test Co'", "never delete projects", "payments use card 4242…").
3. **Agent instructions** for your QA standards (which negative cases are mandatory, severity rules, what counts as a bug).
4. **Runtime limits** (max turns, budget) per agent or per run.

### Why some test cases stay "Pending" / end as "Skipped"

The agent plans the cases first, then runs them one by one. A case has no result when:

- the run stopped early (max turns, budget, cancel); or
- the agent decided a case did not belong to its pages (common in parallel runs: a sub-agent for `/status` planned the Book-demo form checks from the shared acceptance criteria and then left them).

Since 2026-10-14:

- `complete_task` refuses once while planned cases have no result and tells the agent to run them or record them as **skipped with a reason**;
- when a run ends, any case still without a result is marked **Skipped** with a "Not run: …" note (never "Pending" forever);
- sub-agents are told to plan only cases they will run on their own pages.
