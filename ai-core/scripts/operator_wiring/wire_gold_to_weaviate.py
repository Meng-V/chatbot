"""Wire the operator-verified gold set into Weaviate + UrlSeen.

For each gold case with allowed_urls:
  - Create one Weaviate chunk per allowed_url (text = Q + A)
  - chunk_id = "operator-gold-{case_id}-{position}"  (idempotent)
  - document_id = "d-operator-gold-{case_id}"
  - source_url = the allowed_url
  - Other metadata fields from gold case (scope_campus -> campus, etc.)
  - Embed via text-embedding-3-large
  - Insert UrlSeen row (idempotent ON CONFLICT)

Output: counts of (cases processed, chunks upserted, urls added to UrlSeen).

Rollback:
  DELETE FROM "UrlSeen" WHERE source = 'operator_gold_2026-05-22';
  Weaviate: delete by chunk_id prefix "operator-gold-*"
"""
import json, os, sys, asyncio, hashlib
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/Users/qum/Documents/GitHub/chatbot/.claude/worktrees/nice-mcnulty-42183e")
AI_CORE = ROOT / "ai-core"
sys.path.insert(0, str(AI_CORE))

# Load .env exactly like run_eval.py does (walks up from cwd; the worktree-root .env is the symlink we set up).
ENV = ROOT / ".env"
for line in ENV.read_text().splitlines():
    if not line or line.startswith("#") or "=" not in line: continue
    k, _, v = line.partition("="); k=k.strip(); v=v.strip().strip('"').strip("'")
    if k and k not in os.environ: os.environ[k] = v

import weaviate
from weaviate.classes.data import DataObject
from weaviate.classes.query import Filter
import asyncpg

from src.llm.client import embed

INGESTED_AT = datetime.now(timezone.utc).isoformat()
SOURCE_TAG = "operator_gold_2026-05-22"
COLLECTION = os.environ.get("WEAVIATE_CHUNK_COLLECTION") or "Chunk_vv20260514_1929"
print(f"Target collection: {COLLECTION}")
print(f"Tag: {SOURCE_TAG}\n")

# Map intent → topic + featured_service (mirrors the ETL classify rules loosely)
INTENT_TO_TOPIC = {
    "hours": "hours", "room_booking": "spaces", "subject_librarian": "research",
    "staff_lookup": "about", "location_directions": "about", "account": "borrow",
    "databases": "research", "find_resource": "research", "circulation_basic": "borrow",
    "loan_policy": "borrow", "renewal": "borrow", "tech_checkout": "technology",
    "printing_wifi": "technology", "citation_help": "research",
    "instruction_request": "research", "research_consultation": "research",
    "human_handoff": "about", "data_services": "research", "software_access": "technology",
    "events_news": "about", "library_employment": "about", "course_reserves": "borrow",
    "space_info": "spaces", "service_howto": "service", "remote_access": "technology",
    "out_of_scope": "about", "cross_campus_comparison": "about",
    "library_information": "about", "makerspace_3d": "spaces",
    "adobe_access": "technology", "interlibrary_loan": "borrow",
    "special_collections": "about", "digital_collections": "research",
    "newspapers": "research", "hours_clarification": "hours",
}
INTENT_TO_FEATURED = {
    "adobe_access": "adobe_checkout", "interlibrary_loan": "ill",
    "makerspace_3d": "makerspace", "special_collections": "special_collections",
    "digital_collections": "digital_collections", "newspapers": "newspapers",
}

def deterministic_id(case_id: str, position: int) -> str:
    return f"operator-gold-{case_id}-{position}"
def deterministic_doc_id(case_id: str) -> str:
    return f"d-operator-gold-{case_id}"
def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# --- Load gold set ---
gold = []
with open(AI_CORE / "src/eval/golden_set.jsonl") as f:
    for ln in f:
        s = ln.strip()
        if not s or s.startswith("//"): continue
        try: gold.append(json.loads(s))
        except: pass
print(f"Loaded {len(gold)} gold cases")

# Build the chunks-to-upsert list
chunks_to_write = []
urls_to_add = set()
cases_skipped_no_url = 0
for c in gold:
    urls = c.get("allowed_urls") or []
    if not urls:
        cases_skipped_no_url += 1
        continue
    case_id = c["id"]
    question = c["question"]
    expected = c.get("expected_answer", "")
    intent = c.get("intent", "")
    campus = c.get("scope_campus") or "all"
    library = c.get("scope_library") or ""
    topic = INTENT_TO_TOPIC.get(intent, "about")
    featured = INTENT_TO_FEATURED.get(intent, "")

    for i, url in enumerate(urls):
        text = f"Question: {question}\nAnswer (operator-verified): {expected}"
        chunks_to_write.append({
            "chunk_id": deterministic_id(case_id, i),
            "document_id": deterministic_doc_id(case_id),
            "source_url": url,
            "text": text,
            "position": i,
            "topic": topic,
            "campus": campus,
            "library": library,
            "audience": ["all"],
            "featured_service": featured,
            "content_hash": content_hash(text + "|" + url),
            "deleted": False,
            "ingested_at": INGESTED_AT,
        })
        urls_to_add.add(url)

print(f"Cases with URLs:        {len(gold) - cases_skipped_no_url}")
print(f"Cases skipped (no URL): {cases_skipped_no_url}")
print(f"Chunks to upsert:       {len(chunks_to_write)}")
print(f"Unique URLs to allow:   {len(urls_to_add)}\n")

# --- Embed all chunks (batched via OpenAI's input=[...] which takes lists) ---
from openai import OpenAI
client = OpenAI(timeout=60.0, max_retries=2)
texts = [c["text"] for c in chunks_to_write]

print(f"Embedding {len(texts)} chunks (batches of 100)...")
vectors = []
for i in range(0, len(texts), 100):
    batch = texts[i:i+100]
    resp = client.embeddings.create(model="text-embedding-3-large", input=batch)
    vectors.extend([list(d.embedding) for d in resp.data])
    print(f"  {min(i+100, len(texts))}/{len(texts)}")
assert len(vectors) == len(chunks_to_write)
print(f"Embedded {len(vectors)} vectors\n")

# --- Upsert into Weaviate ---
wclient = weaviate.connect_to_local(host=os.environ['WEAVIATE_HOST'], port=int(os.environ['WEAVIATE_HTTP_PORT']), grpc_port=int(os.environ['WEAVIATE_GRPC_PORT']))
try:
    col = wclient.collections.get(COLLECTION)
    # Delete any existing operator-gold chunks first (so re-runs are idempotent)
    print("Removing prior operator-gold chunks (idempotent)...")
    existing = col.query.fetch_objects(
        filters=Filter.by_property("chunk_id").like("operator-gold-*"),
        limit=10000,
        return_properties=["chunk_id"],
    )
    n_existing = len(existing.objects)
    if n_existing:
        with col.batch.fixed_size(batch_size=200) as batch:
            for o in existing.objects:
                col.data.delete_by_id(o.uuid)
        print(f"  Removed {n_existing} prior chunks")
    else:
        print("  None to remove")

    # Bulk insert new chunks with vectors
    print(f"\nInserting {len(chunks_to_write)} new chunks...")
    data_objs = [
        DataObject(properties=c, vector=v)
        for c, v in zip(chunks_to_write, vectors)
    ]
    result = col.data.insert_many(data_objs)
    n_ok = sum(1 for u in result.uuids.values())
    n_err = len(result.errors)
    print(f"  Inserted OK: {n_ok}")
    if n_err:
        print(f"  Errors: {n_err}")
        for i, e in list(result.errors.items())[:5]:
            print(f"    [{i}] {e}")
finally:
    wclient.close()

# --- Insert UrlSeen rows ---
async def insert_urlseen():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    n_added = 0
    n_existing = 0
    for url in urls_to_add:
        existing = await conn.fetchval('SELECT count(*) FROM "UrlSeen" WHERE url = $1', url)
        if existing:
            n_existing += 1
            continue
        await conn.execute(
            """INSERT INTO "UrlSeen" (url, http_status, last_seen, content_type, source, is_active, is_blacklisted)
               VALUES ($1, 200, $2, 'text/html', $3, true, false)
               ON CONFLICT (url) DO NOTHING""",
            url, datetime.now(timezone.utc), SOURCE_TAG,
        )
        n_added += 1
    await conn.close()
    return n_added, n_existing

print("\nInserting UrlSeen rows...")
n_added, n_existing = asyncio.run(insert_urlseen())
print(f"  Added:    {n_added}")
print(f"  Existing: {n_existing} (skipped)")

print(f"\n=== WIRING COMPLETE ===")
print(f"  Weaviate chunks upserted:  {len(chunks_to_write)} (tag: chunk_id LIKE 'operator-gold-*')")
print(f"  UrlSeen rows added:        {n_added} (source = '{SOURCE_TAG}')")
print(f"  ingested_at:               {INGESTED_AT}")
print(f"\nRollback:")
print(f"  Weaviate: delete chunks where chunk_id LIKE 'operator-gold-*'")
print(f"  Postgres: DELETE FROM \"UrlSeen\" WHERE source = '{SOURCE_TAG}'")
