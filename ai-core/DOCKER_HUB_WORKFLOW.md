# Docker Hub Workflow: Build & Push Your Custom Weaviate Image

## Overview

This guide shows how to:
1. Build your custom Weaviate image
2. Push it to YOUR Docker Hub account
3. Use your custom image in production

---

## Prerequisites

1. **Docker Hub Account**
   - Sign up at https://hub.docker.com
   - Note your username (e.g., `mengqu` or `qum`)

2. **Docker Installed**
   ```bash
   docker --version
   ```

---

## Step 1: Login to Docker Hub

```bash
# Login to Docker Hub
docker login

# Enter your credentials:
# Username: your-dockerhub-username
# Password: your-password-or-access-token

# Verify login
docker info | grep Username
```

**Security Tip:** Use access tokens instead of passwords:
- Go to https://hub.docker.com/settings/security
- Create new access token
- Use token as password when logging in

---

## Step 2: Build Your Custom Image

```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core

# Build the image with your Docker Hub username
# Format: username/image-name:tag
docker build -f Dockerfile.weaviate -t yourusername/miami-weaviate:1.0.0 .

# Example with actual username:
docker build -f Dockerfile.weaviate -t mengqu/miami-weaviate:1.0.0 .

# Also tag as 'latest' for convenience
docker tag mengqu/miami-weaviate:1.0.0 mengqu/miami-weaviate:latest
```

**Naming Convention:**
- `username`: Your Docker Hub username
- `image-name`: Descriptive name (e.g., `miami-weaviate`, `chatbot-vectordb`)
- `tag`: Version number (e.g., `1.0.0`, `v1`, `latest`)

---

## Step 3: Test Your Image Locally

```bash
# Stop any running Weaviate containers
docker stop weaviate-local weaviate-custom 2>/dev/null
docker rm weaviate-local weaviate-custom 2>/dev/null

# Run your custom image
docker run -d \
  --name weaviate-test \
  -p 8080:8080 \
  -p 50051:50051 \
  -v weaviate_data:/var/lib/weaviate \
  mengqu/miami-weaviate:1.0.0

# Test connection
curl http://localhost:8080/v1/meta

# Check logs
docker logs weaviate-test

# If working, stop test container
docker stop weaviate-test
docker rm weaviate-test
```

---

## Step 4: Push to Docker Hub

```bash
# Push specific version
docker push mengqu/miami-weaviate:1.0.0

# Push latest tag
docker push mengqu/miami-weaviate:latest
```

**Output:**
```
The push refers to repository [docker.io/mengqu/miami-weaviate]
5f70bf18a086: Pushed
1.0.0: digest: sha256:abc123... size: 1234
```

---

## Step 5: Verify on Docker Hub

Visit: `https://hub.docker.com/r/yourusername/miami-weaviate`

You should see:
- Your image with tags (1.0.0, latest)
- Push date
- Image size
- Pull command

---

## Step 6: Update docker-compose.yml to Use Your Image

```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
```

Edit `docker-compose.custom.yml`:

```yaml
version: '3.4'

services:
  weaviate:
    # YOUR custom image from YOUR Docker Hub account
    image: mengqu/miami-weaviate:1.0.0
    # Or use 'latest' for auto-updates: mengqu/miami-weaviate:latest
    
    container_name: weaviate-custom
    restart: on-failure:0
    ports:
      - "8080:8080"
      - "50051:50051"
    environment:
      QUERY_DEFAULTS_LIMIT: 25
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'true'
      PERSISTENCE_DATA_PATH: '/var/lib/weaviate'
      DEFAULT_VECTORIZER_MODULE: 'none'
      ENABLE_MODULES: ''
      CLUSTER_HOSTNAME: 'node1'
    volumes:
      - weaviate_data:/var/lib/weaviate

volumes:
  weaviate_data:
```

---

## Step 7: Deploy Using Your Custom Image

```bash
# Pull your image from Docker Hub (on any machine)
docker pull mengqu/miami-weaviate:1.0.0

# Start with docker-compose
docker-compose -f docker-compose.custom.yml up -d

# Verify
curl http://localhost:8080/v1/meta
docker ps | grep weaviate
```

---

## Making Updates (Version 1.0.1, 1.0.2, etc.)

### When you need to update your image:

```bash
# 1. Make changes to Dockerfile.weaviate if needed
# 2. Build new version
docker build -f Dockerfile.weaviate -t mengqu/miami-weaviate:1.0.1 .

# 3. Also update 'latest' tag
docker tag mengqu/miami-weaviate:1.0.1 mengqu/miami-weaviate:latest

# 4. Test locally
docker run -d --name test -p 8080:8080 mengqu/miami-weaviate:1.0.1
curl http://localhost:8080/v1/meta
docker stop test && docker rm test

# 5. Push both tags
docker push mengqu/miami-weaviate:1.0.1
docker push mengqu/miami-weaviate:latest

# 6. Update docker-compose.custom.yml
# Change: image: mengqu/miami-weaviate:1.0.1

# 7. Pull and restart on deployment server
docker-compose -f docker-compose.custom.yml pull
docker-compose -f docker-compose.custom.yml up -d
```

---

## Deploy to Another Server

On a new server (e.g., production server):

```bash
# 1. Login to Docker Hub
docker login

# 2. Pull your custom image
docker pull mengqu/miami-weaviate:1.0.0

# 3. Copy docker-compose.custom.yml to server
scp docker-compose.custom.yml user@server:/path/to/project/

# 4. Start on remote server
ssh user@server
cd /path/to/project
docker-compose -f docker-compose.custom.yml up -d
```

---

## Docker Hub Repository Settings

### Make Repository Private (Optional)

1. Go to https://hub.docker.com/repository/docker/mengqu/miami-weaviate/general
2. Click "Settings"
3. Change visibility to "Private"
4. Now only you can pull the image (requires login)

### Make Repository Public (Default)

- Anyone can pull: `docker pull mengqu/miami-weaviate:1.0.0`
- No authentication needed
- Good for open-source projects

---

## Complete Example Workflow

```bash
# === ON YOUR LOCAL MACHINE ===

# 1. Login
docker login
# Username: mengqu
# Password: [your-token]

# 2. Build custom image
cd /Users/qum/Documents/GitHub/chatbot/ai-core
docker build -f Dockerfile.weaviate -t mengqu/miami-weaviate:1.0.0 .
docker tag mengqu/miami-weaviate:1.0.0 mengqu/miami-weaviate:latest

# 3. Test locally
docker run -d --name test -p 8080:8080 -v weaviate_data:/var/lib/weaviate mengqu/miami-weaviate:1.0.0
curl http://localhost:8080/v1/meta
docker stop test && docker rm test

# 4. Push to Docker Hub
docker push mengqu/miami-weaviate:1.0.0
docker push mengqu/miami-weaviate:latest

# 5. Use in production
docker-compose -f docker-compose.custom.yml up -d


# === ON PRODUCTION SERVER ===

# 1. Login to Docker Hub (if private repo)
docker login

# 2. Pull your image
docker pull mengqu/miami-weaviate:1.0.0

# 3. Run with docker-compose
docker-compose -f docker-compose.custom.yml up -d

# 4. Initialize data
python scripts/initialize_rag_classifier.py
```

---

## Dockerfile Customization Examples

### Example 1: Add Custom Configuration File

```dockerfile
FROM cr.weaviate.io/semitechnologies/weaviate:1.27.3

LABEL maintainer="qum@miamioh.edu"

# Copy custom config
COPY ./config/weaviate.yaml /etc/weaviate/config.yaml

ENV DEFAULT_VECTORIZER_MODULE=none \
    ENABLE_MODULES=''

EXPOSE 8080 50051
```

### Example 2: Add Monitoring Tools

```dockerfile
FROM cr.weaviate.io/semitechnologies/weaviate:1.27.3

LABEL maintainer="qum@miamioh.edu"

# Install monitoring tools
RUN apt-get update && apt-get install -y \
    curl \
    netcat \
    htop \
    && rm -rf /var/lib/apt/lists/*

ENV DEFAULT_VECTORIZER_MODULE=none

EXPOSE 8080 50051
```

### Example 3: Add Initialization Script

```dockerfile
FROM cr.weaviate.io/semitechnologies/weaviate:1.27.3

LABEL maintainer="qum@miamioh.edu"

# Copy startup script
COPY ./scripts/init-weaviate.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/init-weaviate.sh

ENV DEFAULT_VECTORIZER_MODULE=none

EXPOSE 8080 50051

# Use custom entrypoint
ENTRYPOINT ["/usr/local/bin/init-weaviate.sh"]
```

---

## Managing Multiple Environments

Create separate images for dev/staging/prod:

```bash
# Development
docker build -f Dockerfile.weaviate -t mengqu/miami-weaviate:dev .
docker push mengqu/miami-weaviate:dev

# Staging
docker build -f Dockerfile.weaviate -t mengqu/miami-weaviate:staging .
docker push mengqu/miami-weaviate:staging

# Production
docker build -f Dockerfile.weaviate -t mengqu/miami-weaviate:1.0.0 .
docker tag mengqu/miami-weaviate:1.0.0 mengqu/miami-weaviate:prod
docker push mengqu/miami-weaviate:1.0.0
docker push mengqu/miami-weaviate:prod
```

Then in docker-compose:
```yaml
# docker-compose.dev.yml
image: mengqu/miami-weaviate:dev

# docker-compose.staging.yml
image: mengqu/miami-weaviate:staging

# docker-compose.prod.yml
image: mengqu/miami-weaviate:prod
```

---

## Automated Build with GitHub Actions (Optional)

Create `.github/workflows/docker-build.yml`:

```yaml
name: Build and Push Docker Image

on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Login to Docker Hub
      uses: docker/login-action@v2
      with:
        username: ${{ secrets.DOCKERHUB_USERNAME }}
        password: ${{ secrets.DOCKERHUB_TOKEN }}
    
    - name: Build and push
      uses: docker/build-push-action@v4
      with:
        context: .
        file: ./Dockerfile.weaviate
        push: true
        tags: |
          mengqu/miami-weaviate:latest
          mengqu/miami-weaviate:${{ github.sha }}
```

---

## Troubleshooting

### "denied: requested access to the resource is denied"

**Solution:** Make sure you're logged in and using your correct username:
```bash
docker login
docker build -t YOUR-ACTUAL-USERNAME/miami-weaviate:1.0.0 .
```

### "repository name must be lowercase"

**Solution:** Use lowercase for image name:
```bash
# Wrong: MiamiWeaviate
# Correct: miami-weaviate
docker build -t mengqu/miami-weaviate:1.0.0 .
```

### Image too large

**Solution:** Use multi-stage builds or clean up layers:
```dockerfile
RUN apt-get update && apt-get install -y curl \
    && rm -rf /var/lib/apt/lists/*  # Clean up in same layer
```

---

## Summary

**Your Custom Docker Hub Workflow:**

1. **Build:** `docker build -f Dockerfile.weaviate -t yourusername/miami-weaviate:1.0.0 .`
2. **Test:** `docker run -d --name test -p 8080:8080 yourusername/miami-weaviate:1.0.0`
3. **Push:** `docker push yourusername/miami-weaviate:1.0.0`
4. **Deploy:** Update `docker-compose.custom.yml` with your image
5. **Use:** `docker-compose -f docker-compose.custom.yml up -d`

**Benefits:**
- ✅ Full control over your Weaviate configuration
- ✅ Can add custom startup scripts, configs, monitoring
- ✅ Easy to deploy to multiple servers
- ✅ Version control for your infrastructure
- ✅ No dependency on external Docker registries
