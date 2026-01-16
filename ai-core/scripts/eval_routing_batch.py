#!/usr/bin/env python3
"""
Batch Evaluation Script for Routing Classification

Tests routing accuracy on a list of questions with expected agent assignments.
Outputs detailed results, confusion matrix, and hard negatives for training.
"""

import asyncio
import sys
import json
import csv
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.orchestrator import library_graph
from src.utils.logger import AgentLogger


def load_test_data(file_path: str) -> List[Dict[str, Any]]:
    """Load test data from CSV or JSONL file."""
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"Test data file not found: {file_path}")
    
    test_cases = []
    
    if file_path.suffix == '.csv':
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                test_cases.append({
                    'question': row['question'],
                    'expected_primary_agent_id': row['expected_primary_agent_id'],
                    'notes': row.get('notes', ''),
                    'category': row.get('category', '')
                })
    elif file_path.suffix == '.jsonl':
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    test_cases.append(json.loads(line))
    else:
        raise ValueError(f"Unsupported file format: {file_path.suffix}. Use .csv or .jsonl")
    
    return test_cases


async def evaluate_single_question(question: str, expected_agent_id: str) -> Dict[str, Any]:
    """Evaluate a single question through the routing system."""
    logger = AgentLogger()
    
    try:
        # Run through library_graph
        result = await library_graph.ainvoke({
            "user_message": question,
            "messages": [],
            "conversation_history": [],
            "conversation_id": None,
            "_logger": logger
        })
        
        # Extract routing information
        predicted_agent_id = result.get("primary_agent_id")
        needs_clarification = result.get("needs_clarification", False)
        classification_confidence = result.get("classification_confidence")
        classified_intent = result.get("classified_intent")
        out_of_scope = result.get("out_of_scope", False)
        rag_category = result.get("rag_category")
        processed_query = result.get("processed_query", question)
        
        # Determine if this is a pass or fail
        if needs_clarification:
            status = "clarification"
            is_correct = None  # Don't count as pass/fail
        elif predicted_agent_id == expected_agent_id:
            status = "pass"
            is_correct = True
        else:
            status = "fail"
            is_correct = False
        
        return {
            "question": question,
            "expected_agent_id": expected_agent_id,
            "predicted_agent_id": predicted_agent_id,
            "needs_clarification": needs_clarification,
            "classification_confidence": classification_confidence,
            "classified_intent": classified_intent,
            "rag_category": rag_category,
            "out_of_scope": out_of_scope,
            "processed_query": processed_query,
            "status": status,
            "is_correct": is_correct
        }
    
    except Exception as e:
        return {
            "question": question,
            "expected_agent_id": expected_agent_id,
            "predicted_agent_id": None,
            "needs_clarification": False,
            "classification_confidence": None,
            "classified_intent": None,
            "rag_category": None,
            "out_of_scope": False,
            "processed_query": question,
            "status": "error",
            "is_correct": False,
            "error": str(e)
        }


async def evaluate_batch(test_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Evaluate all test cases."""
    results = []
    
    print(f"Evaluating {len(test_cases)} test cases...")
    print("=" * 80)
    
    for i, test_case in enumerate(test_cases, 1):
        question = test_case['question']
        expected_agent_id = test_case['expected_primary_agent_id']
        
        print(f"\n[{i}/{len(test_cases)}] {question[:60]}...")
        
        result = await evaluate_single_question(question, expected_agent_id)
        result['notes'] = test_case.get('notes', '')
        result['category'] = test_case.get('category', '')
        
        # Print result
        status_emoji = {
            "pass": "✅",
            "fail": "❌",
            "clarification": "⚠️",
            "error": "🔥"
        }
        emoji = status_emoji.get(result['status'], "❓")
        
        if result['status'] == 'pass':
            print(f"  {emoji} PASS - {result['predicted_agent_id']}")
        elif result['status'] == 'fail':
            print(f"  {emoji} FAIL - Expected: {expected_agent_id}, Got: {result['predicted_agent_id']}")
        elif result['status'] == 'clarification':
            print(f"  {emoji} CLARIFICATION - {result.get('classified_intent', 'unknown')}")
        else:
            print(f"  {emoji} ERROR - {result.get('error', 'unknown')}")
        
        if result.get('classification_confidence'):
            print(f"     Confidence: {result['classification_confidence']:.2f}")
        
        results.append(result)
    
    return results


def calculate_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate accuracy, precision, recall, and other metrics."""
    # Filter out clarifications and errors for accuracy calculation
    evaluated_results = [r for r in results if r['is_correct'] is not None]
    
    total = len(evaluated_results)
    correct = sum(1 for r in evaluated_results if r['is_correct'])
    
    accuracy = correct / total if total > 0 else 0
    
    clarification_count = sum(1 for r in results if r['status'] == 'clarification')
    clarification_rate = clarification_count / len(results) if results else 0
    
    error_count = sum(1 for r in results if r['status'] == 'error')
    
    # Calculate per-agent precision and recall
    agent_stats = defaultdict(lambda: {'tp': 0, 'fp': 0, 'fn': 0})
    
    for r in evaluated_results:
        expected = r['expected_agent_id']
        predicted = r['predicted_agent_id']
        
        if expected == predicted:
            agent_stats[expected]['tp'] += 1
        else:
            agent_stats[expected]['fn'] += 1
            if predicted:
                agent_stats[predicted]['fp'] += 1
    
    per_agent_metrics = {}
    for agent, stats in agent_stats.items():
        tp = stats['tp']
        fp = stats['fp']
        fn = stats['fn']
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        per_agent_metrics[agent] = {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'support': tp + fn
        }
    
    # Calculate confusion pairs
    confusion_pairs = Counter()
    for r in evaluated_results:
        if not r['is_correct']:
            pair = (r['expected_agent_id'], r['predicted_agent_id'])
            confusion_pairs[pair] += 1
    
    return {
        'total_cases': len(results),
        'evaluated_cases': total,
        'correct': correct,
        'accuracy': accuracy,
        'clarification_count': clarification_count,
        'clarification_rate': clarification_rate,
        'error_count': error_count,
        'per_agent_metrics': per_agent_metrics,
        'confusion_pairs': confusion_pairs.most_common(20)
    }


def save_results(results: List[Dict[str, Any]], metrics: Dict[str, Any], output_dir: Path):
    """Save results to CSV and JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save detailed results as CSV
    csv_path = output_dir / "eval_results.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = [
            'question', 'expected_agent_id', 'predicted_agent_id', 'status',
            'classification_confidence', 'classified_intent', 'rag_category',
            'out_of_scope', 'needs_clarification', 'notes', 'category'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for r in results:
            writer.writerow({
                'question': r['question'],
                'expected_agent_id': r['expected_agent_id'],
                'predicted_agent_id': r.get('predicted_agent_id', ''),
                'status': r['status'],
                'classification_confidence': r.get('classification_confidence', ''),
                'classified_intent': r.get('classified_intent', ''),
                'rag_category': r.get('rag_category', ''),
                'out_of_scope': r.get('out_of_scope', False),
                'needs_clarification': r.get('needs_clarification', False),
                'notes': r.get('notes', ''),
                'category': r.get('category', '')
            })
    
    print(f"\n✅ Saved detailed results to: {csv_path}")
    
    # Save full results as JSON
    json_path = output_dir / "eval_results.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'results': results,
            'metrics': {
                **metrics,
                'confusion_pairs': [
                    {'expected': pair[0], 'predicted': pair[1], 'count': count}
                    for (pair, count) in metrics['confusion_pairs']
                ],
                'per_agent_metrics': {
                    agent: {k: float(v) if isinstance(v, (int, float)) else v for k, v in stats.items()}
                    for agent, stats in metrics['per_agent_metrics'].items()
                }
            }
        }, f, indent=2)
    
    print(f"✅ Saved JSON results to: {json_path}")


def save_hard_negatives(results: List[Dict[str, Any]], output_dir: Path):
    """Save hard negatives (failures and clarifications) for training."""
    hard_negatives = []
    
    for r in results:
        if r['status'] in ['fail', 'clarification']:
            hard_negative = {
                'question': r['question'],
                'expected_primary_agent_id': r['expected_agent_id'],
                'predicted_primary_agent_id': r.get('predicted_agent_id') or 'clarification',
                'router_category': r.get('rag_category', ''),
                'confidence': r.get('classification_confidence'),
                'suggested_label': r.get('classified_intent', ''),
                'notes': r.get('notes', ''),
                'status': r['status']
            }
            hard_negatives.append(hard_negative)
    
    if hard_negatives:
        jsonl_path = output_dir / "hard_negatives.jsonl"
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for hn in hard_negatives:
                f.write(json.dumps(hn) + '\n')
        
        print(f"✅ Saved {len(hard_negatives)} hard negatives to: {jsonl_path}")
    else:
        print("✅ No hard negatives found (perfect accuracy!)")


def print_summary(metrics: Dict[str, Any]):
    """Print evaluation summary."""
    print("\n" + "=" * 80)
    print("EVALUATION SUMMARY")
    print("=" * 80)
    
    print(f"\nTotal test cases: {metrics['total_cases']}")
    print(f"Evaluated (excluding clarifications): {metrics['evaluated_cases']}")
    print(f"Correct: {metrics['correct']}")
    print(f"Accuracy: {metrics['accuracy']:.1%}")
    print(f"Clarifications: {metrics['clarification_count']} ({metrics['clarification_rate']:.1%})")
    print(f"Errors: {metrics['error_count']}")
    
    print("\n" + "-" * 80)
    print("PER-AGENT METRICS")
    print("-" * 80)
    print(f"{'Agent':<25} {'Precision':<12} {'Recall':<12} {'F1':<12} {'Support':<10}")
    print("-" * 80)
    
    for agent, stats in sorted(metrics['per_agent_metrics'].items()):
        print(f"{agent:<25} {stats['precision']:<12.1%} {stats['recall']:<12.1%} "
              f"{stats['f1']:<12.1%} {stats['support']:<10}")
    
    if metrics['confusion_pairs']:
        print("\n" + "-" * 80)
        print("TOP 20 CONFUSION PAIRS")
        print("-" * 80)
        print(f"{'Expected':<25} {'Predicted':<25} {'Count':<10}")
        print("-" * 80)
        
        for (expected, predicted), count in metrics['confusion_pairs']:
            print(f"{expected:<25} {predicted:<25} {count:<10}")


async def main():
    """Main evaluation function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch evaluation of routing classification')
    parser.add_argument('input_file', help='Path to test data file (CSV or JSONL)')
    parser.add_argument('--output-dir', default='eval_results', help='Output directory for results')
    
    args = parser.parse_args()
    
    # Load test data
    print(f"Loading test data from: {args.input_file}")
    test_cases = load_test_data(args.input_file)
    print(f"Loaded {len(test_cases)} test cases")
    
    # Run evaluation
    results = await evaluate_batch(test_cases)
    
    # Calculate metrics
    metrics = calculate_metrics(results)
    
    # Save results
    output_dir = Path(args.output_dir)
    save_results(results, metrics, output_dir)
    save_hard_negatives(results, output_dir)
    
    # Print summary
    print_summary(metrics)
    
    print("\n" + "=" * 80)
    print("Evaluation complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
