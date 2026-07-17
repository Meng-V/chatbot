# Librarian Correction Tickets

**Added:** July 16, 2026
**Code:** `ai-core/src/api/admin/ticket_router.py` (tests: `test_ticket_router.py`)
**Table:** `CorrectionTicket` (see `prisma/schema.prisma`)

The channel for library staff to report a wrong or outdated chatbot
answer. Before this existed, librarians had no way to flag errors except
emailing the maintainer ad hoc.

---

## How librarians use it

1. Open the form link (distributed by the maintainer — bookmarkable):

   `https://<host>/librarian/ticket?key=<LIBRARIAN_TICKET_CODE>`

2. Fill in: their name + Miami email, what the patron asked, what the
   bot answered (pasted), what the answer SHOULD be (or where the
   correct info lives), and an optional supporting URL.
3. Submit. They get a confirmation page with the ticket id.

Every submission is:
- **stored in Postgres** (`CorrectionTicket`, status `open`), and
- **emailed to the maintainer** (`ALERT_EMAIL_TO`, currently
  qum@miamioh.edu) through the alert SMTP transport.

A mail failure never loses a ticket — the row is written first; failed
notifications show a ⚠️ marker in the queue.

## How the maintainer reviews

- Queue (newest first): `https://<host>/admin/tickets/view?key=<ADMIN_API_TOKEN>`
- Each ticket has a status link cycling `open → reviewed → done`.
- Typical flow: read the report → fix via gold set / corrections pool /
  code → mark `done`.

## Configuration

Two env vars (see [07-ENVIRONMENT-VARIABLES.md](./07-ENVIRONMENT-VARIABLES.md)):

- `ADMIN_API_TOKEN` — mounts the whole admin block, gates the queue.
- `LIBRARIAN_TICKET_CODE` — opens the staff form. Without it the form
  answers 401 (fail-closed). Rotate by changing the value and
  re-distributing the link.

Plus the `ALERT_SMTP_*` block for the email notifications.

**nginx**: the site config only proxies an explicit list of paths to the
backend, so `/librarian/` and `/admin/` each need a `location` block with
`proxy_pass http://smartchatbot_backend;` (added to
`/etc/nginx/sites-enabled/default` on 2026-07-17; a missing block shows up
as a 404 on an otherwise-working host).

## Security notes

- The staff code is deliberately separate from (and weaker than) the
  admin token: the form exposes no stored data, only accepts reports.
  The queue — which shows ticket contents — requires the admin token.
- All rendered content is `html.escape()`d; ticket text may quote
  bot output influenced by patron input, so it is treated as untrusted.
- Field length is capped (8 kB per field) to keep paste-bombs out.
