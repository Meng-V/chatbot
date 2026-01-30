#!/usr/bin/env python3
"""
Ingest Oxford LibGuides Policy Pages

Fetches authoritative Oxford circulation/borrowing policy pages from LibGuides,
parses content, generates semantic chunks and atomic fact cards, then saves to JSONL.

Usage:
    python -m scripts.ingest_libguides_policies_oxford
"""

import os
import sys
import json
import hashlib
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment
repo_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=repo_root / ".env")

# Oxford LibGuides URLs (authoritative sources)
OXFORD_POLICY_URLS = [
    "https://libguides.lib.miamioh.edu/mul-circulation-policies",
    "https://libguides.lib.miamioh.edu/mul-circulation-policies/loan-periods-fines",
    "https://libguides.lib.miamioh.edu/mul-circulation-policies/loan-periods-ohiolink-ill",
    "https://libguides.lib.miamioh.edu/mul-circulation-policies/recall-request",
    "https://libguides.lib.miamioh.edu/c.php?g=1009317&p=7311851",
    "https://libguides.lib.miamioh.edu/reserves-textbooks",
    "https://libguides.lib.miamioh.edu/c.php?g=1009317&p=7311853",
    "https://libguides.lib.miamioh.edu/reserves-textbooks/coursematerial",
    "https://libguides.lib.miamioh.edu/c.php?g=900679&p=6824859",
    "https://libguides.lib.miamioh.edu/reserves-textbooks/facultyadditional",
    "https://libguides.lib.miamioh.edu/reserves-textbooks/StreamingVideoAndRemoteInstruction",
    "https://libguides.lib.miamioh.edu/reserves-textbooks/electronicreserves",
]


def get_topic_from_url(url: str) -> str:
    """Extract topic from URL pattern."""
    if "loan-periods-fines" in url:
        return "loan_periods"
    elif "loan-periods-ohiolink-ill" in url or "ohiolink" in url.lower():
        return "ohiolink_ill"
    elif "recall-request" in url:
        return "recall_request"
    elif "reserves-textbooks/coursematerial" in url:
        return "course_materials"
    elif "StreamingVideoAndRemoteInstruction" in url:
        return "streaming_video"
    elif "electronicreserves" in url:
        return "electronic_reserves"
    elif "reserves-textbooks" in url:
        return "reserves_textbooks"
    elif "mul-circulation-policies" in url or "circulation" in url:
        return "circulation_policies"
    else:
        return "library_policies"


async def fetch_page(url: str) -> Optional[str]:
    """Fetch HTML content from URL."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as e:
        print(f"⚠️  Error fetching {url}: {str(e)}")
        return None


def parse_libguides_content(html: str, url: str) -> Dict[str, Any]:
    """Parse LibGuides HTML and extract main content."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Get page title
    title_elem = soup.find('h1') or soup.find('title')
    title = title_elem.get_text(strip=True) if title_elem else "Policy Page"
    
    # Remove navigation, sidebars, footers
    for element in soup.find_all(['nav', 'footer', 'aside', 'script', 'style']):
        element.decompose()
    
    # Remove SpringShare elements
    for cls in ['s-lib-header', 's-lib-footer', 's-lib-side-borders', 's-lib-box-std']:
        for element in soup.find_all(class_=cls):
            element.decompose()
    
    # Extract main content area
    content_area = (
        soup.find('div', class_='s-lib-main') or
        soup.find('div', id='s-lg-guide-main') or
        soup.find('main') or
        soup.find('article') or
        soup.body
    )
    
    if not content_area:
        return {"title": title, "sections": [], "tables": []}
    
    # Extract sections by headings
    sections = []
    current_section = {"heading": title, "level": 1, "content": ""}
    
    for element in content_area.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'table']):
        if element.name in ['h1', 'h2', 'h3', 'h4']:
            if current_section["content"].strip():
                sections.append(current_section.copy())
            level = int(element.name[1])
            current_section = {
                "heading": element.get_text(strip=True),
                "level": level,
                "content": ""
            }
        elif element.name == 'table':
            # Store table separately for fact extraction
            continue
        else:
            text = element.get_text(separator=' ', strip=True)
            if text:
                current_section["content"] += text + "\n\n"
    
    if current_section["content"].strip():
        sections.append(current_section)
    
    # Extract tables for structured data
    tables = []
    for table in content_area.find_all('table'):
        rows = []
        for tr in table.find_all('tr'):
            cells = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
            if cells and any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)
    
    return {
        "title": title,
        "sections": sections,
        "tables": tables
    }


def create_chunks(parsed_data: Dict[str, Any], url: str, topic: str) -> List[Dict[str, Any]]:
    """Create semantic chunks from parsed content."""
    chunks = []
    chunk_id_counter = 0
    
    for section in parsed_data["sections"]:
        heading = section["heading"]
        content = section["content"].strip()
        
        if not content:
            continue
        
        # Split into smaller chunks if too long (aim for 300-700 tokens, ~400-900 chars)
        max_chunk_size = 900
        if len(content) <= max_chunk_size:
            # Single chunk
            chunk_text = f"{heading}\n\n{content}"
            chunk_id = hashlib.sha256(f"{url}|{chunk_id_counter}".encode()).hexdigest()[:16]
            chunks.append({
                "id": chunk_id,
                "canonical_url": url,
                "source_url": url,
                "title": parsed_data["title"],
                "section_path": heading,
                "campus_scope": "oxford",
                "topic": topic,
                "audience": "students",  # Default, could be enhanced
                "keywords": extract_keywords(heading, content),
                "chunk_text": chunk_text
            })
            chunk_id_counter += 1
        else:
            # Split by paragraphs with overlap
            paragraphs = content.split('\n\n')
            current_chunk = heading + "\n\n"
            
            for para in paragraphs:
                if len(current_chunk) + len(para) > max_chunk_size and len(current_chunk) > len(heading) + 10:
                    # Save current chunk
                    chunk_id = hashlib.sha256(f"{url}|{chunk_id_counter}".encode()).hexdigest()[:16]
                    chunks.append({
                        "id": chunk_id,
                        "canonical_url": url,
                        "source_url": url,
                        "title": parsed_data["title"],
                        "section_path": heading,
                        "campus_scope": "oxford",
                        "topic": topic,
                        "audience": "students",
                        "keywords": extract_keywords(heading, current_chunk),
                        "chunk_text": current_chunk.strip()
                    })
                    chunk_id_counter += 1
                    # Start new chunk with overlap (keep heading and last sentence)
                    current_chunk = heading + "\n\n"
                
                current_chunk += para + "\n\n"
            
            # Save final chunk
            if len(current_chunk) > len(heading) + 10:
                chunk_id = hashlib.sha256(f"{url}|{chunk_id_counter}".encode()).hexdigest()[:16]
                chunks.append({
                    "id": chunk_id,
                    "canonical_url": url,
                    "source_url": url,
                    "title": parsed_data["title"],
                    "section_path": heading,
                    "campus_scope": "oxford",
                    "topic": topic,
                    "audience": "students",
                    "keywords": extract_keywords(heading, current_chunk),
                    "chunk_text": current_chunk.strip()
                })
    
    return chunks


def extract_keywords(heading: str, content: str) -> List[str]:
    """Extract keywords from heading and content."""
    keywords = set()
    text = (heading + " " + content).lower()
    
    # Common policy keywords
    policy_terms = [
        "loan", "borrow", "checkout", "renew", "renewal", "fine", "fee", "overdue",
        "recall", "request", "hold", "reserve", "ill", "interlibrary", "ohiolink",
        "delivery", "mail", "course", "textbook", "streaming", "video", "electronic"
    ]
    
    for term in policy_terms:
        if term in text:
            keywords.add(term)
    
    return sorted(list(keywords))


def generate_fact_cards(parsed_data: Dict[str, Any], url: str, topic: str) -> List[Dict[str, Any]]:
    """Generate atomic Q/A fact cards from parsed content."""
    facts = []
    
    # Extract facts from tables (loan periods, fines, etc.)
    for table_idx, table in enumerate(parsed_data["tables"]):
        if len(table) < 2:
            continue
        
        headers = table[0]
        for row_idx, row in enumerate(table[1:], 1):
            if len(row) != len(headers):
                continue
            
            # Create fact from table row
            fact_id = hashlib.sha256(f"{url}|table_{table_idx}_row_{row_idx}".encode()).hexdigest()[:16]
            
            # Determine fact type
            fact_type = "loan_period" if "loan" in topic or "period" in ' '.join(headers).lower() else "circulation_policy"
            if "fine" in ' '.join(headers).lower() or "fee" in ' '.join(headers).lower():
                fact_type = "fine_fee"
            
            # Generate question patterns
            question_patterns = generate_question_patterns_from_table(headers, row, topic)
            
            # Generate answer from row data
            answer = generate_answer_from_table(headers, row)
            
            facts.append({
                "id": fact_id,
                "campus_scope": "oxford",
                "fact_type": fact_type,
                "question_patterns": question_patterns,
                "answer": answer,
                "canonical_url": url,
                "source_url": url,
                "anchor_hint": f"table_{table_idx}",
                "tags": extract_keywords(' '.join(headers), ' '.join(row))
            })
    
    # Extract facts from sections (for non-tabular content)
    for section in parsed_data["sections"]:
        heading = section["heading"]
        content = section["content"]
        
        # Skip if too short
        if len(content) < 50:
            continue
        
        # Generate fact for key sections
        if any(kw in heading.lower() for kw in ["how to", "steps", "process", "request", "recall"]):
            fact_id = hashlib.sha256(f"{url}|section_{heading}".encode()).hexdigest()[:16]
            question_patterns = generate_question_patterns_from_section(heading, content, topic)
            answer = content[:300].strip() + ("..." if len(content) > 300 else "")
            
            facts.append({
                "id": fact_id,
                "campus_scope": "oxford",
                "fact_type": infer_fact_type(topic, heading),
                "question_patterns": question_patterns,
                "answer": answer,
                "canonical_url": url,
                "source_url": url,
                "anchor_hint": heading.lower().replace(' ', '-')[:50],
                "tags": extract_keywords(heading, content)
            })
    
    return facts


def generate_question_patterns_from_table(headers: List[str], row: List[str], topic: str) -> List[str]:
    """Generate question patterns from table row."""
    patterns = []
    
    # Assume first column is the item type (e.g., "Books", "DVDs")
    if len(row) > 0:
        item_type = row[0]
        
        # Loan period questions
        if len(headers) > 1 and "loan" in headers[1].lower():
            patterns.extend([
                f"how long can I borrow {item_type.lower()}",
                f"what is the loan period for {item_type.lower()}",
                f"{item_type.lower()} loan period",
                f"how many days can I keep {item_type.lower()}",
                f"checkout period for {item_type.lower()}",
            ])
        
        # Fine questions
        if len(headers) > 2 and "fine" in headers[2].lower():
            patterns.extend([
                f"what are the fines for {item_type.lower()}",
                f"{item_type.lower()} overdue fines",
                f"late fees for {item_type.lower()}",
                f"how much is the fine for {item_type.lower()}",
            ])
        
        # Renewal questions
        if any("renew" in h.lower() for h in headers):
            patterns.extend([
                f"can I renew {item_type.lower()}",
                f"how to renew {item_type.lower()}",
                f"{item_type.lower()} renewal",
                f"renewing {item_type.lower()}",
            ])
    
    return patterns[:15]  # Limit to 15 patterns


def generate_question_patterns_from_section(heading: str, content: str, topic: str) -> List[str]:
    """Generate question patterns from section content."""
    patterns = [
        heading.lower(),
        f"how to {heading.lower()}",
        f"what is {heading.lower()}",
    ]
    
    # Topic-specific patterns
    if "recall" in heading.lower():
        patterns.extend([
            "how do I recall a book",
            "what is a recall",
            "book recall process",
            "recall vs request",
            "how does recall work",
        ])
    elif "request" in heading.lower():
        patterns.extend([
            "how do I request a book",
            "book request process",
            "requesting library materials",
            "how to place a hold",
        ])
    elif "ohiolink" in heading.lower() or "ill" in heading.lower():
        patterns.extend([
            "ohiolink loan period",
            "interlibrary loan",
            "ill borrowing",
            "how long can I keep ohiolink books",
        ])
    elif "reserve" in heading.lower():
        patterns.extend([
            "course reserves",
            "textbook reserves",
            "how to access course materials",
            "reserve materials",
        ])
    elif "streaming" in heading.lower():
        patterns.extend([
            "streaming video for class",
            "video for my course",
            "how to stream course videos",
        ])
    
    return patterns[:20]


def generate_answer_from_table(headers: List[str], row: List[str]) -> str:
    """Generate natural language answer from table row."""
    if len(row) < 2:
        return ' '.join(row)
    
    item_type = row[0]
    parts = [f"{item_type}:"]
    
    for i, header in enumerate(headers[1:], 1):
        if i < len(row) and row[i]:
            parts.append(f"{header}: {row[i]}")
    
    return ' '.join(parts)


def infer_fact_type(topic: str, heading: str) -> str:
    """Infer fact type from topic and heading."""
    text = (topic + " " + heading).lower()
    
    if "fine" in text or "fee" in text:
        return "fine_fee"
    elif "renew" in text:
        return "renewal"
    elif "recall" in text:
        return "recall"
    elif "request" in text or "hold" in text:
        return "request"
    elif "ohiolink" in text:
        return "ohiolink"
    elif "ill" in text or "interlibrary" in text:
        return "ill"
    elif "reserve" in text:
        return "reserves"
    elif "streaming" in text or "video" in text:
        return "streaming"
    elif "electronic" in text:
        return "e_reserves"
    else:
        return "loan_period"


async def main():
    """Main ingestion pipeline."""
    print("=" * 80)
    print("Oxford LibGuides Policy Ingestion")
    print("=" * 80)
    print(f"📄 Processing {len(OXFORD_POLICY_URLS)} policy pages...\n")
    
    all_chunks = []
    all_facts = []
    
    for idx, url in enumerate(OXFORD_POLICY_URLS, 1):
        print(f"[{idx}/{len(OXFORD_POLICY_URLS)}] Fetching: {url}")
        
        html = await fetch_page(url)
        if not html:
            print(f"   ❌ Failed to fetch")
            continue
        
        topic = get_topic_from_url(url)
        print(f"   📌 Topic: {topic}")
        
        parsed = parse_libguides_content(html, url)
        print(f"   📝 Title: {parsed['title']}")
        print(f"   📊 Sections: {len(parsed['sections'])}, Tables: {len(parsed['tables'])}")
        
        chunks = create_chunks(parsed, url, topic)
        facts = generate_fact_cards(parsed, url, topic)
        
        all_chunks.extend(chunks)
        all_facts.extend(facts)
        
        print(f"   ✅ Generated {len(chunks)} chunks, {len(facts)} fact cards\n")
        
        # Be polite to server
        await asyncio.sleep(0.5)
    
    # Save outputs
    output_dir = repo_root / "ai-core" / "data" / "policies"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    chunks_file = output_dir / "circulation_policies_oxford_chunks.jsonl"
    facts_file = output_dir / "circulation_policies_oxford_facts.jsonl"
    
    print("=" * 80)
    print("💾 Saving outputs...")
    
    with open(chunks_file, 'w', encoding='utf-8') as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
    print(f"✅ Chunks: {chunks_file} ({len(all_chunks)} items)")
    
    with open(facts_file, 'w', encoding='utf-8') as f:
        for fact in all_facts:
            f.write(json.dumps(fact, ensure_ascii=False) + '\n')
    print(f"✅ Facts: {facts_file} ({len(all_facts)} items)")
    
    print("\n" + "=" * 80)
    print("🎉 Ingestion complete!")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Review generated JSONL files")
    print("2. Run: python -m scripts.upsert_policies_to_weaviate")
    print("3. Test policy queries")


if __name__ == "__main__":
    asyncio.run(main())
