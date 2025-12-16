# Environment Variables Reference

**Last Updated:** December 16, 2025  
**Version:** 3.0.0

Complete reference for all environment variables used in the chatbot.

---

## Core Configuration

### OpenAI API
```bash
OPENAI_API_KEY=sk-...
OPENAI_MODEL=o4-mini
```
- **OPENAI_API_KEY**: Your OpenAI API key (required)
- **OPENAI_MODEL**: AI model to use (default: o4-mini, no temperature parameter)

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
OPENAI_MODEL=o4-mini

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

**Document Version:** 3.0.0
