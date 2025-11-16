# 历史对话数据清理与RAG优化策略

## 📊 现状分析

### 数据规模
- **总量**：3年 × 2000次/年 = 约6000条对话记录
- **文件大小**：单个CSV约3MB（短期数据），完整数据预计更大
- **当前RAG结构**：简单的Q&A对（question + answer + topic + source）

### CSV原始数据结构
```
- Chat ID: 对话唯一标识
- Patron: 用户信息
- Contact Info: 联系方式
- Timestamp: 时间戳
- Wait Time / Duration: 等待和对话时长
- Rating (0-4): 用户评分
- Initial Question: 初始问题
- Transcript: 完整对话记录（多轮对话，时间戳 + 说话人 + 内容）
- Tags: 标签
- Message Count: 消息数量
```

---

## 🎯 数据清理策略

### 1️⃣ **数据质量过滤**

#### 1.1 按评分筛选（优先级：高）
```python
# 保留高质量对话
- Rating >= 3: 高质量回答，优先纳入RAG
- Rating == 2: 需人工审核
- Rating <= 1 或 Rating == 0（无评分）: 谨慎使用，可能包含问题
```

**建议**：
- 先用Rating >= 3的数据（约60-70%）构建基础RAG
- 无评分的数据可作为补充，但需额外质量检查

#### 1.2 按对话长度筛选
```python
# 过滤过短或过长的对话
- Message Count < 2: 无效对话，删除
- Message Count 2-20: 正常对话，保留
- Message Count > 20: 超长对话，需拆分处理
```

#### 1.3 按主题范围筛选（极其重要）
根据你的`scope_definition.py`，必须严格过滤：

**保留**（IN_SCOPE）：
- 图书馆资源查询（书籍、数据库、文章）
- 图书馆服务（预订房间、续借、打印）
- 图书馆空间和开放时间
- Subject Librarian咨询
- 图书馆政策（罚款、借阅规则）

**删除**（OUT_OF_SCOPE）：
- 大学一般性问题（入学、学费、住房）
- 课程作业帮助
- IT技术支持（Canvas、邮箱）
- 非图书馆设施

---

### 2️⃣ **对话解析与分段**

#### 2.1 解析Transcript字段
```python
# Transcript格式示例：
# "09:13:17 - Barry Zaslow : Hi Kayla..."
# "09:13:36 - Patron : Sadly I need..."

def parse_transcript(transcript_text):
    """
    将完整对话拆分为结构化的消息列表
    """
    messages = []
    lines = transcript_text.split('\n')
    
    for line in lines:
        match = re.match(r'(\d{2}:\d{2}:\d{2}|\d{2}:\d{2}) - ([^:]+) : (.+)', line)
        if match:
            time, speaker, content = match.groups()
            messages.append({
                'time': time,
                'speaker': speaker.strip(),
                'content': content.strip()
            })
    
    return messages
```

#### 2.2 提取Q&A对（核心逻辑）

**策略A：首问-首答提取**
```python
# 最简单，适合快速构建
def extract_first_qa(messages, initial_question):
    """
    提取Initial Question + 图书馆员的第一个回答
    """
    librarian_answer = None
    
    for msg in messages:
        if msg['speaker'] != 'Patron':  # 图书馆员回复
            librarian_answer = msg['content']
            break
    
    if librarian_answer:
        return {
            'question': initial_question,
            'answer': librarian_answer
        }
    return None
```

**策略B：多轮对话拆分（推荐）**
```python
# 更智能，能捕获完整的交互
def extract_all_qa_pairs(messages, initial_question):
    """
    将多轮对话拆分为多个Q&A对
    """
    qa_pairs = []
    current_question = initial_question
    current_answer_parts = []
    
    i = 0
    while i < len(messages):
        msg = messages[i]
        
        if msg['speaker'] == 'Patron':
            # 如果已有答案，保存当前Q&A
            if current_answer_parts:
                qa_pairs.append({
                    'question': current_question,
                    'answer': ' '.join(current_answer_parts)
                })
                current_answer_parts = []
            
            # 更新问题
            current_question = msg['content']
        else:
            # 图书馆员回复
            current_answer_parts.append(msg['content'])
        
        i += 1
    
    # 保存最后一对
    if current_answer_parts:
        qa_pairs.append({
            'question': current_question,
            'answer': ' '.join(current_answer_parts)
        })
    
    return qa_pairs
```

**策略C：上下文窗口法（最智能）**
```python
# 保留对话上下文，适合复杂问题
def extract_qa_with_context(messages, initial_question, window_size=3):
    """
    每个Q&A对包含前后N条消息作为上下文
    """
    qa_pairs = []
    
    for i, msg in enumerate(messages):
        if msg['speaker'] != 'Patron':  # 图书馆员回复
            # 找到对应的问题（向前查找最近的patron消息）
            question = initial_question
            for j in range(i-1, -1, -1):
                if messages[j]['speaker'] == 'Patron':
                    question = messages[j]['content']
                    break
            
            # 提取上下文窗口
            start = max(0, i - window_size)
            end = min(len(messages), i + window_size + 1)
            context = ' | '.join([
                f"{m['speaker']}: {m['content']}" 
                for m in messages[start:end]
            ])
            
            qa_pairs.append({
                'question': question,
                'answer': msg['content'],
                'context': context  # 新增字段
            })
    
    return qa_pairs
```

---

### 3️⃣ **数据增强与清理**

#### 3.1 清理噪音数据
```python
def clean_message_content(text):
    """
    清理消息中的噪音
    """
    # 移除HTML标签
    text = re.sub(r'<a href="[^"]*"[^>]*>([^<]*)</a>', r'\1', text)
    
    # 移除附件链接
    text = re.sub(r'attached a file:.*?(?=\n|$)', '', text)
    
    # 移除过短的寒暄（可选）
    if len(text.strip()) < 10 and any(greeting in text.lower() for greeting in ['hi', 'hello', 'thanks', 'thank you', 'you\'re welcome']):
        return None
    
    # 标准化空白字符
    text = ' '.join(text.split())
    
    return text
```

#### 3.2 提取结构化信息
```python
def extract_metadata(chat_record):
    """
    提取关键元数据用于后续过滤和分类
    """
    metadata = {
        'chat_id': chat_record['Chat ID'],
        'timestamp': chat_record['Timestamp'],
        'rating': int(chat_record['Rating (0-4)']) if chat_record['Rating (0-4)'] else 0,
        'duration': int(chat_record['Duration (seconds)']),
        'message_count': int(chat_record['Message Count']),
        'tags': chat_record['Tags'].split(',') if chat_record['Tags'] else [],
        'department': chat_record['Department'],
        'answerer': chat_record['Answerer']
    }
    return metadata
```

#### 3.3 主题分类（关键！）
```python
# 基于你的scope_definition.py进行自动分类
TOPIC_KEYWORDS = {
    'discovery_search': ['book', 'article', 'journal', 'database', 'catalog', 'primo', 'find', 'search', 'call number'],
    'booking_or_hours': ['hours', 'open', 'close', 'room', 'reservation', 'book a room', 'study room'],
    'policy_or_service': ['renew', 'return', 'fine', 'overdue', 'print', 'scan', 'borrow', 'interlibrary loan', 'ILL'],
    'subject_librarian': ['librarian', 'subject specialist', 'research help', 'consultation', 'libguide'],
    'course_subject_help': ['course', 'class', 'ENG', 'PSY', 'CHM', 'guide for']
}

def classify_topic(question, answer):
    """
    根据关键词自动分类主题
    """
    combined_text = (question + ' ' + answer).lower()
    
    scores = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined_text)
        scores[topic] = score
    
    # 返回得分最高的主题，如果没有匹配则返回'general'
    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    return 'general_question'
```

---

### 4️⃣ **Weaviate数据结构优化**

#### 4.1 当前结构问题
```python
# 现有schema（太简单）
{
    "question": str,
    "answer": str,
    "topic": str,
    "source": str
}
```

#### 4.2 优化后的Schema（推荐）
```python
# 增强版schema
{
    # 核心内容
    "question": str,              # 用户问题
    "answer": str,                # 图书馆员回答
    
    # 分类和元数据
    "topic": str,                 # 主题分类（discovery_search, booking_or_hours等）
    "subtopic": str,              # 子主题（可选，更细粒度分类）
    "keywords": [str],            # 关键词列表
    
    # 质量指标
    "rating": int,                # 用户评分 0-4
    "confidence_score": float,    # 质量置信度 0.0-1.0
    
    # 上下文（新增！）
    "context": str,               # 对话上下文（前后几轮对话）
    "follow_up_questions": [str], # 后续问题列表
    
    # 可追溯性
    "source": str,                # 来源标识（transcripts）
    "chat_id": str,               # 原始Chat ID
    "timestamp": datetime,        # 时间戳
    "answerer": str,              # 回答的图书馆员
    
    # 实体提取（高级，可选）
    "mentioned_resources": [str], # 提到的资源（书名、数据库名）
    "mentioned_urls": [str],      # 提到的URL
    "mentioned_librarians": [str] # 提到的图书馆员姓名
}
```

#### 4.3 向量化策略

**选项A：单独向量化问题和答案（当前方案）**
```python
# 只用question生成embedding
vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_openai(
    vectorize_property_name='question'
)
```

**选项B：组合向量化（推荐）**
```python
# 组合question + answer + context生成更丰富的embedding
def create_vectorization_text(qa_record):
    """
    创建用于向量化的组合文本
    """
    parts = [
        f"Question: {qa_record['question']}",
        f"Answer: {qa_record['answer']}"
    ]
    
    if qa_record.get('context'):
        parts.append(f"Context: {qa_record['context']}")
    
    if qa_record.get('keywords'):
        parts.append(f"Keywords: {', '.join(qa_record['keywords'])}")
    
    return ' | '.join(parts)
```

**选项C：多向量方案（高级）**
```python
# 为question和answer分别创建向量，支持更精确的检索
# 需要修改Weaviate schema支持multiple vectors
```

---

### 5️⃣ **数据分批处理流程**

#### 阶段1：数据清洗脚本
```python
#!/usr/bin/env python3
"""
Step 1: 清理原始CSV数据
输出：cleaned_transcripts.json
"""
import csv
import json
import re
from datetime import datetime

def clean_transcripts(csv_files):
    all_qa_pairs = []
    stats = {
        'total_chats': 0,
        'filtered_out': 0,
        'qa_pairs_extracted': 0
    }
    
    for csv_file in csv_files:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                stats['total_chats'] += 1
                
                # 质量过滤
                if not should_include_chat(row):
                    stats['filtered_out'] += 1
                    continue
                
                # 解析对话
                messages = parse_transcript(row['Transcript'])
                
                # 提取Q&A对（使用策略B或C）
                qa_pairs = extract_all_qa_pairs(messages, row['Initial Question'])
                
                # 添加元数据和清理
                for qa in qa_pairs:
                    # 清理内容
                    qa['question'] = clean_message_content(qa['question'])
                    qa['answer'] = clean_message_content(qa['answer'])
                    
                    if not qa['question'] or not qa['answer']:
                        continue
                    
                    # 分类主题
                    qa['topic'] = classify_topic(qa['question'], qa['answer'])
                    
                    # 添加元数据
                    qa['rating'] = int(row['Rating (0-4)']) if row['Rating (0-4)'] else 0
                    qa['source'] = 'transcripts'
                    qa['chat_id'] = row['Chat ID']
                    qa['timestamp'] = row['Timestamp']
                    qa['answerer'] = row['Answerer']
                    
                    # 质量评分
                    qa['confidence_score'] = calculate_confidence_score(qa, row)
                    
                    all_qa_pairs.append(qa)
                    stats['qa_pairs_extracted'] += 1
    
    # 保存结果
    with open('cleaned_transcripts.json', 'w', encoding='utf-8') as f:
        json.dump(all_qa_pairs, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 处理完成！")
    print(f"   总对话数: {stats['total_chats']}")
    print(f"   过滤掉: {stats['filtered_out']}")
    print(f"   提取Q&A对: {stats['qa_pairs_extracted']}")
    
    return all_qa_pairs

def should_include_chat(row):
    """
    判断是否应该包含这条对话
    """
    # 过滤低质量
    rating = int(row['Rating (0-4)']) if row['Rating (0-4)'] else 0
    if rating == 1:
        return False
    
    # 过滤过短对话
    if int(row['Message Count']) < 2:
        return False
    
    # 过滤超长对话（可能是复杂案例，需单独处理）
    if int(row['Message Count']) > 30:
        return False
    
    return True

def calculate_confidence_score(qa, row_metadata):
    """
    计算质量置信度（0.0-1.0）
    """
    score = 0.5  # 基础分
    
    # 评分加权
    rating = qa.get('rating', 0)
    if rating >= 4:
        score += 0.3
    elif rating >= 3:
        score += 0.2
    elif rating >= 2:
        score += 0.1
    
    # 答案长度加权（不能太短也不能太长）
    answer_len = len(qa['answer'])
    if 50 <= answer_len <= 500:
        score += 0.1
    elif 20 <= answer_len < 50 or 500 < answer_len <= 1000:
        score += 0.05
    
    # 答案中包含URL（通常是高质量回答）
    if 'http' in qa['answer'] or 'www.' in qa['answer']:
        score += 0.1
    
    return min(1.0, score)
```

#### 阶段2：去重和合并
```python
"""
Step 2: 去重和合并相似问题
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def deduplicate_qa_pairs(qa_pairs, similarity_threshold=0.85):
    """
    使用TF-IDF和余弦相似度去重
    """
    if not qa_pairs:
        return []
    
    # 提取所有问题
    questions = [qa['question'] for qa in qa_pairs]
    
    # 计算TF-IDF向量
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(questions)
    
    # 计算相似度矩阵
    similarity_matrix = cosine_similarity(tfidf_matrix)
    
    # 标记重复项
    duplicates = set()
    merged_pairs = []
    
    for i in range(len(qa_pairs)):
        if i in duplicates:
            continue
        
        similar_indices = []
        for j in range(i + 1, len(qa_pairs)):
            if similarity_matrix[i][j] >= similarity_threshold:
                similar_indices.append(j)
                duplicates.add(j)
        
        # 如果有相似问题，合并答案
        if similar_indices:
            base_qa = qa_pairs[i].copy()
            similar_answers = [qa_pairs[j]['answer'] for j in similar_indices]
            
            # 选择最高质量的答案（基于rating和confidence_score）
            all_candidates = [base_qa] + [qa_pairs[j] for j in similar_indices]
            best_qa = max(all_candidates, key=lambda x: (x['rating'], x['confidence_score']))
            
            merged_pairs.append(best_qa)
        else:
            merged_pairs.append(qa_pairs[i])
    
    print(f"✅ 去重完成: {len(qa_pairs)} -> {len(merged_pairs)} (removed {len(duplicates)} duplicates)")
    
    return merged_pairs
```

#### 阶段3：摄入Weaviate
```python
"""
Step 3: 摄入到Weaviate
修改现有的 ingest_transcripts.py
"""
def create_enhanced_schema(client):
    """
    创建增强版Schema
    """
    try:
        client.collections.create(
            name="TranscriptQA",
            vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_openai(),
            properties=[
                # 核心内容
                wvc.config.Property(name="question", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="answer", data_type=wvc.config.DataType.TEXT),
                
                # 分类
                wvc.config.Property(name="topic", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="keywords", data_type=wvc.config.DataType.TEXT_ARRAY),
                
                # 质量
                wvc.config.Property(name="rating", data_type=wvc.config.DataType.INT),
                wvc.config.Property(name="confidence_score", data_type=wvc.config.DataType.NUMBER),
                
                # 上下文（重要！）
                wvc.config.Property(name="context", data_type=wvc.config.DataType.TEXT),
                
                # 元数据
                wvc.config.Property(name="source", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="chat_id", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="timestamp", data_type=wvc.config.DataType.DATE),
                wvc.config.Property(name="answerer", data_type=wvc.config.DataType.TEXT),
            ]
        )
        print("✅ Created enhanced TranscriptQA collection")
    except Exception as e:
        print(f"Schema creation error: {e}")

def ingest_with_batching(client, qa_pairs, batch_size=100):
    """
    分批摄入数据
    """
    collection = client.collections.get("TranscriptQA")
    
    total_batches = (len(qa_pairs) + batch_size - 1) // batch_size
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min((batch_num + 1) * batch_size, len(qa_pairs))
        batch = qa_pairs[start_idx:end_idx]
        
        with collection.batch.dynamic() as batch_inserter:
            for qa in batch:
                batch_inserter.add_object(
                    properties={
                        'question': qa['question'],
                        'answer': qa['answer'],
                        'topic': qa.get('topic', 'general'),
                        'keywords': qa.get('keywords', []),
                        'rating': qa.get('rating', 0),
                        'confidence_score': qa.get('confidence_score', 0.5),
                        'context': qa.get('context', ''),
                        'source': qa.get('source', 'transcripts'),
                        'chat_id': qa.get('chat_id', ''),
                        'timestamp': qa.get('timestamp', ''),
                        'answerer': qa.get('answerer', '')
                    }
                )
        
        print(f"✅ Batch {batch_num + 1}/{total_batches} ingested ({end_idx}/{len(qa_pairs)} records)")
```

---

### 6️⃣ **查询优化**

#### 6.1 修改transcript_rag_agent.py
```python
async def transcript_rag_query(query: str, log_callback=None, filters=None) -> Dict[str, Any]:
    """
    增强版RAG查询，支持过滤和重排序
    """
    def _search():
        if not client:
            return error_response()
        
        try:
            collection = client.collections.get("TranscriptQA")
            
            # 构建过滤条件（可选）
            where_filter = None
            if filters:
                # 例如：只查询高评分的回答
                if filters.get('min_rating'):
                    where_filter = wvc.query.Filter.by_property('rating').greater_or_equal(filters['min_rating'])
                
                # 或者按主题过滤
                if filters.get('topic'):
                    topic_filter = wvc.query.Filter.by_property('topic').equal(filters['topic'])
                    where_filter = where_filter & topic_filter if where_filter else topic_filter
            
            # 查询
            response = collection.query.near_text(
                query=query,
                limit=5,  # 增加到5个结果
                where=where_filter,
                return_metadata=wvc.query.MetadataQuery(distance=True, score=True)
            )
            
            if not response.objects:
                return no_results_response()
            
            # 重排序：根据confidence_score和距离综合评分
            scored_results = []
            for obj in response.objects:
                props = obj.properties
                distance = obj.metadata.distance
                confidence = props.get('confidence_score', 0.5)
                
                # 综合得分 = (1 - distance) * 0.7 + confidence * 0.3
                combined_score = (1 - distance) * 0.7 + confidence * 0.3
                
                scored_results.append({
                    'question': props.get('question', ''),
                    'answer': props.get('answer', ''),
                    'topic': props.get('topic', ''),
                    'rating': props.get('rating', 0),
                    'score': combined_score
                })
            
            # 按综合得分排序
            scored_results.sort(key=lambda x: x['score'], reverse=True)
            
            # 只返回top 3
            top_results = scored_results[:3]
            
            # 格式化输出
            answers = []
            for result in top_results:
                answers.append(f"**Q:** {result['question']}\n**A:** {result['answer']}")
            
            return {
                "source": "TranscriptRAG",
                "success": True,
                "text": "Based on similar questions from our knowledge base:\n\n" + "\n\n".join(answers),
                "confidence": "high" if top_results[0]['score'] > 0.8 else "medium",
                "matched_topic": top_results[0]['topic']
            }
        
        except Exception as e:
            return error_response(str(e))
    
    return await asyncio.to_thread(_search)
```

---

## 📈 实施建议

### 分阶段实施计划

**Phase 1: 快速原型（1-2天）**
1. 使用策略A（首问-首答）快速提取
2. 只使用Rating >= 3的数据
3. 基本去重
4. 摄入500-1000条测试

**Phase 2: 优化迭代（3-5天）**
1. 实施策略B（多轮对话拆分）
2. 添加主题分类
3. 实施TF-IDF去重
4. 完整摄入所有高质量数据（约3000-4000条）

**Phase 3: 高级特性（1-2周）**
1. 实施策略C（上下文窗口）
2. 升级Weaviate Schema（添加context, confidence_score等）
3. 实体提取（URLs, 资源名称, 图书馆员姓名）
4. A/B测试不同向量化策略

### 质量监控

```python
# 定期评估RAG质量
def evaluate_rag_quality(test_queries):
    """
    使用测试查询集评估RAG效果
    """
    metrics = {
        'avg_relevance': 0,
        'coverage': 0,
        'avg_confidence': 0
    }
    
    for query in test_queries:
        result = transcript_rag_query(query)
        # 计算相关性、覆盖率等指标
        # ...
    
    return metrics
```

---

## 🚀 预期效果

### 优化前（当前状态）
- 简单Q&A对
- 无质量控制
- 无主题分类
- 查询结果质量不稳定

### 优化后
- **数据质量**：只包含高评分（3+）对话
- **覆盖范围**：从6000条对话中提取约5000-8000个高质量Q&A对
- **检索精度**：通过主题过滤和重排序提升相关性
- **上下文理解**：保留对话上下文，支持多轮对话理解
- **可追溯性**：每条回答可追溯到原始对话记录

### 适用场景分布
- **直接回答**：约60-70%的常见问题可直接从RAG回答
- **辅助回答**：约20-30%需要结合API和RAG
- **转人工**：约10%复杂问题需要人工介入

---

## 🛠️ 下一步行动

1. **立即开始**：运行数据清洗脚本（Phase 1）
2. **逐步优化**：基于实际查询效果迭代改进
3. **持续更新**：每季度补充新的对话数据
4. **监控指标**：跟踪RAG命中率、用户满意度

是否需要我开始实现具体的清洗脚本？
