#!/usr/bin/env python3
"""
去重和合并相似的Q&A对
用法: python deduplicate_transcripts.py <input.json> [--output deduplicated.json]
"""
import json
import argparse
import numpy as np
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def calculate_text_similarity(texts: List[str]) -> np.ndarray:
    """
    使用TF-IDF计算文本相似度矩阵
    """
    if len(texts) < 2:
        return np.array([[1.0]])
    
    try:
        vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            lowercase=True
        )
        tfidf_matrix = vectorizer.fit_transform(texts)
        similarity_matrix = cosine_similarity(tfidf_matrix)
        return similarity_matrix
    except Exception as e:
        print(f"⚠️  TF-IDF calculation error: {e}")
        # 返回单位矩阵（每个问题只与自己相似）
        return np.eye(len(texts))


def deduplicate_qa_pairs(
    qa_pairs: List[Dict[str, Any]], 
    similarity_threshold: float = 0.85,
    merge_strategy: str = 'best'
) -> List[Dict[str, Any]]:
    """
    去重Q&A对
    
    Args:
        qa_pairs: Q&A对列表
        similarity_threshold: 相似度阈值 (0.0-1.0)
        merge_strategy: 'best' = 保留最高质量, 'merge' = 合并答案
    
    Returns:
        去重后的Q&A对列表
    """
    if not qa_pairs:
        return []
    
    print(f"\n🔍 开始去重...")
    print(f"   原始数量: {len(qa_pairs)}")
    print(f"   相似度阈值: {similarity_threshold}")
    print(f"   合并策略: {merge_strategy}")
    
    # 提取所有问题
    questions = [qa['question'] for qa in qa_pairs]
    
    # 计算相似度矩阵
    print("   计算TF-IDF相似度...")
    similarity_matrix = calculate_text_similarity(questions)
    
    # 标记重复项和分组
    duplicates = set()
    duplicate_groups = []  # 每个group是相似问题的索引列表
    
    for i in range(len(qa_pairs)):
        if i in duplicates:
            continue
        
        # 找到所有与问题i相似的问题
        similar_indices = []
        for j in range(i + 1, len(qa_pairs)):
            if j not in duplicates and similarity_matrix[i][j] >= similarity_threshold:
                similar_indices.append(j)
                duplicates.add(j)
        
        if similar_indices:
            # 有相似问题，创建一个group
            group = [i] + similar_indices
            duplicate_groups.append(group)
        else:
            # 没有相似问题，单独成组
            duplicate_groups.append([i])
    
    print(f"   发现 {len(duplicates)} 个重复项")
    print(f"   合并为 {len(duplicate_groups)} 组")
    
    # 根据策略合并每个组
    deduplicated_pairs = []
    
    for group in duplicate_groups:
        if len(group) == 1:
            # 单一问题，直接保留
            deduplicated_pairs.append(qa_pairs[group[0]])
        else:
            # 多个相似问题，根据策略处理
            group_pairs = [qa_pairs[idx] for idx in group]
            
            if merge_strategy == 'best':
                # 保留质量最高的
                best_qa = max(group_pairs, key=lambda x: (
                    x['confidence_score'],
                    x['rating'],
                    len(x['answer'])
                ))
                deduplicated_pairs.append(best_qa)
            
            elif merge_strategy == 'merge':
                # 合并答案（使用最高质量的问题，合并所有不重复的答案）
                best_qa = max(group_pairs, key=lambda x: (
                    x['confidence_score'],
                    x['rating']
                ))
                
                # 收集所有不同的答案
                unique_answers = []
                seen_answers = set()
                
                for qa in sorted(group_pairs, key=lambda x: x['confidence_score'], reverse=True):
                    answer_normalized = qa['answer'].lower().strip()
                    if answer_normalized not in seen_answers:
                        unique_answers.append(qa['answer'])
                        seen_answers.add(answer_normalized)
                
                # 如果有多个不同答案，合并它们
                if len(unique_answers) > 1:
                    merged_answer = '\n\n'.join([f"[Option {i+1}] {ans}" 
                                                  for i, ans in enumerate(unique_answers[:3])])
                    best_qa['answer'] = merged_answer
                
                # 合并关键词和标签
                all_keywords = set()
                all_tags = set()
                for qa in group_pairs:
                    all_keywords.update(qa.get('keywords', []))
                    all_tags.update(qa.get('tags', []))
                
                best_qa['keywords'] = list(all_keywords)[:10]  # 最多10个关键词
                best_qa['tags'] = list(all_tags)
                
                deduplicated_pairs.append(best_qa)
    
    print(f"✅ 去重完成: {len(qa_pairs)} -> {len(deduplicated_pairs)}")
    print(f"   减少: {len(qa_pairs) - len(deduplicated_pairs)} 条 ({((len(qa_pairs) - len(deduplicated_pairs)) / len(qa_pairs) * 100):.1f}%)")
    
    return deduplicated_pairs


def analyze_duplicates(qa_pairs: List[Dict[str, Any]], similarity_threshold: float = 0.85):
    """
    分析重复情况但不修改数据
    """
    if not qa_pairs:
        return
    
    print(f"\n📊 分析重复情况...")
    
    questions = [qa['question'] for qa in qa_pairs]
    similarity_matrix = calculate_text_similarity(questions)
    
    # 统计相似对数量
    duplicate_count = 0
    high_similarity_pairs = []
    
    for i in range(len(qa_pairs)):
        for j in range(i + 1, len(qa_pairs)):
            if similarity_matrix[i][j] >= similarity_threshold:
                duplicate_count += 1
                if len(high_similarity_pairs) < 5:  # 只保留前5个例子
                    high_similarity_pairs.append({
                        'q1': questions[i][:100] + '...' if len(questions[i]) > 100 else questions[i],
                        'q2': questions[j][:100] + '...' if len(questions[j]) > 100 else questions[j],
                        'similarity': similarity_matrix[i][j]
                    })
    
    print(f"\n发现 {duplicate_count} 对相似问题 (阈值={similarity_threshold})")
    
    if high_similarity_pairs:
        print("\n示例相似问题对:")
        for idx, pair in enumerate(high_similarity_pairs, 1):
            print(f"\n  [{idx}] 相似度: {pair['similarity']:.3f}")
            print(f"      Q1: {pair['q1']}")
            print(f"      Q2: {pair['q2']}")
    
    # 按主题统计
    topic_stats = defaultdict(int)
    for qa in qa_pairs:
        topic_stats[qa.get('topic', 'unknown')] += 1
    
    print("\n主题分布:")
    for topic, count in sorted(topic_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {topic}: {count}")


def filter_by_quality(qa_pairs: List[Dict[str, Any]], min_confidence: float = 0.5) -> List[Dict[str, Any]]:
    """
    按质量过滤
    """
    filtered = [qa for qa in qa_pairs if qa.get('confidence_score', 0) >= min_confidence]
    print(f"🔍 质量过滤: {len(qa_pairs)} -> {len(filtered)} (removed {len(qa_pairs) - len(filtered)})")
    return filtered


def main():
    parser = argparse.ArgumentParser(description='去重和合并相似Q&A对')
    parser.add_argument('input', help='输入JSON文件 (cleaned_transcripts.json)')
    parser.add_argument('--output', '-o', help='输出JSON文件 (默认: deduplicated_transcripts.json)')
    parser.add_argument('--threshold', '-t', type=float, default=0.85,
                        help='相似度阈值 (0.0-1.0, 默认: 0.85)')
    parser.add_argument('--strategy', '-s', choices=['best', 'merge'], default='best',
                        help='合并策略: best=保留最高质量, merge=合并答案 (默认: best)')
    parser.add_argument('--min-confidence', type=float, default=0.0,
                        help='最低置信度阈值 (0.0-1.0)')
    parser.add_argument('--analyze-only', action='store_true',
                        help='只分析不去重')
    
    args = parser.parse_args()
    
    # 确定输出文件名
    if not args.output:
        input_path = Path(args.input)
        args.output = str(input_path.parent / 'deduplicated_transcripts.json')
    
    print("🚀 开始处理...")
    print(f"输入文件: {args.input}")
    
    # 加载数据
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            qa_pairs = json.load(f)
    except Exception as e:
        print(f"❌ 无法读取输入文件: {e}")
        return
    
    print(f"✅ 加载了 {len(qa_pairs)} 条Q&A对")
    
    # 只分析模式
    if args.analyze_only:
        analyze_duplicates(qa_pairs, args.threshold)
        return
    
    # 质量过滤（可选）
    if args.min_confidence > 0:
        qa_pairs = filter_by_quality(qa_pairs, args.min_confidence)
    
    # 去重
    deduplicated_pairs = deduplicate_qa_pairs(
        qa_pairs, 
        similarity_threshold=args.threshold,
        merge_strategy=args.strategy
    )
    
    # 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(deduplicated_pairs, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 去重数据已保存到: {output_path}")
    print(f"📦 最终数量: {len(deduplicated_pairs)} 条Q&A对")
    
    # 打印最终统计
    print("\n" + "="*60)
    print("📊 最终统计")
    print("="*60)
    
    # 质量分布
    quality_ranges = {
        'Very High (≥0.8)': sum(1 for qa in deduplicated_pairs if qa['confidence_score'] >= 0.8),
        'High (0.7-0.8)': sum(1 for qa in deduplicated_pairs if 0.7 <= qa['confidence_score'] < 0.8),
        'Medium (0.6-0.7)': sum(1 for qa in deduplicated_pairs if 0.6 <= qa['confidence_score'] < 0.7),
        'Low (<0.6)': sum(1 for qa in deduplicated_pairs if qa['confidence_score'] < 0.6)
    }
    
    print("\n质量分布:")
    for range_name, count in quality_ranges.items():
        percentage = (count / len(deduplicated_pairs) * 100) if deduplicated_pairs else 0
        print(f"  - {range_name}: {count} ({percentage:.1f}%)")
    
    # 主题分布
    topic_counts = defaultdict(int)
    for qa in deduplicated_pairs:
        topic_counts[qa['topic']] += 1
    
    print("\n主题分布:")
    for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / len(deduplicated_pairs) * 100) if deduplicated_pairs else 0
        print(f"  - {topic}: {count} ({percentage:.1f}%)")
    
    print("\n" + "="*60)
    print("✨ 下一步: python scripts/ingest_transcripts.py")
    print("="*60)


if __name__ == '__main__':
    main()
