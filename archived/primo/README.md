# Archived: Primo Catalog Search Code

## Status: ARCHIVED - December 16, 2025

This folder contains the archived Primo (catalog search) integration code that has been removed from the active chatbot.

## Why Archived?

The Primo catalog search functionality has been temporarily disabled and removed from the active codebase. The chatbot currently focuses on:
- Library hours and room booking (LibCal)
- Research guides (LibGuides)
- Subject librarian routing
- Website search (Google CSE)
- Live chat handoff (LibChat)

## Files in This Archive

### `primo_tools.py`
- Original Primo API integration
- Search functions for books, articles, and e-resources
- Facet filtering and result parsing

### `primo_multi_tool_agent.py`
- LangGraph agent that used Primo tools
- Multi-step search orchestration
- Citation formatting

## If You Need to Restore This Code

1. Copy files back to their original locations:
   - `primo_tools.py` → `/ai-core/src/tools/`
   - `primo_multi_tool_agent.py` → `/ai-core/src/agents/`

2. Uncomment in `/ai-core/src/graph/orchestrator.py`:
   ```python
   from src.agents.primo_multi_tool_agent import PrimoAgent
   ```

3. Update routing logic to include `discovery_search` intent

4. Add Primo environment variables back to `.env`:
   ```
   PRIMO_SCOPE=MyInst_and_CI
   PRIMO_API_KEY=your_key
   PRIMO_SEARCH_URL=https://api-na.hosted.exlibrisgroup.com/primo/v1/search?
   PRIMO_VID=01OHIOLINK_MU:MU
   ```

5. Regenerate requirements if needed

## Note

This code is preserved for future reference. It was functional at the time of archiving but may need updates if restored later due to:
- API changes
- Python package updates
- Architecture changes in the main codebase

---

**Archived by:** Meng Qu  
**Date:** December 16, 2025  
**Reason:** Catalog search functionality temporarily disabled
