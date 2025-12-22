# System Overview - Miami University Libraries Chatbot

**Last Updated:** December 22, 2025  
**Version:** 3.1.0

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Technology Stack](#technology-stack)
3. [System Components](#system-components)
4. [Data Flow](#data-flow)
5. [Agent System](#agent-system)
6. [Database Schema](#database-schema)

---

## Architecture Overview

The Miami University Libraries Chatbot is a **multi-agent AI system** built with modern Python and React technologies. It uses LangGraph orchestration to route user queries to specialized agents that integrate with various library APIs.

### High-Level Architecture

```
┌─────────────────┐
│   User Browser  │
│   (React App)   │
└────────┬────────┘
         │ Socket.IO
         ↓
┌──────────────────────────────────────────────────┐
│         FastAPI Backend                          │
│  ┌────────────────────────────────────────────┐  │
│  │    RAG Classifier (Weaviate)               │  │
│  │  - Intent classification with confidence   │  │
│  │  - Margin-based ambiguity detection        │  │
│  │  - Generates clarification choices         │  │
│  └──────────────┬─────────────────────────────┘  │
│                 │                                 │
│  ┌──────────────▼─────────────────────────────┐  │
│  │    Clarification System (if ambiguous)     │  │
│  │  - Interactive button choices              │  │
│  │  - User-in-the-loop decision making        │  │
│  └──────────────┬─────────────────────────────┘  │
│                 │                                 │
│  ┌──────────────▼─────────────────────────────┐  │
│  │    Hybrid Router                           │  │
│  │  - Simple → Function calling (<2s)         │  │
│  │  - Complex → LangGraph orchestration       │  │
│  └──────────────┬─────────────────────────────┘  │
│                 │                                 │
│    ┌────────────┴─────────────┐                  │
│    │    5 Specialized Agents  │                  │
│    ├──────────────────────────┤                  │
│    │ 1. LibCal Agent          │                  │
│    │ 2. LibGuides Agent       │                  │
│    │ 3. Subject Librarian     │                  │
│    │ 4. Website Search        │                  │
│    │ 5. LibChat Handoff       │                  │
│    └──────────┬───────────────┘                  │
│               │                                   │
│    External APIs & Databases                     │
└───────┬──────────────────────────────────────────┘
        │
   ┌────┴─────────────────┐
   │                      │
┌──▼──────────┐  ┌───────▼────────┐
│ PostgreSQL  │  │  External APIs │
│  Database   │  │  - LibCal      │
│             │  │  - LibGuides   │
│ Weaviate    │  │  - LibChat     │
│ (RAG + QA)  │  │  - Google CSE  │
└─────────────┘  └────────────────┘
```

---

## Technology Stack

### Backend

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| **Runtime** | Python | 3.13 | Main programming language |
| **Web Framework** | FastAPI | Latest | HTTP API and WebSocket server |
| **AI Orchestration** | LangGraph | Latest | Multi-agent workflow management |
| **LLM** | OpenAI o4-mini | Latest | Natural language understanding |
| **Real-time Communication** | Socket.IO | Latest | WebSocket for live chat |
| **ORM** | Prisma (Python) | 0.15.0 | Database access layer |
| **HTTP Client** | httpx | Latest | Async HTTP requests to APIs |

### Frontend

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| **Framework** | React | 19 | UI framework |
| **Build Tool** | Vite | 7 | Fast dev server and bundler |
| **Styling** | TailwindCSS | 4 | Utility-first CSS |
| **Components** | Radix UI | Latest | Headless UI components |
| **Icons** | Lucide React | Latest | Icon library |
| **WebSocket** | Socket.IO Client | Latest | Real-time communication |

### Databases

| Database | Purpose | Hosted |
|----------|---------|--------|
| **PostgreSQL** | Conversations, subject mappings, library locations | ulblwebt04.lib.miamioh.edu |
| **Weaviate** | RAG classification + correction pool | Weaviate Cloud |

### External APIs

| API | Provider | Purpose |
|-----|----------|---------|
| **LibCal API** | SpringShare | Library hours, room booking |
| **LibGuides API** | SpringShare | Research guides |
| **LibAnswers API** | SpringShare | Chat handoff, availability |
| **Google Custom Search** | Google | Library website search |
| **MuGuide API** | Miami University | Subject-to-librarian mapping |

---

## System Components

### 1. Backend Server (`/ai-core`)

**Entry Point:** `src/main.py`

The FastAPI application that:
- Handles HTTP requests and WebSocket connections
- Manages conversation state
- Orchestrates AI agents via LangGraph
- Stores conversations in PostgreSQL
- Validates and cleans responses

**Key Modules:**
```
ai-core/src/
├── main.py              # FastAPI app entry point
├── graph/               # LangGraph orchestration
│   ├── orchestrator.py  # Meta router & agent coordination
│   └── function_calling.py  # Fast path for simple queries
├── agents/              # Specialized AI agents
├── tools/               # API integration tools
├── services/            # Business logic (location service, etc.)
├── api/                 # API wrappers (LibCal, LibGuides, etc.)
├── database/            # Prisma client and DB operations
├── memory/              # Conversation storage
└── utils/               # Helper functions, logging, validation
```

### 2. Frontend Client (`/client`)

**Entry Point:** `src/App.jsx`

React application that:
- Provides chat interface
- Connects to backend via Socket.IO
- Displays real-time responses
- Handles user input and chat history

**Key Components:**
```
client/src/
├── App.jsx              # Main application component
├── components/          # UI components
│   ├── ChatWindow.jsx   # Main chat interface
│   ├── Message.jsx      # Individual message display
│   └── Input.jsx        # User input field
└── services/
    └── socket.js        # Socket.IO connection management
```

### 3. Database Layer

**PostgreSQL Schema (Prisma):**
```
prisma/schema.prisma     # Main schema (Node.js)
ai-core/schema.prisma    # Python client schema (must have url property)
```

**Key Tables:**
- `Conversation` - User sessions
- `Message` - Individual messages
- `ToolExecution` - Logged tool/agent calls
- `Campus` - Library campuses (Oxford, Hamilton, Middletown)
- `Library` - Library buildings with contact info and LibCal IDs
- `LibrarySpace` - Spaces within libraries (Makerspace, Special Collections)
- `Subject` - Academic subjects mapped to librarians (710 subjects)
- `SubjectLibGuide` - LibGuide mappings
- `SubjectMajorCode` / `SubjectRegCode` / `SubjectDeptCode` - Subject synonyms

### 4. External API Integrations

All API integrations are in `/ai-core/src/api/`:

**LibCal Integration** (`libcal.py`):
- `get_library_hours()` - Fetch hours for a location
- `search_rooms()` - Find available study rooms
- `get_booking_form_link()` - Generate booking URLs

**LibGuides Integration** (`libguides.py`):
- `search_guides()` - Search research guides
- `get_guide_by_id()` - Fetch specific guide details
- `get_subject_librarian()` - Get librarian from LibGuides API

**LibChat Integration** (`askus_hours.py`):
- `get_askus_hours_for_date()` - Check if librarians available for chat
- Returns real-time availability status

**Google Custom Search** (`google_cse.py`):
- `search_library_website()` - Search lib.miamioh.edu content

**MuGuide Integration** (handled in `tools/subject_matcher.py`):
- Database-driven matching using 710 pre-loaded subjects
- Fuzzy matching for subject name variations

---

## Data Flow

### Typical User Query Flow

```
1. User sends message via React frontend
        ↓
2. Socket.IO transmits to FastAPI backend
        ↓
3. Backend saves message to PostgreSQL (Conversation table)
        ↓
4. Meta Router (LangGraph) classifies intent
        ↓
5. Router selects appropriate agent(s):
   - LibCal Agent for hours/booking
   - LibGuides Agent for research guides
   - Subject Librarian Agent for librarian contact
   - Google Site Agent for website content
   - LibChat Agent for human handoff
        ↓
6. Selected agent(s) execute in parallel
        ↓
7. Each agent calls its external API:
   - LibCal Agent → LibCal API
   - LibGuides Agent → LibGuides API
   - Subject Agent → PostgreSQL (MuGuide data)
   - Google Agent → Google CSE API
        ↓
8. Synthesizer combines agent responses using OpenAI LLM
        ↓
9. Response validated (URLs checked, contact info verified)
        ↓
10. Final answer saved to PostgreSQL
        ↓
11. Socket.IO sends response to frontend
        ↓
12. React displays answer to user
```

### Authentication Flow (for APIs requiring OAuth)

```
1. Backend starts → loads CLIENT_ID and CLIENT_SECRET from .env
        ↓
2. First API call triggers OAuth flow:
   - Send credentials to SpringShare token endpoint
   - Receive access token
   - Cache token in memory
        ↓
3. Subsequent API calls use cached token
        ↓
4. If token expires (401 error):
   - Automatically request new token
   - Retry API call
   - Update cached token
```

---

## Agent System

### Meta Router (Intent Classification)

**File:** `src/graph/orchestrator.py`

The Meta Router is the brain of the system. It:
1. **Analyzes user query** using OpenAI LLM
2. **Classifies intent** into categories:
   - `subject_librarian` - Finding a librarian
   - `course_subject_help` - Research guides
   - `booking_or_hours` - Hours or room booking
   - `policy_or_service` - Library policies
   - `human_help` - Needs librarian assistance
   - `general_question` - General info
   - `out_of_scope` - Non-library question
   - `capability_limitation` - Bot can't do this
3. **Selects agents** based on intent
4. **Enforces scope** - Rejects non-library questions

**Important Pre-checks:**
- Catalog search patterns → redirect to human (feature disabled)
- Capability limitations → provide helpful redirect
- Greetings → respond with availability info

### Five Specialized Agents

#### 1. LibCal Comprehensive Agent
**File:** `src/agents/libcal_comprehensive_agent.py`  
**Tools:** `src/tools/libcal_comprehensive_tools.py`

**Capabilities:**
- Check library hours (all campuses)
- Search available study rooms
- Generate booking links
- Check Ask Us chat availability

**Sub-routing:** Internally routes to hours vs. booking tools based on query

#### 2. LibGuides Comprehensive Agent
**File:** `src/agents/libguide_comprehensive_agent.py`  
**Tools:** `src/tools/libguide_comprehensive_tools.py`

**Capabilities:**
- Search research guides by keyword
- Find course-specific guides
- Retrieve guide details and URLs

#### 3. Subject Librarian Agent
**File:** `src/agents/subject_librarian_agent.py`  
**Tools:** `src/tools/subject_matcher.py`

**Capabilities:**
- Match user query to 710 academic subjects
- Fuzzy matching (handles typos and variations)
- Return librarian contact info from LibGuides API
- Handle "show all librarians" requests

**Data Source:** PostgreSQL database (pre-loaded from MuGuide API)

#### 4. Google Site Search Agent
**File:** `src/agents/google_site_comprehensive_agent.py`  
**Tools:** `src/tools/google_site_enhanced_tools.py`

**Capabilities:**
- Search library website content
- Filter and rank results
- Extract relevant snippets

**Scope:** Only searches `lib.miamioh.edu` domain

#### 5. LibChat Handoff Agent
**File:** `src/agents/libchat_agent.py`

**Capabilities:**
- Check if librarians currently available
- Provide hours for live chat
- Generate ticket submission links
- Seamless handoff message with availability

---

## Database Schema

### Conversation Tracking

```prisma
model Conversation {
  id          String   @id @default(uuid())
  sessionId   String?
  startTime   DateTime @default(now())
  endTime     DateTime?
  messages    Message[]
  toolExecutions ToolExecution[]
  modelUsages    ModelTokenUsage[]
}

model Message {
  id             String   @id @default(uuid())
  conversationId String
  type           String   // "user" or "assistant"
  content        String
  timestamp      DateTime @default(now())
  conversation   Conversation @relation(...)
}

model ToolExecution {
  id             String   @id @default(uuid())
  conversationId String
  agentName      String   // e.g., "libcal", "subject_librarian"
  toolName       String   // e.g., "get_hours", "search_guides"
  parameters     Json     // Tool input parameters
  success        Boolean
  executionTime  Int      // milliseconds
  timestamp      DateTime @default(now())
  conversation   Conversation @relation(...)
}
```

### Library Location Hierarchy

```prisma
model Campus {
  id          String    @id @default(uuid())
  name        String    @unique // "Oxford", "Hamilton", "Middletown"
  displayName String    // "Oxford Campus"
  isMain      Boolean   @default(false) // True for Oxford
  libraries   Library[]
}

model Library {
  id               String         @id @default(uuid())
  campusId         String
  name             String         // "King Library"
  displayName      String         // "Edgar W. King Library"
  shortName        String?        // "King"
  libcalBuildingId String @unique // For room reservations
  libcalLocationId String? // For hours API
  phone            String?        // Contact phone
  address          String?        // Physical address
  isMain           Boolean @default(false)
  spaces           LibrarySpace[]
  campus           Campus @relation(...)
}

model LibrarySpace {
  id               String   @id @default(uuid())
  libraryId        String
  name             String   // "Makerspace"
  displayName      String
  shortName        String?
  libcalLocationId String @unique // For hours only
  spaceType        String @default("service")
  library          Library @relation(...)
}
```

### Subject-to-Librarian Mapping

```prisma
model Subject {
  id            String              @id @default(uuid())
  subjectName   String              @unique // e.g., "Biology"
  libguides     SubjectLibGuide[]
  majorCodes    SubjectMajorCode[]
  regCodes      SubjectRegCode[]
  deptCodes     SubjectDeptCode[]
}

model SubjectLibGuide {
  id           String  @id @default(uuid())
  subjectId    String
  guideId      Int     // LibGuides guide ID
  guideUrl     String
  librarian    String? // Librarian name
  librarianEmail String?
  subject      Subject @relation(...)
}
```

---

## Environment Configuration

All configuration stored in `.env` file. See `07-ENVIRONMENT-VARIABLES.md` for complete reference.

**Critical Variables:**
- `OPENAI_API_KEY` - Required for AI responses
- `DATABASE_URL` - PostgreSQL connection
- `LIBCAL_*` - Library hours and booking
- `LIBGUIDES_*` - Research guides
- `LIBANSWERS_*` - Chat handoff
- `GOOGLE_CSE_*` - Website search

---

## Performance Characteristics

### Response Times
- **Simple queries** (hours, contact info): < 2 seconds
- **Complex queries** (multi-agent): 3-5 seconds
- **Database queries**: < 100ms
- **External API calls**: 500ms - 2 seconds each

### Scalability
- **Concurrent users**: Handles 100+ simultaneous conversations
- **Database connections**: Connection pooling via Prisma
- **API rate limits**: Respects SpringShare API limits
- **WebSocket connections**: Managed by Socket.IO

### Monitoring
- Request/response logging in backend console
- Tool execution tracking in PostgreSQL
- Error reporting with stack traces
- Health check endpoint: `/health`

---

## Next Steps

- **Setup & Deployment**: See `02-SETUP-AND-DEPLOYMENT.md`
- **Database Configuration**: See `03-DATABASE-SETUP.md`
- **API Integration**: See `04-API-INTEGRATIONS.md`
- **RAG Correction Pool**: See `05-WEAVIATE-RAG-CORRECTION-POOL.md`
- **Maintenance**: See `06-MAINTENANCE-GUIDE.md`
- **Environment Variables**: See `07-ENVIRONMENT-VARIABLES.md`

---

**Document Version:** 3.1.0  
**Last Reviewed:** December 22, 2025
