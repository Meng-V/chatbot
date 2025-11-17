#!/usr/bin/env python3
"""
RAG Usage Analytics

This script analyzes RAG (Retrieval-Augmented Generation) usage from the database
to help developers understand how frequently the RAG search function is being used.

Usage:
    python scripts/analyze_rag_usage.py [--days 7] [--detailed]
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.prisma_client import get_prisma_client


async def get_rag_usage_stats(days: int = 7, detailed: bool = False):
    """
    Get RAG usage statistics from the database.
    
    Args:
        days: Number of days to look back
        detailed: Whether to show detailed per-query information
    """
    prisma = get_prisma_client()
    
    if not prisma.is_connected():
        await prisma.connect()
    
    # Calculate date range
    start_date = datetime.now() - timedelta(days=days)
    
    print("="*80)
    print(f"RAG USAGE ANALYTICS - Last {days} Days")
    print("="*80)
    print(f"Date Range: {start_date.strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}")
    print()
    
    try:
        # Query all RAG executions
        rag_executions = await prisma.toolexecution.find_many(
            where={
                "agentName": "transcript_rag",
                "toolName": "rag_search",
                "timestamp": {"gte": start_date}
            },
            order={"timestamp": "desc"}
        )
        
        total_queries = len(rag_executions)
        successful_queries = sum(1 for exec in rag_executions if exec.success)
        failed_queries = total_queries - successful_queries
        
        # Calculate average execution time
        avg_execution_time = (
            sum(exec.executionTime for exec in rag_executions) / total_queries
            if total_queries > 0 else 0
        )
        
        print("📊 OVERVIEW")
        print("-"*80)
        print(f"Total RAG Queries: {total_queries}")
        print(f"✅ Successful: {successful_queries} ({successful_queries/total_queries*100:.1f}%)" if total_queries > 0 else "✅ Successful: 0 (0%)")
        print(f"❌ Failed: {failed_queries} ({failed_queries/total_queries*100:.1f}%)" if total_queries > 0 else "❌ Failed: 0 (0%)")
        print(f"⏱️  Average Execution Time: {avg_execution_time:.0f}ms")
        print()
        
        if total_queries == 0:
            print("⚠️  No RAG queries found in the specified time period.")
            return
        
        # Analyze confidence levels
        confidence_counts = {"high": 0, "medium": 0, "low": 0, "none": 0, "unknown": 0}
        similarity_scores = []
        topics = {}
        
        for exec in rag_executions:
            if exec.success and exec.parameters:
                try:
                    params = json.loads(exec.parameters)
                    
                    # Count confidence levels
                    confidence = params.get("confidence", "unknown")
                    confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1
                    
                    # Collect similarity scores
                    similarity = params.get("similarity_score", 0)
                    if similarity > 0:
                        similarity_scores.append(similarity)
                    
                    # Count topics
                    topic = params.get("matched_topic", "unknown")
                    topics[topic] = topics.get(topic, 0) + 1
                except:
                    pass
        
        # Print confidence analysis
        print("🎯 CONFIDENCE LEVELS")
        print("-"*80)
        for level, count in sorted(confidence_counts.items(), key=lambda x: x[1], reverse=True):
            if count > 0:
                percentage = (count / successful_queries * 100) if successful_queries > 0 else 0
                print(f"  {level.upper()}: {count} ({percentage:.1f}%)")
        print()
        
        # Print similarity score analysis
        if similarity_scores:
            avg_similarity = sum(similarity_scores) / len(similarity_scores)
            min_similarity = min(similarity_scores)
            max_similarity = max(similarity_scores)
            
            print("📈 SIMILARITY SCORES")
            print("-"*80)
            print(f"  Average: {avg_similarity:.3f}")
            print(f"  Min: {min_similarity:.3f}")
            print(f"  Max: {max_similarity:.3f}")
            print()
        
        # Print topic distribution
        if topics:
            print("📚 TOPICS MATCHED")
            print("-"*80)
            for topic, count in sorted(topics.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / successful_queries * 100) if successful_queries > 0 else 0
                print(f"  {topic}: {count} ({percentage:.1f}%)")
            print()
        
        # Print daily breakdown
        print("📅 DAILY BREAKDOWN")
        print("-"*80)
        daily_counts = {}
        for exec in rag_executions:
            date_key = exec.timestamp.strftime("%Y-%m-%d")
            daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
        
        for date_key in sorted(daily_counts.keys(), reverse=True):
            count = daily_counts[date_key]
            print(f"  {date_key}: {count} queries")
        print()
        
        # Print detailed queries if requested
        if detailed and rag_executions:
            print("📝 DETAILED QUERY LOG (Last 20)")
            print("-"*80)
            
            for i, exec in enumerate(rag_executions[:20], 1):
                timestamp = exec.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                status = "✅" if exec.success else "❌"
                
                try:
                    params = json.loads(exec.parameters)
                    query = params.get("query", "N/A")
                    confidence = params.get("confidence", "unknown")
                    similarity = params.get("similarity_score", 0)
                    weaviate_ids = params.get("weaviate_ids", [])
                    
                    print(f"\n{i}. {timestamp} {status}")
                    print(f"   Query: {query[:80]}{'...' if len(query) > 80 else ''}")
                    print(f"   Confidence: {confidence} | Similarity: {similarity:.3f}")
                    print(f"   Execution Time: {exec.executionTime}ms")
                    if weaviate_ids:
                        print(f"   Weaviate IDs: {', '.join(weaviate_ids[:3])}{' ...' if len(weaviate_ids) > 3 else ''}")
                except:
                    print(f"\n{i}. {timestamp} {status}")
                    print(f"   Error parsing parameters")
            print()
        
        # Print recommendations
        print("💡 RECOMMENDATIONS")
        print("-"*80)
        
        if avg_similarity < 0.75:
            print("  ⚠️  Low average similarity score. Consider:")
            print("     - Adding more Q&A pairs to RAG database")
            print("     - Improving question phrasing in database")
            print("     - Using scripts/update_rag_facts.py to add missing content")
        
        if confidence_counts.get("low", 0) + confidence_counts.get("none", 0) > successful_queries * 0.3:
            print("  ⚠️  High number of low/no confidence results. Consider:")
            print("     - Reviewing low-confidence queries (use --detailed flag)")
            print("     - Adding specific Q&A pairs for common questions")
        
        if failed_queries > total_queries * 0.1:
            print("  ⚠️  High failure rate. Check:")
            print("     - Weaviate connection stability")
            print("     - Error logs for specific failure reasons")
        
        if total_queries < days * 2:
            print("  ℹ️  Low RAG usage. This could mean:")
            print("     - Users asking questions covered by other agents")
            print("     - Need to improve RAG content coverage")
            print("     - Or simply low overall traffic")
        
        print()
        print("="*80)
        print("For more details, use: python scripts/analyze_rag_usage.py --detailed")
        print("To update RAG content: python scripts/update_rag_facts.py")
        print("="*80)
        
    finally:
        await prisma.disconnect()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze RAG usage statistics")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed query information"
    )
    
    args = parser.parse_args()
    
    try:
        asyncio.run(get_rag_usage_stats(days=args.days, detailed=args.detailed))
    except KeyboardInterrupt:
        print("\n\n⚠️  Analysis interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
