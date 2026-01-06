"""
Routing Evaluation Script

Evaluates routing accuracy on a test set of queries.
Outputs:
- Hit rate per agent
- Confusion matrix
- Margin distribution analysis
- Recommended threshold adjustments

Usage:
    python scripts/evaluate_routing.py [--test-file path/to/test.json]
"""

import asyncio
import sys
import json
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "ai-core"))

from src.router.router_subgraph import route_query
from src.utils.logger import AgentLogger


# ============================================================================
# TEST CASES - Critical edge cases
# ============================================================================

TEST_CASES = [
    # ========================================================================
    # CRITICAL: Computer problems (should NOT go to equipment_checkout)
    # ========================================================================
    {
        "query": "who can I talk to for my computer problems",
        "expected_agent": "libchat_handoff",  # or clarify
        "expected_mode": "clarify",  # Should trigger clarification
        "description": "Entry-ambiguous computer problem (no action verb)"
    },
    {
        "query": "my computer is not working",
        "expected_agent": "out_of_scope",
        "expected_mode": "heuristic",
        "description": "Tech support (out of scope)"
    },
    {
        "query": "I need help with my computer",
        "expected_agent": "out_of_scope",
        "expected_mode": "clarify",  # Could be tech support or equipment
        "description": "Ambiguous computer help"
    },
    
    # ========================================================================
    # Equipment checkout (MUST have action verbs)
    # ========================================================================
    {
        "query": "can I borrow a laptop",
        "expected_agent": "equipment_checkout",
        "expected_mode": "vector",
        "description": "Clear equipment checkout with action verb"
    },
    {
        "query": "how do I check out a Chromebook",
        "expected_agent": "equipment_checkout",
        "expected_mode": "vector",
        "description": "Equipment checkout with action verb"
    },
    {
        "query": "I want to rent a camera",
        "expected_agent": "equipment_checkout",
        "expected_mode": "vector",
        "description": "Equipment checkout with action verb"
    },
    
    # ========================================================================
    # Library hours
    # ========================================================================
    {
        "query": "what time does King Library close",
        "expected_agent": "libcal_hours",
        "expected_mode": "heuristic",
        "description": "Clear hours query"
    },
    {
        "query": "library hours tomorrow",
        "expected_agent": "libcal_hours",
        "expected_mode": "vector",
        "description": "Hours query"
    },
    
    # ========================================================================
    # Subject librarian
    # ========================================================================
    {
        "query": "who is the biology librarian",
        "expected_agent": "subject_librarian",
        "expected_mode": "heuristic",
        "description": "Clear subject librarian query"
    },
    {
        "query": "I need help with psychology research",
        "expected_agent": "subject_librarian",
        "expected_mode": "vector",
        "description": "Subject-based research help"
    },
    
    # ========================================================================
    # Human help
    # ========================================================================
    {
        "query": "I want to talk to a librarian",
        "expected_agent": "libchat_handoff",
        "expected_mode": "heuristic",
        "description": "Explicit human help request"
    },
    {
        "query": "can someone help me",
        "expected_agent": "libchat_handoff",
        "expected_mode": "clarify",  # Could be ambiguous
        "description": "General help request"
    },
    
    # ========================================================================
    # Out of scope
    # ========================================================================
    {
        "query": "what's the answer to homework question 5",
        "expected_agent": "out_of_scope",
        "expected_mode": "heuristic",
        "description": "Homework help (out of scope)"
    },
    {
        "query": "my wifi isn't working",
        "expected_agent": "out_of_scope",
        "expected_mode": "heuristic",
        "description": "Tech support (out of scope)"
    },
    
    # ========================================================================
    # VPN / Database access (NOT equipment checkout)
    # ========================================================================
    {
        "query": "I can't access the library databases from home",
        "expected_agent": "google_site",
        "expected_mode": "vector",
        "description": "Database access issue"
    },
    {
        "query": "VPN not working for library resources",
        "expected_agent": "google_site",
        "expected_mode": "vector",
        "description": "VPN/remote access"
    },
    
    # ========================================================================
    # CS coursework (NOT equipment checkout)
    # ========================================================================
    {
        "query": "I need help with my programming assignment",
        "expected_agent": "out_of_scope",
        "expected_mode": "heuristic",
        "description": "Homework help (out of scope)"
    },
]


async def evaluate_routing(test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evaluate routing on test cases.
    
    Returns:
        Dict with evaluation metrics
    """
    print("🧪 Evaluating Routing System")
    print("=" * 80)
    
    results = []
    confusion_matrix = defaultdict(lambda: defaultdict(int))
    mode_distribution = defaultdict(int)
    margin_by_correctness = {"correct": [], "incorrect": []}
    
    for i, test_case in enumerate(test_cases, 1):
        query = test_case["query"]
        expected_agent = test_case["expected_agent"]
        expected_mode = test_case.get("expected_mode", "any")
        description = test_case.get("description", "")
        
        print(f"\n[{i}/{len(test_cases)}] {description}")
        print(f"   Query: \"{query}\"")
        print(f"   Expected: {expected_agent} ({expected_mode})")
        
        logger = AgentLogger()
        
        try:
            result = await route_query(query=query, logger=logger)
            
            actual_mode = result.get("mode")
            mode_distribution[actual_mode] += 1
            
            if actual_mode == "clarify":
                actual_agent = "clarify"
                print(f"   Result: CLARIFY")
                print(f"   Question: {result.get('clarifying_question', '')}")
            else:
                actual_agent = result.get("agent_id")
                confidence = result.get("confidence")
                reason = result.get("reason", "")
                print(f"   Result: {actual_agent} ({confidence}, {actual_mode})")
                if reason:
                    print(f"   Reason: {reason}")
                
                # Track margin if available
                candidates = result.get("candidates", [])
                if len(candidates) >= 2:
                    margin = candidates[0]["score"] - candidates[1]["score"]
                    if actual_agent == expected_agent:
                        margin_by_correctness["correct"].append(margin)
                    else:
                        margin_by_correctness["incorrect"].append(margin)
            
            # Check correctness
            is_correct = False
            if expected_mode == "clarify":
                is_correct = actual_mode == "clarify"
            elif expected_mode == "any":
                is_correct = actual_agent == expected_agent
            else:
                is_correct = (actual_agent == expected_agent and actual_mode == expected_mode)
            
            confusion_matrix[expected_agent][actual_agent] += 1
            
            status = "✅ PASS" if is_correct else "❌ FAIL"
            print(f"   {status}")
            
            results.append({
                "query": query,
                "expected_agent": expected_agent,
                "actual_agent": actual_agent,
                "expected_mode": expected_mode,
                "actual_mode": actual_mode,
                "is_correct": is_correct,
                "description": description,
                "result": result
            })
            
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
            results.append({
                "query": query,
                "expected_agent": expected_agent,
                "actual_agent": "error",
                "is_correct": False,
                "error": str(e)
            })
    
    # Calculate metrics
    print("\n" + "=" * 80)
    print("📊 EVALUATION RESULTS")
    print("=" * 80)
    
    total = len(results)
    correct = sum(1 for r in results if r["is_correct"])
    accuracy = correct / total if total > 0 else 0
    
    print(f"\n✅ Overall Accuracy: {correct}/{total} ({accuracy:.1%})")
    
    # Mode distribution
    print(f"\n📈 Mode Distribution:")
    for mode, count in sorted(mode_distribution.items()):
        pct = count / total * 100
        print(f"   {mode}: {count} ({pct:.1f}%)")
    
    # Per-agent accuracy
    print(f"\n🎯 Per-Agent Accuracy:")
    agent_stats = defaultdict(lambda: {"correct": 0, "total": 0})
    for r in results:
        if r["expected_agent"] != "clarify":
            agent_stats[r["expected_agent"]]["total"] += 1
            if r["is_correct"]:
                agent_stats[r["expected_agent"]]["correct"] += 1
    
    for agent, stats in sorted(agent_stats.items()):
        if stats["total"] > 0:
            acc = stats["correct"] / stats["total"]
            print(f"   {agent}: {stats['correct']}/{stats['total']} ({acc:.1%})")
    
    # Confusion matrix
    print(f"\n🔀 Confusion Matrix:")
    print("   (rows=expected, cols=actual)")
    all_agents = sorted(set(list(confusion_matrix.keys()) + 
                           [a for row in confusion_matrix.values() for a in row.keys()]))
    
    # Header
    print("   " + " " * 25 + " | " + " | ".join(f"{a[:8]:>8}" for a in all_agents))
    print("   " + "-" * 80)
    
    for expected in all_agents:
        row = confusion_matrix[expected]
        counts = [str(row.get(actual, 0)) for actual in all_agents]
        print(f"   {expected:25} | " + " | ".join(f"{c:>8}" for c in counts))
    
    # Margin analysis
    if margin_by_correctness["correct"] or margin_by_correctness["incorrect"]:
        print(f"\n📏 Margin Analysis:")
        if margin_by_correctness["correct"]:
            avg_correct = sum(margin_by_correctness["correct"]) / len(margin_by_correctness["correct"])
            print(f"   Avg margin (correct): {avg_correct:.3f}")
        if margin_by_correctness["incorrect"]:
            avg_incorrect = sum(margin_by_correctness["incorrect"]) / len(margin_by_correctness["incorrect"])
            print(f"   Avg margin (incorrect): {avg_incorrect:.3f}")
    
    # Failed cases
    failed = [r for r in results if not r["is_correct"]]
    if failed:
        print(f"\n❌ Failed Cases ({len(failed)}):")
        for r in failed:
            print(f"   • \"{r['query']}\"")
            print(f"     Expected: {r['expected_agent']}, Got: {r['actual_agent']}")
            print(f"     Description: {r.get('description', '')}")
    
    print("\n" + "=" * 80)
    
    return {
        "accuracy": accuracy,
        "total": total,
        "correct": correct,
        "results": results,
        "confusion_matrix": dict(confusion_matrix),
        "mode_distribution": dict(mode_distribution),
        "margin_analysis": margin_by_correctness
    }


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Evaluate routing accuracy")
    parser.add_argument(
        "--test-file",
        type=str,
        help="Path to JSON file with test cases"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path to save results JSON"
    )
    
    args = parser.parse_args()
    
    # Load test cases
    if args.test_file:
        with open(args.test_file, 'r') as f:
            test_cases = json.load(f)
    else:
        test_cases = TEST_CASES
    
    try:
        results = await evaluate_routing(test_cases)
        
        # Save results if requested
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\n💾 Results saved to: {args.output}")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
