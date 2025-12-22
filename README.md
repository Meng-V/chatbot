# Miami University Libraries Smart Chatbot

**An intelligent AI assistant helping library users 24/7**

---
Last update: 12/22/2025 Aftenoon

## For Library Administrators and Staff

This chatbot serves as a **24/7 virtual library assistant** that helps students, faculty, and staff with common library questions and services—**reducing workload for librarians** by handling routine inquiries automatically.

**How This Helps Your Library:**
- ✅ **24/7 Availability** - Answers questions even when library staff aren't available
- ✅ **Instant Responses** - Patrons get immediate help (under 5 seconds)
- ✅ **Reduces Repetitive Questions** - Handles common queries about hours, policies, room booking
- ✅ **Seamless Handoff** - Connects patrons to human librarians when needed
- ✅ **Multi-Campus Support** - Serves Oxford, Hamilton, and Middletown campuses
- ✅ **Smart and Safe** - Never makes up contact info; only provides verified information

---

## What Can This Chatbot Do?

The chatbot currently provides **7 core services**:

### 1. 📅 Library Hours
Check current and upcoming hours for all Miami University library locations:
- King Library (Oxford campus)
- Art & Architecture Library (Oxford campus)  
- Rentschler Library (Hamilton campus)
- Gardner-Harvey Library (Middletown campus)

**Example questions:**
- "What time does King Library close today?"
- "Is the Art Library open on Saturday?"
- "Library hours for next week"

### 2. 🏢 Study Room Reservations
Book study rooms and spaces at any library location.

**Example questions:**
- "Book a study room at King Library"
- "Reserve a room for 2 hours tomorrow"
- "Available rooms this afternoon"

### 3. 📚 Research Guides & Course Support
Find subject-specific research guides and course-related library resources through LibGuides integration.

**Example questions:**
- "Research guide for psychology"
- "Resources for ENG 111"
- "Guide for business students"

### 4. 👤 Subject Librarian Finder
Connect users with the right subject librarian based on their academic major, department, or research topic. Covers 710 academic subjects mapped to librarians.

**Example questions:**
- "Who is the biology librarian?"
- "Librarian for computer science"
- "I need help with engineering research"

### 5. 🔍 Library Website Search
Search the library website (lib.miamioh.edu) for policies, services, and general information.

**Example questions:**
- "How do I renew a book?"
- "Can I print in the library?"
- "What are the borrowing policies?"

### 6. 💬 Live Chat Handoff
Seamlessly connect users with a human librarian when needed, including real-time availability checking.

**Example questions:**
- "I need to talk to a librarian"
- "Connect me with library staff"
- "Is a librarian available now?"

### 7. 🎯 Smart Clarification System
When questions are ambiguous, the bot presents interactive button choices to help users clarify their intent, improving accuracy and user experience.

**Example:**
- User asks: "I need help with a computer"
- Bot presents buttons:
  - Borrow equipment (laptops, chargers)
  - Get help with broken computer
  - None of the above

---

## What the Chatbot CANNOT Do

**The bot focuses ONLY on library services.** It will politely redirect patrons for:

❌ **Catalog search** - Cannot search for specific books, articles, or e-resources  
❌ **General university questions** - Admissions, campus events, parking  
❌ **Course content help** - Homework, assignments, or academic advising  
❌ **IT support** - Canvas, email, or technical issues (unless library-specific)  
❌ **Campus services** - Housing, dining, financial aid, registration

**Why These Limits Matter:** By focusing on library services, the bot provides accurate, reliable answers. When a question is outside its scope, it **automatically suggests contacting a human librarian** for help.

**Patron Experience:** The bot will say something like: *"This question is outside my area of expertise. I recommend contacting the Student Services office at..."* or *"Let me connect you with a librarian who can better assist you."*

---

## How It Works (Technical Overview)

### System Components

**Backend:**
- Python 3.13 with FastAPI framework
- LangGraph for AI orchestration
- OpenAI o4-mini model
- PostgreSQL database for conversations and subject mappings
- Socket.IO for real-time communication

**Frontend:**
- React 19 with Vite 7
- TailwindCSS 4 + Radix UI components
- Lucide icons
- Socket.IO client

**External APIs:**
- **LibCal API** - Library hours and room booking
- **LibGuides API** - Research guides
- **LibChat API** - Live chat handoff and availability
- **Google Custom Search** - Library website search
- **MuGuide API** - Subject-to-librarian mapping (710 subjects)

### Architecture

The chatbot uses **RAG-based classification** with **5 specialized agents** orchestrated by an intelligent hybrid routing system:

**Routing System:**
- **RAG Classifier** - Uses Weaviate vector database to classify user intent with confidence scoring
- **Hybrid Router** - Chooses between fast function calling (simple queries) or LangGraph orchestration (complex queries)
- **Meta Router** - Intent classification with scope enforcement

**Specialized Agents:**
1. **LibCal Agent** - Handles hours and room reservations
2. **LibGuides Agent** - Finds research guides
3. **Subject Librarian Agent** - Routes to appropriate librarian (710 subjects)
4. **Website Search Agent** - Searches library website
5. **LibChat Agent** - Connects to human librarians

**Smart Features:**
- **Clarification Choices** - Interactive buttons when questions are ambiguous
- **User-in-the-Loop** - Confirms intent before processing unclear queries

---

## Accessing the Chatbot

**Production URL:** https://new.lib.miamioh.edu/smartchatbot

The chatbot is embedded on library web pages and available 24/7.

---

## For Library Staff: Using the Chatbot Effectively

### When to Let the Bot Handle It
- Standard hours questions
- Room booking requests
- Finding research guides
- Subject librarian contact info
- Common policy questions

### When to Escalate to Human Librarians
- Complex research consultations
- Book/article searches (catalog search temporarily unavailable)
- Detailed policy interpretations
- Technical issues with library accounts
- Complaints or sensitive situations

---

## Updating Bot Knowledge (For Library Managers)

### Fixing Incorrect Answers: RAG Correction Pool

**NEW WORKFLOW**: Weaviate database now serves as a **correction pool** - a tool for fixing bot mistakes rather than a primary information source.

**When to use:**
- The bot gives an incorrect answer about library policies
- You want to correct outdated information
- You need to add an exception or special case

**How it works:**
1. Identify an incorrect bot response
2. Create a corrected question-answer pair
3. Add it to Weaviate using the correction script
4. The bot will learn the correction and use it in future responses

**Documentation:** See `/docs/05-WEAVIATE-RAG-CORRECTION-POOL.md` for detailed workflow

**Scripts available:**
- `add_correction_to_rag.py` - Add corrected Q&A pairs
- `weaviate_cleanup.py` - Clear all corrections (reset)
- `verify_correction.py` - Test if correction is working

**Important:** Contact IT staff or developers to run these scripts.

---

## For IT Staff and Developers

### Server Information
- **Backend:** Runs on port 8000
- **Frontend:** Runs on port 5173 (development) or served via web server (production)
- **Database:** PostgreSQL at ulblwebt04.lib.miamioh.edu
- **Process Management:** Uvicorn with auto-reload

### Quick Start Commands

```bash
# Start both backend and frontend
./local-auto-start.sh

# Start backend only
cd ai-core
source venv/bin/activate
python -m uvicorn src.main:app --reload --port 8000

# Start frontend only
cd client
npm run dev
```

### Comprehensive Developer Documentation

See `/docs/` folder for complete technical documentation:

- **01-SYSTEM-OVERVIEW.md** - Architecture and data flow
- **02-SETUP-AND-DEPLOYMENT.md** - Installation and deployment
- **03-DATABASE-SETUP.md** - PostgreSQL and Prisma configuration
- **04-API-INTEGRATIONS.md** - All API keys and configurations
- **05-WEAVIATE-RAG-CORRECTION-POOL.md** - RAG correction workflow
- **06-MAINTENANCE-GUIDE.md** - Troubleshooting and updates
- **07-ENVIRONMENT-VARIABLES.md** - Complete .env reference

### Environment Variables

All API keys and configuration are stored in `.env` file. See `.env.example` for required variables.

**Key variables:**
- `OPENAI_API_KEY` - OpenAI API access
- `DATABASE_URL` - PostgreSQL connection
- `WEAVIATE_HOST` / `WEAVIATE_API_KEY` - Vector database
- `LIBCAL_*` - LibCal API credentials
- `LIBGUIDES_*` - LibGuides API credentials
- `LIBANSWERS_*` - LibChat API credentials
- `GOOGLE_CSE_*` - Google Custom Search

---

## Security & Privacy

- All conversations stored securely in PostgreSQL
- API access via OAuth 2.0 (SpringShare products)
- HTTPS encryption for all communication
- Follows FERPA and university data policies
- No personally identifiable information shared externally

---

## Performance Metrics

**Response Time:**
- Simple questions: < 2 seconds
- Complex questions: 3-5 seconds

**Accuracy:**
- Library hours: 99%+ (direct API)
- Room booking: 99%+ (direct API)
- Subject librarian matching: 85%+
- Contact information: 100% verified (never makes up emails/phones)

**Availability:**
- 24/7 operation
- 99.9% uptime target
- Auto-restart on errors

---

## Troubleshooting & Support

### Common Issues

**Bot not responding:**
1. Check if backend is running (port 8000)
2. Check frontend connection (port 5173 or web server)
3. Verify DATABASE_URL in .env
4. Check API keys are valid

**Incorrect hours showing:**
- LibCal API may be temporarily unavailable
- Check LibCal credentials in .env
- Verify LibCal location IDs in database

**Bot can't find subject librarian:**
- MuGuide API may be down
- Check subject mappings in PostgreSQL database
- Verify LibGuides API credentials

**For technical issues:**
- Contact IT department
- Review logs in backend console
- Check `/docs/06-MAINTENANCE-GUIDE.md`

### Getting Help

**For Library Staff:**
- Report issues to library IT coordinator
- Suggest improvements via internal channels

**For Developers:**
- Review documentation in `/docs/`
- Check GitHub repository for updates
- Contact development team

---

## Version Information

**Current Version:** 3.1.0  
**Last Updated:** December 22, 2025  
**Status:** Production

**What's New in Version 3.1:**

✅ **Smart Clarification System**
- Interactive button choices for ambiguous questions
- User-in-the-loop decision making
- "None of the above" option for edge cases
- Improved accuracy through user confirmation

✅ **RAG-Based Classification**
- Weaviate vector database for intent classification
- Confidence scoring and margin-based ambiguity detection
- Structured clarification choices when confidence is low

✅ **Database-Driven Accuracy**
- Library addresses from database (not web search)
- Contact information verified and never fabricated
- Location IDs and building data centralized

✅ **Enhanced Hybrid Routing**
- Fast function calling for simple queries (<2s)
- LangGraph orchestration for complex queries (3-5s)
- Intelligent complexity analysis

✅ **Previous Updates (v3.0):**
- Simplified architecture (5 core agents)
- RAG correction pool for fixing mistakes
- Enhanced multi-campus support
- Comprehensive developer documentation

---

## About Miami University Libraries

Miami University Libraries serve the academic community across three campuses (Oxford, Hamilton, and Middletown) with comprehensive collections, services, and technology. This chatbot represents our commitment to innovative, accessible, and student-centered library services.

**Contact Information:**
- **Phone:** (513) 529-4141
- **Website:** https://www.lib.miamioh.edu
- **Ask Us:** https://www.lib.miamioh.edu/research/research-support/ask/

---

**Built with ❤️ by Meng Qu, Miami University Libraries**
