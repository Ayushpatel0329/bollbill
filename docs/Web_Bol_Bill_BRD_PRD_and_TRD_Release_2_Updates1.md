# Web Bol Bill: BRD, PRD and TRD (Release 2 Updates)

Prepared for: Web Bol Bill team | Date: 24 Nov 2026 | Status: Draft v1

This document has three parts: the Business Requirements (BRD: why), the Product Requirements (PRD: what) and the Technical Requirements (TRD: how). It covers six updates: Team grid change, Price list purchase import, Signup/Login, New tab, GST update and the Udhaar Agent.

## Part 1: Business Requirements Document (BRD)

### 1.1 Background

Web Bol Bill is a billing web app for small shopkeepers. Shopkeepers create bills, keep a price list with stock, track udhaar (credit) in the History tab and manage a Team. Three problems stand out today:

- Updating the price list and stock by hand is slow and error-prone.
- Udhaar recovery is manual, so shopkeepers forget or feel awkward asking customers for money.
- There is no account system, so data is not tied to a verified shopkeeper.

### 1.2 Business Objectives

1. Cut the time to update stock and prices from hours to minutes by importing purchase files.
2. Improve udhaar recovery rate and reduce the number of days credit stays unpaid.
3. Give every shopkeeper a secure personal account so data is private and recoverable.
4. Keep GST handling correct so bills remain compliant.
5. Keep the shopkeeper in control of every customer-facing message (human in the loop).

### 1.3 Scope Summary

| # | Update | Business value |
| --- | --- | --- |
| 1 | Remove Shayna Khan from Team grid | Correct team data |
| 2 | Purchase file import in Price list | Faster, accurate stock and price updates |
| 3 | Signup / Login | Security, per-user data, trust |
| 4 | New tab (updates) | To be defined |
| 5 | GST update | Compliance, correct tax on bills |
| 6 | Udhaar Agent and Inbox | Faster credit recovery with less effort |

### 1.4 Success Metrics

- Purchase import: 90% or more of rows in a typical file matched or created without manual work; import time under 1 minute for 500 rows.
- Udhaar: 25% reduction in average days-to-recovery within 60 days of launch; 70% or more of agent drafts approved without edits.
- Auth: signup completion above 80%; zero unauthorized data access incidents.
- Zero customer messages sent without shopkeeper approval.

### 1.5 Stakeholders

Shopkeeper (primary user), shop staff (team members), product owner, developers, and customers who owe udhaar (message recipients).

### 1.6 Assumptions, Risks and Constraints

- Customers have phone numbers saved with their udhaar entries.
- Risk: a tough-toned message could upset a customer, so the shopkeeper must always approve it and tone must stay respectful and legal.
- Risk: wrong item matching in imports could corrupt stock, so a preview step is mandatory.
- Risk: messaging channel costs (WhatsApp or SMS) and provider rules.
- Constraint: Grok API key must never be exposed in the browser.
- Privacy: customer names, numbers and dues are personal data; store and send only what is needed.

## Part 2: Product Requirements Document (PRD)

### 2.1 Feature 1: Team grid update

**Requirement:** In the Team tab, remove the member "Shayna Khan".

**Acceptance criteria**

- Shayna Khan no longer appears in the Team grid after the change.
- Other members are unaffected and grid layout stays aligned.
- If Shayna Khan is linked to past bills or history entries, those records stay intact (shown as a former member or by name only) and nothing breaks.

**Note:** If she is hard-coded in the UI, remove her entry. If she is stored in the database, remove her record or mark her inactive, which is safer than deleting.

### 2.2 Feature 2: Purchase file import (Price list tab)

**Goal:** The shopkeeper uploads the purchase Excel or CSV file once. The app adds new items to the price list and updates stock, price and unit for existing items.

**Placement:** A new option at the very top of the Price list tab: "Import from purchase file" (upload button, drag and drop, accepts .xlsx, .xls, .csv).

**User flow**

1. Shopkeeper clicks the import option and uploads the file.
2. App reads the file and auto-detects columns (Item name, Quantity, Purchase price, Unit). Shopkeeper can fix the column mapping from dropdowns if detection is wrong.
3. App matches each row to an existing price list item (see aliases below).
4. A preview table shows each row with a status: Update existing, New item, or Needs review.
5. Shopkeeper reviews, edits or unticks rows, and clicks Confirm.
6. App applies changes and shows a summary (for example: 42 updated, 8 added, 3 skipped), with an Undo option for the last import.

**What gets updated**

| Field | Existing item | New item |
| --- | --- | --- |
| Stock | Add purchased quantity to current stock (default) or replace it, shopkeeper chooses | Set to purchased quantity |
| Purchase price | Update to new value | Set from file |
| Selling price | Not changed automatically; app can suggest using a margin % the shopkeeper sets | Optional margin % to compute it, else left blank for the shopkeeper |
| Unit | Update if different (warn on mismatch, for example kg vs pcs) | Set from file |

**About aliases (you asked where they come from)** An alias is another name for the same item (for example "Sugar", "Cheeni", "चीनी", "sugar 1kg"). The app should not expect you to know them in advance. Aliases can come from these sources, and you can use any or all:

1. **Auto-learned from imports (recommended):** When a file row does not match any item, the app asks the shopkeeper "Is this the same as an existing item?" The answer is saved as an alias, so the same name matches automatically next time.
2. **Fuzzy matching:** The app compares names ignoring case, spaces, spelling mistakes and common words (for example "Tata Salt 1kg" vs "tata salt"). Close matches are suggested with a confidence score.
3. **Supplier file columns:** If the purchase file has extra columns such as HSN code, SKU or barcode, these are used as strong match keys.
4. **Manual entry:** An "Aliases" field on each item where the shopkeeper can type extra names, separated by commas.
5. **AI suggestion (optional):** Grok can suggest Hindi, English and Hinglish names for an item (for example Cheeni for Sugar). The shopkeeper approves them before saving.
6. **Bulk alias upload (optional):** A simple two-column CSV (alias, item) for shops that already have naming lists.

**Acceptance criteria**

- Files up to 5 MB or 2,000 rows import without error; larger files show a clear message.
- Nothing is written to the price list until the shopkeeper confirms the preview.
- Rows with missing name or invalid numbers are flagged, not silently dropped.
- Duplicate rows for the same item in one file are merged with quantities added.
- Import can be undone for the last import.
- Hindi and English item names are both supported (UTF-8).

### 2.3 Feature 3: Signup / Login

**Goal:** A secure account system for Web Bol Bill whose look matches the existing app theme (same colors, fonts, buttons, spacing, logo and tone).

**Screens**

- Signup: shop name, owner name, mobile number, email, password and confirm password.
- Login: email or mobile with password.
- Forgot password and reset password.
- Logout from the profile menu.
- Optional: login with Google, and OTP login by mobile (many shopkeepers prefer OTP).

**Rules**

- Password minimum 8 characters, with strength indicator and show/hide toggle.
- Email or mobile must be unique.
- Clear, friendly error messages in simple language (Hindi and English labels if the app is bilingual).
- Session stays logged in on the device until logout (Remember me), with automatic expiry for safety.
- Each shopkeeper sees only their own data (bills, price list, history, team, inbox).
- Layout works on mobile first, since most shopkeepers use phones.

**Acceptance criteria**

- A new user can sign up and reach the dashboard in under one minute.
- Wrong credentials never reveal which field was wrong.
- Pages visually match the existing theme in light and dark mode if the app supports both.

### 2.4 Feature 4: New tab (updates)

**Status: details not provided.** See Open Questions. Placeholder requirement: add a new tab to the main navigation named "Updates", styled like existing tabs, which will show product or shop updates. Content, purpose and who sees it must be confirmed before development.

### 2.5 Feature 5: GST update

**Status: details not provided.** See Open Questions. Likely candidates: GST rate per item (0, 5, 12, 18, 28%), GSTIN on shop profile and customer, CGST/SGST/IGST split on bills, tax-inclusive or tax-exclusive pricing, HSN code per item, and GST summary report. Scope must be confirmed.

### 2.6 Feature 6: Udhaar Agent and Inbox

**Goal:** An AI agent, powered by Grok API, watches the udhaar (credit) entries in the History tab, prepares polite reminder messages for overdue customers, and sends them only after the shopkeeper approves. It then helps handle customer replies. The shopkeeper stays in control at every step.

**Shopkeeper settings**

- Reminder after N days: the shopkeeper picks the number of days (default 7; allowed range for example 1 to 60).
- Follow-up gap: days between repeat reminders (default 7, also selectable).
- Maximum number of reminders per customer (default 3).
- Quiet hours and sending time (for example no messages after 8 PM).
- Master switch to turn the agent on or off, and per-customer opt-out (Do not remind).
- Preferred language for messages: Hindi, English or Hinglish.

**Agent behavior**

1. Daily, the agent checks History for unpaid udhaar older than N days.
2. For each overdue customer it drafts a message using customer name, amount due, original date and shop name.
3. Draft goes to the Inbox as a pending item. Nothing is sent yet.
4. Shopkeeper clicks Allow (send as drafted), edits then Allow, or Deny (do not send; optionally snooze for some days).
5. On Allow, the message is sent through the messaging channel.
6. If the customer replies, the agent reads the reply and prepares a response. It follows the autonomy rules below.
7. If the udhaar is still unpaid after the follow-up gap (default another 7 days), the agent drafts a second reminder with a firmer tone. This also goes to the Inbox for approval.
8. When the shopkeeper marks the udhaar as paid, all pending reminders for that customer are cancelled.

**Tone levels**

| Reminder | Tone | Example idea |
| --- | --- | --- |
| 1st | Friendly and polite | Gentle reminder with amount and date, thanks the customer |
| 2nd | Firm but respectful | States the amount is overdue, asks for a payment date |
| 3rd (final) | Strict and clear | Requests immediate payment, mentions the shop may need to take further steps, never threatening |

The agent must never use abusive language, threats of violence or legal action it cannot back, public shaming, or contact customers at odd hours. Strictness means clarity, not harassment.

**Replies handling and human in the loop** You asked that the agent handle replies on its own while keeping a human in the loop. Recommended model, with a setting so the shopkeeper chooses:

- **Auto-reply (safe cases only):** Simple acknowledgements, such as "I will pay on Friday" (agent confirms and records a promised date), thanks, or asking the amount again. Agent can reply directly if the shopkeeper enabled Auto-reply.
- **Needs shopkeeper (always escalated):** Disputes about the amount, claims of already having paid, requests for discount or installments, anger or abuse, legal words, or anything the agent is not confident about. These appear in the Inbox as Needs your attention, with a suggested reply.
- **Mode choice:** (a) Approve every reply, (b) Auto-reply only to safe cases, escalate the rest. Default is (a) at launch.
- A promise date recorded by the agent pauses reminders until that date passes.

**Inbox tab**

- Placed in the web navigation immediately to the left of the Team tab.
- Shows a vertical list (one line per item), each line like: "Ramesh owes ₹1,250 for 7 days. Send reminder?" with Deny and Allow buttons on the side.
- Each item can be expanded to see the full drafted message, edit it, the customer's history and past messages.
- Filters: Pending approval, Needs attention, Sent, Denied. A badge on the tab shows the count of pending items.
- Bulk actions: Allow all selected, Deny all selected.
- Conversation view for each customer showing sent reminders and replies in order.

**Acceptance criteria**

- No message leaves the system without an explicit Allow (or an enabled safe auto-reply rule).
- Changing the day setting changes which customers are flagged from the next run.
- Customers who paid or opted out never get reminders.
- All agent actions are logged (what was drafted, who approved, what was sent, when).
- Inbox shows correct amounts and dates that match History.

## Part 3: Technical Requirements Document (TRD)

### 3.1 Assumed architecture

Since the stack is not specified, this TRD assumes a typical web app: a React (or similar) frontend, a backend API (Node or Python), and a relational database (PostgreSQL or similar). Adapt names to the actual stack.

### 3.2 Feature 1: Team grid

- Find the source of the Team grid (static list in code or a team members table).
- Remove or deactivate the record for Shayna Khan (set status inactive rather than delete if bills refer to her).
- Make the grid query filter inactive members. Re-test layout.

### 3.3 Feature 2: Purchase file import

**Frontend**

- Upload component at the top of the Price list tab; accepts .xlsx, .xls, .csv; client-side size check.
- Column mapping step and a preview table with row status and editable cells.

**Backend endpoints**

- POST /api/pricelist/import/parse: receives the file, returns detected columns and parsed rows with match suggestions.
- POST /api/pricelist/import/commit: receives the confirmed rows and options (stock mode: add or replace, margin %), applies in one database transaction.
- POST /api/pricelist/import/{id}/undo: reverts the last import using stored before-values.

**Parsing and matching**

- Libraries: SheetJS (xlsx) for Excel, a CSV parser such as Papa Parse, or pandas on a Python backend. Force UTF-8 and handle Excel encodings.
- Normalize names: lowercase, trim, remove extra spaces and punctuation, normalize units (kg, kgs, kilogram to kg).
- Match order: exact barcode, SKU or HSN, then exact alias, then exact normalized name, then fuzzy score (for example Jaro-Winkler or trigram). Auto-accept only above a high threshold (for example 0.92); the middle band is flagged Needs review.
- Optional Grok call for ambiguous rows or alias suggestions, returning JSON that the shopkeeper confirms.

**Data model changes**

- items: add purchase\_price, unit, stock (if missing), updated\_at.
- item\_aliases(id, item\_id, alias, normalized\_alias, source \[manual, import, ai\], created\_at) with a unique index on (shop\_id, normalized\_alias).
- import\_batches(id, shop\_id, filename, status, summary\_json, created\_at) and import\_batch\_rows(batch\_id, item\_id, before\_json, after\_json) for audit and undo.

**Validation**

- Reject rows with non-numeric quantity or price, negative values, and empty names; report row numbers.
- Guard against formula injection: prefix cell values starting with =, +, - or @ when exporting; never evaluate formulas on import.
- File type check by content, not just extension; size and row limits.

### 3.4 Feature 3: Signup / Login

- Auth approach: use a proven solution (for example Firebase Auth, Supabase Auth, Auth0 or a framework library) instead of building password handling from scratch. If self-built: hash passwords with bcrypt or argon2, never store plain text.
- Sessions: short-lived access token plus refresh token in httpOnly, secure, SameSite cookies; or server sessions.
- Tables: users(id, email, mobile, password\_hash, shop\_id, created\_at, last\_login), shops(id, name, owner\_id), password\_resets(token\_hash, user\_id, expires\_at).
- Every table that holds shop data gets shop\_id, and every query filters by the logged-in user's shop\_id (tenant isolation). Add this to existing tables with a migration and assign existing data to the first account.
- Security: rate limiting on login and reset endpoints, account lockout or captcha after repeated failures, HTTPS only, CSRF protection, email or OTP verification, generic error messages.
- OTP login (optional): integrate an SMS provider such as MSG91 or Twilio, with 6-digit codes expiring in 5 minutes.
- Theme: reuse the existing design tokens (colors, fonts, radius, spacing) and shared button and input components so screens match. Mobile-first layout with accessible labels and focus states.
- Route guards: unauthenticated users are redirected to Login; authenticated users skip Login and Signup.

### 3.5 Feature 4: New tab

Add a route and navigation entry for the tab. Content source (static, database or API) to be decided after the requirement is clarified.

### 3.6 Feature 5: GST update

To be detailed after scope confirmation. Expected technical items: gst\_rate and hsn\_code on items, gstin on shops and customers, bill-level tax breakup (CGST, SGST or IGST based on state of supply), rounding rules, a tax-inclusive toggle, migration for old bills (keep old totals unchanged), and a GST summary report or export.

### 3.7 Feature 6: Udhaar Agent and Inbox

**Components**

1. Scheduler: a daily job (cron or queue worker) that finds overdue udhaar per shop using that shop's settings.
2. Agent service: backend module that calls the Grok API (xAI) to draft messages and classify replies.
3. Inbox API and UI: list, approve, deny and edit items.
4. Messaging service: sends and receives messages through a channel provider.
5. Webhook receiver: receives customer replies and passes them to the agent.

**Messaging channel (decision needed):** WhatsApp Business API (best reach in India; requires approved message templates for first contact and an official provider), SMS (simpler, needs DLT registration in India) or both. The system is built behind a channel interface so providers can be swapped.

**Grok API usage**

- Calls are made only from the backend. The API key is stored in an environment variable or secrets manager and is never sent to the browser or committed to code. Rotate the key if it has ever been shared in plain text.
- Drafting prompt inputs: customer first name, amount, days overdue, reminder level (1, 2 or 3), language, shop name. The prompt includes strict rules: respectful tone, no threats, no invented facts, include only given amount and date, keep under about 60 words.
- Reply handling: Grok classifies the customer's reply as one of: promise\_to\_pay (with date), will\_pay\_soon, already\_paid\_claim, dispute, discount\_request, abusive, unrelated or unclear; it also returns a confidence value and a suggested reply, in strict JSON that the backend validates.
- Safety: validate output server-side, reject messages that contain amounts or dates that do not match the database, and fall back to a safe template if validation fails or the API times out.
- Send only the minimum personal data to the model (first name, amount, days). Avoid phone numbers and full addresses in prompts.
- Handle rate limits and failures with retries and backoff; keep the item pending if the API is down.

**Data model**

- agent\_settings(shop\_id, enabled, remind\_after\_days, followup\_gap\_days, max\_reminders, send\_window, language, reply\_mode)
- udhaar\_reminders(id, shop\_id, udhaar\_id, customer\_id, level, draft\_text, final\_text, status \[pending, approved, denied, sent, failed, cancelled\], approved\_by, approved\_at, sent\_at, snooze\_until)
- conversations and messages(id, customer\_id, direction \[out, in\], text, classification, confidence, handled\_by \[agent, shopkeeper\], created\_at)
- customer\_flags(customer\_id, do\_not\_remind, promise\_date)
- agent\_audit\_log(id, shop\_id, action, details\_json, created\_at)

**Core logic**

- Overdue rule: due if today minus udhaar date is at least remind\_after\_days and unpaid. A level-N+1 reminder is created only if the level-N reminder was sent at least followup\_gap\_days ago, no promise date is active and level is below max\_reminders.
- Idempotency: unique key on (udhaar\_id, level) so the daily job never creates duplicate drafts.
- State machine: pending, then approved, then sent; or pending, then denied, optionally snoozed. Marking udhaar as paid cancels all pending and approved items.
- Human in the loop: the send function checks that status is approved (or a valid safe auto-reply rule) before calling the provider; this check is enforced in the backend, not only in the UI.
- Escalation: replies classified as dispute, already\_paid\_claim, discount\_request, abusive or low confidence (below a threshold such as 0.75) always create a Needs attention inbox item and are never auto-answered.
- Sending limits: respect quiet hours, per-shop daily send cap, and per-customer cap.

**Inbox UI**

- New route /inbox and a nav entry placed before Team. Badge count from a lightweight endpoint (GET /api/inbox/count).
- Endpoints: GET /api/inbox?status=, POST /api/inbox/{id}/allow, POST /api/inbox/{id}/deny, PATCH /api/inbox/{id} (edit text), POST /api/inbox/bulk.
- Real-time updates via polling every 30 to 60 seconds or WebSocket or SSE.

**Compliance and ethics:** Follow local debt-collection and messaging rules (opt-out handling, DLT or WhatsApp template rules), keep consent where required, and include the shop name in each message.

### 3.8 Non-functional requirements

- Performance: page load under 3 seconds on a mid-range phone; import preview for 500 rows under 5 seconds.
- Security: HTTPS, secrets in environment variables, input validation, tenant isolation, audit logs.
- Reliability: daily job is retry-safe; failed sends are retried or flagged.
- Backups: daily database backup; import undo data kept for 30 days.
- Browser support: latest Chrome, Edge, Safari and Firefox; mobile web responsive.
- Testing: unit tests for matching, overdue logic and state machine; end-to-end tests for import, login and inbox approval.

### 3.9 Suggested delivery order

1. Team grid fix (small, quick).
2. Signup / Login (needed first so all later data is tied to a shop).
3. Purchase file import.
4. GST update (after scope is confirmed).
5. Udhaar Agent and Inbox (largest piece; build Inbox with approval flow first, then the agent, then reply handling).
6. New tab (after scope is confirmed).

## Open Questions

1. **New tab (item 4):** What is the tab's name and purpose? What content goes in it, and who sees it?
2. **GST update (item 5):** Which parts are needed: rates per item, GSTIN, CGST/SGST/IGST split, HSN codes, inclusive pricing, reports?
3. **Messaging channel:** WhatsApp, SMS or both? Does the shop already have a provider account?
4. **Reply mode default:** Should the agent send replies automatically for safe cases, or should the shopkeeper approve every reply at first?
5. **Import stock rule:** When a purchase file is uploaded, should stock be added to current stock (recommended) or replace it?
6. **Selling price:** Should the app suggest selling prices from a margin %, or leave selling price untouched?
7. **Login method:** Email and password only, or also mobile OTP and Google login?
8. **Current tech stack:** Which frontend, backend and database are used, so this TRD can be made exact?
9. **Existing data:** Should all current data be assigned to the first account that signs up?
