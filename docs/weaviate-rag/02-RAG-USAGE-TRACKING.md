# RAG Usage Tracking & Analytics

## Overview

The chatbot now automatically tracks every RAG (Retrieval-Augmented Generation) query in the Prisma database, allowing developers to monitor usage frequency, confidence levels, and performance metrics.

---

## What Gets Tracked

Every time the `transcript_rag` agent is called, the following information is logged to the database:

### Tracked Metrics

| Field | Description | Example |
|-------|-------------|---------|
| **agent_name** | Always "transcript_rag" | `transcript_rag` |
| **tool_name** | Always "rag_search" | `rag_search` |
| **query** | User's original question | "When was King Library built?" |
| **confidence** | RAG confidence level | `high`, `medium`, `low`, `none` |
| **similarity_score** | Vector similarity (0-1) | `0.92` |
| **matched_topic** | Topic category matched | `building_information` |
| **num_results** | Number of results returned | `3` |
| **success** | Whether query succeeded | `true` / `false` |
| **execution_time** | Query time in milliseconds | `245` |
| **timestamp** | When query was executed | `2025-11-17 12:30:45` |
| **conversation_id** | Associated conversation | UUID |

---

## Database Schema

RAG usage is stored in the `ToolExecution` table:

```prisma
model ToolExecution {
  id              String       @id @default(uuid())
  conversationId  String
  agentName       String        // "transcript_rag"
  toolName        String        // "rag_search"
  parameters      String        // JSON with query details
  success         Boolean
  executionTime   Int           // milliseconds
  timestamp       DateTime      @default(now())
  conversation    Conversation  @relation(fields: [conversationId], references: [id])
  
  @@index([conversationId])
  @@index([agentName])
  @@index([toolName])
}
```

The `parameters` field contains JSON:
```json
{
  "query": "When was King Library built?",
  "confidence": "high",
  "similarity_score": 0.92,
  "matched_topic": "building_information",
  "num_results": 3
}
```

---

## How to View RAG Usage

### Quick Analytics

```bash
# Last 7 days summary
python scripts/analyze_rag_usage.py

# Last 30 days summary
python scripts/analyze_rag_usage.py --days 30

# Detailed query log
python scripts/analyze_rag_usage.py --detailed
```

### Example Output

```
================================================================================
RAG USAGE ANALYTICS - Last 7 Days
================================================================================
Date Range: 2025-11-10 to 2025-11-17

📊 OVERVIEW
--------------------------------------------------------------------------------
Total RAG Queries: 127
✅ Successful: 122 (96.1%)
❌ Failed: 5 (3.9%)
⏱️  Average Execution Time: 245ms

🎯 CONFIDENCE LEVELS
--------------------------------------------------------------------------------
  HIGH: 87 (71.3%)
  MEDIUM: 28 (23.0%)
  LOW: 7 (5.7%)

📈 SIMILARITY SCORES
--------------------------------------------------------------------------------
  Average: 0.856
  Min: 0.623
  Max: 0.985

📚 TOPICS MATCHED
--------------------------------------------------------------------------------
  building_information: 34 (27.9%)
  policy_or_service: 29 (23.8%)
  location_information: 24 (19.7%)
  hours: 18 (14.8%)
  general: 17 (13.9%)

📅 DAILY BREAKDOWN
--------------------------------------------------------------------------------
  2025-11-17: 23 queries
  2025-11-16: 19 queries
  2025-11-15: 18 queries
  ...
```

---

## Querying Usage Programmatically

### Python Example

```python
import asyncio
from src.database.prisma_client import get_prisma_client
from datetime import datetime, timedelta

async def get_rag_stats():
    prisma = get_prisma_client()
    
    if not prisma.is_connected():
        await prisma.connect()
    
    # Get RAG queries from last 7 days
    start_date = datetime.now() - timedelta(days=7)
    
    rag_queries = await prisma.toolexecution.find_many(
        where={
            "agentName": "transcript_rag",
            "toolName": "rag_search",
            "timestamp": {"gte": start_date}
        },
        order={"timestamp": "desc"}
    )
    
    print(f"Total RAG queries: {len(rag_queries)}")
    
    await prisma.disconnect()

asyncio.run(get_rag_stats())
```

### SQL Query (Direct Database Access)

```sql
-- Get RAG usage summary
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as total_queries,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
    AVG(execution_time) as avg_execution_time_ms
FROM "ToolExecution"
WHERE 
    "agentName" = 'transcript_rag' 
    AND "toolName" = 'rag_search'
    AND timestamp >= NOW() - INTERVAL '7 days'
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

```sql
-- Get confidence level distribution
SELECT 
    parameters::json->>'confidence' as confidence_level,
    COUNT(*) as count,
    AVG((parameters::json->>'similarity_score')::float) as avg_similarity
FROM "ToolExecution"
WHERE 
    "agentName" = 'transcript_rag' 
    AND "toolName" = 'rag_search'
    AND timestamp >= NOW() - INTERVAL '7 days'
GROUP BY parameters::json->>'confidence'
ORDER BY count DESC;
```

---

## Use Cases

### 1. Monitor RAG Performance

Track whether RAG is providing high-confidence answers:

```bash
python scripts/analyze_rag_usage.py --days 7
```

Look for:
- **High confidence %**: Should be > 60%
- **Average similarity**: Should be > 0.80
- **Failure rate**: Should be < 5%

### 2. Identify Content Gaps

Use detailed logs to find queries with low confidence:

```bash
python scripts/analyze_rag_usage.py --detailed | grep "low\|none"
```

Then add missing Q&A pairs:
```bash
# Edit with missing content
nano scripts/update_rag_facts.py

# Update database
python scripts/update_rag_facts.py
```

### 3. Track RAG Adoption

Monitor how often RAG is being used vs other agents:

```python
# Get all tool executions
tool_usage = await prisma.toolexecution.find_many(
    where={"timestamp": {"gte": start_date}}
)

# Group by agent
from collections import Counter
agent_counts = Counter(t.agentName for t in tool_usage)
```

### 4. Performance Monitoring

Track execution time trends:

```bash
# Check if RAG is slowing down
python scripts/analyze_rag_usage.py --days 30
```

Alert if average execution time > 500ms.

---

## Integration with Monitoring Tools

### Export to CSV

```python
import csv
import asyncio
from src.database.prisma_client import get_prisma_client
import json

async def export_rag_usage():
    prisma = get_prisma_client()
    await prisma.connect()
    
    executions = await prisma.toolexecution.find_many(
        where={"agentName": "transcript_rag"}
    )
    
    with open('rag_usage.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'timestamp', 'conversation_id', 'query', 
            'confidence', 'similarity', 'execution_time'
        ])
        
        for exec in executions:
            params = json.loads(exec.parameters)
            writer.writerow([
                exec.timestamp,
                exec.conversationId,
                params.get('query', ''),
                params.get('confidence', ''),
                params.get('similarity_score', 0),
                exec.executionTime
            ])
    
    await prisma.disconnect()

asyncio.run(export_rag_usage())
```

### Grafana Dashboard Query

```sql
-- Prometheus/Grafana time series query
SELECT 
    time_bucket('1 hour', timestamp) AS time,
    COUNT(*) as queries_per_hour,
    AVG(execution_time) as avg_execution_time
FROM "ToolExecution"
WHERE 
    "agentName" = 'transcript_rag'
    AND timestamp > $__timeFrom()
GROUP BY time
ORDER BY time;
```

---

## Best Practices

### 1. Regular Monitoring

Schedule weekly reviews:
```bash
# Add to cron (weekly report)
0 9 * * 1 cd /path/to/ai-core && python scripts/analyze_rag_usage.py --days 7 > /tmp/rag_report.txt
```

### 2. Set Alerts

Monitor key metrics:
- **Alert if success rate < 90%**: Check Weaviate connection
- **Alert if avg similarity < 0.70**: Update RAG content
- **Alert if execution time > 500ms**: Check Weaviate performance

### 3. Continuous Improvement

Monthly workflow:
1. Run analytics: `python scripts/analyze_rag_usage.py --days 30 --detailed`
2. Identify low-confidence queries
3. Add missing Q&A pairs: `python scripts/update_rag_facts.py`
4. Re-test: `python scripts/test_fact_queries.py`

### 4. Privacy Considerations

RAG queries contain user questions. Ensure:
- Database access is restricted
- Logs are rotated/archived properly
- Comply with data retention policies

---

## Troubleshooting

### No RAG Usage Showing

**Check:**
1. Is RAG being called? Check orchestrator logs
2. Is conversation_id being passed? Check main.py
3. Database connection working? Check Prisma logs

**Test:**
```bash
# Trigger a RAG query
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"message": "When was King Library built?"}'

# Check database
python scripts/analyze_rag_usage.py --days 1
```

### Incorrect Statistics

**Check:**
1. Timezone settings in database
2. Date range in queries
3. JSON parsing in parameters field

### Performance Issues

If analytics script is slow:
```sql
-- Add indexes (should already exist)
CREATE INDEX IF NOT EXISTS idx_toolexecution_agent_timestamp 
ON "ToolExecution"("agentName", "timestamp");
```

---

## Future Enhancements

Potential additions:
- [ ] Real-time dashboard (React + WebSocket)
- [ ] Automated weekly email reports
- [ ] A/B testing for RAG improvements
- [ ] User satisfaction correlation
- [ ] Topic-specific analytics
- [ ] Query clustering/grouping

---

## Quick Reference

| Task | Command |
|------|---------|
| View usage summary | `python scripts/analyze_rag_usage.py` |
| Last 30 days | `python scripts/analyze_rag_usage.py --days 30` |
| Detailed queries | `python scripts/analyze_rag_usage.py --detailed` |
| Export to CSV | See "Export to CSV" section |
| Update RAG content | `python scripts/update_rag_facts.py` |

---

**Last Updated**: November 2025  
**Version**: 1.0
