# ChromaDB Setup Guide

This application uses ChromaDB for semantic recommendations. The setup varies by environment.

## Environment Modes

### Development (Default)
- Uses **PersistentClient** - ChromaDB embedded in the application
- Data stored in `./data/recommendations_vectordb/` directory
- No external ChromaDB server required
- Best for local development

### Staging/Production
- Uses **HttpClient** - Connects to standalone ChromaDB server
- ChromaDB runs as a separate service
- Better performance and isolation
- Automatic failover to PersistentClient if server unavailable

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Application Environment
# Options: development, staging, production
ENVIRONMENT=development

# ChromaDB Configuration
# Force server mode (optional - auto-enabled for staging/production)
USE_CHROMA_SERVER=false

# ChromaDB server connection (for staging/production)
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

## Running ChromaDB Server

### Option 1: Docker Compose (Recommended)

The ChromaDB service is included in `compose.yaml`:

```bash
# Start all services including ChromaDB
docker-compose up -d

# Start only ChromaDB
docker-compose up -d chromadb

# Check ChromaDB is running
curl http://localhost:8000/api/v1/heartbeat
```

### Option 2: Standalone Docker

```bash
docker run -d \
  --name chromadb \
  -p 8000:8000 \
  -v chroma-data:/chroma/chroma \
  -e IS_PERSISTENT=TRUE \
  -e ANONYMIZED_TELEMETRY=FALSE \
  chromadb/chroma:latest
```

### Option 3: Python (Development Only)

```bash
pip install chromadb
chroma run --host localhost --port 8000 --path ./chroma_db
```

## Switching Between Modes

### Force Server Mode in Development

```bash
# In .env
USE_CHROMA_SERVER=true
```

### Force Embedded Mode in Staging/Production

```bash
# In .env
USE_CHROMA_SERVER=false
ENVIRONMENT=development
```

## Performance Benefits

### PersistentClient (Development)
- ✅ No external dependencies
- ✅ Simple setup
- ❌ Slower (initializes on each request)
- ❌ File locking issues in multi-process

### HttpClient (Staging/Production)
- ✅ Much faster (server stays loaded)
- ✅ Shared across processes
- ✅ Better resource management
- ✅ Singleton pattern + server caching
- ❌ Requires external service

## Troubleshooting

### Connection Errors

If you see `Failed to connect to ChromaDB server`:

1. **Check server is running:**
   ```bash
   curl http://localhost:8000/api/v1/heartbeat
   ```

2. **Check logs:**
   ```bash
   docker-compose logs chromadb
   ```

3. **Application auto-fallback:**
   - Application will automatically fall back to PersistentClient
   - Check application logs for "Falling back to persistent client"

### Port Conflicts

If port 8000 is in use:

1. **Change port in `.env`:**
   ```bash
   CHROMA_PORT=8001
   ```

2. **Update `compose.yaml`:**
   ```yaml
   chromadb:
     ports:
       - "8001:8000"
   ```

### Performance Issues

If recommendations are slow:

1. **Check if using server mode:**
   - Look for "Connecting to ChromaDB server" in logs
   - Server mode is 3-6x faster than embedded

2. **Verify caching is working:**
   - Look for "Using server-side cache" in logs
   - Client-side cache hits should be instant

3. **Check ChromaDB health:**
   ```bash
   docker stats chromadb
   ```

## Migration from PersistentClient

If you have existing data in `./data/recommendations_vectordb/`:

### Option 1: Start Fresh (Recommended for Testing)
```bash
# Remove old data
rm -rf ./data/recommendations_vectordb/

# Start ChromaDB server
docker-compose up -d chromadb

# Recommendations will rebuild as workflows are used
```

### Option 2: Migrate Data
```bash
# TODO: Add migration script if needed
# Contact dev team for migration assistance
```

## Monitoring

### Check ChromaDB Status
```bash
# Via Docker
docker-compose ps chromadb

# Via API
curl http://localhost:8000/api/v1/heartbeat

# Check collections
curl http://localhost:8000/api/v1/collections
```

### Performance Metrics

Monitor these logs:
- `"Using server-side cache"` - Server cache hit (instant)
- `"Using cached recommendations"` - Client cache hit (instant)
- `"Connecting to ChromaDB server"` - Using server mode
- `"Using persistent ChromaDB client"` - Using embedded mode

## Production Deployment

### Recommended Setup

1. **Run ChromaDB as separate service:**
   ```yaml
   # In docker-compose.prod.yaml
   chromadb:
     image: chromadb/chroma:latest
     restart: always
     volumes:
       - /var/lib/chromadb:/chroma/chroma
   ```

2. **Environment variables:**
   ```bash
   ENVIRONMENT=production
   CHROMA_HOST=chromadb
   CHROMA_PORT=8000
   USE_CHROMA_SERVER=true
   ```

3. **Health checks:**
   ```yaml
   chromadb:
     healthcheck:
       test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
       interval: 30s
       timeout: 10s
       retries: 3
   ```

## Additional Resources

- [ChromaDB Documentation](https://docs.trychroma.com/)
- [ChromaDB Docker Guide](https://docs.trychroma.com/deployment/docker)
- [Performance Optimization Guide](https://docs.trychroma.com/guides/performance)
