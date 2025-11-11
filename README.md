# Miami University Libraries Smart Chatbot

**An intelligent AI assistant that helps students, faculty, and staff navigate library resources and services 24/7.**

---

## 🎯 What Does This Chatbot Do?

The Smart Chatbot is your virtual library assistant, designed to answer questions and help with common library tasks instantly. It can:

### **Find Resources**
- Search for books, articles, journals, and e-resources in our catalog
- Check if materials are available and where to find them
- Provide call numbers and location information

### **Library Information**
- **Hours**: Get current and upcoming hours for all Miami University library locations:
  - King Library (Oxford)
  - Art & Architecture Library (Oxford)
  - Rentschler Library (Hamilton)
  - Gardner-Harvey Library (Middletown)
- **Room Booking**: Reserve study rooms and spaces
- **Policies**: Answer questions about borrowing, renewals, fines, printing, and more

### **Course & Subject Help**
- Find course-specific research guides
- Connect you with subject librarians for your major or class
- Recommend databases and resources for your field of study

### **Website Search**
- Search all library website content (lib.miamioh.edu)
- Find policies, services, and general information
- Access guides, tutorials, and FAQs

### **Human Support**
- Connect you with a real librarian via chat when needed
- Seamlessly hand off complex questions to human experts

### **Smart Memory**
- Remembers context from your conversation
- Uses AI-powered search through library documentation and FAQs

---

## ⚠️ Important: What This Chatbot Can and Cannot Answer

### ✅ IN SCOPE - Library Questions ONLY

This chatbot is **strictly limited** to Miami University **LIBRARIES** questions. It can help with:

- **Library resources**: Books, articles, databases, research materials
- **Library services**: Study rooms, hours, borrowing, renewals, printing IN THE LIBRARY
- **Library spaces**: King Library, Art & Architecture Library, regional libraries
- **Library staff**: Subject librarians, research consultations
- **Library policies**: Borrowing policies, fines FOR LIBRARY MATERIALS, access rules

### ❌ OUT OF SCOPE - Cannot Answer

The chatbot **CANNOT** answer questions about:

- ❌ General Miami University (admissions, housing, dining, campus life)
- ❌ Course content, homework, assignments, test preparation
- ❌ IT support (Canvas, email, Wi-Fi) unless library-specific
- ❌ Academic advising, career services, health services
- ❌ Student organizations, campus events unless library-related
- ❌ Tuition, financial aid, course registration

**For these questions**, you'll be redirected to the appropriate university service.

### 🔒 Information Accuracy Guarantee

**The chatbot will NEVER make up information**:
- ✅ All contact information (emails, phone numbers) comes from official APIs
- ✅ Librarian names and contact details are verified from LibGuides API
- ✅ If specific information isn't available, general library contact is provided
- ✅ Phone: (513) 529-4141 | Website: https://www.lib.miamioh.edu

See [SCOPE_ENFORCEMENT_REPORT.md](SCOPE_ENFORCEMENT_REPORT.md) for complete details on scope boundaries.

---

## 💡 Why Is This Chatbot Special?

### **Always Available**
Unlike human staff, the chatbot is available 24/7, including nights, weekends, and holidays. Students can get help whenever they need it.

### **Instant Responses**
Most questions are answered in seconds. No waiting in queues or for email responses.

### **Multiple Specializations**
The chatbot uses **7 specialized AI agents** that work together:
1. **Discovery Agent** - Searches the library catalog for books and articles
2. **Hours & Booking Agent** - Handles library hours and room reservations
3. **Subject Guide Agent** - Finds course-specific research guides
4. **Subject Librarian Agent** - **NEW** Routes to appropriate subject librarian based on 710 mapped academic subjects, majors, and departments
5. **Website Search Agent** - Searches library website content
6. **Chat Handoff Agent** - Connects to human librarians when needed
7. **Memory Agent** - Recalls library documentation and FAQs using AI-powered search

### **Intelligent Routing**
The system automatically determines which agent(s) to use based on your question. Simple queries get fast responses, complex questions engage multiple agents for comprehensive answers.

### **Modern AI Technology**
Powered by OpenAI's latest models and LangGraph orchestration, the chatbot provides accurate, context-aware responses while maintaining conversation memory.

---

## 📊 Key Benefits

### **For Students**
- Get research help anytime, anywhere
- Find materials quickly without navigating complex systems
- Book study rooms in seconds
- Learn about library services without reading lengthy pages

### **For Faculty & Staff**
- Quick access to library resources and policies
- Easy course guide discovery for class assignments
- Fast answers to common questions
- More time for librarians to handle complex research needs

### **For Library Administration**
- Reduces repetitive question volume at service desks
- Provides 24/7 support without additional staffing
- Tracks common questions to identify service gaps
- Scales to handle peak periods (start of semester, finals)
- Maintains consistent, accurate information delivery
- **Update AI knowledge easily** - Librarians can refine responses and add new information without programming skills (see [Knowledge Management Guide](KNOWLEDGE_MANAGEMENT.md))

### **For IT & Systems**
- Modern Python-based architecture (FastAPI + LangGraph)
- Scalable and maintainable codebase
- Secure OAuth integration with SpringShare products
- Real-time communication via Socket.IO
- Comprehensive logging and monitoring

---

## 🚀 Quick Start

### **For End Users**
Visit the chatbot at: **https://new.lib.miamioh.edu/smartchatbot**

Simply type your question and the chatbot will help you immediately!

### **For Administrators**
The chatbot runs on Miami University's server infrastructure. The backend is Python-based and the frontend is a React application.

**System Requirements:**
- Backend runs on port 8000 (Python/FastAPI)
- Frontend runs on port 5173 (React/Vite)
- PostgreSQL database for conversation storage
- Weaviate vector database for AI memory
- OpenAI API access for language model

### **For Developers**
See the [Developer Guide](DEVELOPER_GUIDE.md) for detailed technical documentation and setup instructions.

---

## 🔐 Security & Privacy

- **Data Protection**: All conversations are stored securely in our PostgreSQL database
- **API Security**: Uses OAuth 2.0 for SpringShare API access
- **HTTPS**: All communication is encrypted
- **Privacy**: Conversations are used only for service improvement
- **Compliance**: Follows university data policies and FERPA guidelines

---

## 📈 Performance Metrics

### **Response Time**
- Simple queries: < 2 seconds
- Complex queries: 3-5 seconds
- Multi-agent coordination: 5-8 seconds

### **Accuracy**
- Library hours: 99%+ accuracy (direct API integration)
- Catalog search: Matches Primo search results
- Subject librarian matching: 85%+ accuracy with fuzzy matching across 710 subjects
- Contact information: 100% verified (NEVER makes up emails, phone numbers, or names)
- Scope enforcement: Automatically detects and redirects out-of-scope questions
- Website search: Powered by Google Custom Search Engine

### **Availability**
- Uptime target: 99.9%
- 24/7 operation
- Auto-restart on errors
- Health monitoring and alerts

---

## 🛠️ System Architecture

### **Technology Stack**
- **Backend**: Python 3.12, FastAPI, LangGraph
- **AI**: OpenAI o4-mini model with function calling
- **Frontend**: React, Vite, Socket.IO
- **Database**: PostgreSQL (conversations + 710 subject mappings), Weaviate (vector search)
- **APIs**: Primo, LibCal, LibGuides, LibAnswers, Google CSE, MuGuide
- **Features**: Strict scope enforcement, contact validation, fuzzy subject matching

### **Infrastructure**
- **Development**: Local development on localhost
- **Production**: Deployed at new.lib.miamioh.edu
- **Environment**: Ubuntu server with Python virtual environment
- **Process Manager**: Uvicorn with auto-reload

---

## 📞 Support & Contact

### **For Users**
- If the chatbot can't help, it will connect you with a human librarian
- Or contact library directly: https://www.lib.miamioh.edu/research/research-support/ask/

### **For Technical Issues**
- Report bugs via GitHub Issues

### **For Feature Requests**
- Submit ideas to library administration
- Technical suggestions via GitHub Issues
- Librarian feedback via internal channels

---

## 📚 Additional Resources

### **Documentation**
- **User Guide**: `README.md` (this document) - Overview with scope boundaries
- **Developer Guide**: `doc/DEVELOPER_GUIDE.md` - Complete setup and deployment guide
- **Knowledge Management Guide**: `doc/KNOWLEDGE_MANAGEMENT.md` - How to update AI responses and add new knowledge
- **Scope Enforcement Report**: `doc/SCOPE_ENFORCEMENT_REPORT.md` - Detailed scope boundaries and validation rules
- **MuGuide Integration Report**: `doc/MUGUIDE_INTEGRATION_REPORT.md` - Subject mapping technical documentation
- **Environment Guide**: `doc/ENV_QUICK_REFERENCE.md` - Environment configuration reference

### **API & System**
- **API Documentation**: Visit `/docs` endpoint when backend is running
- **Health Check**: Visit `/health` for system status
- **Project Repository**: [GitHub repository link]

---

## 🎓 About Miami University Libraries

Miami University Libraries serve the academic community across three campuses (Oxford, Hamilton, and Middletown) with comprehensive collections, services, and technology. This chatbot represents our commitment to innovative, accessible, and student-centered library services.

---

## ⚙️ Version Information

- **Current Version**: 2.0.0
- **Last Updated**: November 11, 2025
- **Platform**: Python AI-Core with React Frontend
- **AI Model**: OpenAI o4-mini
- **Agents**: 7 specialized agents
- **Subject Mappings**: 710 subjects, 587 LibGuides, 586 majors
- **Status**: Production-ready

### **What's New in Version 2.0**

#### ✅ Strict Scope Enforcement
- ONLY answers Miami University **LIBRARIES** questions
- Automatically detects and redirects out-of-scope questions
- Prevents answering general university, homework, or IT questions

#### ✅ MuGuide Integration
- 710 academic subjects mapped to LibGuides
- 586 major codes indexed
- 316 department codes linked
- Intelligent fuzzy matching for subject queries

#### ✅ Contact Information Validation
- NEVER generates fake emails, phone numbers, or names
- All contact info verified from LibGuides API
- Fallback to general library contact: (513) 529-4141

#### ✅ Subject Librarian Agent (NEW)
- Routes users to appropriate subject librarian
- Combines MuGuide database with LibGuides API
- Provides verified contact information

#### ✅ Enhanced Database Schema
- 5 new Prisma models for subject mappings
- Optimized indexes for fast lookup
- Idempotent data ingestion process

---

**Built with ❤️ by Miami University Libraries Web Services Team**
