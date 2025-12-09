# Knowledge Management Documentation

## Overview

This folder contains documentation for managing the chatbot's integration with library guides, routing logic, and scope enforcement to ensure it only answers library-related questions.

---

## 📚 Documentation Files

### Knowledge Management
- **[01-OVERVIEW.md](./01-OVERVIEW.md)** - High-level overview of knowledge management strategy
- **[02-DETAILED-GUIDE.md](./02-DETAILED-GUIDE.md)** - Comprehensive knowledge management guide

### Routing & Integration
- **[03-ROUTING-GUIDE.md](./03-ROUTING-GUIDE.md)** - LibGuide vs MyGuide routing logic and implementation
- **[04-INTEGRATION-REPORT.md](./04-INTEGRATION-REPORT.md)** - MyGuide API integration report and features

### Quality Control
- **[05-SCOPE-ENFORCEMENT.md](./05-SCOPE-ENFORCEMENT.md)** - How the chatbot enforces library-related scope

---

## 🎯 Key Concepts

### LibGuides
- **What**: Library subject guides created by librarians
- **Source**: SpringShare LibGuides platform
- **Access**: Via Google Site Search (public website)

### MyGuides
- **What**: Research guides with structured API
- **Source**: Miami University custom platform
- **Access**: Via MyGuide API integration

### Scope Enforcement
- **Purpose**: Ensure chatbot only answers library-related questions
- **Method**: AI classification + confidence thresholds
- **Result**: Polite deflection of off-topic questions

---

## 🔄 Routing Logic

```
Student Question
      ↓
Intent Classification
      ↓
├── LibGuide Topics → Google Site Agent
│   (general library info, policies)
│
├── Research Topics → MyGuide Agent
│   (subject-specific research help)
│
└── Off-Topic → Polite Deflection
    (homework, non-library questions)
```

---

## 🛠️ Integration Features

### MyGuide API
- **Endpoint**: Custom REST API
- **Features**: Guide search, subject filtering, metadata
- **Agent**: `myguide_agent.py`
- **Documentation**: [04-INTEGRATION-REPORT.md](./04-INTEGRATION-REPORT.md)

### Google Site Search
- **Purpose**: Search library website and LibGuides
- **Features**: Custom Search Engine API
- **Agent**: `google_site_agent.py`
- **Coverage**: All public library pages

---

## 📊 Question Categories

| Category | Description | Routing | Example |
|----------|-------------|---------|---------|
| **Policy** | Library rules, hours | Google Site + RAG | "What are library hours?" |
| **Research** | Subject research help | MyGuide + RAG | "How do I cite APA?" |
| **Discovery** | Find books/databases | Discovery Agent | "Find books on climate" |
| **Technical** | Access issues | Google Site | "Can't login to database" |
| **Off-Topic** | Non-library | Deflection | "What's for lunch?" |

---

## 🚀 Common Tasks

### Update Guide Routing
Edit routing logic in:
```
/ai-core/src/graph/hybrid_router.py
/ai-core/src/graph/orchestrator.py
```

### Add New Guide Source
1. Create new agent in `/ai-core/src/agents/`
2. Register in orchestrator agent mapping
3. Update intent classification rules
4. Test with sample queries

📖 **Full Guide**: [02-DETAILED-GUIDE.md](./02-DETAILED-GUIDE.md)

---

### Test Scope Enforcement
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python -c "
from src.graph.hybrid_router import route_query
result = route_query('What is the meaning of life?')
print(result)
"
# Should deflect non-library questions
```

📖 **Full Guide**: [05-SCOPE-ENFORCEMENT.md](./05-SCOPE-ENFORCEMENT.md)

---

## 📖 Reading Order

For understanding the system:
1. [01-OVERVIEW.md](./01-OVERVIEW.md) - Start here
2. [03-ROUTING-GUIDE.md](./03-ROUTING-GUIDE.md) - Learn routing
3. [05-SCOPE-ENFORCEMENT.md](./05-SCOPE-ENFORCEMENT.md) - Understand limits

For technical implementation:
1. [02-DETAILED-GUIDE.md](./02-DETAILED-GUIDE.md) - Complete guide
2. [04-INTEGRATION-REPORT.md](./04-INTEGRATION-REPORT.md) - MyGuide details

---

## 🎯 Best Practices

1. **Update guides regularly** - Keep MyGuide API in sync
2. **Monitor deflections** - Track off-topic questions
3. **Test routing** - Verify questions go to correct agents
4. **Review scope** - Adjust enforcement thresholds as needed

---

**Guide students to the right resources!** 📚✨

---

**Last Updated**: December 9, 2025  
**Developer**: Meng Qu, Miami University Libraries - Oxford, OH
