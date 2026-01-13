#!/usr/bin/env python3
"""
Scrape circulation/ILL policy pages from LibGuides and create JSONL for Weaviate import.

This script fetches content from specified LibGuides pages and formats them
for import into a Weaviate collection that provides URL-only responses.
"""

import os
import sys
import json
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv

root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

# Pages to scrape
POLICY_PAGES = [
    "https://libguides.lib.miamioh.edu/circulation-policies/contents",
    "https://libguides.lib.miamioh.edu/circulation-policies/loan-periods-fines",
    "https://libguides.lib.miamioh.edu/circulation-policies/ohiolink-loan-periods-fines",
    "https://libguides.lib.miamioh.edu/circulation-policies/book-recalls-requests",
    "https://libguides.lib.miamioh.edu/circulation-policies/ill-ohiolink",
    "https://libguides.lib.miamioh.edu/reserves-textbooks",
    "https://libguides.lib.miamioh.edu/circulation-policies/affiliated-patrons",
]

OUTPUT_FILE = "ai-core/data/circulation_policies.jsonl"


def generate_id(url: str, chunk_index: int = 0) -> str:
    """Generate deterministic ID from URL and chunk index."""
    combined = f"{url}:{chunk_index}"
    return hashlib.md5(combined.encode()).hexdigest()[:16]


def extract_keywords(text: str, title: str) -> List[str]:
    """Extract keywords for better search matching."""
    keywords = set()
    
    # Common policy-related terms
    policy_terms = [
        "loan", "borrow", "checkout", "due date", "fine", "fee", "charge",
        "overdue", "renewal", "request", "recall", "hold", "reserve",
        "ohiolink", "ill", "interlibrary loan", "affiliated patron",
        "textbook", "course reserve", "replacement", "lost", "damaged"
    ]
    
    text_lower = text.lower()
    title_lower = title.lower()
    
    for term in policy_terms:
        if term in text_lower or term in title_lower:
            keywords.add(term)
    
    return list(keywords)


def chunk_text(text: str, max_length: int = 1000) -> List[str]:
    """Split text into chunks of approximately max_length."""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    sentences = text.split('. ')
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        sentence_length = len(sentence) + 2  # +2 for '. '
        
        if current_length + sentence_length > max_length and current_chunk:
            chunks.append('. '.join(current_chunk) + '.')
            current_chunk = [sentence]
            current_length = sentence_length
        else:
            current_chunk.append(sentence)
            current_length += sentence_length
    
    if current_chunk:
        chunks.append('. '.join(current_chunk) + '.')
    
    return chunks


async def scrape_libguide_page(session: aiohttp.ClientSession, url: str) -> Dict[str, Any]:
    """Scrape a single LibGuides page."""
    print(f"📖 Scraping: {url}")
    
    try:
        async with session.get(url) as response:
            if response.status != 200:
                print(f"  ❌ Failed to fetch (status {response.status})")
                return None
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract title
            title_elem = soup.find('h1') or soup.find('title')
            title = title_elem.get_text(strip=True) if title_elem else url.split('/')[-1]
            
            # Extract main content
            # LibGuides typically uses specific containers
            content_areas = []
            
            # Try common LibGuides content selectors
            for selector in ['.s-lg-box-content', '#s-lg-guide-main', '.guide-content']:
                elements = soup.select(selector)
                if elements:
                    content_areas.extend(elements)
            
            # If no specific containers found, use body
            if not content_areas:
                content_areas = [soup.find('body')]
            
            # Extract text from content areas
            text_parts = []
            headings = []
            
            for area in content_areas:
                if not area:
                    continue
                
                # Extract headings
                for heading in area.find_all(['h1', 'h2', 'h3', 'h4']):
                    heading_text = heading.get_text(strip=True)
                    if heading_text and heading_text not in headings:
                        headings.append(heading_text)
                
                # Extract paragraphs and list items
                for elem in area.find_all(['p', 'li', 'div']):
                    text = elem.get_text(strip=True)
                    if text and len(text) > 20:  # Filter out very short snippets
                        text_parts.append(text)
            
            full_text = ' '.join(text_parts)
            
            # Clean up text
            full_text = ' '.join(full_text.split())  # Normalize whitespace
            
            if len(full_text) < 100:
                print(f"  ⚠️ Very short content extracted ({len(full_text)} chars)")
            
            return {
                'url': url,
                'title': title,
                'headings': headings,
                'text': full_text,
                'keywords': extract_keywords(full_text, title)
            }
    
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


async def scrape_all_pages() -> List[Dict[str, Any]]:
    """Scrape all policy pages."""
    print("="*70)
    print("🌐 LibGuides Policy Pages Scraper")
    print("="*70)
    
    async with aiohttp.ClientSession() as session:
        tasks = [scrape_libguide_page(session, url) for url in POLICY_PAGES]
        results = await asyncio.gather(*tasks)
    
    # Filter out None results
    return [r for r in results if r is not None]


def create_jsonl_records(scraped_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert scraped data to JSONL records."""
    records = []
    build_timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    
    for page_data in scraped_data:
        url = page_data['url']
        title = page_data['title']
        headings = page_data['headings']
        text = page_data['text']
        keywords = page_data['keywords']
        
        # Chunk the text
        chunks = chunk_text(text, max_length=800)
        
        print(f"  📄 {title}: {len(chunks)} chunk(s)")
        
        for idx, chunk in enumerate(chunks):
            record = {
                "id": generate_id(url, idx),
                "final_url": url,
                "canonical_url": url,
                "aliases": [],
                "title": title,
                "headings": headings,
                "summary": chunk[:200] + "..." if len(chunk) > 200 else chunk,
                "chunk_index": idx,
                "chunk_text": chunk,
                "tags": keywords,
                "last_build_utc": build_timestamp,
                "response_mode": "url_only",  # Special flag for URL-only responses
            }
            records.append(record)
    
    return records


def write_jsonl(records: List[Dict[str, Any]], output_path: str):
    """Write records to JSONL file."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record) + '\n')
    
    print(f"\n✅ Wrote {len(records)} records to {output_path}")


async def main():
    """Main execution."""
    # Scrape pages
    scraped_data = await scrape_all_pages()
    
    if not scraped_data:
        print("\n❌ No data scraped. Exiting.")
        sys.exit(1)
    
    print(f"\n📊 Successfully scraped {len(scraped_data)} pages")
    
    # Create JSONL records
    records = create_jsonl_records(scraped_data)
    
    # Write to file
    output_path = root_dir / OUTPUT_FILE
    write_jsonl(records, str(output_path))
    
    print("\n" + "="*70)
    print("📊 Summary")
    print("="*70)
    print(f"Pages scraped: {len(scraped_data)}")
    print(f"Total records: {len(records)}")
    print(f"Output file: {output_path}")
    print("\nNext steps:")
    print("  1. Review the generated JSONL file")
    print("  2. Import into Weaviate:")
    print(f"     python scripts/import_weaviate_jsonl.py --input {OUTPUT_FILE} --collection CirculationPolicies")


if __name__ == "__main__":
    asyncio.run(main())
