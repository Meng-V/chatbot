# Miami University Library Chatbot - Documentation Index

Welcome to the comprehensive documentation for the Miami University Library AI Chatbot system. This documentation is organized by feature area to help you quickly find what you need.

---

## 📁 Documentation Structure

### 🚀 [Getting Started](./getting-started/)
Essential guides for understanding and using the chatbot system.
- **[Quick Start Guide](./getting-started/README.md)** - 5-minute setup and common tasks
- **[Main README](../README.md)** - Complete overview for library managers

### 🤖 [Weaviate RAG System](./weaviate-rag/)
Everything about the knowledge base and retrieval-augmented generation.
- **01-SETUP.md** - Initial Weaviate cloud setup
- **02-RAG-USAGE-TRACKING.md** - Tracking RAG query usage and analytics
- **03-RECORD-MANAGEMENT.md** - Managing and deleting problematic records
- **04-CLEANUP-QUICKSTART.md** - Quick reference for cleaning bad records
- **05-FACT-GROUNDING.md** - Ensuring factual accuracy in responses
- **06-FACT-GROUNDING-QUICKSTART.md** - Quick start for fact correction
- **07-FACT-CORRECTION.md** - Summary of fact correction features

### 📊 [Data Management](./data-management/)
Processing, cleaning, and optimizing transcript data.
- **01-CLEANING-STRATEGY.md** - Comprehensive transcript cleaning strategy
- **02-PROCESS-NEW-YEAR-DATA.md** - Adding new year transcript data
- **03-DATA-PIPELINE.md** - Complete RAG data pipeline
- **04-VECTOR-OPTIMIZATION.md** - Optimizing vector search performance
- **05-OPTIMIZATION-QUICKSTART.md** - Quick optimization guide

### 🏗️ [Architecture](./architecture/)
System design, components, and developer resources.
- **01-SYSTEM-ARCHITECTURE.md** - Complete system architecture diagram
- **02-DEVELOPER-GUIDE.md** - Developer setup and contribution guide
- **03-PROJECT-SUMMARY.md** - 2025 RAG project summary

### 📚 [Knowledge Management](./knowledge-management/)
Managing library guides and knowledge routing.
- **01-OVERVIEW.md** - Knowledge management overview
- **02-DETAILED-GUIDE.md** - Detailed knowledge management guide
- **03-ROUTING-GUIDE.md** - LibGuide vs MyGuide routing
- **04-INTEGRATION-REPORT.md** - MyGuide integration report
- **05-SCOPE-ENFORCEMENT.md** - Scope enforcement implementation

---

## 🎯 Quick Access by Task

### For Library Managers (Non-Technical)
Start here to understand what the chatbot does and how to use it:
1. [Main README](./getting-started/README.md) - System overview
2. [Weaviate RAG Overview](./weaviate-rag/) - Understanding the knowledge base

### For Developers
Technical setup and development:
1. [Developer Guide](./architecture/02-DEVELOPER-GUIDE.md)
2. [System Architecture](./architecture/01-SYSTEM-ARCHITECTURE.md)
3. [Data Pipeline](./data-management/03-DATA-PIPELINE.md)

### For Data Management
Working with transcript data:
1. [Cleaning Strategy](./data-management/01-CLEANING-STRATEGY.md)
2. [Process New Year Data](./data-management/02-PROCESS-NEW-YEAR-DATA.md)
3. [Vector Optimization](./data-management/04-VECTOR-OPTIMIZATION.md)

### For RAG Management
Managing the knowledge base:
1. [Weaviate Setup](./weaviate-rag/01-SETUP.md)
2. [Record Management](./weaviate-rag/03-RECORD-MANAGEMENT.md)
3. [Cleanup Guide](./weaviate-rag/04-CLEANUP-QUICKSTART.md)

### For Quality Assurance
Ensuring accurate responses:
1. [Fact Grounding](./weaviate-rag/05-FACT-GROUNDING.md)
2. [RAG Usage Tracking](./weaviate-rag/02-RAG-USAGE-TRACKING.md)
3. [Fact Correction](./weaviate-rag/07-FACT-CORRECTION.md)

---

## 🔑 Key Concepts

### What is RAG (Retrieval-Augmented Generation)?
RAG combines your library's Q&A knowledge base with AI to provide accurate, grounded answers to student questions.

### What is Weaviate?
Weaviate is the cloud vector database that stores your 1,568 Q&A pairs with semantic search capabilities.

### What is Vector Optimization?
Process of preparing transcript data for efficient semantic search in the knowledge base.

---

## 📞 Support

- **Technical Issues**: Check [Developer Guide](./architecture/02-DEVELOPER-GUIDE.md)
- **Data Problems**: See [Cleaning Strategy](./data-management/01-CLEANING-STRATEGY.md)
- **Wrong Answers**: Use [Record Management](./weaviate-rag/03-RECORD-MANAGEMENT.md)

---

## 📝 Document Version

**Last Updated**: November 2025  
**System Version**: 2.0  
**Documentation Structure**: Organized by feature area

---

## 🗺️ Navigation Tips

- **Numbered files** (01-, 02-) indicate recommended reading order
- **QUICKSTART** files provide quick reference
- **GUIDE** files provide detailed instructions
- **SUMMARY** files provide overview information

---

**Welcome to the Miami University Library AI Chatbot Documentation!**
