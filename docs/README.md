# Developer Documentation

**Miami University Libraries Chatbot - Version 3.0.0**  
**Last Updated:** December 17, 2025

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

## 🔑 Key Changes in Version 3.0

### Removed Features
- ❌ **Primo catalog search** - Archived to `/archived/primo/`
- ❌ **RAG as active search** - Repurposed as correction pool only

### Updated Features
- ✅ **RAG correction pool** - Quality control tool for fixing bot errors
- ✅ **6 focused capabilities** - Hours, booking, guides, librarians, search, chat
- ✅ **Weaviate management scripts** - Easy correction workflow

### New in Version 3.0 (December 2025)
- ✅ **Enhanced subject librarian search** - Course codes, fuzzy matching, regional campus support
- ✅ **Server monitoring** - Auto-restart with email alerts
- ✅ **Comprehensive logging** - Structured JSON logs with rotation
- ✅ **Personal account queries** - Direct links to library account
- ✅ **Database optimization** - 4 new tables for verified contacts and LibGuides

---

## 📝 System Version

**Version:** 3.0.0  
**Release Date:** December 16, 2025  
**Developer:** Meng Qu, Miami University Libraries  
**Repository:** Internal GitHub

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
