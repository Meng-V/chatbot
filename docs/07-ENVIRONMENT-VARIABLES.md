# Environment Variables Reference

**Last Updated:** July 17, 2026

Complete reference for all environment variables used in the chatbot.

---

## Operator Alerts & Admin Surfaces (added 2026-07)

### Email alerts (`ai-core/src/observability/alerting.py`)

Sends the operator an email on dependency down/recovered events; the
correction-ticket system uses the same transport. The AWS host blocks
outbound port 25, so an authenticated relay on 587 is required
(configured and verified working 2026-07-17 via a Gmail App Password).

```bash
ALERT_EMAIL_ENABLED=true                 # "false" silences alerts
ALERT_EMAIL_TO=qum@miamioh.edu           # operator inbox
ALERT_EMAIL_FROM=qum@miamioh.edu         # must equal ALERT_SMTP_USER for Gmail
ALERT_SMTP_HOST=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_SMTP_STARTTLS=true
ALERT_SMTP_USER=qum@miamioh.edu
ALERT_SMTP_PASSWORD=<16-char Gmail App Password, no spaces>
```

Verify: `cd ai-core && .venv/bin/python -m src.observability.alerting`
(sends a test email).

### Admin & librarian surfaces (`ai-core/src/main.py`)

```bash
ADMIN_API_TOKEN=<secret>          # gates /admin/* (reviews, corrections,
                                  # cost, ticket queue). Unset = routes
                                  # not mounted at all (fail-closed).
LIBRARIAN_TICKET_CODE=<secret>    # staff access code for the correction-
                                  # ticket form at /librarian/ticket?key=...
                                  # Weaker secret by design: distributable
                                  # to library staff, exposes no PII.
```

See [13-CORRECTION-TICKETS.md](./13-CORRECTION-TICKETS.md) for the ticket
workflow.

---

## Core Configuration

### OpenAI API
```bash
OPENAI_API_KEY=sk-...
# Model TIERS (OPENAI_MODEL is deprecated -- no longer read):
LLM_MODEL_BASIC=gpt-5.6-luna        # synthesizer / surface questions
LLM_MODEL_REASONING=gpt-5.6-terra   # agent loop, escalation, clarify
LLM_MODEL_CHEAP=gpt-5.4-nano        # eval judge, mechanical extraction
LLM_MODEL_EMBEDDING=text-embedding-3-large  # changing this invalidates the vector index
```
- **OPENAI_API_KEY**: Your OpenAI API key (required)
- Tier values above are the production settings as of 2026-07-17; swap
  models per tier without touching call sites (`src/config/models.py`).

---

## Database

### PostgreSQL
```bash
DATABASE_URL=postgresql://user:password@host/database?sslmode=require
```
- Full PostgreSQL connection string including SSL mode

---

## Weaviate (RAG Correction Pool)

```bash
WEAVIATE_HOST=https://your-cluster.weaviate.network
WEAVIATE_API_KEY=your_api_key
```
- **WEAVIATE_HOST**: Weaviate Cloud cluster URL (without trailing slash)
- **WEAVIATE_API_KEY**: API key for authentication

---

## LibCal API (Hours & Room Booking)

### Authentication
```bash
LIBCAL_CLIENT_ID=your_client_id
LIBCAL_CLIENT_SECRET=your_client_secret
LIBCAL_TOKEN_URL=https://miamioh.libcal.com/1.1/oauth/token
LIBCAL_API_BASE_URL=https://miamioh.libcal.com/1.1
```

### Location IDs (Hours API)
```bash
LIBCAL_KING_LOCATION_ID=8113
LIBCAL_ART_LOCATION_ID=8116
LIBCAL_HAMILTON_LOCATION_ID=9226
LIBCAL_MIDDLETOWN_LOCATION_ID=9227
LIBCAL_ASKUS_ID=8876
```

### Building IDs (Reservations API)
```bash
LIBCAL_KING_BUILDING_ID=2047
LIBCAL_ART_BUILDING_ID=4089
LIBCAL_HAMILTON_BUILDING_ID=4792
LIBCAL_MIDDLETOWN_BUILDING_ID=4845
```

---

## LibGuides API (Research Guides)

```bash
LIBGUIDES_SITE_ID=2047
LIBGUIDES_API_KEY=your_api_key
LIBGUIDES_API_URL=https://lgapi-us.libapps.com/1.1
```

---

## LibAnswers API (Chat Handoff)

```bash
LIBANSWERS_IID=2047
LIBANSWERS_CLIENT_ID=your_client_id
LIBANSWERS_CLIENT_SECRET=your_client_secret
LIBANSWERS_TOKEN_URL=https://miamioh.libanswers.com/1.1/oauth/token
LIBANSWERS_API_BASE_URL=https://miamioh.libanswers.com/1.1
```

---

## Google Custom Search Engine

```bash
GOOGLE_CSE_API_KEY=your_google_api_key
GOOGLE_CSE_CX=your_search_engine_id
```

---

## Removed Variables (Version 3.0)

These variables are **no longer used** and can be removed from `.env`:

```bash
# ❌ REMOVED - Primo catalog search disabled
PRIMO_SCOPE=MyInst_and_CI
PRIMO_API_KEY=...
PRIMO_SEARCH_URL=https://api-na.hosted.exlibrisgroup.com/primo/v1/search?
PRIMO_VID=01OHIOLINK_MU:MU
```

---

## Complete .env Template

```bash
# ============================================
# Miami University Libraries Chatbot
# Environment Configuration
# Version 3.0.0
# ============================================

# ==================== OpenAI ====================
OPENAI_API_KEY=sk-...
LLM_MODEL_BASIC=gpt-5.6-luna
LLM_MODEL_REASONING=gpt-5.6-terra
LLM_MODEL_CHEAP=gpt-5.4-nano
LLM_MODEL_EMBEDDING=text-embedding-3-large

# ==================== Database ====================
DATABASE_URL=postgresql://user:password@host/database?sslmode=require

# ==================== Weaviate RAG ====================
WEAVIATE_HOST=https://your-cluster.weaviate.network
WEAVIATE_API_KEY=your_api_key

# ==================== LibCal API ====================
# Authentication
LIBCAL_CLIENT_ID=your_client_id
LIBCAL_CLIENT_SECRET=your_client_secret
LIBCAL_TOKEN_URL=https://miamioh.libcal.com/1.1/oauth/token
LIBCAL_API_BASE_URL=https://miamioh.libcal.com/1.1

# Location IDs (Hours API)
LIBCAL_KING_LOCATION_ID=8113
LIBCAL_ART_LOCATION_ID=8116
LIBCAL_HAMILTON_LOCATION_ID=9226
LIBCAL_MIDDLETOWN_LOCATION_ID=9227
LIBCAL_ASKUS_ID=8876

# Building IDs (Reservations API)
LIBCAL_KING_BUILDING_ID=2047
LIBCAL_ART_BUILDING_ID=4089
LIBCAL_HAMILTON_BUILDING_ID=4792
LIBCAL_MIDDLETOWN_BUILDING_ID=4845

# ==================== LibGuides API ====================
LIBGUIDES_SITE_ID=2047
LIBGUIDES_API_KEY=your_api_key
LIBGUIDES_API_URL=https://lgapi-us.libapps.com/1.1

# ==================== LibAnswers API ====================
LIBANSWERS_IID=2047
LIBANSWERS_CLIENT_ID=your_client_id
LIBANSWERS_CLIENT_SECRET=your_client_secret
LIBANSWERS_TOKEN_URL=https://miamioh.libanswers.com/1.1/oauth/token
LIBANSWERS_API_BASE_URL=https://miamioh.libanswers.com/1.1

# ==================== Google Custom Search ====================
GOOGLE_CSE_API_KEY=your_google_api_key
GOOGLE_CSE_CX=your_search_engine_id
```

---

**Document Version:** updated 2026-07-17 (model tiers, alerts, admin surfaces)
