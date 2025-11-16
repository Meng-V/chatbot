# RAG数据优化项目总结

## 📋 项目概述

本项目为Miami University Libraries Chatbot的历史对话数据提供完整的清洗、去重和RAG摄入方案，旨在优化知识库质量并提升Chatbot回答准确率。

## 🎯 核心目标

1. **数据清洗**：从3年6000条对话中提取高质量Q&A对
2. **去重优化**：移除重复和低质量内容
3. **智能分类**：自动主题分类和质量评分
4. **RAG增强**：升级schema，支持更智能的检索和排序

## 📁 新增文件清单

### 1. 核心脚本 (ai-core/scripts/)

| 文件 | 功能 | 关键特性 |
|------|------|----------|
| **clean_transcripts.py** | 数据清洗主脚本 | • 解析CSV对话记录<br>• 提取Q&A对（3种策略）<br>• 主题自动分类<br>• 质量评分<br>• 过滤超范围问题 |
| **deduplicate_transcripts.py** | 去重脚本 | • TF-IDF相似度计算<br>• 智能合并策略<br>• 质量保留/答案合并<br>• 去重统计分析 |
| **test_sample.py** | 快速测试脚本 | • 自动化测试流程<br>• 示例文件处理<br>• 结果验证 |

### 2. 增强的Agent (ai-core/src/agents/)

| 文件 | 修改内容 |
|------|----------|
| **transcript_rag_agent.py** | • 支持新schema字段<br>• 质量过滤（rating ≥ 2）<br>• 混合重排序算法<br>• 智能降级查询 |

### 3. 升级的摄入脚本 (ai-core/scripts/)

| 文件 | 修改内容 |
|------|----------|
| **ingest_transcripts.py** | • 增强schema定义<br>• 支持12个字段<br>• 批量进度显示<br>• 错误统计 |

### 4. 文档 (ai-core/docs/ 和 根目录)

| 文件 | 内容 |
|------|------|
| **transcript_data_cleaning_strategy.md** | 详细清理策略文档（40KB+）<br>• 数据分析<br>• 6种策略方案<br>• Schema设计<br>• 实施计划 |
| **RAG_DATA_PIPELINE_README.md** | 完整流程指南<br>• 三步处理流程<br>• Schema说明<br>• 高级用法<br>• FAQ |
| **QUICKSTART_CN.md** | 快速开始指南<br>• 背景介绍<br>• 架构说明<br>• 具体操作步骤<br>• 优化建议 |
| **RAG_OPTIMIZATION_SUMMARY.md** | 本文件：项目总结 |

## 🔧 技术架构

### 数据流程

```
CSV原始文件 (6000条对话)
    ↓
[clean_transcripts.py]
    ├─ 解析Transcript字段
    ├─ 提取Q&A对（3种策略）
    ├─ 主题分类
    ├─ 质量评分
    └─ 过滤超范围问题
    ↓
cleaned_transcripts.json (~5000条)
    ↓
[deduplicate_transcripts.py]
    ├─ TF-IDF相似度计算
    ├─ 重复检测（threshold=0.85）
    └─ 智能合并
    ↓
final_transcripts.json (~4000条)
    ↓
[ingest_transcripts.py]
    └─ 摄入Weaviate
    ↓
TranscriptQA Collection
    ↓
[transcript_rag_agent.py]
    ├─ 质量过滤
    ├─ 语义检索
    ├─ 混合重排序
    └─ 返回Top 3结果
```

### Schema对比

#### 优化前（简单版）
```python
{
    "question": str,
    "answer": str,
    "topic": str,
    "source": str
}
```

#### 优化后（增强版）
```python
{
    # 核心内容
    "question": str,
    "answer": str,
    
    # 分类
    "topic": str,              # 主题分类
    "keywords": [str],         # 关键词
    
    # 质量
    "rating": int,             # 用户评分 0-4
    "confidence_score": float, # 质量置信度 0.0-1.0
    
    # 上下文（可选）
    "context": str,            # 对话上下文
    
    # 元数据
    "source": str,
    "chat_id": str,
    "timestamp": str,
    "answerer": str,
    "department": str,
    "tags": [str]
}
```

## 📊 关键算法

### 1. 主题分类算法

```python
# 基于关键词匹配
TOPIC_KEYWORDS = {
    'discovery_search': ['book', 'article', 'database', ...],
    'booking_or_hours': ['hours', 'room', 'reservation', ...],
    'policy_or_service': ['renew', 'return', 'fine', ...],
    ...
}

# 计算每个主题得分
for topic, keywords in TOPIC_KEYWORDS.items():
    score = sum(1 for kw in keywords if kw in text)

# 返回最高分主题
return max(scores, key=scores.get)
```

### 2. 质量评分算法

```python
confidence_score = 0.5  # 基础分

# 用户评分加权（最高+0.3）
if rating >= 4: score += 0.3
elif rating >= 3: score += 0.2

# 答案长度适中（+0.1）
if 50 <= len(answer) <= 500: score += 0.1

# 包含URL（+0.1）
if 'http' in answer: score += 0.1

# 对话时长合理（+0.05）
if 30 <= duration <= 600: score += 0.05
```

### 3. 去重算法

```python
# TF-IDF向量化
vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
tfidf_matrix = vectorizer.fit_transform(questions)

# 余弦相似度
similarity_matrix = cosine_similarity(tfidf_matrix)

# 标记重复（相似度 >= 0.85）
for i, j in combinations:
    if similarity_matrix[i][j] >= 0.85:
        mark_as_duplicate(j)

# 保留最高质量
best = max(duplicates, key=lambda x: (x.confidence, x.rating))
```

### 4. RAG混合重排序

```python
# 获取5个候选结果
results = weaviate.query.near_text(query, limit=5)

# 计算综合得分
for result in results:
    combined_score = (
        semantic_similarity * 0.6 +   # 语义相关性60%
        confidence_score * 0.3 +       # 质量置信度30%
        (rating / 4.0) * 0.1           # 用户评分10%
    )

# 按综合得分排序，返回Top 3
return sorted(results, key=lambda x: x.combined_score)[:3]
```

## 📈 预期效果

### 数据质量提升

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| **数据量** | 简单Q&A | 5000+条 | 完整覆盖 |
| **质量控制** | 无 | confidence_score | ✓ |
| **主题分类** | 手动 | 自动6类 | ✓ |
| **去重** | 无 | TF-IDF去重 | 减少20-30% |
| **元数据** | 4字段 | 12字段 | 3x |

### RAG性能提升

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| **查询过滤** | 无 | Rating ≥ 2 | ✓ |
| **结果数量** | 3个 | 5→3（重排序） | ✓ |
| **排序算法** | 距离 | 混合得分 | ✓ |
| **置信度** | 简单 | 三级判断 | ✓ |
| **降级策略** | 无 | 自动重试 | ✓ |

### 覆盖率预估

- **可直接回答**: 60-70%
  - discovery_search: 35%
  - policy_or_service: 25%
  - booking_or_hours: 17%

- **需辅助回答**: 20-30%
  - subject_librarian: 13%（需API）
  - course_subject_help: 10%（需LibGuide）

- **转人工**: 10%
  - 复杂问题
  - 实时信息

## 🚀 实施步骤

### Phase 1: 快速验证（1天）

```bash
# 测试示例文件
python scripts/test_sample.py

# 验证结果
cat ai-core/data/test_cleaned.json | jq '.[0]'
```

### Phase 2: 完整处理（1-2天）

```bash
# 清洗所有历史数据
python scripts/clean_transcripts.py *.csv -o cleaned.json --strategy all

# 去重
python scripts/deduplicate_transcripts.py cleaned.json -o final.json

# 摄入Weaviate
TRANSCRIPTS_PATH=final.json python scripts/ingest_transcripts.py
```

### Phase 3: 测试优化（3-5天）

```python
# 测试RAG查询
from src.agents.transcript_rag_agent import transcript_rag_query
import asyncio

test_queries = [
    "How do I renew a book?",
    "What are library hours?",
    "Who is the biology librarian?",
]

for q in test_queries:
    result = await transcript_rag_query(q)
    print(f"Confidence: {result['confidence']}")
```

### Phase 4: 持续监控（长期）

- 跟踪RAG命中率
- 收集用户反馈
- 每季度更新数据
- 调整算法参数

## 📚 使用文档

### 快速开始
👉 [QUICKSTART_CN.md](../../QUICKSTART_CN.md)

### 详细策略
👉 [transcript_data_cleaning_strategy.md](./transcript_data_cleaning_strategy.md)

### 完整流程
👉 [RAG_DATA_PIPELINE_README.md](./RAG_DATA_PIPELINE_README.md)

## 🎯 核心创新点

1. **三策略Q&A提取**
   - First: 快速原型
   - All: 完整覆盖（推荐）
   - Context: 高级上下文保留

2. **自动质量评分**
   - 多维度评估（评分+长度+URL+时长）
   - 0.0-1.0连续评分
   - 可用于后续过滤和排序

3. **智能主题分类**
   - 基于scope_definition.py
   - 关键词自动匹配
   - 6大主题 + out_of_scope检测

4. **TF-IDF去重**
   - 相似度可调（推荐0.85）
   - 两种合并策略（best/merge）
   - 保留最高质量答案

5. **混合重排序**
   - 语义相似度60%
   - 质量置信度30%
   - 用户评分10%
   - 综合评估更准确

## 🔄 维护计划

### 每季度（推荐）

1. 导出新的对话CSV
2. 运行清洗脚本
3. 与现有数据合并
4. 去重后重新摄入

### 每月

1. 查看RAG命中率统计
2. 分析未命中的问题
3. 调整关键词和分类规则

### 实时

1. 监控查询日志
2. 收集用户反馈
3. 标记低质量回答

## 🛠️ 技术栈

- **Python 3.8+**
- **Weaviate v4** (向量数据库)
- **OpenAI API** (text-embedding-ada-002)
- **scikit-learn** (TF-IDF, 相似度计算)
- **LangGraph** (Agent编排)
- **LangChain** (LLM框架)

## 📞 支持

如有问题或建议：

1. 查看详细文档
2. 检查脚本日志输出
3. 参考常见问题（FAQ）
4. 联系开发团队

---

## 📊 项目统计

- **代码量**: 约1500行Python
- **文档量**: 约15000字
- **脚本数**: 3个核心脚本
- **文档数**: 4个详细文档
- **Schema字段**: 从4个扩展到12个
- **算法**: 4个核心算法
- **预期数据**: 4000-5000条高质量Q&A

---

**创建日期**: 2024-11-16  
**版本**: 1.0  
**状态**: ✅ 准备就绪
