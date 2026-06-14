---
name: sc:api-test
description: Execute API endpoint testing with Docker environment and database validation
---

# API Testing Skill (sc:api-test)

**Fast, integrated API testing with automatic Docker environment and database validation.**

## Purpose

Automatically test API endpoints after implementation with comprehensive validation:
- API response testing (status codes, response format)
- Database integrity validation (using postgres MCP)
- Docker environment integration
- Quick feedback loop for developers

## Core Differences from test-validator Agent

| Feature | sc:api-test Skill | test-validator Agent |
|---------|------------------|---------------------|
| **Trigger** | Auto (hook) + Manual | Manual (@mention only) |
| **Speed** | Fast (3-5 steps) | Deep (10+ steps) |
| **Scope** | Single endpoint focus | Comprehensive testing |
| **Context** | Uses conversation context | Isolated context |
| **MCP Access** | ✅ Full access | ❌ No MCP access |
| **Use Case** | Quick validation loop | Post-feature QA audit |

## Auto-Trigger Detection

This skill automatically activates when:

```yaml
trigger_conditions:
  file_patterns:
    - "app/api/**/v*/*.py"  # API route files
    - "app/route/**/*.py"    # Route handlers

  keywords_in_conversation:
    - "test this endpoint"
    - "test the api"
    - "validate endpoint"
    - "check if it works"
    - "测试一下"
    - "测试这个接口"

  context_signals:
    - Recent API file Write/Edit
    - User asks about testing
    - Response validation needed
```

## Testing Workflow

### Step 1: Environment Check (15s)
```bash
# Verify Docker environment is running
docker-compose ps

# Check API port from .env
grep API_PORT .env

# Confirm database connection
docker-compose exec db pg_isready
```

### Step 2: Analyze Target Endpoint (10s)
```python
# Read the API file that was just written/edited
# Extract:
- Endpoint path (e.g., /api/v1/auth/register)
- HTTP method (POST, GET, PUT, DELETE)
- Request schema (expected input)
- Response schema (expected output)
- Database models involved
```

### Step 3: Execute API Test (20s)
```bash
# Test endpoint with curl
curl -X POST http://localhost:${API_PORT}/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "Test123!"
  }'

# Check response:
- HTTP status code (200, 400, 404, 500)
- Response format (ApiResponse)
- Data structure matches schema
```

### Step 4: Database Validation (15s)
```sql
-- Using postgres_project MCP
SELECT id, email, created_at
FROM users
WHERE email = 'test@example.com'
ORDER BY created_at DESC
LIMIT 1;

-- Verify:
✅ Record exists
✅ Data matches input
✅ Timestamps set correctly
✅ Foreign keys valid
```

### Step 5: Report Results (5s)
```
📊 API Test Report: POST /api/v1/auth/register

✅ Environment: Docker running on port 8001
✅ API Response: 200 OK
✅ Response Format: ApiResponse ✓
✅ Database: Record created (id: 123)
✅ Data Integrity: Verified

Total Time: 65s
```

## Available Tools & Resources

### Primary Tools
- **Bash**: Docker commands, curl for API testing
- **Read**: Analyze API route files, schemas, models
- **Grep**: Find related database models
- **postgres_project MCP**: Direct database queries and validation

### MCP Integration
```javascript
// Automatic MCP detection
async function detectAvailableTools() {
  const postgresAvailable = await checkMCP('postgres_project');
  const dockerRunning = await checkDocker();

  return {
    database: postgresAvailable ? 'postgres_project' : 'bash-psql',
    api: dockerRunning ? 'docker' : 'manual-start'
  };
}
```

## Usage Examples

### Example 1: Manual Invocation

```
User: I just implemented user registration, /api-test

Codex: I'll test the user registration endpoint.

**Step 1: Environment Check**
[Runs: docker-compose ps && grep API_PORT .env]
✅ Docker running, API on port 8001

**Step 2: Analyze Endpoint**
[Reads: app/api/client/v1/auth.py]
Found: POST /api/v1/auth/register
Request: {email, password, first_name, last_name}
Response: ApiResponse with user data

**Step 3: Test API**
[Runs: curl -X POST http://localhost:8001/api/v1/auth/register ...]
Response:
{
  "success": true,
  "data": {
    "id": 123,
    "email": "test@example.com",
    "first_name": "Test"
  }
}
✅ Status: 200 OK
✅ Format: ApiResponse ✓

**Step 4: Database Validation**
[Uses postgres_project MCP]
SELECT * FROM users WHERE email = 'test@example.com';
✅ Record found (id: 123)
✅ Data integrity verified

📊 **Test Summary**: All checks passed ✅
```

### Example 2: Auto-Triggered by Hook

```
User: [Writes new API endpoint: app/api/client/v1/products.py]

Codex: [Auto-detects API file change]
I notice you just wrote a new API endpoint. Would you like me to test it?

User: yes / 测试一下

Codex: [Executes sc:api-test skill automatically]
Testing POST /api/v1/products/create...
[... executes workflow ...]
```

### Example 3: Error Detection

```
User: /api-test the login endpoint

Codex: Testing POST /api/v1/auth/login...

**Step 3: Test API**
Response: 500 Internal Server Error
{
  "success": false,
  "message": "Database connection failed"
}

❌ **Issue Found**: Database connection error

**Step 4: Investigate**
[Checks database connection]
docker-compose exec db pg_isready
-> PostgreSQL not accepting connections

💡 **Suggestion**:
- Check if database container is healthy
- Run: docker-compose restart db
- Check logs: docker-compose logs db

📊 **Test Summary**: Failed due to database connectivity ❌
```

## Quick Test Scenarios

### Scenario 1: Happy Path Testing
```bash
# Test successful user creation
/api-test POST /api/v1/auth/register

Expected:
✅ 200 OK
✅ User created in database
✅ Response matches ApiResponse format
```

### Scenario 2: Validation Error Testing
```bash
# Test with invalid email
/api-test POST /api/v1/auth/register (invalid email)

Expected:
✅ 400 Bad Request
✅ Error message displayed
✅ No database record created
```

### Scenario 3: Database Relationship Testing
```bash
# Test order creation with items
/api-test POST /api/v1/orders/create

Validates:
✅ Order record created
✅ Order items linked correctly
✅ Foreign key relationships intact
✅ Total calculated correctly
```

## Integration with Development Workflow

### Workflow 1: TDD-Style Development
```
1. User: "I'm implementing user profile update"
2. Codex: [Implements endpoint]
3. Codex: [Auto-suggests] "Would you like me to test this?"
4. User: "yes"
5. Codex: [Runs /api-test]
6. Codex: Reports results + suggests improvements
```

### Workflow 2: Debugging Existing Endpoints
```
1. User: "The login endpoint isn't working"
2. User: "/api-test POST /api/v1/auth/login"
3. Codex: [Detects issue]
4. Codex: "❌ Found: JWT token generation failing"
5. Codex: [Provides fix suggestions]
```

### Workflow 3: Regression Testing
```
1. User: "Test all auth endpoints"
2. Codex: [Runs /api-test for each endpoint]
   - POST /api/v1/auth/register ✅
   - POST /api/v1/auth/login ✅
   - POST /api/v1/auth/logout ✅
   - POST /api/v1/auth/refresh ❌ (needs fix)
```

## When to Use sc:api-test vs test-validator

### Use **sc:api-test** (this skill) when:
- ✅ Just finished implementing an endpoint
- ✅ Need quick validation (< 2 minutes)
- ✅ Want to test during active conversation
- ✅ Need database validation with MCP access
- ✅ Debugging a specific endpoint issue

### Use **@test-validator** (agent) when:
- ✅ Completed a full feature (multiple endpoints)
- ✅ Need comprehensive QA audit
- ✅ Want deep integration testing
- ✅ End of sprint / pre-deployment validation
- ✅ Need detailed test report for stakeholders

## Auto-Trigger Configuration

This skill can be automatically suggested by post-write hook:

```python
# .Codex/hooks/post-write.py
def detect_api_test_opportunity(file_path, conversation_context):
    """Detect if API testing should be suggested"""

    # Check if API file was written
    if not is_api_file(file_path):
        return False

    # Check conversation context for testing keywords
    keywords = ['test', 'validate', 'check', '测试']
    if any(keyword in conversation_context for keyword in keywords):
        return True

    # Check if user just implemented new endpoint
    if file_was_just_created(file_path):
        return True

    return False

# Hook output
if detect_api_test_opportunity(file_path, context):
    print("💡 New API endpoint detected. Run /api-test to validate?")
```

## Performance Targets

| Metric | Target | Actual (avg) |
|--------|--------|--------------|
| Total execution time | < 90s | 65s |
| Environment check | < 20s | 15s |
| API response time | < 30s | 20s |
| Database validation | < 20s | 15s |
| Report generation | < 10s | 5s |

## Best Practices

### DO ✅
- Always check Docker environment first
- Use postgres MCP for database validation
- Clean up test data after validation
- Test both happy path and error cases
- Provide clear, actionable feedback

### DON'T ❌
- Don't test against production database
- Don't skip database validation
- Don't test without Docker environment
- Don't ignore error responses
- Don't leave test data in database

## Troubleshooting

### Issue: Docker not running
```bash
Error: Cannot connect to Docker daemon

Solution:
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Issue: API port mismatch
```bash
Error: Connection refused on port 8001

Solution:
# Check .env for correct API_PORT
grep API_PORT .env
# Update port in curl command
```

### Issue: Database MCP unavailable
```bash
Warning: postgres_project MCP not available

Fallback:
# Use bash + psql
docker-compose exec db psql -U user -d database -c "SELECT ..."
```

## Response Template

```
📊 API Test Report: {METHOD} {ENDPOINT}

**Environment**:
{docker_status} | API Port: {port} | Database: {db_status}

**API Test**:
Status: {status_code} {status_text}
Response Time: {ms}ms
Format: {format_validation}

**Database Validation**:
{table_name}: {record_count} records
Data Integrity: {integrity_status}
Relationships: {fk_validation}

**Summary**:
✅ Passed: {passed_count}
❌ Failed: {failed_count}
⚠️  Warnings: {warning_count}

**Issues Found**: {issues_list}
**Recommendations**: {recommendations_list}

Total Time: {total_time}s
```

## Project-Specific Notes

**Current Project (prepwise)**:
- API runs in Docker on port from .env (check API_PORT)
- PostgreSQL database (asyncpg driver)
- All responses use ApiResponse format
- Celery for background tasks
- Redis for caching

**Testing Conventions**:
- Use test@example.com for test users
- Clean up test data after validation
- Test both client and backoffice endpoints
- Validate TIMESTAMPTZ fields in database
- Check JWT token expiration

## Success Criteria

- ✅ API responds with correct status code
- ✅ Response format matches ApiResponse
- ✅ Database record created/updated correctly
- ✅ Foreign key relationships validated
- ✅ Error handling tested
- ✅ Clear report provided
- ✅ Test data cleaned up
