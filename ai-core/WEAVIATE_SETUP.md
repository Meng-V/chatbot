# Weaviate Local Setup Guide

## Architecture

```
User Question
    ↓
OpenAI API (text-embedding-3-large)
    ↓ [1536-dim vector]
Weaviate (Vector Database)
    ↓ [Similarity Search]
Top K Similar Examples
```

**Key Points:**
- ✅ OpenAI generates embeddings (external API)
- ✅ Weaviate stores vectors and performs similarity search
- ✅ No Weaviate vectorizer modules enabled
- ✅ Weaviate = pure vector database only

---

## Docker Image Sources

### Option 1: Weaviate Container Registry (Default)
```yaml
image: cr.weaviate.io/semitechnologies/weaviate:1.27.3
```

**Pros:**
- Official primary source
- Latest releases first
- Optimized delivery

**Cons:**
- May be slower in some regions
- May require authentication for some versions

### Option 2: Docker Hub (Alternative)
```yaml
image: semitechnologies/weaviate:1.27.3
```

**Pros:**
- Widely available CDN
- Fast global mirrors
- No authentication needed for public images

**Cons:**
- Slightly delayed updates
- Rate limits for anonymous users (100 pulls/6 hours)

---

## Setup Methods

### Method 1: Docker Compose with Weaviate Registry (Recommended)

```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core

# Start using default compose file
docker-compose -f docker-compose.weaviate.yml up -d

# Verify
curl http://localhost:8080/v1/meta
```

### Method 2: Docker Compose with Docker Hub

```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core

# Start using Docker Hub mirror
docker-compose -f docker-compose.weaviate.dockerhub.yml up -d

# Verify
curl http://localhost:8080/v1/meta
```

### Method 3: Manual Docker Pull + Run

#### From Weaviate Container Registry:
```bash
# Pull image
docker pull cr.weaviate.io/semitechnologies/weaviate:1.27.3

# Run container
docker run -d \
  --name weaviate-local \
  -p 8080:8080 \
  -p 50051:50051 \
  -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true \
  -e PERSISTENCE_DATA_PATH=/var/lib/weaviate \
  -e DEFAULT_VECTORIZER_MODULE=none \
  -e ENABLE_MODULES='' \
  -e CLUSTER_HOSTNAME=node1 \
  -v weaviate_data:/var/lib/weaviate \
  --restart on-failure:0 \
  cr.weaviate.io/semitechnologies/weaviate:1.27.3
```

#### From Docker Hub:
```bash
# Pull image from Docker Hub
docker pull semitechnologies/weaviate:1.27.3

# Run container
docker run -d \
  --name weaviate-local \
  -p 8080:8080 \
  -p 50051:50051 \
  -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true \
  -e PERSISTENCE_DATA_PATH=/var/lib/weaviate \
  -e DEFAULT_VECTORIZER_MODULE=none \
  -e ENABLE_MODULES='' \
  -e CLUSTER_HOSTNAME=node1 \
  -v weaviate_data:/var/lib/weaviate \
  --restart on-failure:0 \
  semitechnologies/weaviate:1.27.3
```

---

## Docker Hub Usage Details

### Check Available Versions on Docker Hub

Visit: https://hub.docker.com/r/semitechnologies/weaviate/tags

Or use CLI:
```bash
# List all tags
curl https://registry.hub.docker.com/v2/repositories/semitechnologies/weaviate/tags | jq '.'

# Search for specific version
docker search semitechnologies/weaviate
```

### Pull Specific Version from Docker Hub

```bash
# Latest version
docker pull semitechnologies/weaviate:latest

# Specific version
docker pull semitechnologies/weaviate:1.27.3

# Specific minor version (auto-updates patch)
docker pull semitechnologies/weaviate:1.27

# Specific major version (auto-updates minor)
docker pull semitechnologies/weaviate:1
```

### Switch Between Image Sources

If you started with one source and want to switch:

```bash
# 1. Stop current container
docker stop weaviate-local
docker rm weaviate-local

# 2. Pull new image source
docker pull semitechnologies/weaviate:1.27.3

# 3. Start with new image
docker-compose -f docker-compose.weaviate.dockerhub.yml up -d

# Note: Your data persists in the volume (weaviate_data)
```

---

## Docker Hub Rate Limits

**Anonymous users:** 100 pulls per 6 hours per IP  
**Authenticated users:** 200 pulls per 6 hours

### Check Your Rate Limit Status

```bash
TOKEN=$(curl "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl --head -H "Authorization: Bearer $TOKEN" https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest
```

Look for headers:
- `ratelimit-limit`: Your limit
- `ratelimit-remaining`: Remaining pulls

### Avoid Rate Limits

1. **Use Docker Hub account:**
```bash
docker login
# Enter username and password
```

2. **Use Weaviate Container Registry:**
```bash
docker-compose -f docker-compose.weaviate.yml up -d
```

3. **Pull image once, reuse:**
```bash
# Images are cached locally
docker images | grep weaviate
```

---

## Environment Variables Explained

| Variable | Value | Purpose |
|----------|-------|---------|
| `DEFAULT_VECTORIZER_MODULE` | `none` | **CRITICAL**: Disables Weaviate's built-in vectorizers |
| `ENABLE_MODULES` | `''` | Disables all modules (no text2vec-*, generative-*, etc.) |
| `AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED` | `true` | Allows local access without API key |
| `PERSISTENCE_DATA_PATH` | `/var/lib/weaviate` | Where Weaviate stores data inside container |
| `QUERY_DEFAULTS_LIMIT` | `25` | Default result limit for queries |

**Why `DEFAULT_VECTORIZER_MODULE: 'none'`?**
- You generate embeddings via OpenAI API in Python
- Weaviate receives pre-computed vectors
- No need for Weaviate to call embedding models

---

## Data Flow

### 1. Creating Embeddings (Your Python Code)

```python
from openai import OpenAI

client = OpenAI(api_key=OPENAI_API_KEY)
response = client.embeddings.create(
    model="text-embedding-3-large",
    input="Can I borrow a laptop?"
)
vector = response.data[0].embedding  # 1536-dim vector
```

### 2. Storing in Weaviate

```python
import weaviate

client = weaviate.connect_to_local()
collection = client.collections.get("QuestionCategory")

collection.data.insert(
    properties={"text": "Can I borrow a laptop?", "category": "equipment"},
    vector=vector  # Pre-computed by OpenAI
)
```

### 3. Querying Weaviate

```python
results = collection.query.near_vector(
    near_vector=query_vector,  # Also from OpenAI
    limit=5
)
```

**Weaviate's role:** Store vectors, compute cosine similarity, return top K matches.

---

## Verification Commands

```bash
# Check container is running
docker ps | grep weaviate

# Check logs
docker logs weaviate-local -f

# Test REST API
curl http://localhost:8080/v1/meta

# Test from Python
python -c "import weaviate; c = weaviate.connect_to_local(); print('Ready:', c.is_ready()); c.close()"

# Check collections
curl http://localhost:8080/v1/schema
```

---

## Troubleshooting

### Image Pull Failed from cr.weaviate.io

**Problem:** `Error pulling image from cr.weaviate.io`

**Solution:**
```bash
# Switch to Docker Hub
docker-compose -f docker-compose.weaviate.dockerhub.yml up -d
```

### Docker Hub Rate Limit Exceeded

**Problem:** `toomanyrequests: You have reached your pull rate limit`

**Solution 1 - Login to Docker Hub:**
```bash
docker login
# Enter credentials
```

**Solution 2 - Use Weaviate Registry:**
```bash
docker-compose -f docker-compose.weaviate.yml up -d
```

**Solution 3 - Use cached image:**
```bash
# If you already pulled it once
docker images | grep weaviate
docker run -d --name weaviate-local [image-id]
```

### Port 8080 Already in Use

**Problem:** `port is already allocated`

**Solution:**
```bash
# Find what's using port 8080
lsof -i :8080

# Change port in docker-compose.yml
ports:
  - "8081:8080"  # Changed from 8080:8080

# Update Python code to connect to localhost:8081
```

---

## Production Considerations

For production deployment, update docker-compose.yml:

```yaml
environment:
  # Enable authentication
  AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'false'
  AUTHENTICATION_APIKEY_ENABLED: 'true'
  AUTHENTICATION_APIKEY_ALLOWED_KEYS: 'your-secret-key-here'
  
  # Add monitoring
  PROMETHEUS_MONITORING_ENABLED: 'true'
  
  # Tune performance
  QUERY_DEFAULTS_LIMIT: 100
  QUERY_MAXIMUM_RESULTS: 10000
```

And update your Python code:
```python
client = weaviate.connect_to_local(
    auth_credentials=weaviate.auth.AuthApiKey("your-secret-key-here")
)
```

---

## Summary

**Your Setup:**
- ✅ OpenAI API generates embeddings (external)
- ✅ Weaviate stores vectors (local Docker)
- ✅ No Weaviate vectorizer modules needed
- ✅ Works with both cr.weaviate.io and Docker Hub images

**Recommended Command:**
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
docker-compose -f docker-compose.weaviate.yml up -d
python scripts/initialize_rag_classifier.py
```

**If you encounter issues, switch to Docker Hub:**
```bash
docker-compose -f docker-compose.weaviate.dockerhub.yml up -d
```
