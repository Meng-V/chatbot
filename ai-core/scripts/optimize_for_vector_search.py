#!/usr/bin/env python3
"""
Optimize RAG Data for Vector Search

This script processes Q&A pairs to make them more suitable for vector-based semantic search:
1. Generalizes questions to be more abstract and broadly applicable
2. Enhances answers to be comprehensive and objective
3. Merges similar questions with the best answer
4. Optimizes keywords and topics for better retrieval
5. Removes unnecessary metadata

Usage:
    python3 scripts/optimize_for_vector_search.py \\
        --input data/final_filtered.json \\
        --output data/optimized_for_weaviate.json
"""

import json
import os
import asyncio
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple
from collections import defaultdict
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Load environment
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# Use o4-mini model (no temperature parameter)
llm = ChatOpenAI(model="o4-mini", api_key=OPENAI_API_KEY)


GENERALIZATION_PROMPT = """You are an expert librarian and knowledge engineer. Your task is to transform specific Q&A pairs into more general, reusable knowledge that works well in a vector search system.

OBJECTIVE: Make questions more abstract and answers more comprehensive, while maintaining accuracy.

INPUT Q&A:
Question: {question}
Answer: {answer}

YOUR TASK:
1. GENERALIZE THE QUESTION:
   - Remove specific details (names, dates, specific book titles)
   - Make it applicable to broader scenarios
   - Keep the core intent
   - Example: "Is the book 'ABC' available?" → "How can I check if a specific book is available in the library?"

2. ENHANCE THE ANSWER:
   - Make it comprehensive and step-by-step if applicable
   - Include general principles, not just specific cases
   - Remove outdated temporal references
   - Keep it objective and professional
   - Add context that helps understanding

3. EXTRACT KEY CONCEPTS:
   - Identify 5-7 important keywords
   - Focus on concepts, not specific instances

4. CLASSIFY TOPIC:
   - Choose from: discovery_search, policy_or_service, technical_help, general_question, research_help

OUTPUT FORMAT (JSON):
{{
  "generalized_question": "...",
  "enhanced_answer": "...",
  "keywords": ["keyword1", "keyword2", ...],
  "topic": "topic_name"
}}

IMPORTANT:
- Be concise but complete
- Focus on reusability
- Maintain factual accuracy
- Use clear, professional language

Return ONLY the JSON, no additional text.
"""


async def generalize_qa_with_ai(question: str, answer: str, batch_delay: float = 0.1) -> Dict[str, Any]:
    """
    Use AI to generalize a Q&A pair for better vector search performance.
    """
    try:
        prompt = GENERALIZATION_PROMPT.format(question=question, answer=answer)
        response = await llm.ainvoke(prompt)
        result = json.loads(response.content)
        
        # Validate result
        if not all(k in result for k in ['generalized_question', 'enhanced_answer', 'keywords', 'topic']):
            raise ValueError("Missing required fields in AI response")
        
        await asyncio.sleep(batch_delay)  # Rate limiting
        return result
    
    except Exception as e:
        print(f"⚠️  AI generalization failed: {e}")
        # Fallback: return original data
        return {
            "generalized_question": question,
            "enhanced_answer": answer,
            "keywords": [],
            "topic": "general_question"
        }


def cluster_similar_questions(qa_pairs: List[Dict], similarity_threshold: float = 0.80) -> List[List[int]]:
    """
    Cluster similar questions using TF-IDF and cosine similarity.
    Returns list of clusters (each cluster is a list of indices).
    """
    questions = [qa.get('generalized_question', qa.get('question', '')) for qa in qa_pairs]
    
    # TF-IDF vectorization
    vectorizer = TfidfVectorizer(max_features=500, stop_words='english', ngram_range=(1, 2))
    tfidf_matrix = vectorizer.fit_transform(questions)
    
    # Compute similarity
    similarity_matrix = cosine_similarity(tfidf_matrix)
    
    # Cluster using threshold
    visited = set()
    clusters = []
    
    for i in range(len(qa_pairs)):
        if i in visited:
            continue
        
        # Find all similar items
        cluster = [i]
        visited.add(i)
        
        for j in range(i + 1, len(qa_pairs)):
            if j not in visited and similarity_matrix[i][j] >= similarity_threshold:
                cluster.append(j)
                visited.add(j)
        
        clusters.append(cluster)
    
    return clusters


def select_best_from_cluster(qa_pairs: List[Dict], cluster_indices: List[int]) -> Dict[str, Any]:
    """
    Select the best Q&A from a cluster, or merge them intelligently.
    """
    if len(cluster_indices) == 1:
        return qa_pairs[cluster_indices[0]]
    
    # Get all Q&As in cluster
    cluster_qas = [qa_pairs[i] for i in cluster_indices]
    
    # Score based on confidence and answer length
    def score_qa(qa):
        confidence = qa.get('confidence_score', 0.5)
        answer_len = len(qa.get('enhanced_answer', qa.get('answer', '')))
        # Prefer longer, more detailed answers (but not too long)
        optimal_length = 400
        length_score = 1.0 - abs(answer_len - optimal_length) / optimal_length
        length_score = max(0, min(1, length_score))
        
        return confidence * 0.6 + length_score * 0.4
    
    # Select best
    best_qa = max(cluster_qas, key=score_qa)
    
    # Merge keywords from all items
    all_keywords = set()
    for qa in cluster_qas:
        all_keywords.update(qa.get('keywords', []))
    
    best_qa['keywords'] = list(all_keywords)[:10]  # Keep top 10
    
    return best_qa


async def optimize_dataset(
    input_file: str,
    output_file: str,
    similarity_threshold: float = 0.80,
    batch_size: int = 10
):
    """
    Main optimization pipeline.
    """
    print("="*70)
    print("🚀 Optimizing RAG Dataset for Vector Search")
    print("="*70)
    
    # Load data
    print(f"\n📂 Loading data from: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        qa_pairs = json.load(f)
    print(f"   Loaded: {len(qa_pairs)} Q&A pairs")
    
    # Step 1: AI Generalization
    print(f"\n{'='*70}")
    print("📍 Step 1: AI-Powered Generalization")
    print(f"{'='*70}")
    print(f"Using o4-mini model to generalize questions and enhance answers")
    print(f"Batch size: {batch_size}")
    print(f"Estimated time: {len(qa_pairs) / (batch_size * 6):.0f}-{len(qa_pairs) / (batch_size * 4):.0f} minutes\n")
    
    optimized_pairs = []
    for i in range(0, len(qa_pairs), batch_size):
        batch = qa_pairs[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1}/{(len(qa_pairs)-1)//batch_size + 1} ({i+1}-{min(i+batch_size, len(qa_pairs))}/{len(qa_pairs)})...")
        
        tasks = [
            generalize_qa_with_ai(
                qa.get('question', ''),
                qa.get('answer', '')
            )
            for qa in batch
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Merge with original data
        for qa, result in zip(batch, results):
            optimized_qa = {
                'question': result['generalized_question'],
                'answer': result['enhanced_answer'],
                'keywords': result.get('keywords', qa.get('keywords', [])),
                'topic': result.get('topic', qa.get('topic', 'general_question')),
                'confidence_score': qa.get('confidence_score', 0.8)  # Keep for merging
            }
            optimized_pairs.append(optimized_qa)
    
    print(f"✅ Generalization complete: {len(optimized_pairs)} items")
    
    # Step 2: Cluster and Merge Similar Questions
    print(f"\n{'='*70}")
    print("📍 Step 2: Clustering and Merging Similar Questions")
    print(f"{'='*70}")
    print(f"Similarity threshold: {similarity_threshold}")
    
    clusters = cluster_similar_questions(optimized_pairs, similarity_threshold)
    
    print(f"   Found {len(clusters)} unique question clusters")
    print(f"   Merged: {len(optimized_pairs) - len(clusters)} duplicate questions")
    
    # Select best from each cluster
    final_pairs = []
    for cluster in clusters:
        best_qa = select_best_from_cluster(optimized_pairs, cluster)
        # Remove confidence_score (not needed in final data)
        best_qa.pop('confidence_score', None)
        final_pairs.append(best_qa)
    
    # Step 3: Final Statistics
    print(f"\n{'='*70}")
    print("📊 Final Dataset Statistics")
    print(f"{'='*70}")
    
    print(f"\nData Reduction:")
    print(f"   Original: {len(qa_pairs)}")
    print(f"   After merging: {len(final_pairs)}")
    print(f"   Reduction: {len(qa_pairs) - len(final_pairs)} ({(len(qa_pairs) - len(final_pairs))/len(qa_pairs)*100:.1f}%)")
    
    # Topic distribution
    topic_counts = defaultdict(int)
    for qa in final_pairs:
        topic_counts[qa['topic']] += 1
    
    print(f"\nTopic Distribution:")
    for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"   - {topic}: {count} ({count/len(final_pairs)*100:.1f}%)")
    
    # Save optimized data
    print(f"\n💾 Saving optimized data...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_pairs, f, indent=2, ensure_ascii=False)
    
    file_size = Path(output_file).stat().st_size / 1024 / 1024
    print(f"✅ Saved to: {output_file}")
    print(f"   Count: {len(final_pairs)} items")
    print(f"   Size: {file_size:.2f}MB")
    
    print(f"\n{'='*70}")
    print("✨ Optimization Complete!")
    print(f"{'='*70}")
    print(f"\nNext Steps:")
    print(f"1. Review the optimized data: {output_file}")
    print(f"2. Ingest into Weaviate:")
    print(f"   python3 scripts/ingest_transcripts_optimized.py")
    
    return final_pairs


def main():
    parser = argparse.ArgumentParser(
        description='Optimize RAG data for vector search',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--input', default='data/final_filtered.json',
                        help='Input JSON file (default: data/final_filtered.json)')
    parser.add_argument('--output', default='data/optimized_for_weaviate.json',
                        help='Output JSON file (default: data/optimized_for_weaviate.json)')
    parser.add_argument('--similarity-threshold', type=float, default=0.80,
                        help='Similarity threshold for merging questions (default: 0.80)')
    parser.add_argument('--batch-size', type=int, default=10,
                        help='AI processing batch size (default: 10)')
    
    args = parser.parse_args()
    
    # Validate input file
    if not Path(args.input).exists():
        print(f"❌ Error: Input file not found: {args.input}")
        return
    
    # Run optimization
    asyncio.run(optimize_dataset(
        input_file=args.input,
        output_file=args.output,
        similarity_threshold=args.similarity_threshold,
        batch_size=args.batch_size
    ))


if __name__ == '__main__':
    main()
