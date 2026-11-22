# 23 — Testing the Real OneClarity.ai Website

Step-by-step process for pointing the QA agent at your company's own web app, plus which Azure model to use.

## 23.1 Choose the model

You have three deployments in Azure AI Foundry. Measured on the Demo Shop (2026-10-13):

| Deployment | Result | Time | Cost per run |
| --- | --- | --- | --- |
| gpt-5-nano | Ran end to end but found **0 of 6** bugs; invented a missing "cart page" and gave up | 3–5 min | ~$0.02–0.04 |
| **gpt-5-mini** | Found **2 real bugs** (wrong password accepted, wrong total for quantity 12) with screenshots, then paused for approval | 3 min | **~$0.14** |
| gpt-4o-mini | Not measured. Older, cheaper model; weaker at long multi-step tool use than gpt-5-mini | – | lower |

**Use `gpt-5-mini`.** It is now the default in `backend/.env` (`AZURE_OPENAI_DEPLOYMENT=gpt-5-mini`, cost rates $0.25 / $2.00 per 1M tokens, list price; confirm on your Azure pricing page). You can also set a different deployment per agent on **Agents → QA Agent → Overview → Azure deployment**.

> The generic step-by-step checklist (and the exact oneclarity.ai configuration that is already set up) is in [25-setup-any-website.md](25-setup-any-website.md).

## 23.2 Prepare (once)

1. **Use a non-production environment.** Ask your team for the staging / UAT URL of oneclarity.ai. The agent clicks buttons and submits forms; never point it at production with real customer data.
2. **Create a dedicated test account** on that environment:
   - no MFA / OTP and no CAPTCHA on login (or allow-list the account), otherwise the agent gets stuck at login;
   - test data only; permission to submit forms.
3. **Network:** the agent's browser runs on the machine that runs the worker (today: your Mac). If staging is behind VPN or IP allow-listing, connect the VPN on that machine.
4. **Find the extra domains the site loads.** Open staging in Chrome → DevTools → Network → reload, and note other domains it calls: CDN, fonts, analytics, login provider (Auth0, Microsoft / Google login, Cognito…), API host (e.g. `api.oneclarity.ai`). The agent's browser is locked to the base URL's domain and blocks everything else unless you list it (see step 5). Use `*` only if you trust the site completely.

## 23.3 Set it up in the console

5. **Target apps → Add target**
   - Name: `OneClarity staging`
   - Base URL: your staging URL
   - Environment: `Staging`
   - Test login: the test account from step 2
   - **Extra allowed domains**: the domains from step 4 (one per chip)
   - Notes for the agent: rules for this site, e.g. "Do not delete projects", "Use company 'QA Test Co'", "Payments use test card 4242…".
   - Repository (optional): GitHub repo URL, if you want approved bugs filed as GitHub issues (also add a secret named `github-token`).
6. **Tasks → New task.** Start small and specific:
   - Title: "Smoke test: login and dashboard"
   - Goal: "Check that a user can log in, see the dashboard and log out."
   - Pages: `/login`, `/dashboard`
   - Acceptance criteria: 2–4 Given / When / Then lines
   - Bug filing: off for the first run
7. **Agents → QA Agent**: runtime **OpenAI Agents SDK · Azure**; check the per-run budget ($3 default) and max turns (80).

## 23.4 Run and review

8. Restart `./scripts/dev.sh` if you changed `.env`, then **Run now** on the task.
9. Watch the live log and the "What the agent sees" screenshot. Cancel if it goes off track.
10. Review the result:
    - Test results tab: is each pass / fail correct? Check the screenshots.
    - Bugs tab: are the bugs real and reproducible? Reject false ones with a comment.
11. Improve and repeat:
    - add facts the agent got wrong to the target's **Notes**;
    - make acceptance criteria more specific;
    - for repeated mistakes, edit the agent's **Instructions** (Agents → Instructions tab).
12. When results are reliable, widen the scope (more pages and features), then turn on bug filing.

## 23.5 What to expect and limits today

- One run covers one task; keep tasks to 1–3 features for good results.
- The agent cannot pass MFA, CAPTCHA, email verification links or SMS codes.
- File uploads and arbitrary JavaScript in the browser are blocked on purpose.
- Page content and screenshots are sent to your Azure OpenAI deployment (your tenant) for the model to read.
- Screenshots and logs stay on the worker machine (`backend/var/`).
- Runs start only when you press **Run now** (see [24-how-and-when-agents-run.md](24-how-and-when-agents-run.md)).
