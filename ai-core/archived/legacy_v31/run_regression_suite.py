#!/usr/bin/env python3
"""
Run regression test suite against the production routing pipeline.

Reads: test_data/regression_questions.csv
Outputs: test_data/regression_results.jsonl

Environment:
- Set DISABLE_GOOGLE_SITE_SEARCH=1 to avoid external API calls
"""

import os
import sys
import csv
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.orchestrator import library_graph
from src.state import AgentState
from src.utils.logger import AgentLogger


async def run_single_question(question: str, logger: AgentLogger) -> Dict[str, Any]:
    """
    Run a single question through the production routing pipeline.
    
    Returns:
        Dict with routing and response information
    """
    # Initialize state with minimal required fields
    initial_state: AgentState = {
        "user_message": question,
        "messages": [{"role": "user", "content": question}],
        "conversation_history": [],
        "_logger": logger,
    }
    
    try:
        # Invoke production graph
        result = await library_graph.ainvoke(initial_state)
        
        # Extract key routing information
        category = result.get("category")
        primary_agent_id = result.get("primary_agent_id")
        classification_confidence = result.get("classification_confidence")
        needs_clarification = result.get("needs_clarification", False)
        clarifying_question = result.get("clarifying_question")
        
        # Get response snippet (first 200 chars)
        messages = result.get("messages", [])
        response_snippet = ""
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, dict):
                response_snippet = last_msg.get("content", "")[:200]
            else:
                response_snippet = str(last_msg)[:200]
        
        return {
            "question": question,
            "category": category,
            "primary_agent_id": primary_agent_id,
            "classification_confidence": float(classification_confidence) if classification_confidence is not None else None,
            "needs_clarification": needs_clarification,
            "clarification_reason": clarifying_question if needs_clarification else None,
            "response_snippet": response_snippet,
            "status": "success"
        }
        
    except Exception as e:
        return {
            "question": question,
            "category": None,
            "primary_agent_id": None,
            "classification_confidence": None,
            "needs_clarification": None,
            "clarification_reason": None,
            "response_snippet": None,
            "status": "error",
            "error": str(e)
        }


async def main():
    """Main regression suite runner."""
    print("=" * 80)
    print("Running Regression Test Suite")
    print("=" * 80)
    print()
    
    # Ensure Google CSE is disabled
    os.environ["DISABLE_GOOGLE_SITE_SEARCH"] = "1"
    print("🚫 Google Site Search: DISABLED")
    print()
    
    # Define paths
    script_dir = Path(__file__).parent
    input_csv = script_dir.parent / "test_data" / "regression_questions.csv"
    output_jsonl = script_dir.parent / "test_data" / "regression_results.jsonl"
    
    # Check if input exists
    if not input_csv.exists():
        print(f"❌ Error: Input file not found: {input_csv}")
        print("Run build_regression_questions.py first to generate the question set.")
        return 1
    
    # Load questions
    questions: List[str] = []
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            question = row.get('question', '').strip()
            if question:
                questions.append(question)
    
    print(f"📊 Loaded {len(questions)} questions from {input_csv.name}")
    print()
    
    # Process each question
    results = []
    logger = AgentLogger()
    
    for i, question in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {question[:60]}{'...' if len(question) > 60 else ''}")
        
        result = await run_single_question(question, logger)
        results.append(result)
        
        # Show brief status
        status_symbol = "✅" if result["status"] == "success" else "❌"
        agent = result.get("primary_agent_id", "N/A")
        conf = result.get("classification_confidence")
        conf_str = f"{conf:.2f}" if conf is not None else "N/A"
        clarif = "⚠️ CLARIFY" if result.get("needs_clarification") else ""
        
        print(f"  {status_symbol} {agent} (conf: {conf_str}) {clarif}")
        print()
    
    # Write results to JSONL
    output_jsonl.parent.mkdir(exist_ok=True)
    with open(output_jsonl, 'w', encoding='utf-8') as f:
        for result in results:
            f.write(json.dumps(result) + '\n')
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    # Calculate statistics
    total = len(results)
    successful = sum(1 for r in results if r["status"] == "success")
    errors = sum(1 for r in results if r["status"] == "error")
    clarifications = sum(1 for r in results if r.get("needs_clarification"))
    
    # Agent distribution
    agent_counts: Dict[str, int] = {}
    for r in results:
        if r["status"] == "success":
            agent = r.get("primary_agent_id", "unknown")
            agent_counts[agent] = agent_counts.get(agent, 0) + 1
    
    print(f"Total questions: {total}")
    print(f"Successful: {successful}")
    print(f"Errors: {errors}")
    print(f"Clarifications: {clarifications} ({100*clarifications/total:.1f}%)")
    print()
    
    print("Agent Distribution:")
    for agent, count in sorted(agent_counts.items(), key=lambda x: x[1], reverse=True):
        pct = 100 * count / successful
        print(f"  {agent}: {count} ({pct:.1f}%)")
    
    print()
    print(f"✅ Results saved to: {output_jsonl}")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
