#!/usr/bin/env python3
"""
高级数据过滤：使用AI辅助清洗低质量和与API重复的Q&A对
"""
import json
import os
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict
import argparse
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# 加载环境变量
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# 使用o4-mini模型（不支持temperature参数）
llm = ChatOpenAI(model="o4-mini", api_key=OPENAI_API_KEY)

# ============================================================================
# 过滤规则定义
# ============================================================================

# 简单寒暄语模式（直接过滤，不需要AI）
SIMPLE_GREETINGS = [
    'hi', 'hello', 'hey', 'thanks', 'thank you', "you're welcome",
    'ok', 'okay', 'sure', 'yes', 'no', 'bye', 'goodbye',
    'got it', 'perfect', 'great', 'awesome', 'cool',
    'sorry', 'my bad', 'oops', 'alright', 'k', 'thx'
]

# API Agent职责定义（用于识别重复）
API_AGENT_CAPABILITIES = """
Miami University Libraries Chatbot 现有API Agents：

1. **Primo Agent** - 实时图书馆目录检索
   - 搜索书籍、文章、期刊
   - 检查资源可用性和位置
   - 获取call number
   - 查询电子资源访问
   职责：任何需要查询当前馆藏的问题

2. **LibCal Agent** - 实时图书馆时间和空间管理
   - 查询图书馆开放时间（King, Art & Architecture等）
   - 预订学习室
   - 检查房间可用性
   职责：任何需要实时时间或预订信息的问题

3. **LibGuide Agent** - LibGuides数据库
   - 课程研究指南
   - 学科指南
   - 数据库推荐
   职责：课程相关的研究指南查询

4. **Subject Librarian Agent** - 学科馆员数据库
   - 查找特定学科的librarian
   - 获取联系方式
   职责："谁是XX学科的librarian"类问题

5. **Google Site Agent** - 图书馆网站搜索
   - 搜索lib.miamioh.edu内容
   - 政策文档查询
   职责：网站内容查询
"""

# AI过滤提示词
FILTER_SYSTEM_PROMPT = f"""你是一个数据质量专家，负责过滤图书馆chatbot的RAG训练数据。

{API_AGENT_CAPABILITIES}

你的任务是判断每个Q&A对是否应该**删除**。需要删除的情况：

**1. 低质量内容（必删）**：
   - 纯寒暄语（Hi, Thanks, OK等）
   - 无意义的短语（Got it, Sure等）
   - 不完整的句子或问题
   - 拼写严重错误导致无法理解
   - 攻击性、不恰当或骚扰性内容
   - 个人信息（电话号码、地址等，但@miamioh.edu邮箱可保留）

**2. 与API重复（建议删除）**：
   - **实时数据查询**：问题需要实时查询当前数据（如"今天图书馆几点关门"、"这本书现在可借吗"）
   - **动态目录检索**：需要搜索当前馆藏的问题（如"你们有XX这本书吗"）
   - **实时预订**：需要检查或预订房间的问题
   - **当前时间表**：询问当前学期的开放时间

**3. 应该保留的（即使看起来与API相关）**：
   - **操作指南**：如何使用某个服务（如"如何续借书籍"、"如何使用ILL"）
   - **政策解释**：图书馆政策说明（如"逾期罚款是多少"、"可以借几本书"）
   - **使用技巧**：如何操作数据库、如何打印等
   - **一般性知识**：不需要实时数据的问题（如"什么是interlibrary loan"）
   - **故障排查**：解决常见问题的方法
   - **复杂案例**：需要librarian经验和判断的问题

**判断原则**：
- 如果问题可以通过API**实时查询**最新数据回答 → 删除（让API处理）
- 如果问题需要**人工经验**、**解释说明**、**操作指导** → 保留（RAG价值）

请对每个Q&A对返回JSON格式：
{{
    "should_delete": true/false,
    "reason": "删除原因分类",
    "explanation": "简短解释（1-2句话）"
}}

删除原因分类只能是以下之一：
- "greeting": 寒暄语
- "low_quality": 低质量内容
- "inappropriate": 不恰当内容
- "api_duplicate": 与API重复
- "keep": 应该保留
"""


async def ai_judge_single_qa(qa: Dict[str, Any], batch_mode: bool = False) -> Dict[str, Any]:
    """
    使用AI判断单个Q&A对是否应该删除
    """
    question = qa.get('question', '')
    answer = qa.get('answer', '')
    topic = qa.get('topic', '')
    
    prompt = f"""
Q&A对信息：
- 主题分类: {topic}
- 问题: {question}
- 答案: {answer[:200]}{"..." if len(answer) > 200 else ""}

请判断这个Q&A对是否应该删除，并返回JSON格式的判断结果。
"""
    
    messages = [
        SystemMessage(content=FILTER_SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ]
    
    try:
        response = await llm.ainvoke(messages)
        result_text = response.content.strip()
        
        # 解析JSON
        if result_text.startswith('```json'):
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif result_text.startswith('```'):
            result_text = result_text.split('```')[1].split('```')[0].strip()
        
        result = json.loads(result_text)
        return result
    
    except Exception as e:
        print(f"⚠️  AI判断出错: {e}")
        # 默认保留
        return {
            "should_delete": False,
            "reason": "keep",
            "explanation": "AI判断出错，默认保留"
        }


def simple_filter(qa: Dict[str, Any]) -> Dict[str, Any]:
    """
    简单规则过滤（不需要AI）
    """
    question = qa.get('question', '').lower().strip()
    answer = qa.get('answer', '').lower().strip()
    
    # 1. 过滤纯寒暄语
    if question in SIMPLE_GREETINGS or answer in SIMPLE_GREETINGS:
        return {
            "should_delete": True,
            "reason": "greeting",
            "explanation": "纯寒暄语"
        }
    
    # 2. 问题或答案太短（<10字符）
    if len(question) < 10 or len(answer) < 10:
        return {
            "should_delete": True,
            "reason": "low_quality",
            "explanation": "内容太短"
        }
    
    # 3. 问题和答案完全相同
    if question == answer:
        return {
            "should_delete": True,
            "reason": "low_quality",
            "explanation": "问答相同"
        }
    
    # 4. 包含明显攻击性词汇
    offensive_keywords = ['fuck', 'shit', 'damn', 'stupid', 'idiot', 'hate']
    if any(keyword in question or keyword in answer for keyword in offensive_keywords):
        return {
            "should_delete": True,
            "reason": "inappropriate",
            "explanation": "包含不当内容"
        }
    
    # 需要AI进一步判断
    return None


async def filter_qa_pairs_batch(
    qa_pairs: List[Dict[str, Any]], 
    use_ai: bool = True,
    batch_size: int = 10
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    批量过滤Q&A对
    
    Returns:
        (kept_pairs, deleted_pairs, filter_stats)
    """
    print(f"\n🔍 开始高级过滤...")
    print(f"   原始数量: {len(qa_pairs)}")
    print(f"   使用AI: {use_ai}")
    
    kept_pairs = []
    deleted_pairs = []
    filter_stats = defaultdict(int)
    
    # 第1阶段：简单规则过滤
    print(f"\n📋 阶段1: 简单规则过滤...")
    ai_review_queue = []
    
    for i, qa in enumerate(qa_pairs):
        simple_result = simple_filter(qa)
        
        if simple_result:
            if simple_result['should_delete']:
                filter_stats[simple_result['reason']] += 1
                # 保存删除记录
                qa['_delete_reason'] = simple_result['explanation']
                qa['_delete_category'] = simple_result['reason']
                deleted_pairs.append(qa)
            else:
                kept_pairs.append(qa)
        else:
            # 需要AI判断
            ai_review_queue.append(qa)
        
        if (i + 1) % 1000 == 0:
            print(f"   进度: {i + 1}/{len(qa_pairs)}")
    
    print(f"   简单规则过滤掉: {sum(filter_stats.values())}")
    print(f"   需要AI审核: {len(ai_review_queue)}")
    
    # 第2阶段：AI审核（如果启用）
    if use_ai and ai_review_queue:
        print(f"\n🤖 阶段2: AI智能过滤...")
        print(f"   这将调用{len(ai_review_queue)}次AI API，可能需要几分钟...")
        
        # 分批处理以避免过多并发
        for batch_start in range(0, len(ai_review_queue), batch_size):
            batch_end = min(batch_start + batch_size, len(ai_review_queue))
            batch = ai_review_queue[batch_start:batch_end]
            
            # 并发处理batch
            tasks = [ai_judge_single_qa(qa) for qa in batch]
            results = await asyncio.gather(*tasks)
            
            for qa, result in zip(batch, results):
                if result['should_delete']:
                    filter_stats[result['reason']] += 1
                    # 保存删除原因到qa对象
                    qa['_delete_reason'] = result['explanation']
                    qa['_delete_category'] = result['reason']
                    deleted_pairs.append(qa)
                else:
                    kept_pairs.append(qa)
            
            print(f"   AI进度: {batch_end}/{len(ai_review_queue)}")
    else:
        # 不使用AI，全部保留
        kept_pairs.extend(ai_review_queue)
    
    print(f"\n✅ 过滤完成!")
    print(f"   保留: {len(kept_pairs)}")
    print(f"   删除: {len(deleted_pairs)}")
    
    return kept_pairs, deleted_pairs, dict(filter_stats)


async def main():
    parser = argparse.ArgumentParser(description='高级数据过滤（AI辅助）')
    parser.add_argument('input', help='输入JSON文件')
    parser.add_argument('--output', '-o', help='输出JSON文件（默认: filtered_*.json）')
    parser.add_argument('--use-ai', action='store_true', default=True,
                        help='使用AI进行智能过滤（默认开启）')
    parser.add_argument('--no-ai', action='store_true',
                        help='只使用简单规则，不调用AI')
    parser.add_argument('--batch-size', type=int, default=10,
                        help='AI处理批次大小（默认10）')
    parser.add_argument('--sample', type=int,
                        help='只处理前N条（用于测试）')
    
    args = parser.parse_args()
    
    # 确定输出文件名
    if not args.output:
        input_path = Path(args.input)
        args.output = str(input_path.parent / f"filtered_{input_path.name}")
    
    print("🚀 高级数据过滤开始...")
    print(f"输入文件: {args.input}")
    print(f"输出文件: {args.output}")
    
    # 加载数据
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            qa_pairs = json.load(f)
    except Exception as e:
        print(f"❌ 无法读取输入文件: {e}")
        return
    
    print(f"✅ 加载了 {len(qa_pairs)} 条Q&A对")
    
    # 测试模式
    if args.sample:
        qa_pairs = qa_pairs[:args.sample]
        print(f"🧪 测试模式：只处理前 {args.sample} 条")
    
    # 过滤
    use_ai = args.use_ai and not args.no_ai
    filtered_pairs, deleted_pairs, stats = await filter_qa_pairs_batch(
        qa_pairs,
        use_ai=use_ai,
        batch_size=args.batch_size
    )
    
    # 保存保留的数据
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(filtered_pairs, f, indent=2, ensure_ascii=False)
    
    # 保存被删除的数据（用于审查）
    deleted_path = output_path.parent / f"deleted_{output_path.name}"
    with open(deleted_path, 'w', encoding='utf-8') as f:
        json.dump(deleted_pairs, f, indent=2, ensure_ascii=False)
    
    print(f"🗑️  被删除的数据已保存到: {deleted_path} (用于审查)")
    
    print(f"\n✅ 过滤后的数据已保存到: {output_path}")
    print(f"📦 最终数量: {len(filtered_pairs)} 条Q&A对")
    
    # 打印统计
    print("\n" + "="*60)
    print("📊 过滤统计")
    print("="*60)
    print(f"原始数量: {len(qa_pairs)}")
    print(f"保留数量: {len(filtered_pairs)}")
    print(f"删除数量: {len(qa_pairs) - len(filtered_pairs)}")
    
    if stats:
        print("\n删除原因分布:")
        reason_names = {
            'greeting': '寒暄语',
            'low_quality': '低质量',
            'inappropriate': '不当内容',
            'api_duplicate': 'API重复'
        }
        for reason, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
            reason_display = reason_names.get(reason, reason)
            print(f"  - {reason_display}: {count}")
    
    # 主题分布
    print("\n保留数据的主题分布:")
    topic_counts = defaultdict(int)
    for qa in filtered_pairs:
        topic_counts[qa.get('topic', 'unknown')] += 1
    
    for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / len(filtered_pairs) * 100) if filtered_pairs else 0
        print(f"  - {topic}: {count} ({percentage:.1f}%)")
    
    print("\n" + "="*60)
    print("✨ 下一步: python scripts/ingest_transcripts.py")
    print("="*60)


if __name__ == '__main__':
    asyncio.run(main())
