#!/usr/bin/env python3
"""
快速测试脚本：处理示例CSV文件
用于验证数据清洗流程是否正常工作
"""
import subprocess
import sys
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

def main():
    # 检查示例CSV文件
    csv_file = Path("/Users/qum/Documents/GitHub/chatbot/chat_transcript_2025-11-06_10_00_32.csv")
    
    if not csv_file.exists():
        print(f"❌ 找不到CSV文件: {csv_file}")
        print("请确保文件路径正确")
        sys.exit(1)
    
    print("="*60)
    print("🧪 RAG数据处理流程测试")
    print("="*60)
    print(f"\n📁 测试文件: {csv_file}")
    print(f"📦 文件大小: {csv_file.stat().st_size / 1024 / 1024:.2f} MB")
    
    # 切换到scripts目录
    scripts_dir = Path(__file__).parent
    
    # 第1步: 清洗数据（使用first策略快速测试）
    step1_output = scripts_dir.parent / "data" / "test_cleaned.json"
    step1_output.parent.mkdir(exist_ok=True)
    
    if not run_command(
        [
            sys.executable,
            str(scripts_dir / "clean_transcripts.py"),
            str(csv_file),
            "--output", str(step1_output),
            "--strategy", "first",  # 快速模式
            "--min-confidence", "0.5"
        ],
        "第1步: 清洗数据（first策略）"
    ):
        return
    
    # 检查输出文件
    if not step1_output.exists():
        print(f"\n❌ 输出文件不存在: {step1_output}")
        return
    
    import json
    with open(step1_output) as f:
        cleaned_data = json.load(f)
    
    print(f"\n📊 清洗结果: {len(cleaned_data)} 条Q&A对")
    
    if len(cleaned_data) == 0:
        print("⚠️  警告: 没有提取到任何数据！")
        return
    
    # 显示第一条示例
    print(f"\n📄 示例数据:")
    print(json.dumps(cleaned_data[0], indent=2, ensure_ascii=False)[:500] + "...")
    
    # 第2步: 去重（可选，如果数据量较小可以跳过）
    if len(cleaned_data) > 100:
        step2_output = scripts_dir.parent / "data" / "test_deduplicated.json"
        
        if not run_command(
            [
                sys.executable,
                str(scripts_dir / "deduplicate_transcripts.py"),
                str(step1_output),
                "--output", str(step2_output),
                "--threshold", "0.85",
                "--strategy", "best"
            ],
            "第2步: 去重"
        ):
            return
        
        with open(step2_output) as f:
            dedup_data = json.load(f)
        
        print(f"\n📊 去重结果: {len(dedup_data)} 条Q&A对")
        final_file = step2_output
    else:
        print(f"\n⏭️  数据量较小（{len(cleaned_data)}条），跳过去重步骤")
        final_file = step1_output
    
    # 总结
    print("\n" + "="*60)
    print("✨ 测试完成！")
    print("="*60)
    print(f"\n📦 处理后的数据文件: {final_file}")
    print(f"📊 数据条数: {len(cleaned_data)}")
    
    print("\n下一步:")
    print(f"  1. 检查数据质量: cat {final_file} | jq '.[0]'")
    print(f"  2. 摄入Weaviate: TRANSCRIPTS_PATH={final_file} python scripts/ingest_transcripts.py")
    print(f"  3. 测试查询: python -c \"import asyncio; from src.agents.transcript_rag_agent import transcript_rag_query; print(asyncio.run(transcript_rag_query('How do I renew a book?')))\"")
    print()

if __name__ == '__main__':
    main()
