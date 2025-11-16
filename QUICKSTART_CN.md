# 快速开始：历史对话RAG优化

## 📝 背景

你有3年（2023-2025）的历史对话数据，平均每年2000次图书馆员和学生的在线问答记录。现在需要将这些数据清理并导入Weaviate RAG系统，以提升Chatbot的回答能力。

## 🎯 目标

构建一个高质量的RAG知识库，使Chatbot能够：
- **直接回答**：60-70%的常见问题
- **辅助回答**：20-30%需要结合API的问题  
- **转人工**：10%的复杂问题

## 📊 当前系统架构

你的系统使用**混合路由架构**：

```
用户问题
    ↓
Meta Router (LLM分类)
    ↓
┌───────────────────────────────────────┐
│ 根据问题类型选择Agent:                  │
│ - discovery_search → Primo Agent      │
│ - subject_librarian → Subject Agent   │
│ - booking_or_hours → LibCal Agent     │
│ - policy_or_service → Google + RAG    │
│ - general_question → RAG + Google     │
└───────────────────────────────────────┘
    ↓
RAG (transcript_rag_agent.py)
    ↓
Weaviate (TranscriptQA collection)
```

## 🚀 三步完成数据处理

### 前置准备

```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core

# 安装依赖
pip install scikit-learn numpy

# 确认.env配置
# WEAVIATE_HOST=...
# WEAVIATE_API_KEY=...
# OPENAI_API_KEY=...
```

### 方案A：快速测试（推荐先做）

使用示例文件快速验证流程：

```bash
# 运行自动化测试脚本
python scripts/test_sample.py
```

这会自动：
1. ✅ 清洗 `chat_transcript_2025-11-06_10_00_32.csv`
2. ✅ 提取Q&A对
3. ✅ 生成 `ai-core/data/test_cleaned.json`
4. ✅ 显示统计信息

### 方案B：处理完整数据（生产环境）

#### 第1步：数据清洗

```bash
# 处理所有历史CSV文件（假设你有三个文件）
python scripts/clean_transcripts.py \
    /path/to/chat_transcript_2023.csv \
    /path/to/chat_transcript_2024.csv \
    /path/to/chat_transcript_2025.csv \
    --output ai-core/data/cleaned_transcripts.json \
    --strategy all \
    --min-confidence 0.5
```

**预期结果**：
- 📥 输入：6000条对话
- 📤 输出：约5000条Q&A对
- ⏱️ 耗时：5-10分钟

#### 第2步：去重（推荐）

```bash
python scripts/deduplicate_transcripts.py \
    ai-core/data/cleaned_transcripts.json \
    --output ai-core/data/final_transcripts.json \
    --threshold 0.85 \
    --strategy best \
    --min-confidence 0.6
```

**预期结果**：
- 📥 输入：约5000条Q&A对
- 📤 输出：约4000条唯一Q&A对
- ⏱️ 耗时：2-5分钟

#### 第3步：摄入Weaviate

```bash
# 使用处理好的数据
TRANSCRIPTS_PATH=ai-core/data/final_transcripts.json \
python scripts/ingest_transcripts.py
```

**预期结果**：
- 📥 输入：约4000条Q&A对
- 📤 输出：Weaviate中的TranscriptQA collection
- ⏱️ 耗时：5-10分钟

## 📋 数据处理规则

### ✅ 保留的对话

- ⭐ Rating ≥ 2（用户评分至少为2）
- 💬 Message Count 2-30（有效对话长度）
- 📚 在图书馆服务范围内
- ✍️ 有实质性问答内容

### ❌ 过滤的对话

- 🚫 超出范围：入学、学费、住房、食堂、IT支持等
- 👎 Rating = 1（低评分）
- 📉 消息太少（< 2条）或太多（> 30条）
- 🗑️ 纯寒暄语（Hi, Thanks等）

### 🎯 主题自动分类

基于关键词匹配：

| 主题 | 关键词示例 | 占比 |
|------|-----------|------|
| **discovery_search** | book, article, database, catalog | 35% |
| **policy_or_service** | renew, return, fine, print, scan | 25% |
| **booking_or_hours** | hours, room, reservation, open | 17% |
| **subject_librarian** | librarian, research help, guide | 13% |
| **general_question** | 其他图书馆相关问题 | 10% |

### 📊 质量评分算法

自动计算`confidence_score`（0.0-1.0）：

```python
score = 0.5  # 基础分

# 用户评分加权
if rating >= 4: score += 0.3
elif rating >= 3: score += 0.2

# 答案长度适中
if 50 <= len(answer) <= 500: score += 0.1

# 包含URL（通常是高质量回答）
if 'http' in answer: score += 0.1

# 对话时长合理
if 30s <= duration <= 600s: score += 0.05
```

## 🔍 验证数据质量

### 查看统计信息

```bash
# 查看清洗后的统计
python scripts/clean_transcripts.py *.csv -o test.json

# 分析重复情况但不去重
python scripts/deduplicate_transcripts.py test.json --analyze-only
```

### 随机查看数据

```bash
# 查看第一条记录
cat ai-core/data/final_transcripts.json | jq '.[0]'

# 随机查看一条
cat ai-core/data/final_transcripts.json | jq '.[] | select(.rating >= 4)' | head -1
```

### 测试RAG查询

```python
# 在Python中测试
import asyncio
from src.agents.transcript_rag_agent import transcript_rag_query

async def test():
    queries = [
        "How do I renew a book?",
        "What are the library hours?",
        "Who is the biology librarian?",
        "How do I print in the library?"
    ]
    
    for q in queries:
        print(f"\n{'='*60}")
        print(f"Q: {q}")
        result = await transcript_rag_query(q)
        print(f"Success: {result['success']}")
        print(f"Confidence: {result.get('confidence', 'N/A')}")
        print(f"\nA: {result['text'][:200]}...")

asyncio.run(test())
```

## 📈 优化后的RAG特性

### 增强的Schema

相比之前的简单`question`+`answer`，现在包含：

```json
{
  "question": "问题文本",
  "answer": "答案文本",
  "topic": "discovery_search",
  "keywords": ["book", "search", "catalog"],
  "rating": 4,
  "confidence_score": 0.85,
  "context": "对话上下文（可选）",
  "source": "transcripts",
  "chat_id": "11527278",
  "timestamp": "2025-01-02 09:10:41",
  "answerer": "Barry Zaslow",
  "department": "Reference",
  "tags": []
}
```

### 智能查询与重排序

`transcript_rag_agent.py`现在支持：

1. **质量过滤**：默认只查询Rating ≥ 2的答案
2. **多结果检索**：获取5个候选结果
3. **混合重排序**：
   ```python
   combined_score = 
       semantic_similarity * 0.6 +
       confidence_score * 0.3 +
       rating * 0.1
   ```
4. **智能降级**：无高质量结果时移除过滤条件重试

## 📚 完整文档

详细策略和技术细节请参考：

- 📖 [完整数据清理策略](ai-core/docs/transcript_data_cleaning_strategy.md)
- 📘 [数据处理流程指南](ai-core/docs/RAG_DATA_PIPELINE_README.md)

## 🎯 下一步计划

### 短期（1-2周）

1. ✅ 使用test_sample.py验证流程
2. ✅ 处理完整3年数据
3. ✅ 监控RAG命中率和质量
4. 📊 收集用户反馈

### 中期（1-2月）

1. 🔄 根据反馈调整过滤规则
2. 🎯 优化主题分类准确度
3. 📈 A/B测试不同向量化策略
4. 🔍 添加实体提取（资源名、URL等）

### 长期（3-6月）

1. 🤖 自动化数据更新流程（每季度）
2. 📊 构建质量监控仪表板
3. 🧠 训练自定义embedding模型
4. 🔗 与其他数据源整合（FAQ、文档等）

## ❓ 常见问题

### Q: 数据量太大，处理时间长怎么办？

```bash
# 分批处理
python scripts/clean_transcripts.py 2023.csv -o cleaned_2023.json
python scripts/clean_transcripts.py 2024.csv -o cleaned_2024.json
python scripts/clean_transcripts.py 2025.csv -o cleaned_2025.json

# 合并JSON文件
jq -s 'add' cleaned_*.json > all_cleaned.json

# 然后去重和摄入
python scripts/deduplicate_transcripts.py all_cleaned.json -o final.json
```

### Q: 如何调整相似度阈值？

从严格到宽松测试：

```bash
# 严格（95%相似才算重复）
python scripts/deduplicate_transcripts.py data.json -t 0.95 -o strict.json

# 推荐（85%相似算重复）
python scripts/deduplicate_transcripts.py data.json -t 0.85 -o medium.json

# 宽松（75%相似算重复）
python scripts/deduplicate_transcripts.py data.json -t 0.75 -o loose.json
```

### Q: 如何只保留最高质量数据？

```bash
# 只保留Rating >= 3 且 confidence >= 0.7
python scripts/clean_transcripts.py *.csv \
    --min-confidence 0.7 \
    -o high_quality.json

# 去重时进一步过滤
python scripts/deduplicate_transcripts.py high_quality.json \
    --min-confidence 0.8 \
    -o premium.json
```

### Q: 需要重新建collection吗？

如果schema改变了（增加了新字段），需要：

```bash
# 1. 删除旧collection（在Weaviate控制台或代码中）
# 2. 重新运行ingest脚本会自动创建新schema
python scripts/ingest_transcripts.py
```

## 🆘 获取帮助

如有问题：

1. 查看详细日志输出
2. 检查CSV文件格式
3. 确认依赖包已安装
4. 参考完整文档：`ai-core/docs/`

---

**预期成果**：

- 📦 **数据量**：从6000条对话提取4000-5000条高质量Q&A对
- 🎯 **覆盖率**：能够直接或辅助回答60-80%的用户问题
- ⭐ **质量**：平均confidence_score ≥ 0.7
- 🚀 **性能**：RAG查询响应时间 < 500ms

开始处理你的数据吧！🎉
