#!/usr/bin/env python3
"""
清理和处理历史对话CSV文件，准备RAG摄入
用法: python clean_transcripts.py <csv_file1> [csv_file2] ... [--output output.json]
"""
import csv
import json
import re
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

# 主题关键词字典（基于scope_definition.py）
TOPIC_KEYWORDS = {
    'discovery_search': [
        'book', 'article', 'journal', 'database', 'catalog', 'primo', 
        'find', 'search', 'call number', 'isbn', 'doi', 'citation',
        'ebook', 'e-book', 'electronic', 'full text', 'pdf'
    ],
    'booking_or_hours': [
        'hours', 'open', 'close', 'room', 'reservation', 'book a room', 
        'study room', 'schedule', 'available', 'reserve'
    ],
    'policy_or_service': [
        'renew', 'return', 'fine', 'overdue', 'print', 'scan', 'copy',
        'borrow', 'interlibrary loan', 'ill', 'checkout', 'due date'
    ],
    'subject_librarian': [
        'librarian', 'subject specialist', 'research help', 'consultation',
        'libguide', 'research guide', 'subject guide', 'contact', 'who can help'
    ],
    'course_subject_help': [
        'course', 'class', 'assignment', 'professor', 'instructor',
        'eng ', 'psy ', 'chm ', 'bio ', 'guide for'
    ]
}

# 超出范围的关键词（需要过滤）
OUT_OF_SCOPE_KEYWORDS = [
    'admission', 'tuition', 'housing', 'dining hall', 'parking',
    'canvas', 'blackboard', 'email account', 'password reset',
    'homework', 'test answer', 'solve this problem',
    'armstrong', 'rec center', 'student center'
]


def anonymize_librarian_name(name: str) -> str:
    """
    隐私保护：将图书馆员姓名替换为"Librarian"
    保留"Patron"不变
    """
    if not name or name.strip() == '':
        return ''
    
    name_stripped = name.strip()
    
    # 保留Patron不变
    if name_stripped.lower() == 'patron':
        return 'Patron'
    
    # 其他所有名字都替换为Librarian
    return 'Librarian'


def parse_transcript(transcript_text: str, anonymize: bool = True) -> List[Dict[str, str]]:
    """
    解析Transcript字段，提取结构化消息列表
    
    格式: "HH:MM:SS - Speaker Name : Message content"
    
    Args:
        transcript_text: 对话文本
        anonymize: 是否匿名化图书馆员姓名（默认True）
    """
    messages = []
    if not transcript_text or transcript_text.strip() == '':
        return messages
    
    lines = transcript_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 匹配时间戳 - 说话人 : 内容
        match = re.match(r'(\d{2}:\d{2}(?::\d{2})?) - ([^:]+) : (.+)', line)
        if match:
            time, speaker, content = match.groups()
            
            # 隐私保护：替换图书馆员姓名
            if anonymize:
                speaker = anonymize_librarian_name(speaker)
            
            messages.append({
                'time': time.strip(),
                'speaker': speaker.strip(),
                'content': content.strip()
            })
    
    return messages


def clean_message_content(text: str) -> Optional[str]:
    """
    清理消息内容，移除HTML标签、链接等噪音
    """
    if not text:
        return None
    
    # 移除HTML标签但保留链接文本
    text = re.sub(r'<a href="[^"]*"[^>]*>([^<]*)</a>', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    
    # 移除"attached a file"类型的消息
    if 'attached a file:' in text.lower():
        return None
    
    # 移除纯URL行
    if text.startswith('http') and len(text.split()) == 1:
        return None
    
    # 标准化空白字符
    text = ' '.join(text.split())
    
    # 过滤过短的寒暄语（小于10个字符且只包含常见寒暄）
    if len(text) < 10:
        greetings = ['hi', 'hello', 'thanks', 'thank you', "you're welcome", 
                     'ok', 'okay', 'sure', 'yes', 'no', 'got it']
        if text.lower().strip('!.?') in greetings:
            return None
    
    return text


def is_out_of_scope(text: str) -> bool:
    """
    检查文本是否超出图书馆服务范围
    """
    text_lower = text.lower()
    
    # 检查是否包含超范围关键词
    for keyword in OUT_OF_SCOPE_KEYWORDS:
        if keyword in text_lower:
            return True
    
    return False


def classify_topic(question: str, answer: str) -> str:
    """
    根据关键词自动分类主题
    """
    combined_text = (question + ' ' + answer).lower()
    
    # 检查是否超出范围
    if is_out_of_scope(combined_text):
        return 'out_of_scope'
    
    # 计算每个主题的得分
    scores = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined_text)
        scores[topic] = score
    
    # 返回得分最高的主题
    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    
    return 'general_question'


def extract_keywords(text: str, top_n: int = 5) -> List[str]:
    """
    简单的关键词提取（基于词频）
    """
    # 移除常见停用词
    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
                 'i', 'you', 'we', 'they', 'this', 'that', 'these', 'those', 'can', 'do'}
    
    # 分词并统计
    words = re.findall(r'\b[a-z]+\b', text.lower())
    word_freq = defaultdict(int)
    
    for word in words:
        if len(word) > 3 and word not in stopwords:
            word_freq[word] += 1
    
    # 返回top N高频词
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [word for word, freq in sorted_words[:top_n]]


def calculate_confidence_score(qa: Dict[str, Any], metadata: Dict[str, Any]) -> float:
    """
    计算QA对的质量置信度 (0.0 - 1.0)
    """
    score = 0.5  # 基础分
    
    # 1. 用户评分加权 (最高+0.3)
    rating = metadata.get('rating', 0)
    if rating >= 4:
        score += 0.3
    elif rating >= 3:
        score += 0.2
    elif rating >= 2:
        score += 0.1
    
    # 2. 答案长度加权 (最高+0.1)
    answer_len = len(qa.get('answer', ''))
    if 50 <= answer_len <= 500:
        score += 0.1
    elif 20 <= answer_len < 50 or 500 < answer_len <= 1000:
        score += 0.05
    
    # 3. 答案包含URL通常质量较高 (+0.1)
    answer = qa.get('answer', '')
    if 'http' in answer or 'lib.miamioh.edu' in answer:
        score += 0.1
    
    # 4. 对话时长合理 (+0.05)
    duration = metadata.get('duration', 0)
    if 30 <= duration <= 600:  # 30秒到10分钟
        score += 0.05
    
    return min(1.0, score)


def extract_first_qa(messages: List[Dict], initial_question: str) -> Optional[Dict[str, str]]:
    """
    策略A: 提取Initial Question + 图书馆员的第一个实质性回答
    最简单快速的方法
    """
    librarian_answer = None
    
    for msg in messages:
        if msg['speaker'] != 'Patron':  # 图书馆员回复
            content = clean_message_content(msg['content'])
            if content and len(content) > 15:  # 实质性回答
                librarian_answer = content
                break
    
    if librarian_answer and initial_question:
        return {
            'question': initial_question,
            'answer': librarian_answer
        }
    
    return None


def extract_all_qa_pairs(messages: List[Dict], initial_question: str) -> List[Dict[str, str]]:
    """
    策略B: 提取所有Q&A对（推荐）
    将多轮对话拆分为多个独立的Q&A
    """
    qa_pairs = []
    current_question = initial_question
    current_answer_parts = []
    
    for msg in messages:
        content = clean_message_content(msg['content'])
        if not content:
            continue
        
        if msg['speaker'] == 'Patron':
            # 用户问题
            # 如果已有答案，保存当前Q&A
            if current_answer_parts and current_question:
                qa_pairs.append({
                    'question': current_question,
                    'answer': ' '.join(current_answer_parts)
                })
                current_answer_parts = []
            
            # 更新当前问题（过滤掉太短的消息）
            if len(content) > 15:
                current_question = content
        else:
            # 图书馆员回复
            if len(content) > 15:  # 只保留实质性回复
                current_answer_parts.append(content)
    
    # 保存最后一对
    if current_answer_parts and current_question:
        qa_pairs.append({
            'question': current_question,
            'answer': ' '.join(current_answer_parts)
        })
    
    return qa_pairs


def should_include_chat(row: Dict[str, str]) -> tuple[bool, str]:
    """
    判断是否应该包含这条对话
    返回: (是否包含, 原因)
    """
    # 1. 过滤消息数过少
    message_count = int(row.get('Message Count', 0))
    if message_count < 2:
        return False, 'too_few_messages'
    
    # 2. 过滤超长对话（可能是复杂案例）
    if message_count > 30:
        return False, 'too_long'
    
    # 3. 过滤低评分（Rating == 1）
    rating = row.get('Rating (0-4)', '').strip()
    if rating and rating != '' and int(float(rating)) == 1:
        return False, 'low_rating'
    
    # 4. 必须有Initial Question
    if not row.get('Initial Question', '').strip():
        return False, 'no_initial_question'
    
    # 5. 必须有Transcript
    if not row.get('Transcript', '').strip():
        return False, 'no_transcript'
    
    # 6. 检查是否明显超出范围
    initial_q = row.get('Initial Question', '').lower()
    if is_out_of_scope(initial_q):
        return False, 'out_of_scope'
    
    return True, 'ok'


def process_csv_file(csv_file: str, extraction_strategy: str = 'all') -> tuple[List[Dict], Dict]:
    """
    处理单个CSV文件
    
    Args:
        csv_file: CSV文件路径
        extraction_strategy: 'first' 或 'all'
    
    Returns:
        (qa_pairs列表, 统计信息)
    """
    qa_pairs = []
    stats = {
        'total_chats': 0,
        'filtered_out': defaultdict(int),
        'qa_pairs_extracted': 0
    }
    
    print(f"\n📁 Processing: {csv_file}")
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                stats['total_chats'] += 1
                
                # 判断是否包含
                should_include, reason = should_include_chat(row)
                if not should_include:
                    stats['filtered_out'][reason] += 1
                    continue
                
                # 解析对话（带隐私保护）
                messages = parse_transcript(row.get('Transcript', ''), anonymize=True)
                if not messages:
                    stats['filtered_out']['empty_messages'] += 1
                    continue
                
                # 提取元数据（隐私保护：替换Answerer姓名）
                answerer = row.get('Answerer', '')
                if answerer and answerer.strip():
                    answerer = 'Librarian'  # 隐私保护
                
                metadata = {
                    'chat_id': row.get('Chat ID', ''),
                    'timestamp': row.get('Timestamp', ''),
                    'rating': int(float(row.get('Rating (0-4)', 0))) if row.get('Rating (0-4)', '').strip() else 0,
                    'duration': int(float(row.get('Duration (seconds)', 0))) if row.get('Duration (seconds)', '').strip() else 0,
                    'message_count': int(row.get('Message Count', 0)),
                    'answerer': answerer,  # 已匿名化
                    'department': row.get('Department', ''),
                    'tags': [tag.strip() for tag in row.get('Tags', '').split(',') if tag.strip()]
                }
                
                # 根据策略提取Q&A对
                if extraction_strategy == 'first':
                    qa = extract_first_qa(messages, row.get('Initial Question', ''))
                    extracted_pairs = [qa] if qa else []
                else:  # 'all'
                    extracted_pairs = extract_all_qa_pairs(messages, row.get('Initial Question', ''))
                
                # 处理每个Q&A对
                for qa in extracted_pairs:
                    if not qa or not qa.get('question') or not qa.get('answer'):
                        continue
                    
                    # 分类主题
                    topic = classify_topic(qa['question'], qa['answer'])
                    
                    # 跳过超出范围的问题
                    if topic == 'out_of_scope':
                        stats['filtered_out']['out_of_scope'] += 1
                        continue
                    
                    # 提取关键词
                    keywords = extract_keywords(qa['question'] + ' ' + qa['answer'])
                    
                    # 计算置信度
                    confidence_score = calculate_confidence_score(qa, metadata)
                    
                    # 构建完整记录
                    full_qa = {
                        # 核心内容
                        'question': qa['question'],
                        'answer': qa['answer'],
                        
                        # 分类
                        'topic': topic,
                        'keywords': keywords,
                        
                        # 质量
                        'rating': metadata['rating'],
                        'confidence_score': round(confidence_score, 3),
                        
                        # 元数据
                        'source': 'transcripts',
                        'chat_id': metadata['chat_id'],
                        'timestamp': metadata['timestamp'],
                        'answerer': metadata['answerer'],
                        'department': metadata['department'],
                        'tags': metadata['tags']
                    }
                    
                    qa_pairs.append(full_qa)
                    stats['qa_pairs_extracted'] += 1
    
    except Exception as e:
        print(f"❌ Error processing {csv_file}: {e}")
        return [], stats
    
    return qa_pairs, stats


def merge_stats(stats_list: List[Dict]) -> Dict:
    """合并多个统计信息"""
    merged = {
        'total_chats': 0,
        'filtered_out': defaultdict(int),
        'qa_pairs_extracted': 0
    }
    
    for stats in stats_list:
        merged['total_chats'] += stats['total_chats']
        merged['qa_pairs_extracted'] += stats['qa_pairs_extracted']
        for reason, count in stats['filtered_out'].items():
            merged['filtered_out'][reason] += count
    
    return merged


def print_statistics(stats: Dict):
    """打印统计信息"""
    print("\n" + "="*60)
    print("📊 处理统计")
    print("="*60)
    print(f"总对话数: {stats['total_chats']}")
    print(f"提取的Q&A对: {stats['qa_pairs_extracted']}")
    print(f"过滤掉: {sum(stats['filtered_out'].values())}")
    print("\n过滤原因分布:")
    for reason, count in sorted(stats['filtered_out'].items(), key=lambda x: x[1], reverse=True):
        print(f"  - {reason}: {count}")
    
    if stats['total_chats'] > 0:
        retention_rate = (stats['qa_pairs_extracted'] / stats['total_chats']) * 100
        print(f"\n✅ 数据保留率: {retention_rate:.1f}%")


def main():
    parser = argparse.ArgumentParser(description='清理历史对话CSV文件准备RAG摄入（带隐私保护）')
    parser.add_argument('csv_files', nargs='+', help='CSV文件路径（可以多个）')
    parser.add_argument('--output', '-o', default='cleaned_transcripts.json', help='输出JSON文件名')
    parser.add_argument('--strategy', '-s', choices=['first', 'all'], default='all',
                        help='提取策略: first=只提取首问首答, all=提取所有Q&A对 (推荐)')
    parser.add_argument('--min-confidence', type=float, default=0.0,
                        help='最低置信度阈值 (0.0-1.0)')
    
    args = parser.parse_args()
    
    print("🚀 开始处理历史对话数据...")
    print(f"🔒 隐私保护: 已启用（所有图书馆员姓名将替换为'Librarian'）")
    print(f"提取策略: {args.strategy}")
    print(f"最低置信度: {args.min_confidence}")
    
    # 处理所有CSV文件
    all_qa_pairs = []
    all_stats = []
    
    for csv_file in args.csv_files:
        qa_pairs, stats = process_csv_file(csv_file, args.strategy)
        all_qa_pairs.extend(qa_pairs)
        all_stats.append(stats)
    
    # 合并统计
    merged_stats = merge_stats(all_stats)
    
    # 按置信度过滤
    if args.min_confidence > 0:
        before_count = len(all_qa_pairs)
        all_qa_pairs = [qa for qa in all_qa_pairs if qa['confidence_score'] >= args.min_confidence]
        after_count = len(all_qa_pairs)
        print(f"\n🔍 置信度过滤: {before_count} -> {after_count} (removed {before_count - after_count})")
    
    # 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_qa_pairs, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 数据已保存到: {output_path}")
    print(f"📦 共 {len(all_qa_pairs)} 条Q&A对")
    
    # 打印统计
    print_statistics(merged_stats)
    
    # 主题分布统计
    print("\n" + "="*60)
    print("📋 主题分布")
    print("="*60)
    topic_counts = defaultdict(int)
    for qa in all_qa_pairs:
        topic_counts[qa['topic']] += 1
    
    for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / len(all_qa_pairs)) * 100
        print(f"  - {topic}: {count} ({percentage:.1f}%)")
    
    # 质量分布
    print("\n" + "="*60)
    print("⭐ 质量分布")
    print("="*60)
    confidence_ranges = {
        'Very High (0.8-1.0)': 0,
        'High (0.7-0.8)': 0,
        'Medium (0.6-0.7)': 0,
        'Low (0.5-0.6)': 0,
        'Very Low (<0.5)': 0
    }
    
    for qa in all_qa_pairs:
        conf = qa['confidence_score']
        if conf >= 0.8:
            confidence_ranges['Very High (0.8-1.0)'] += 1
        elif conf >= 0.7:
            confidence_ranges['High (0.7-0.8)'] += 1
        elif conf >= 0.6:
            confidence_ranges['Medium (0.6-0.7)'] += 1
        elif conf >= 0.5:
            confidence_ranges['Low (0.5-0.6)'] += 1
        else:
            confidence_ranges['Very Low (<0.5)'] += 1
    
    for range_name, count in confidence_ranges.items():
        if len(all_qa_pairs) > 0:
            percentage = (count / len(all_qa_pairs)) * 100
            print(f"  - {range_name}: {count} ({percentage:.1f}%)")
    
    print("\n" + "="*60)
    print("✨ 处理完成！下一步:")
    print("  1. 检查输出文件质量")
    print("  2. 可选: 运行去重脚本 (deduplicate_transcripts.py)")
    print("  3. 运行: python scripts/ingest_transcripts.py")
    print("="*60)


if __name__ == '__main__':
    main()
