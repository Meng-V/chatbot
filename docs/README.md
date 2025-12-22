# Developer Documentation

**Miami University Libraries Chatbot - Version 3.1.0**  
**Last Updated:** December 22, 2025 Afternoon

---

## 📚 Documentation Index

This folder contains technical documentation for developers working on the chatbot system.

### Core Documentation

1. **[01-SYSTEM-OVERVIEW.md](./01-SYSTEM-OVERVIEW.md)**  
   Complete system architecture, technology stack, components, data flow, and agent system.

2. **[02-SETUP-AND-DEPLOYMENT.md](./02-SETUP-AND-DEPLOYMENT.md)**  
   Initial setup, database configuration, running locally, production deployment, and server maintenance.

3. **[05-WEAVIATE-RAG-CORRECTION-POOL.md](./05-WEAVIATE-RAG-CORRECTION-POOL.md)**  
   Using Weaviate as a correction pool to fix bot mistakes. Includes scripts and workflows.

4. **[07-ENVIRONMENT-VARIABLES.md](./07-ENVIRONMENT-VARIABLES.md)**  
   Complete reference for all environment variables and configuration.

5. **[08-SUBJECT-LIBRARIAN-SYSTEM.md](./08-SUBJECT-LIBRARIAN-SYSTEM.md)**  
   Enhanced subject librarian search with course codes, fuzzy matching, and regional campus support.

6. **[09-SERVER-MONITORING.md](./09-SERVER-MONITORING.md)**  
   Server health monitoring, auto-restart, email alerts, and comprehensive logging.

7. **[10-DEPLOYMENT-GUIDE.md](./10-DEPLOYMENT-GUIDE.md)**  
   Complete deployment guide with database sync, verification, and maintenance procedures.

8. **[11-CLARIFICATION-SYSTEM.md](./11-CLARIFICATION-SYSTEM.md)**  
   Smart clarification choices system with RAG-based classification, user-in-the-loop decision making, and interactive button UI.

---

## 🚀 Quick Start

**For Administrators (Non-Technical):**  
Start with the main [README.md](../README.md) in the project root.

**For Developers:**
1. Read [01-SYSTEM-OVERVIEW.md](./01-SYSTEM-OVERVIEW.md) for architecture
2. Follow [02-SETUP-AND-DEPLOYMENT.md](./02-SETUP-AND-DEPLOYMENT.md) for setup
3. Review [07-ENVIRONMENT-VARIABLES.md](./07-ENVIRONMENT-VARIABLES.md) for configuration

**For RAG Correction Management:**  
See [05-WEAVIATE-RAG-CORRECTION-POOL.md](./05-WEAVIATE-RAG-CORRECTION-POOL.md) for adding corrections to fix bot mistakes.

---

## 🔑 Key Changes in Version 3.1

### New in Version 3.1 (December 2025)
- ✅ **Smart Clarification System** - Interactive button choices for ambiguous questions
- ✅ **RAG-Based Classification** - Weaviate vector database for intent classification with confidence scoring
- ✅ **User-in-the-Loop** - Confirms user intent before processing unclear queries
- ✅ **Database-Driven Addresses** - Library contact info from database, not web search
- ✅ **Structured Clarification Choices** - Up to 3 category options + "None of the above"
- ✅ **Socket.IO Integration** - Real-time clarification choice handling

### Previous Updates (Version 3.0)
- ✅ **Enhanced subject librarian search** - Course codes, fuzzy matching, 710 subjects
- ✅ **Server monitoring** - Auto-restart with email alerts
- ✅ **RAG correction pool** - Quality control tool for fixing bot errors
- ✅ **Database optimization** - Library locations and verified contacts

---

## 📝 System Version

**Version:** 3.1.0  
**Release Date:** December 22, 2025  
**Developer:** Meng Qu, Miami University Libraries  
**Repository:** GitHub

---

## 📞 Support

**Technical Questions:**  
Review documentation or contact development team.

**Deployment Issues:**  
See [02-SETUP-AND-DEPLOYMENT.md](./02-SETUP-AND-DEPLOYMENT.md) troubleshooting section.

**Bot Errors:**  
Use RAG correction pool - [05-WEAVIATE-RAG-CORRECTION-POOL.md](./05-WEAVIATE-RAG-CORRECTION-POOL.md)

---

*Developed and maintained by Miami University Libraries Web Services*
