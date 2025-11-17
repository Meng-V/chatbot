# RAG数据处理流程完整指南

## 📌 概述

本文档提供了从原始CSV对话记录到Weaviate RAG数据库的完整数据处理流程。

## 🗂️ 文件结构

```
chatbot/
├── ai-core/
│   ├── scripts/
│   │   ├── clean_transcripts.py       # 第1步：数据清洗
│   │   ├── deduplicate_transcripts.py # 第2步：去重（可选）
│   │   └── ingest_transcripts.py      # 第3步：摄入Weaviate
│   ├── src/
│   │   └── agents/
│   │       └── transcript_rag_agent.py # RAG查询agent（已增强）
│   └── docs/
│       ├── transcript_data_cleaning_strategy.md  # 详细策略文档
│       └── RAG_DATA_PIPELINE_README.md           # 本文件
└── [CSV文件存放位置]
```

## 🚀 快速开始

### 前置要求

1. **安装依赖包**：
```bash
cd ai-core
pip install scikit-learn numpy  # 用于去重脚本
```

2. **确保已有Weaviate配置**：
   - 在`.env`文件中设置：
     - `WEAVIATE_HOST`
     - `WEAVIATE_API_KEY`
     - `OPENAI_API_KEY`

### 完整流程（3步）

#### 第1步：清洗数据

```bash
# 处理单个CSV文件
python scripts/clean_transcripts.py chat_transcript_2025-11-06_10_00_32.csv

# 处理多个CSV文件（2023-2025年）
python scripts/clean_transcripts.py \
    chat_transcript_2023.csv \
    chat_transcript_2024.csv \
    chat_transcript_2025.csv \
    --output cleaned_transcripts.json \
    --strategy all \
    --min-confidence 0.5
```

**参数说明**：
- `csv_files`: CSV文件路径（可以指定多个）
- `--output`: 输出JSON文件名（默认：`cleaned_transcripts.json`）
- `--strategy`: 提取策略
  - `first`: 只提取首问首答（快速）
  - `all`: 提取所有Q&A对（推荐）
- `--min-confidence`: 最低置信度阈值（0.0-1.0）

**预期输出**：
```
✅ 数据已保存到: cleaned_transcripts.json
📦 共 5247 条Q&A对

📊 处理统计
总对话数: 6000
提取的Q&A对: 5247
过滤掉: 753

主题分布:
  - discovery_search: 1850 (35.3%)
  - policy_or_service: 1312 (25.0%)
  - booking_or_hours: 892 (17.0%)
  - subject_librarian: 678 (12.9%)
  - general_question: 515 (9.8%)
```

#### 第2步：去重（可选但推荐）

```bash
# 去重并保留最高质量的回答
python scripts/deduplicate_transcripts.py \
    cleaned_transcripts.json \
    --output deduplicated_transcripts.json \
    --threshold 0.85 \
    --strategy best \
    --min-confidence 0.6
```

**参数说明**：
- `input`: 输入JSON文件（来自第1步）
- `--output`: 输出文件名（默认：`deduplicated_transcripts.json`）
- `--threshold`: 相似度阈值（0.85 = 85%相似即视为重复）
- `--strategy`: 合并策略
  - `best`: 保留最高质量的回答（推荐）
  - `merge`: 合并多个答案
- `--min-confidence`: 过滤低质量数据
- `--analyze-only`: 只分析不去重

**预期输出**：
```
✅ 去重完成: 5247 -> 4182 (removed 1065 duplicates)
📦 最终数量: 4182 条Q&A对

质量分布:
  - Very High (≥0.8): 1254 (30.0%)
  - High (0.7-0.8): 1672 (40.0%)
  - Medium (0.6-0.7): 1046 (25.0%)
  - Low (<0.6): 210 (5.0%)
```

#### 第3步：摄入Weaviate

```bash
# 使用默认路径（ai-core/data/transcripts_clean.json）
python scripts/ingest_transcripts.py

# 或指定文件路径
TRANSCRIPTS_PATH=/path/to/deduplicated_transcripts.json python scripts/ingest_transcripts.py
```

**预期输出**：
```
✅ Created TranscriptQA collection with enhanced schema
📦 Preparing to ingest 4182 transcripts...
   Progress: 100/4182...
   Progress: 200/4182...
   ...
✅ Ingestion complete!
   Success: 4182
   Errors: 0
   Total: 4182
```

## 📊 数据Schema说明

### 输入数据（CSV格式）

| 字段名 | 说明 | 示例 |
|--------|------|------|
| Chat ID | 对话唯一标识 | 11527278 |
| Initial Question | 用户的初始问题 | "Do you have The Great Gatsby?" |
| Transcript | 完整对话记录 | "09:13:17 - Librarian : Hi..." |
| Rating (0-4) | 用户评分 | 4 |
| Message Count | 消息数量 | 8 |
| Answerer | 回答的图书馆员 | Barry Zaslow |
| Timestamp | 时间戳 | 2025-01-02 09:10:41 |

### 输出数据（JSON格式）

```json
{
  "question": "Do you have The Great Gatsby?",
  "answer": "Yes, we have multiple copies...",
  "topic": "discovery_search",
  "keywords": ["book", "gatsby", "search", "catalog"],
  "rating": 4,
  "confidence_score": 0.85,
  "source": "transcripts",
  "chat_id": "11527278",
  "timestamp": "2025-01-02 09:10:41",
  "answerer": "Barry Zaslow",
  "department": "Reference",
  "tags": []
}
```

### Weaviate Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| **question** | TEXT | 用户问题（向量化） |
| **answer** | TEXT | 图书馆员回答 |
| **topic** | TEXT | 主题分类 |
| **keywords** | TEXT_ARRAY | 关键词列表 |
| **rating** | INT | 用户评分 (0-4) |
| **confidence_score** | NUMBER | 质量置信度 (0.0-1.0) |
| **context** | TEXT | 对话上下文（可选） |
| **source** | TEXT | 数据来源 |
| **chat_id** | TEXT | 原始对话ID |
| **timestamp** | TEXT | 时间戳 |
| **answerer** | TEXT | 回答人 |
| **department** | TEXT | 部门 |
| **tags** | TEXT_ARRAY | 标签列表 |

## 🎯 数据过滤规则

### 自动过滤（在clean_transcripts.py中）

以下对话会被**自动过滤掉**：

1. **消息数过少**：Message Count < 2
2. **消息数过多**：Message Count > 30（复杂案例）
3. **低评分**：Rating = 1
4. **无初始问题**：Initial Question为空
5. **无对话记录**：Transcript为空
6. **超出范围**：包含OUT_OF_SCOPE关键词
   - 入学、学费、住房、食堂
   - Canvas、Blackboard、邮箱
   - 作业帮助、考试答案

### 主题分类

基于关键词自动分类为：

- `discovery_search`: 图书/文章检索
- `booking_or_hours`: 预订房间/开放时间
- `policy_or_service`: 政策/服务（续借、罚款等）
- `subject_librarian`: Subject Librarian咨询
- `course_subject_help`: 课程资源帮助
- `general_question`: 一般性问题

### 质量评分（confidence_score）

自动计算，范围0.0-1.0：

- **+0.3**: Rating ≥ 4
- **+0.2**: Rating = 3
- **+0.1**: 答案长度适中（50-500字符）
- **+0.1**: 答案包含URL
- **+0.05**: 对话时长合理（30秒-10分钟）

## 🔧 高级用法

### 按年份分别处理

```bash
# 2023年数据
python scripts/clean_transcripts.py chat_transcript_2023.csv -o cleaned_2023.json

# 2024年数据
python scripts/clean_transcripts.py chat_transcript_2024.csv -o cleaned_2024.json

# 2025年数据
python scripts/clean_transcripts.py chat_transcript_2025.csv -o cleaned_2025.json

# 合并所有文件
cat cleaned_2023.json cleaned_2024.json cleaned_2025.json > all_cleaned.json

# 去重
python scripts/deduplicate_transcripts.py all_cleaned.json -o final_data.json
```

### 只提取高质量数据

```bash
# 只保留Rating >= 3 且 confidence >= 0.7的数据
python scripts/clean_transcripts.py *.csv \
    --output high_quality.json \
    --min-confidence 0.7
    
# 在去重时进一步过滤
python scripts/deduplicate_transcripts.py high_quality.json \
    --min-confidence 0.8 \
    --output premium_data.json
```

### 分析数据但不去重

```bash
# 查看有多少重复数据
python scripts/deduplicate_transcripts.py cleaned_transcripts.json --analyze-only
```

## 📈 优化建议

### Phase 1: 快速原型（当前可做）

1. 使用`--strategy first`快速提取
2. 只使用Rating >= 3的数据
3. 摄入500-1000条测试效果

```bash
python scripts/clean_transcripts.py sample.csv \
    --strategy first \
    --min-confidence 0.6 \
    --output test_data.json
```

### Phase 2: 生产级别

1. 使用`--strategy all`提取所有Q&A对
2. 完整去重流程
3. 摄入所有高质量数据（3000-5000条）

```bash
# 完整流程
python scripts/clean_transcripts.py *.csv --strategy all -o cleaned.json
python scripts/deduplicate_transcripts.py cleaned.json -o final.json
TRANSCRIPTS_PATH=final.json python scripts/ingest_transcripts.py
```

### Phase 3: 持续优化

1. 每季度更新数据
2. 监控RAG命中率
3. 根据反馈调整过滤规则

## 🧪 测试RAG效果

摄入数据后，可以直接测试：

```python
from src.agents.transcript_rag_agent import transcript_rag_query
import asyncio

# 测试查询
async def test():
    result = await transcript_rag_query("How do I renew a book?")
    print(result['text'])

asyncio.run(test())
```

## 📊 预期效果

### 数据量预估

- **原始对话**：3年 × 2000条/年 = 6000条
- **清洗后**：约5000-5500条Q&A对（过滤率10-20%）
- **去重后**：约4000-5000条唯一Q&A对（去重率20-30%）

### 覆盖率预估

根据主题分布：

- **可直接回答**（60-70%）：
  - discovery_search（35%）
  - policy_or_service（25%）
  - booking_or_hours（17%）
  
- **需辅助回答**（20-30%）：
  - subject_librarian（13%）需结合API
  - course_subject_help（10%）需结合LibGuide

- **转人工**（10%）：
  - 复杂问题
  - 需要实时信息

## ❓ 常见问题

### Q1: 如果CSV文件太大怎么办？

可以分批处理：

```bash
# 拆分大文件
split -l 5000 large_transcript.csv transcript_part_

# 分别处理
python scripts/clean_transcripts.py transcript_part_* -o cleaned.json
```

### Q2: 如何更新已有数据？

重新运行完整流程会**覆盖**现有collection。如需增量更新，需要：

1. 导出现有数据
2. 合并新旧数据
3. 去重
4. 重新摄入

### Q3: 如何验证数据质量？

```bash
# 查看统计信息
python scripts/deduplicate_transcripts.py cleaned.json --analyze-only

# 随机抽查
python -c "import json; import random; data = json.load(open('cleaned.json')); print(json.dumps(random.choice(data), indent=2))"
```

### Q4: 如何调整相似度阈值？

从高到低测试：

```bash
# 严格去重（0.90 = 90%相似才算重复）
python scripts/deduplicate_transcripts.py cleaned.json -t 0.90 -o strict.json

# 宽松去重（0.80 = 80%相似就算重复）
python scripts/deduplicate_transcripts.py cleaned.json -t 0.80 -o loose.json
```

## 🔗 相关文档

- [详细清理策略](./transcript_data_cleaning_strategy.md)
- [Scope Definition](../src/config/scope_definition.py)
- [RAG Agent实现](../src/agents/transcript_rag_agent.py)

## 🆘 获取帮助

如遇到问题：

1. 检查CSV文件格式是否正确
2. 确认Python依赖已安装
3. 查看错误日志
4. 联系开发团队

---

**最后更新**: 2025-11-16
