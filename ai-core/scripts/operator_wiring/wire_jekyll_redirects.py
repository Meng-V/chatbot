"""Wire Jekyll redirect aliases into UrlSeen.

For each /Users/qum/Documents/GitHub/Jekyll_Dev-master/_redirects/*.md:
  - Parse YAML front-matter to extract `permalink` (source) + `redirect-to` (dest)
  - Skip if permalink OR redirect-to is under /blog/ or /news/ or matches /YYYY/MM/DD/
  - Compute absolute SOURCE URL  = https://www.lib.miamioh.edu + permalink
  - Compute absolute DEST URL    = redirect-to (if absolute) OR https://www.lib.miamioh.edu + redirect-to
  - INSERT both into UrlSeen (idempotent ON CONFLICT)
  - Also build alias-Weaviate chunks: each alias source_url becomes a chunk
    whose text says "Alias for {canonical}" and whose source_url is the alias.
    This way retrieval surfaces the alias if a user mentions /NYT or /ill.

Source tag: 'jekyll_redirect_2026-05-22' (rollback identifier)
"""
import os, re, sys, asyncio, hashlib
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/Users/qum/Documents/GitHub/chatbot/.claude/worktrees/nice-mcnulty-42183e")
AI_CORE = ROOT / "ai-core"
sys.path.insert(0, str(AI_CORE))

ENV = ROOT / ".env"
for line in ENV.read_text().splitlines():
    if not line or line.startswith("#") or "=" not in line: continue
    k, _, v = line.partition("="); k=k.strip(); v=v.strip().strip('"').strip("'")
    if k and k not in os.environ: os.environ[k] = v

REDIRECTS_DIR = Path("/Users/qum/Documents/GitHub/Jekyll_Dev-master/_redirects")
SOURCE_TAG = "jekyll_redirect_2026-05-22"
JEKYLL_BASE = "https://www.lib.miamioh.edu"
COLLECTION = os.environ.get("WEAVIATE_CHUNK_COLLECTION") or "Chunk_vv20260514_1929"

# Exclusion regexes — operator said skip blog/news + the date-stamped post URLs
EXCLUDE_PATTERNS = [
    re.compile(r"^/blog/"),
    re.compile(r"^/news/"),
    re.compile(r"^/about/news-events/"),
    re.compile(r"^/\d{4}/\d{2}/\d{2}/"),  # dated blog posts like /2020/06/15/...
]
def should_exclude(path_or_url: str) -> bool:
    # If it's absolute, extract the path component
    if path_or_url.startswith("http"):
        m = re.match(r"https?://[^/]+(/.*)", path_or_url)
        path = m.group(1) if m else path_or_url
    else:
        path = path_or_url
    return any(p.search(path) for p in EXCLUDE_PATTERNS)

def parse_front_matter(text: str) -> dict:
    """Tiny YAML front-matter parser — just for permalink + redirect-to."""
    m = re.search(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m: return {}
    out = {}
    for ln in m.group(1).splitlines():
        if ":" not in ln: continue
        k, _, v = ln.partition(":")
        k = k.strip(); v = v.strip()
        # Strip outer quotes
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        out[k] = v
    return out

def absolutize(path_or_url: str) -> str:
    """Convert relative path to absolute, or pass through if already absolute."""
    if path_or_url.startswith("http"):
        return path_or_url
    if not path_or_url.startswith("/"):
        path_or_url = "/" + path_or_url
    return JEKYLL_BASE + path_or_url

def norm(u: str) -> str:
    """Idempotent canonicalize — trim trailing whitespace; keep trailing slash as-is."""
    return u.strip()

# --- Parse all files ---
pairs = []          # (source_url, dest_url, file_name)
skipped = []        # (file_name, reason)
for f in sorted(REDIRECTS_DIR.glob("*.md")):
    front = parse_front_matter(f.read_text(encoding="utf-8"))
    permalink = front.get("permalink")
    redirect_to = front.get("redirect-to") or front.get("redirect_to")
    if not permalink or not redirect_to:
        skipped.append((f.name, "missing-fields"))
        continue
    if should_exclude(permalink) or should_exclude(redirect_to):
        skipped.append((f.name, f"excluded (perm={permalink} -> {redirect_to})"))
        continue
    src = norm(absolutize(permalink))
    dst = norm(absolutize(redirect_to))
    pairs.append((src, dst, f.name))

print(f"Parsed {len(list(REDIRECTS_DIR.glob('*.md')))} files")
print(f"  Pairs to wire: {len(pairs)}")
print(f"  Skipped:       {len(skipped)}")
for fn, why in skipped[:10]:
    print(f"    {fn:<50} {why}")
print()

# --- Compute the set of URLs to insert into UrlSeen ---
urls_to_add = set()
for src, dst, _ in pairs:
    urls_to_add.add(src)
    urls_to_add.add(dst)

# Build alias map: dest -> [sources] (so we know which sources alias each canonical)
dest_to_sources = {}
for src, dst, _ in pairs:
    dest_to_sources.setdefault(dst, []).append(src)

# --- UrlSeen INSERT ---
async def insert_urlseen():
    import asyncpg
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    added, existed = 0, 0
    for url in urls_to_add:
        n = await conn.fetchval('SELECT count(*) FROM "UrlSeen" WHERE url = $1', url)
        if n:
            existed += 1
            continue
        await conn.execute("""
            INSERT INTO "UrlSeen" (
              url, "httpStatus", "contentType", source, priority,
              "isActive", "isBlacklisted", "lastSeen", "createdAt", "updatedAt"
            ) VALUES (
              $1, 200, 'text/html', $2, 'normal',
              true, false, $3, $3, $3
            ) ON CONFLICT (url) DO NOTHING
        """, url, SOURCE_TAG, now)
        added += 1
    # Final counts
    n_tagged = await conn.fetchval('SELECT count(*) FROM "UrlSeen" WHERE source = $1', SOURCE_TAG)
    n_total = await conn.fetchval('SELECT count(*) FROM "UrlSeen"')
    await conn.close()
    return added, existed, n_tagged, n_total

print("Writing UrlSeen rows...")
added, existed, n_tagged, n_total = asyncio.run(insert_urlseen())
print(f"  Added:    {added}")
print(f"  Existed:  {existed}")
print(f"  Total with tag '{SOURCE_TAG}': {n_tagged}")
print(f"  Total UrlSeen rows overall:       {n_total}")
print()

# --- Weaviate alias chunks ---
# For each (src, dst) pair: create a chunk at source_url=src whose text
# announces "Alias for {dst}". This way semantic retrieval against a
# user query that mentions /NYT or "ill" finds the alias chunk too.
def deterministic_chunk_id(file_stem: str) -> str:
    return f"jekyll-redirect-{file_stem}"

import weaviate
from weaviate.classes.data import DataObject
from weaviate.classes.query import Filter
from openai import OpenAI

client = OpenAI(timeout=60.0, max_retries=2)

# Build chunk objects
chunks_to_write = []
for src, dst, fname in pairs:
    stem = fname[:-3]  # strip .md
    text = f"This URL ({src}) is a Miami University Libraries shortcut/alias that redirects to {dst}."
    chunks_to_write.append({
        "chunk_id": deterministic_chunk_id(stem),
        "document_id": f"d-jekyll-redirect-{stem}",
        "source_url": src,
        "text": text,
        "position": 0,
        "topic": "about",
        "campus": "oxford",
        "library": "",
        "audience": ["all"],
        "featured_service": "",
        "content_hash": hashlib.sha256((text + "|" + src).encode()).hexdigest(),
        "deleted": False,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    })

print(f"Embedding {len(chunks_to_write)} alias chunks (batches of 100)...")
texts = [c["text"] for c in chunks_to_write]
vectors = []
for i in range(0, len(texts), 100):
    resp = client.embeddings.create(model="text-embedding-3-large", input=texts[i:i+100])
    vectors.extend([list(d.embedding) for d in resp.data])
    print(f"  {min(i+100, len(texts))}/{len(texts)}")
print(f"Embedded {len(vectors)} vectors")

# Upsert into Weaviate
wclient = weaviate.connect_to_local(host=os.environ['WEAVIATE_HOST'], port=int(os.environ['WEAVIATE_HTTP_PORT']), grpc_port=int(os.environ['WEAVIATE_GRPC_PORT']))
try:
    col = wclient.collections.get(COLLECTION)
    print("Removing any prior jekyll-redirect-* chunks (idempotent)...")
    existing = col.query.fetch_objects(
        filters=Filter.by_property("chunk_id").like("jekyll-redirect-*"),
        limit=5000,
        return_properties=["chunk_id"],
    )
    for o in existing.objects:
        col.data.delete_by_id(o.uuid)
    print(f"  Removed {len(existing.objects)} prior chunks")

    print(f"\nInserting {len(chunks_to_write)} alias chunks...")
    data_objs = [DataObject(properties=c, vector=v) for c, v in zip(chunks_to_write, vectors)]
    result = col.data.insert_many(data_objs)
    n_ok = sum(1 for _ in result.uuids.values())
    n_err = len(result.errors)
    print(f"  Inserted OK: {n_ok}")
    if n_err:
        print(f"  Errors: {n_err}")
        for i, e in list(result.errors.items())[:5]:
            print(f"    [{i}] {e}")
finally:
    wclient.close()

print(f"\n=== JEKYLL REDIRECT WIRING COMPLETE ===")
print(f"  UrlSeen rows added:     {added}")
print(f"  Weaviate alias chunks:  {len(chunks_to_write)} (tag: chunk_id LIKE 'jekyll-redirect-*')")
print(f"  Aliases with multiple sources (potential dedups):")
multi = {d: s for d, s in dest_to_sources.items() if len(s) > 1}
for d, srcs in sorted(multi.items()):
    print(f"    {d}")
    for s in srcs:
        print(f"      <- {s}")
print(f"\nRollback:")
print(f"  Weaviate: delete chunks where chunk_id LIKE 'jekyll-redirect-*'")
print(f"  Postgres: DELETE FROM \"UrlSeen\" WHERE source = '{SOURCE_TAG}'")
