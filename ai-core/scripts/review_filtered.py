#!/usr/bin/env python3
"""
查看过滤结果，对比删除前后的数据
"""
import json
import sys
from pathlib import Path

def review_filtering(original_file, filtered_file, num_samples=20):
    """对比原始和过滤后的数据"""
    
    with open(original_file, 'r', encoding='utf-8') as f:
        original = json.load(f)
    
    with open(filtered_file, 'r', encoding='utf-8') as f:
        filtered = json.load(f)
    
    # 找出被删除的记录
    filtered_ids = {(qa['question'], qa['answer']) for qa in filtered}
    deleted = [qa for qa in original if (qa['question'], qa['answer']) not in filtered_ids]
    
    print("="*60)
    print("📊 过滤结果对比")
    print("="*60)
    print(f"原始数量: {len(original)}")
    print(f"保留数量: {len(filtered)}")
    print(f"删除数量: {len(deleted)}")
    print(f"删除率: {len(deleted)/len(original)*100:.1f}%")
    
    # 按主题统计删除情况
    print("\n删除数据的主题分布:")
    deleted_topics = {}
    for qa in deleted:
        topic = qa.get('topic', 'unknown')
        deleted_topics[topic] = deleted_topics.get(topic, 0) + 1
    
    for topic, count in sorted(deleted_topics.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / len(deleted) * 100) if deleted else 0
        print(f"  - {topic}: {count} ({percentage:.1f}%)")
    
    # 显示被删除的示例
    print(f"\n{'='*60}")
    print(f"🗑️ 被删除的示例 (前{num_samples}条)")
    print(f"{'='*60}")
    
    for i, qa in enumerate(deleted[:num_samples]):
        print(f"\n[删除示例 {i+1}]")
        print(f"主题: {qa.get('topic', 'unknown')}")
        print(f"评分: {qa.get('rating', 0)}")
        print(f"问题: {qa['question'][:100]}...")
        print(f"答案: {qa['answer'][:100]}...")
        if '_delete_reason' in qa:
            print(f"删除原因: {qa['_delete_reason']}")
        print("-" * 60)
    
    # 显示保留的示例
    print(f"\n{'='*60}")
    print(f"✅ 保留的示例 (前{num_samples}条)")
    print(f"{'='*60}")
    
    for i, qa in enumerate(filtered[:num_samples]):
        print(f"\n[保留示例 {i+1}]")
        print(f"主题: {qa.get('topic', 'unknown')}")
        print(f"评分: {qa.get('rating', 0)}")
        print(f"问题: {qa['question'][:100]}...")
        print(f"答案: {qa['answer'][:100]}...")
        print("-" * 60)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python review_filtered.py <原始文件> <过滤后文件> [示例数量]")
        sys.exit(1)
    
    original_file = sys.argv[1]
    filtered_file = sys.argv[2]
    num_samples = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    
    review_filtering(original_file, filtered_file, num_samples)
