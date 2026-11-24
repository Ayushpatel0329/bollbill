# BOLL BILL: backend + AI

```
bollbill/
  DEPLOY.md                step-by-step: Supabase, Render, Netlify, tests, troubleshooting
  supabase/schema.sql      database: tables, security rules, functions (run once in Supabase)
  backend/                 AI service (Python, FastAPI) -> talks to Claude
    app/main.py            endpoints: /agent/chat, /agent/voice-bill, /agent/actions/...
    app/tools.py           what the AI is allowed to do (read tools + one "ask owner first" action)
    app/agent.py           Claude calls (prompts, tool loop)
    app/drafts.py          checks everything the AI returns for a voice bill
    app/analytics.py       sales / udhaar / stock calculations (no AI involved)
    app/auth.py, db.py     login-token check, database client (uses the USER's token)
    tests/                 offline tests
    .env.example           the settings the service needs
    Dockerfile
  frontend/index.html      your app: landing + login + onboarding + cloud sync + Assistant tab
  frontend/tests/          offline sync test
```

## How the pieces connect

```
Browser (index.html)
   |-- login, shop, items, bills --> Supabase (Auth + Postgres, protected by Row Level Security)
   |-- "AI se bill banao", Assistant --> AI service --> Claude
                                            |
                                            +--> Supabase, with the logged-in user's own token
```

* The browser keeps working like before (instant, even offline). Every change is copied to Supabase in the background.
* If `BB_CONFIG` in `index.html` is empty, the app runs in **local demo mode** (data only in that browser).
* The AI service never has a master database key. It uses the user's token, so the AI can only see
  the logged-in owner's own shop.
* The Claude API key lives only in the AI service, never in the HTML.

## What the AI can and cannot do

| Can (reads, answers directly) | Cannot without the owner tapping "Haan" |
|---|---|
| today / week / month sales, GST collected | mark udhaar as paid (one bill or a whole customer) |
| udhaar per customer | |
| low stock, top selling items, find a bill | |
| turn a spoken sentence into a **draft** bill (nothing is saved; the app shows it) | |

It cannot delete anything, change prices, or create bills by itself. Every AI call is logged in `agent_runs`.

## Run the tests (no internet needed)

```
cd backend && python -m tests.test_backend      # 14 tests: bill maths, reports, AI-output checks, tools, agent loop
node frontend/tests/sync_harness.js             # 15 checks: cloud sync, 2 devices, offline, number clashes
```

## Known limits of this version

* Login is email + password. Mobile-number OTP needs an SMS provider (MSG91/Twilio) and costs money; add later.
* Two devices editing the price list at the same moment: the last save wins.
* The app screen shows the latest 500 bills (plus every unpaid udhaar bill, whatever its age).
* "Delete all saved bills" in History also deletes the cloud copy (hard delete). Change to soft delete before you rely on it for accounts.
* Rate limits are kept in the memory of one server process; use Redis if you run several.
* `agent_runs` can be edited by the shop owner, so treat it as a debugging log, not a tamper-proof audit trail.
