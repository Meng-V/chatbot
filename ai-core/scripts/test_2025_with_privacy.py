#!/usr/bin/env python3
"""
测试2025年数据处理（带隐私保护）
专门用于验证数据清洗流程和隐私保护功能
"""
import subprocess
import sys
import json
from pathlib import Path

def run_command(cmd, description):
    """运行命令并显示结果"""
    print(f"\n{'='*60}")
    print(f"🚀 {description}")
    print(f"{'='*60}")
    print(f"命令: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    if result.returncode != 0:
        print(f"\n❌ 失败！退出码: {result.returncode}")
        return False
    else:
        print(f"\n✅ 成功！")
        return True

def check_privacy_protection(json_file):
    """检查隐私保护是否生效"""
    print(f"\n{'='*60}")
    print("🔍 检查隐私保护")
    print(f"{'='*60}")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 检查是否有真实姓名泄露
    real_names_found = []
    librarian_count = 0
    patron_count = 0
    
    for qa in data:
        # 检查answerer字段
        answerer = qa.get('answerer', '')
        if answerer and answerer != 'Librarian':
            real_names_found.append(f"Answerer field: {answerer}")
        elif answerer == 'Librarian':
            librarian_count += 1
    
    # 随机抽查10条对话内容
    import random
    sample_size = min(10, len(data))
    samples = random.sample(data, sample_size)
    
    print(f"\n📊 隐私保护统计:")
    print(f"  - 总Q&A对数: {len(data)}")
    print(f"  - Answerer为'Librarian': {librarian_count}")
    print(f"  - 发现真实姓名: {len(real_names_found)}")
    
    if real_names_found:
        print(f"\n⚠️  警告：发现以下真实姓名：")
        for name in real_names_found[:5]:  # 只显示前5个
            print(f"     {name}")
        return False
    else:
        print(f"\n✅ 隐私保护验证通过：未发现真实姓名泄露")
        return True

def show_sample_data(json_file, num_samples=3):
    """显示示例数据"""
    print(f"\n{'='*60}")
    print("📄 示例数据（验证隐私保护）")
    print(f"{'='*60}")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    for i in range(min(num_samples, len(data))):
        print(f"\n[示例 {i+1}]")
        print(f"问题: {data[i]['question'][:100]}...")
        print(f"答案: {data[i]['answer'][:100]}...")
        print(f"主题: {data[i]['topic']}")
        print(f"评分: {data[i]['rating']}")
        print(f"置信度: {data[i]['confidence_score']}")
        print(f"回答者: {data[i]['answerer']}")  # 应该是"Librarian"
        print("-" * 60)

def main():
    print("="*60)
    print("🧪 2025年数据处理测试（带隐私保护）")
    print("="*60)
    
    # CSV文件路径
    csv_2025 = Path("/Users/qum/Documents/GitHub/chatbot/tran_raw_2025.csv")
    
    if not csv_2025.exists():
        print(f"❌ 找不到2025年CSV文件: {csv_2025}")
        sys.exit(1)
    
    print(f"\n📁 测试文件: {csv_2025}")
    print(f"📦 文件大小: {csv_2025.stat().st_size / 1024 / 1024:.2f} MB")
    
    # 切换到scripts目录
    scripts_dir = Path(__file__).parent
    
    # 输出目录
    output_dir = scripts_dir.parent / "data" / "test_2025"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 第1步: 清洗数据（使用all策略）
    step1_output = output_dir / "cleaned_2025.json"
    
    print("\n" + "="*60)
    print("📋 处理策略")
    print("="*60)
    print("✓ 提取策略: all（提取所有Q&A对）")
    print("✓ 隐私保护: 已启用")
    print("✓ 最低置信度: 0.5")
    print("✓ 图书馆员姓名 → 'Librarian'")
    
    if not run_command(
        [
            sys.executable,
            str(scripts_dir / "clean_transcripts.py"),
            str(csv_2025),
            "--output", str(step1_output),
            "--strategy", "all",
            "--min-confidence", "0.5"
        ],
        "第1步: 清洗2025年数据"
    ):
        return
    
    # 检查输出文件
    if not step1_output.exists():
        print(f"\n❌ 输出文件不存在: {step1_output}")
        return
    
    with open(step1_output) as f:
        cleaned_data = json.load(f)
    
    print(f"\n📊 清洗结果: {len(cleaned_data)} 条Q&A对")
    
    if len(cleaned_data) == 0:
        print("⚠️  警告: 没有提取到任何数据！")
        return
    
    # 隐私保护检查
    privacy_ok = check_privacy_protection(step1_output)
    
    # 显示示例数据
    show_sample_data(step1_output, num_samples=5)
    
    # 主题分布统计
    print(f"\n{'='*60}")
    print("📊 主题分布")
    print(f"{'='*60}")
    
    topic_counts = {}
    for qa in cleaned_data:
        topic = qa.get('topic', 'unknown')
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
    
    for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / len(cleaned_data)) * 100
        print(f"  - {topic}: {count} ({percentage:.1f}%)")
    
    # 质量分布
    print(f"\n{'='*60}")
    print("⭐ 质量分布")
    print(f"{'='*60}")
    
    quality_ranges = {
        'Very High (≥0.8)': 0,
        'High (0.7-0.8)': 0,
        'Medium (0.6-0.7)': 0,
        'Low (0.5-0.6)': 0,
        'Very Low (<0.5)': 0
    }
    
    for qa in cleaned_data:
        conf = qa['confidence_score']
        if conf >= 0.8:
            quality_ranges['Very High (≥0.8)'] += 1
        elif conf >= 0.7:
            quality_ranges['High (0.7-0.8)'] += 1
        elif conf >= 0.6:
            quality_ranges['Medium (0.6-0.7)'] += 1
        elif conf >= 0.5:
            quality_ranges['Low (0.5-0.6)'] += 1
        else:
            quality_ranges['Very Low (<0.5)'] += 1
    
    for range_name, count in quality_ranges.items():
        if len(cleaned_data) > 0:
            percentage = (count / len(cleaned_data)) * 100
            print(f"  - {range_name}: {count} ({percentage:.1f}%)")
    
    # 总结
    print("\n" + "="*60)
    print("✨ 测试完成！")
    print("="*60)
    
    if privacy_ok:
        print("\n✅ 隐私保护: 通过验证")
    else:
        print("\n⚠️  隐私保护: 需要检查")
    
    print(f"\n📦 处理后的数据文件: {step1_output}")
    print(f"📊 数据条数: {len(cleaned_data)}")
    
    # 下一步建议
    print("\n" + "="*60)
    print("📋 下一步建议")
    print("="*60)
    
    if len(cleaned_data) >= 500:
        print("\n✅ 数据量充足，可以继续去重和摄入流程：")
        print(f"\n1. 去重（可选）:")
        print(f"   python scripts/deduplicate_transcripts.py \\")
        print(f"       {step1_output} \\")
        print(f"       --output {output_dir}/dedup_2025.json \\")
        print(f"       --threshold 0.85")
        
        print(f"\n2. 摄入Weaviate:")
        print(f"   TRANSCRIPTS_PATH={step1_output} \\")
        print(f"   python scripts/ingest_transcripts.py")
        
        print(f"\n3. 测试RAG查询:")
        print(f"   python -c \"import asyncio; from src.agents.transcript_rag_agent import transcript_rag_query; print(asyncio.run(transcript_rag_query('How do I renew a book?')))\"")
        
        print(f"\n4. 如果满意，处理完整3年数据:")
        print(f"   python scripts/clean_transcripts.py \\")
        print(f"       tran_raw_2023.csv tran_raw_2024.csv tran_raw_2025.csv \\")
        print(f"       --output data/all_cleaned.json")
    else:
        print(f"\n⚠️  数据量较少（{len(cleaned_data)}条），建议检查:")
        print("   1. CSV文件格式是否正确")
        print("   2. 过滤规则是否过于严格")
        print("   3. 降低--min-confidence阈值重试")
    
    print()

if __name__ == '__main__':
    main()
