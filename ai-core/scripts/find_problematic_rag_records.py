#!/usr/bin/env python3
"""
Find Problematic RAG Records

This script helps identify Weaviate records that may need to be deleted by:
- Finding records with low confidence matches
- Identifying records that appear in error reports
- Listing records that users reported as incorrect

Usage:
    # Find low confidence matches
    python scripts/find_problematic_rag_records.py --low-confidence
    
    # Find specific query matches
    python scripts/find_problematic_rag_records.py --query "wrong answer"
    
    # Show records from last N days
    python scripts/find_problematic_rag_records.py --days 7
    
    # Export IDs to file for deletion
    python scripts/find_problematic_rag_records.py --low-confidence --export ids.txt
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


async def find_low_confidence_records(days: int = 7, min_occurrences: int = 2):
    """
    Find Weaviate records that consistently return low confidence matches.
    
    Args:
        days: Look back this many days
        min_occurrences: Minimum times a record must appear to be considered
    """
    prisma = get_prisma_client()
    
    if not prisma.is_connected():
        await prisma.connect()
    
    start_date = datetime.now() - timedelta(days=days)
    
    print(f"\n🔍 Finding low confidence RAG matches (last {days} days)...")
    
    # Get all RAG executions
    executions = await prisma.toolexecution.find_many(
        where={
            "agentName": "transcript_rag",
            "toolName": "rag_search",
            "timestamp": {"gte": start_date},
            "success": True
        },
        order={"timestamp": "desc"}
    )
    
    # Track Weaviate IDs and their statistics
    id_stats = {}
    
    for exec in executions:
        try:
            params = json.loads(exec.parameters)
            confidence = params.get("confidence", "unknown")
            weaviate_ids = params.get("weaviate_ids", [])
            query = params.get("query", "N/A")
            similarity = params.get("similarity_score", 0)
            
            # Track each Weaviate ID that appeared in low confidence results
            if confidence in ["low", "none"]:
                for weaviate_id in weaviate_ids:
                    if weaviate_id not in id_stats:
                        id_stats[weaviate_id] = {
                            "count": 0,
                            "low_confidence_count": 0,
                            "queries": [],
                            "avg_similarity": []
                        }
                    
                    id_stats[weaviate_id]["count"] += 1
                    id_stats[weaviate_id]["low_confidence_count"] += 1
                    id_stats[weaviate_id]["queries"].append(query)
                    id_stats[weaviate_id]["avg_similarity"].append(similarity)
        except:
            continue
    
    await prisma.disconnect()
    
    # Filter by minimum occurrences
    problematic_ids = {
        wid: stats 
        for wid, stats in id_stats.items() 
        if stats["low_confidence_count"] >= min_occurrences
    }
    
    if not problematic_ids:
        print(f"✅ No problematic records found (with {min_occurrences}+ occurrences)")
        return []
    
    # Sort by low confidence count
    sorted_ids = sorted(
        problematic_ids.items(),
        key=lambda x: x[1]["low_confidence_count"],
        reverse=True
    )
    
    print(f"\n📊 Found {len(sorted_ids)} problematic record(s):\n")
    print(f"{'ID':<40} {'Low Conf.':<12} {'Avg Sim':<10} {'Sample Query'}")
    print("=" * 100)
    
    result_ids = []
    for weaviate_id, stats in sorted_ids[:20]:  # Top 20
        avg_sim = sum(stats["avg_similarity"]) / len(stats["avg_similarity"])
        sample_query = stats["queries"][0][:50]
        
        print(f"{weaviate_id:<40} {stats['low_confidence_count']:<12} {avg_sim:.3f}      {sample_query}...")
        result_ids.append(weaviate_id)
    
    if len(sorted_ids) > 20:
        print(f"\n... and {len(sorted_ids) - 20} more")
    
    return result_ids


async def find_records_by_query(query_text: str):
    """Find Weaviate records that matched a specific query."""
    prisma = get_prisma_client()
    
    if not prisma.is_connected():
        await prisma.connect()
    
    print(f"\n🔍 Searching for RAG executions matching: '{query_text}'...")
    
    # Get all RAG executions
    executions = await prisma.toolexecution.find_many(
        where={
            "agentName": "transcript_rag",
            "toolName": "rag_search",
            "success": True
        },
        order={"timestamp": "desc"},
        take=1000  # Last 1000 executions
    )
    
    matching_ids = []
    
    for exec in executions:
        try:
            params = json.loads(exec.parameters)
            query = params.get("query", "").lower()
            
            if query_text.lower() in query:
                weaviate_ids = params.get("weaviate_ids", [])
                confidence = params.get("confidence", "unknown")
                similarity = params.get("similarity_score", 0)
                
                print(f"\n📝 Query: {params.get('query', 'N/A')[:80]}")
                print(f"   Confidence: {confidence} | Similarity: {similarity:.3f}")
                print(f"   Weaviate IDs: {', '.join(weaviate_ids[:3])}")
                
                matching_ids.extend(weaviate_ids)
        except:
            continue
    
    await prisma.disconnect()
    
    # Remove duplicates
    unique_ids = list(set(matching_ids))
    
    print(f"\n✅ Found {len(unique_ids)} unique Weaviate record(s)")
    
    return unique_ids


async def show_recent_rag_usage(days: int = 7):
    """Show recent RAG usage with Weaviate IDs."""
    prisma = get_prisma_client()
    
    if not prisma.is_connected():
        await prisma.connect()
    
    start_date = datetime.now() - timedelta(days=days)
    
    print(f"\n📊 Recent RAG usage (last {days} days):\n")
    
    executions = await prisma.toolexecution.find_many(
        where={
            "agentName": "transcript_rag",
            "toolName": "rag_search",
            "timestamp": {"gte": start_date}
        },
        order={"timestamp": "desc"},
        take=20
    )
    
    for i, exec in enumerate(executions, 1):
        try:
            params = json.loads(exec.parameters)
            query = params.get("query", "N/A")
            confidence = params.get("confidence", "unknown")
            weaviate_ids = params.get("weaviate_ids", [])
            
            print(f"{i}. {exec.timestamp.strftime('%Y-%m-%d %H:%M')}")
            print(f"   Query: {query[:70]}...")
            print(f"   Confidence: {confidence}")
            print(f"   Weaviate IDs: {', '.join(weaviate_ids)}")
            print()
        except:
            continue
    
    await prisma.disconnect()
    
    return []


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Find problematic Weaviate records from RAG usage logs"
    )
    
    parser.add_argument(
        '--low-confidence',
        action='store_true',
        help='Find records with frequent low confidence matches'
    )
    parser.add_argument(
        '--query',
        type=str,
        help='Find records that matched a specific query text'
    )
    parser.add_argument(
        '--recent',
        action='store_true',
        help='Show recent RAG usage with Weaviate IDs'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days to look back (default: 7)'
    )
    parser.add_argument(
        '--min-occurrences',
        type=int,
        default=2,
        help='Minimum occurrences for low confidence (default: 2)'
    )
    parser.add_argument(
        '--export',
        type=str,
        help='Export found IDs to file (one per line)'
    )
    
    args = parser.parse_args()
    
    print("="*80)
    print("FIND PROBLEMATIC RAG RECORDS")
    print("="*80)
    
    found_ids = []
    
    try:
        if args.low_confidence:
            found_ids = asyncio.run(
                find_low_confidence_records(
                    days=args.days,
                    min_occurrences=args.min_occurrences
                )
            )
        
        elif args.query:
            found_ids = asyncio.run(find_records_by_query(args.query))
        
        elif args.recent:
            asyncio.run(show_recent_rag_usage(days=args.days))
        
        else:
            print("\n⚠️  Please specify an action:")
            print("  --low-confidence  : Find records with low confidence")
            print("  --query TEXT      : Find records matching query")
            print("  --recent          : Show recent RAG usage")
            parser.print_help()
            return
        
        # Export IDs if requested
        if found_ids and args.export:
            export_path = Path(args.export)
            with open(export_path, 'w') as f:
                for wid in found_ids:
                    f.write(f"{wid}\n")
            
            print(f"\n💾 Exported {len(found_ids)} IDs to: {export_path}")
            print(f"\nTo delete these records, run:")
            print(f"  python scripts/delete_weaviate_records.py --file {export_path}")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
