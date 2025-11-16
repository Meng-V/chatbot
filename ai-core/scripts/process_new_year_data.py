#!/usr/bin/env python3
"""
Automated Pipeline for Processing New Year Chat Transcript Data
For processing 2026 and future years' data

Usage:
    python3 scripts/process_new_year_data.py \\
        --year 2026 \\
        --csv-files ../tran_raw_2026.csv \\
        --output data/2026_final.json

Complete Workflow:
    1. Data Cleaning (with privacy protection)
    2. Deduplication
    3. High-Quality Filtering
    4. AI-Assisted Smart Filtering
    5. Weaviate Ingestion (optional)
"""

import json
import os
import sys
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import functions from existing scripts
from clean_transcripts import process_csv_file, print_statistics
from deduplicate_transcripts import deduplicate_qa_pairs
from advanced_filter import filter_qa_pairs_batch

def print_step(step_num: int, title: str):
    """Print step title."""
    print(f"\n{'='*70}")
    print(f"📍 Step {step_num}: {title}")
    print(f"{'='*70}\n")


def save_checkpoint(data: List[Dict], filepath: str, description: str):
    """Save checkpoint data."""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    file_size = Path(filepath).stat().st_size / 1024 / 1024
    print(f"✅ {description}")
    print(f"   File: {filepath}")
    print(f"   Count: {len(data)} items")
    print(f"   Size: {file_size:.2f}MB")


async def process_new_year_data(
    year: int,
    csv_files: List[str],
    output_dir: str = "data",
    min_confidence: float = 0.7,
    dedup_threshold: float = 0.85,
    ai_batch_size: int = 20,
    skip_ai_filter: bool = False,
    auto_ingest: bool = False
):
    """
    Complete pipeline for processing new year transcript data.
    
    Args:
        year: Year of the data (e.g., 2026)
        csv_files: List of CSV file paths
        output_dir: Output directory
        min_confidence: Minimum confidence threshold (for high-quality filtering)
        dedup_threshold: Deduplication similarity threshold
        ai_batch_size: AI processing batch size
        skip_ai_filter: Whether to skip AI filtering
        auto_ingest: Whether to auto-ingest into Weaviate
    """
    
    start_time = datetime.now()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print("="*70)
    print(f"🚀 Starting to Process {year} Chat Transcript Data")
    print(f"{'='*70}")
    print(f"📅 Year: {year}")
    print(f"📁 CSV Files: {len(csv_files)} file(s)")
    print(f"📂 Output Directory: {output_dir}")
    print(f"⚙️  Minimum Confidence: {min_confidence}")
    print(f"🔄 Deduplication Threshold: {dedup_threshold}")
    print(f"🤖 AI Batch Size: {ai_batch_size}")
    print(f"⏰ Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # ========================================================================
    # Step 1: Data Cleaning (with privacy protection)
    # ========================================================================
    print_step(1, "Data Cleaning & Q&A Extraction (Privacy Protection Enabled)")
    
    all_qa_pairs = []
    for csv_file in csv_files:
        print(f"\n📄 Processing file: {csv_file}")
        qa_pairs, stats = process_csv_file(csv_file, extraction_strategy='all')
        all_qa_pairs.extend(qa_pairs)
        print(f"   ✓ Extracted: {len(qa_pairs)} Q&A pairs")
    
    step1_file = output_path / f"{year}_step1_cleaned.json"
    save_checkpoint(all_qa_pairs, str(step1_file), f"Step 1 Complete: Cleaned Data")
    
    # ========================================================================
    # Step 2: Deduplication
    # ========================================================================
    print_step(2, "Deduplication Processing")
    
    print(f"Deduplication Threshold: {dedup_threshold}")
    print(f"Strategy: best (keep highest quality)")
    
    deduped_pairs, dedup_stats = deduplicate_qa_pairs(
        all_qa_pairs,
        similarity_threshold=dedup_threshold,
        merge_strategy='best',
        min_confidence=0.0  # Don't filter yet, will filter in next step
    )
    
    step2_file = output_path / f"{year}_step2_deduped.json"
    save_checkpoint(deduped_pairs, str(step2_file), f"Step 2 Complete: Deduplicated Data")
    
    removed = len(all_qa_pairs) - len(deduped_pairs)
    print(f"\n📊 Deduplication Statistics:")
    print(f"   Before Dedup: {len(all_qa_pairs)}")
    print(f"   After Dedup: {len(deduped_pairs)}")
    print(f"   Removed: {removed} ({removed/len(all_qa_pairs)*100:.1f}%)")
    
    # ========================================================================
    # Step 3: High-Quality Filtering
    # ========================================================================
    print_step(3, f"High-Quality Filtering (confidence≥{min_confidence})")
    
    high_quality = [
        qa for qa in deduped_pairs 
        if qa.get('confidence_score', 0) >= min_confidence
    ]
    
    step3_file = output_path / f"{year}_step3_high_quality.json"
    save_checkpoint(high_quality, str(step3_file), f"Step 3 Complete: High-Quality Data")
    
    filtered_out = len(deduped_pairs) - len(high_quality)
    print(f"\n📊 Quality Filtering Statistics:")
    print(f"   Before Filtering: {len(deduped_pairs)}")
    print(f"   After Filtering: {len(high_quality)}")
    print(f"   Filtered Out: {filtered_out} ({filtered_out/len(deduped_pairs)*100:.1f}%)")
    
    # ========================================================================
    # Step 4: AI-Assisted Smart Filtering (optional)
    # ========================================================================
    if skip_ai_filter:
        print_step(4, "AI-Assisted Smart Filtering (Skipped)")
        final_pairs = high_quality
        deleted_pairs = []
        filter_stats = {}
    else:
        print_step(4, "AI-Assisted Smart Filtering (using o4-mini model)")
        
        print(f"🤖 Using o4-mini model for intelligent filtering")
        print(f"📦 Batch Size: {ai_batch_size}")
        print(f"⏱️  Estimated Time: {len(high_quality) / (ai_batch_size * 3):.0f}-{len(high_quality) / (ai_batch_size * 2):.0f} minutes")
        print(f"\n🔍 Filtering Rules:")
        print(f"   ✓ Remove greetings (Hi, Thanks, OK, etc.)")
        print(f"   ✓ Remove low-quality content (incomplete, meaningless)")
        print(f"   ✓ Remove inappropriate content (personal info, offensive)")
        print(f"   ✓ Remove API duplicates (questions covered by existing API agents)")
        
        final_pairs, deleted_pairs, filter_stats = await filter_qa_pairs_batch(
            high_quality,
            use_ai=True,
            batch_size=ai_batch_size
        )
        
        # Save deleted data for review
        deleted_file = output_path / f"{year}_deleted.json"
        save_checkpoint(deleted_pairs, str(deleted_file), "Deleted Data (For Review)")
    
    # Save final results
    final_file = output_path / f"{year}_final.json"
    save_checkpoint(final_pairs, str(final_file), "Step 4 Complete: Final Filtered Data")
    
    if filter_stats:
        print(f"\n📊 AI Filtering Statistics:")
        print(f"   Original: {len(high_quality)}")
        print(f"   Kept: {len(final_pairs)}")
        print(f"   Deleted: {len(deleted_pairs)}")
        
        reason_names = {
            'greeting': 'Greetings',
            'low_quality': 'Low Quality',
            'inappropriate': 'Inappropriate',
            'api_duplicate': 'API Duplicate'
        }
        
        print(f"\n   Deletion Reason Distribution:")
        for reason, count in sorted(filter_stats.items(), key=lambda x: x[1], reverse=True):
            reason_display = reason_names.get(reason, reason)
            percentage = count / len(deleted_pairs) * 100 if deleted_pairs else 0
            print(f"     - {reason_display}: {count} ({percentage:.1f}%)")
    
    # ========================================================================
    # Final Data Statistics
    # ========================================================================
    print(f"\n{'='*70}")
    print(f"📊 Final Data Statistics")
    print(f"{'='*70}")
    
    # Topic distribution
    topic_counts = defaultdict(int)
    quality_counts = defaultdict(int)
    
    for qa in final_pairs:
        topic_counts[qa.get('topic', 'unknown')] += 1
        conf = qa.get('confidence_score', 0)
        if conf >= 0.9:
            quality_counts['very_high'] += 1
        elif conf >= 0.8:
            quality_counts['high'] += 1
        elif conf >= 0.7:
            quality_counts['medium'] += 1
        else:
            quality_counts['low'] += 1
    
    print(f"\nTopic Distribution:")
    for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = count / len(final_pairs) * 100
        print(f"  - {topic}: {count} ({percentage:.1f}%)")
    
    print(f"\nQuality Distribution:")
    quality_labels = {
        'very_high': 'Very High (≥0.9)',
        'high': 'High (0.8-0.9)',
        'medium': 'Medium (0.7-0.8)',
        'low': 'Low (<0.7)'
    }
    for level in ['very_high', 'high', 'medium', 'low']:
        count = quality_counts[level]
        percentage = count / len(final_pairs) * 100 if final_pairs else 0
        print(f"  - {quality_labels[level]}: {count} ({percentage:.1f}%)")
    
    # ========================================================================
    # Step 5: Weaviate Ingestion (optional)
    # ========================================================================
    if auto_ingest:
        print_step(5, "Weaviate Ingestion")
        
        try:
            # Dynamic import to avoid dependency issues
            from ingest_transcripts import ingest, get_client
            
            client = get_client()
            ingest(client, str(final_file))
            client.close()
            
            print(f"✅ Successfully ingested {len(final_pairs)} items into Weaviate")
        
        except Exception as e:
            print(f"⚠️  Weaviate ingestion failed: {e}")
            print(f"   Please run manually: TRANSCRIPTS_PATH={final_file} python3 scripts/ingest_transcripts.py")
    else:
        print_step(5, "Weaviate Ingestion (Skipped)")
        print(f"Manual ingestion command:")
        print(f"  TRANSCRIPTS_PATH={final_file} python3 scripts/ingest_transcripts.py")
    
    # ========================================================================
    # Completion Summary
    # ========================================================================
    end_time = datetime.now()
    duration = end_time - start_time
    
    print(f"\n{'='*70}")
    print(f"✨ Processing Complete!")
    print(f"{'='*70}")
    print(f"⏰ Start Time: {start_time.strftime('%H:%M:%S')}")
    print(f"⏰ End Time: {end_time.strftime('%H:%M:%S')}")
    print(f"⏱️  Total Duration: {duration.total_seconds() / 60:.1f} minutes")
    print(f"\n📦 Final Outputs:")
    print(f"   - Final Data: {final_file} ({len(final_pairs)} items)")
    if not skip_ai_filter:
        print(f"   - Deleted Data: {deleted_file} ({len(deleted_pairs)} items)")
    print(f"\n📊 Data Pipeline:")
    print(f"   Raw CSV → {len(all_qa_pairs)} items")
    print(f"   After Dedup → {len(deduped_pairs)} items (-{len(all_qa_pairs)-len(deduped_pairs)})")
    print(f"   High-Quality Filter → {len(high_quality)} items (-{len(deduped_pairs)-len(high_quality)})")
    if not skip_ai_filter:
        print(f"   AI Filtering → {len(final_pairs)} items (-{len(high_quality)-len(final_pairs)})")
    print(f"   Retention Rate: {len(final_pairs)/len(all_qa_pairs)*100:.1f}%")
    
    return final_file


def main():
    parser = argparse.ArgumentParser(
        description='Complete automated pipeline for processing new year transcript data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example Usage:

  # Basic usage (process 2026 data)
  python3 scripts/process_new_year_data.py \\
      --year 2026 \\
      --csv-files ../tran_raw_2026.csv

  # Process multiple CSV files
  python3 scripts/process_new_year_data.py \\
      --year 2026 \\
      --csv-files ../tran_raw_2026_part1.csv ../tran_raw_2026_part2.csv

  # Custom parameters
  python3 scripts/process_new_year_data.py \\
      --year 2026 \\
      --csv-files ../tran_raw_2026.csv \\
      --min-confidence 0.8 \\
      --dedup-threshold 0.9 \\
      --ai-batch-size 30

  # Skip AI filtering (faster but may retain lower quality data)
  python3 scripts/process_new_year_data.py \\
      --year 2026 \\
      --csv-files ../tran_raw_2026.csv \\
      --skip-ai-filter

  # Auto-ingest into Weaviate
  python3 scripts/process_new_year_data.py \\
      --year 2026 \\
      --csv-files ../tran_raw_2026.csv \\
      --auto-ingest
        """
    )
    
    parser.add_argument('--year', type=int, required=True,
                        help='Data year (e.g., 2026)')
    parser.add_argument('--csv-files', nargs='+', required=True,
                        help='CSV file path(s) (can specify multiple)')
    parser.add_argument('--output-dir', default='data',
                        help='Output directory (default: data)')
    parser.add_argument('--min-confidence', type=float, default=0.7,
                        help='Minimum confidence threshold (default: 0.7)')
    parser.add_argument('--dedup-threshold', type=float, default=0.85,
                        help='Deduplication similarity threshold (default: 0.85)')
    parser.add_argument('--ai-batch-size', type=int, default=20,
                        help='AI processing batch size (default: 20)')
    parser.add_argument('--skip-ai-filter', action='store_true',
                        help='Skip AI-assisted filtering (faster but lower quality)')
    parser.add_argument('--auto-ingest', action='store_true',
                        help='Automatically ingest into Weaviate')
    
    args = parser.parse_args()
    
    # Validate CSV file existence
    for csv_file in args.csv_files:
        if not Path(csv_file).exists():
            print(f"❌ Error: CSV file not found: {csv_file}")
            sys.exit(1)
    
    # Run main pipeline
    asyncio.run(process_new_year_data(
        year=args.year,
        csv_files=args.csv_files,
        output_dir=args.output_dir,
        min_confidence=args.min_confidence,
        dedup_threshold=args.dedup_threshold,
        ai_batch_size=args.ai_batch_size,
        skip_ai_filter=args.skip_ai_filter,
        auto_ingest=args.auto_ingest
    ))


if __name__ == '__main__':
    main()
