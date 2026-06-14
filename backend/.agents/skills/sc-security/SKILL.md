---
name: sc:security
description: Comprehensive security audit for Python/FastAPI applications with OWASP compliance
---

# Security Audit Skill (sc:security)

**Comprehensive security analysis for Python/FastAPI applications with OWASP Top 10 compliance checking.**

## Purpose

Automated security audit workflow with:
- OWASP Top 10 vulnerability scanning
- Dependency vulnerability check (Safety, pip-audit)
- Code security pattern analysis
- Authentication/Authorization review
- Database security validation
- API security best practices
- Configuration security audit

## Core Security Focus Areas

| Category | Priority | Tools |
|----------|----------|-------|
| **Injection** | Critical | Code analysis, SQLAlchemy patterns |
| **Authentication** | Critical | JWT validation, password policies |
| **Sensitive Data** | Critical | Secrets scanning, encryption check |
| **Dependencies** | High | Safety, pip-audit |
| **Access Control** | High | Permission validation |
| **Configuration** | High | .env security, debug mode |
| **CORS** | Medium | CORS policy review |
| **Rate Limiting** | Medium | API throttling check |

## Auto-Trigger Detection

This skill automatically activates when:

```yaml
trigger_conditions:
  file_patterns:
    - "app/api/**/*.py"           # API endpoints
    - "app/services/**/*.py"      # Service layer
    - "app/core/security.py"      # Security module
    - "app/core/config.py"        # Configuration
    - "requirements.txt"          # Dependencies
    - "docker-compose*.yml"       # Docker config

  keywords_in_conversation:
    - "security audit"
    - "vulnerability scan"
    - "security check"
    - "owasp"
    - "安全审计"
    - "安全检查"

  context_signals:
    - Authentication implementation
    - Authorization changes
    - API endpoint creation
    - Database query modification
    - Dependency updates
```

## Security Audit Workflow

### Step 1: Dependency Vulnerability Scan (30s)
```bash
# Activate virtual environment and scan dependencies
source venv/bin/activate && pip install safety pip-audit

# Run Safety (Python package vulnerability database)
source venv/bin/activate && safety check --json

# Run pip-audit (PyPI Advisory Database)
source venv/bin/activate && pip-audit --format json

# Example output:
# ⚠️  Found 3 vulnerabilities:
# - cryptography 3.4.7 (CVE-2023-XXXX) - Update to 41.0.0+
# - pillow 9.0.0 (CVE-2023-YYYY) - Update to 10.0.0+
# - requests 2.27.0 (CVE-2023-ZZZZ) - Update to 2.31.0+
```

### Step 2: Code Security Analysis (60s)
```python
# Scan for common security issues

# 1. SQL Injection Risk
patterns_to_check = [
    # ❌ BAD: String concatenation in queries
    r'\.execute\(["\'].*\+.*["\']',
    r'\.execute\(f["\'].*\{.*\}.*["\']',

    # ✅ GOOD: Parameterized queries
    # session.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id})
]

# 2. Hardcoded Secrets
secrets_patterns = [
    r'password\s*=\s*["\'][^"\']+["\']',
    r'api_key\s*=\s*["\'][^"\']+["\']',
    r'secret_key\s*=\s*["\'][^"\']+["\']',
    r'token\s*=\s*["\'][^"\']+["\']',
]

# 3. Weak Password Hashing
weak_hash_patterns = [
    r'hashlib\.md5',          # ❌ Weak
    r'hashlib\.sha1',         # ❌ Weak
    # ✅ GOOD: bcrypt, argon2, scrypt
]

# 4. Insecure Random
insecure_random = [
    r'random\.random',        # ❌ Not cryptographically secure
    r'random\.randint',       # ❌ Not cryptographically secure
    # ✅ GOOD: secrets.token_urlsafe()
]
```

### Step 3: Authentication Security Review (40s)
```python
# Check app/core/security.py and app/services/*/auth*.py

security_checks = {
    "JWT Security": [
        "✅ Algorithm: Check if using HS256/RS256 (not 'none')",
        "✅ Secret Key: Verify SECRET_KEY from environment",
        "✅ Expiration: Token expiration set (15-60 min)",
        "✅ Refresh Token: Separate refresh token logic",
        "❌ Token Validation: Verify signature validation",
    ],

    "Password Security": [
        "✅ Hashing: Using bcrypt/argon2 (not MD5/SHA1)",
        "✅ Salt: Automatic salting enabled",
        "✅ Policy: Minimum 8 chars, complexity requirements",
        "✅ Reset: Secure password reset flow with token expiration",
        "❌ Storage: Never store plaintext passwords",
    ],

    "Session Security": [
        "✅ Session Timeout: Configured appropriately",
        "✅ Secure Cookies: HttpOnly, Secure, SameSite flags",
        "✅ CSRF Protection: CSRF tokens for state-changing ops",
        "✅ Session Invalidation: Logout invalidates session",
    ],
}
```

### Step 4: API Security Analysis (50s)
```python
# Check app/api/**/*.py endpoints

api_security_checks = {
    "Input Validation": [
        "✅ Pydantic Schemas: All inputs validated",
        "✅ Type Checking: Strict type validation",
        "✅ Length Limits: Max length enforced",
        "✅ Sanitization: XSS prevention (HTML escaping)",
        "❌ File Upload: Size limits, type validation",
    ],

    "Authorization": [
        "✅ Authentication: Protected endpoints use Depends(get_current_user)",
        "✅ Role Checking: Role-based access control (RBAC)",
        "✅ Resource Ownership: Users can only access own resources",
        "❌ Admin Routes: Separate admin authentication",
    ],

    "Error Handling": [
        "✅ Generic Errors: Don't expose stack traces",
        "✅ Status Codes: Correct HTTP status codes (400, 401, 403, 404)",
        "❌ Error Messages: No sensitive info in error messages",
        "✅ Logging: Security events logged (login failures, unauthorized access)",
    ],

    "Rate Limiting": [
        "⚠️  API Rate Limits: Consider slowapi or similar",
        "⚠️  Login Throttling: Prevent brute force attacks",
        "⚠️  DDoS Protection: CloudFlare or similar",
    ],
}
```

### Step 5: Database Security Review (30s)
```python
# Check app/db/ and app/models/

database_security = {
    "Query Security": [
        "✅ ORM Usage: SQLAlchemy ORM (prevents SQL injection)",
        "✅ Raw Queries: If used, must use parameterization",
        "❌ Dynamic Queries: Avoid string concatenation",
        "✅ Prepared Statements: Use SQLAlchemy text() with params",
    ],

    "Access Control": [
        "✅ Least Privilege: Database user has minimal permissions",
        "✅ Connection String: Stored in environment variables",
        "❌ Public Access: Database not exposed to internet",
        "✅ Encryption: SSL/TLS for database connections",
    ],

    "Data Protection": [
        "✅ PII Encryption: Sensitive fields encrypted at rest",
        "✅ Backup Security: Encrypted backups",
        "✅ Audit Logging: Database access logged",
        "⚠️  Data Masking: Consider for development environments",
    ],
}
```

### Step 6: Configuration Security Audit (20s)
```bash
# Check .env, docker-compose*.yml, app/core/config.py

# 1. Environment Variables
grep -E "(SECRET|PASSWORD|KEY|TOKEN)" .env
# ✅ No secrets committed to git
# ✅ .env in .gitignore
# ❌ No default secrets in code

# 2. Debug Mode
grep "debug.*=.*True" app/core/config.py
# ❌ Debug mode disabled in production
# ✅ ENV-based configuration

# 3. CORS Configuration
grep -A 5 "CORS" app/route/route.py
# ⚠️  CORS: Not allow_origins=["*"] in production
# ✅ Specific origin whitelist
# ✅ allow_credentials carefully configured

# 4. Docker Security
grep -E "(privileged|cap_add)" docker-compose*.yml
# ❌ No privileged containers
# ❌ No unnecessary capabilities
# ✅ Read-only volumes where possible
```

### Step 7: OWASP Top 10 Compliance Check (40s)
```yaml
OWASP_Top_10_2021:
  A01_Broken_Access_Control:
    severity: Critical
    checks:
      - "✅ Authentication on protected routes"
      - "✅ Authorization checks (user can only access own data)"
      - "✅ No IDOR vulnerabilities (validate resource ownership)"
      - "❌ Admin panel separate authentication"

  A02_Cryptographic_Failures:
    severity: Critical
    checks:
      - "✅ HTTPS enforced (production)"
      - "✅ Password hashing (bcrypt/argon2)"
      - "✅ Sensitive data encrypted at rest"
      - "✅ No hardcoded secrets"
      - "⚠️  Database SSL/TLS connection"

  A03_Injection:
    severity: Critical
    checks:
      - "✅ SQLAlchemy ORM (prevents SQL injection)"
      - "✅ Pydantic validation (prevents NoSQL injection)"
      - "✅ No eval/exec usage"
      - "✅ Command injection prevention"

  A04_Insecure_Design:
    severity: High
    checks:
      - "✅ Secure development lifecycle"
      - "✅ Threat modeling performed"
      - "⚠️  Rate limiting implemented"
      - "⚠️  Circuit breakers for external services"

  A05_Security_Misconfiguration:
    severity: High
    checks:
      - "❌ Debug mode disabled in production"
      - "✅ Unnecessary features disabled"
      - "✅ Security headers configured"
      - "✅ Error handling doesn't leak info"

  A06_Vulnerable_Components:
    severity: High
    checks:
      - "Run: safety check"
      - "Run: pip-audit"
      - "✅ Dependency pinning (requirements.txt)"
      - "⚠️  Regular dependency updates"

  A07_Authentication_Failures:
    severity: High
    checks:
      - "✅ Strong password policy"
      - "✅ Multi-factor authentication support"
      - "✅ Session timeout configured"
      - "⚠️  Account lockout after failed attempts"

  A08_Software_Data_Integrity:
    severity: High
    checks:
      - "✅ Code signing (git commits)"
      - "✅ Dependency integrity (pip hash-checking mode)"
      - "⚠️  CI/CD pipeline security"

  A09_Logging_Monitoring:
    severity: Medium
    checks:
      - "✅ Security events logged"
      - "✅ Log integrity protection"
      - "⚠️  Real-time monitoring"
      - "⚠️  Alerting for suspicious activity"

  A10_SSRF:
    severity: Medium
    checks:
      - "✅ URL validation for external requests"
      - "✅ Whitelist allowed domains"
      - "✅ No user-controlled URLs without validation"
```

### Step 8: Generate Security Report (10s)
```
🔒 Security Audit Report: {project_name}

**Scan Date**: {timestamp}
**Severity Breakdown**:
- 🔴 Critical: {critical_count}
- 🟠 High: {high_count}
- 🟡 Medium: {medium_count}
- 🟢 Low: {low_count}

**Vulnerability Summary**:
{vulnerability_list}

**OWASP Top 10 Compliance**:
{owasp_compliance_matrix}

**Critical Issues Found**:
{critical_issues_with_file_locations}

**Recommendations**:
{prioritized_fix_list}

**Security Score**: {score}/100

Total Time: {total_time}s
```

## Usage Examples

### Example 1: Full Security Audit

```
User: /security

Codex: Running comprehensive security audit...

**Step 1: Dependency Scan**
[Runs: safety check && pip-audit]
⚠️  Found 2 vulnerabilities:
- cryptography 3.4.7 → Update to 41.0.0+ (CVE-2023-XXXX)
- requests 2.27.0 → Update to 2.31.0+ (CVE-2023-YYYY)

**Step 2: Code Analysis**
[Scans: app/ directory]
✅ No SQL injection patterns found
✅ No hardcoded secrets detected
⚠️  Found weak random usage in app/utils/token.py:15
   Recommendation: Use secrets.token_urlsafe() instead of random.randint()

**Step 3: Authentication Review**
[Analyzes: app/core/security.py, app/services/*/auth*.py]
✅ JWT: Using HS256 algorithm
✅ Password: bcrypt hashing
✅ Secret: Loaded from environment
⚠️  Token expiration: 1 day (recommend 15-60 minutes)
❌ Rate limiting: Not implemented for login endpoint

**Step 4: API Security**
[Analyzes: app/api/]
✅ Input validation: Pydantic schemas on all endpoints
✅ Authorization: Protected routes use dependencies
⚠️  File upload: Missing size limits in app/api/client/v1/upload.py
❌ Error handling: Stack trace exposed in app/api/client/v1/debug.py:45

**Step 5: Database Security**
[Analyzes: app/db/, app/models/]
✅ ORM usage: SQLAlchemy prevents SQL injection
✅ Connection: Using environment variables
⚠️  SSL/TLS: Database connection not using SSL

**Step 6: Configuration Audit**
[Checks: .env, docker-compose.yml, app/core/config.py]
✅ Debug mode: Controlled by ENV variable
✅ Secrets: Not committed to git
⚠️  CORS: Using allow_origins=["*"] (tighten for production)

**Step 7: OWASP Compliance**
A01 - Broken Access Control: ✅ Pass
A02 - Cryptographic Failures: ⚠️  Warning (DB SSL)
A03 - Injection: ✅ Pass
A04 - Insecure Design: ⚠️  Warning (Rate limiting)
A05 - Security Misconfiguration: ⚠️  Warning (CORS)
A06 - Vulnerable Components: ❌ Fail (2 outdated packages)
A07 - Authentication Failures: ⚠️  Warning (Token expiration)
A08 - Software Data Integrity: ✅ Pass
A09 - Logging Monitoring: ⚠️  Warning
A10 - SSRF: ✅ Pass

🔒 **Security Score**: 72/100

**Critical Issues** (Fix Immediately):
1. Update cryptography to 41.0.0+ (CVE-2023-XXXX)
2. Update requests to 2.31.0+ (CVE-2023-YYYY)
3. Remove stack trace exposure in debug endpoint

**High Priority** (Fix Soon):
1. Implement rate limiting for authentication endpoints
2. Enable database SSL/TLS connections
3. Add file upload size limits
4. Reduce JWT token expiration to 60 minutes

**Medium Priority** (Plan to Fix):
1. Tighten CORS policy for production
2. Replace random.randint with secrets module
3. Implement account lockout mechanism

Total Time: 180s
```

### Example 2: Authentication Security Focus

```
User: Check authentication security

Codex: Running authentication-focused security audit...

**JWT Token Analysis**:
✅ Algorithm: HS256 (secure)
✅ Secret Key: From environment (SECRET_KEY)
✅ Signature Validation: Properly verified
⚠️  Expiration: 24 hours (recommend 15-60 minutes)
✅ Refresh Token: Separate logic implemented

**Password Security**:
✅ Hashing: bcrypt with automatic salting
✅ Complexity: Minimum 8 chars, requires letters + numbers
✅ Reset Flow: Token-based with 15-minute expiration
❌ Password History: Not checking previous passwords

**Session Management**:
✅ Timeout: 30 minutes of inactivity
⚠️  Cookie Flags: Missing HttpOnly on some cookies
✅ Logout: Properly invalidates session
❌ Concurrent Sessions: Not limiting simultaneous logins

**Brute Force Protection**:
❌ Rate Limiting: Not implemented
❌ Account Lockout: No lockout after failed attempts
⚠️  Monitoring: Login failures logged but no alerting

**Recommendations**:
1. Reduce JWT expiration to 60 minutes
2. Add password history check (last 5 passwords)
3. Implement rate limiting (5 attempts per 15 minutes)
4. Add account lockout after 10 failed attempts
5. Set HttpOnly flag on all authentication cookies
6. Limit concurrent sessions to 3 devices
```

### Example 3: Pre-Deployment Security Check

```
User: We're deploying to production tomorrow, run security check

Codex: Running pre-deployment security audit...

**Production Readiness Check**:

❌ **Critical** - Debug mode still enabled in config
   Fix: Set ENV=production in .env

❌ **Critical** - CORS allows all origins (allow_origins=["*"])
   Fix: Set specific origin whitelist in production config

⚠️  **High** - Database connection not using SSL
   Fix: Add ?sslmode=require to POSTGRES_HOST connection string

⚠️  **High** - No rate limiting on API endpoints
   Fix: Implement slowapi or FastAPI limiter

⚠️  **Medium** - JWT token expiration too long (24h)
   Fix: Reduce to 1 hour for production

⚠️  **Medium** - Missing security headers
   Fix: Add security headers middleware:
   - X-Content-Type-Options: nosniff
   - X-Frame-Options: DENY
   - X-XSS-Protection: 1; mode=block
   - Strict-Transport-Security: max-age=31536000

✅ All dependencies up to date
✅ No hardcoded secrets found
✅ Authentication properly implemented
✅ Input validation comprehensive

🔒 **Pre-Deployment Security Score**: 68/100

⚠️  **WARNING**: 2 critical issues must be fixed before production deployment!

**Deployment Checklist**:
1. ❌ Set ENV=production
2. ❌ Configure production CORS whitelist
3. ⚠️  Enable database SSL
4. ⚠️  Add rate limiting
5. ✅ Review all environment variables
6. ✅ Verify SECRET_KEY is strong
7. ⚠️  Add security headers
8. ✅ Disable debug endpoints
```

## Security Tools Integration

### Dependency Scanners
```bash
# Install security tools
source venv/bin/activate && pip install safety pip-audit bandit

# Safety - Check against vulnerability database
source venv/bin/activate && safety check --json

# pip-audit - PyPI Advisory Database
source venv/bin/activate && pip-audit --format json

# Bandit - Python security linter
source venv/bin/activate && bandit -r app/ -f json
```

### Static Code Analysis
```bash
# Bandit security linter
source venv/bin/activate && bandit -r app/ \
  -ll \  # Only high severity
  -f custom \
  --msg-template "{abspath}:{line}: [{test_id}] {msg}"
```

## Security Best Practices

### DO ✅
- Use environment variables for secrets
- Implement proper authentication/authorization
- Validate all user inputs with Pydantic
- Use parameterized queries (SQLAlchemy ORM)
- Enable HTTPS in production
- Hash passwords with bcrypt/argon2
- Set secure cookie flags (HttpOnly, Secure, SameSite)
- Implement rate limiting
- Log security events
- Keep dependencies up to date
- Use secrets module for cryptographic randomness

### DON'T ❌
- Hardcode secrets in code
- Use weak hashing (MD5, SHA1)
- Enable debug mode in production
- Allow CORS from all origins
- Expose stack traces to users
- Use string concatenation for SQL queries
- Store passwords in plaintext
- Skip input validation
- Ignore security warnings
- Use random module for security tokens

## OWASP Top 10 Quick Reference

### A01: Broken Access Control
```python
# ❌ BAD: No authorization check
@router.get("/users/{user_id}/profile")
async def get_profile(user_id: int):
    return await get_user_profile(user_id)

# ✅ GOOD: Verify user can access this resource
@router.get("/users/{user_id}/profile")
async def get_profile(
    user_id: int,
    current_user: User = Depends(get_current_user)
):
    if current_user.id != user_id and not current_user.is_admin:
        raise APIException(status_code=403, message="Forbidden")
    return await get_user_profile(user_id)
```

### A02: Cryptographic Failures
```python
# ❌ BAD: Weak hashing
import hashlib
password_hash = hashlib.md5(password.encode()).hexdigest()

# ✅ GOOD: Strong hashing with bcrypt
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
password_hash = pwd_context.hash(password)
```

### A03: Injection
```python
# ❌ BAD: SQL injection vulnerable
query = f"SELECT * FROM users WHERE email = '{email}'"
result = await db.execute(query)

# ✅ GOOD: Parameterized query
query = text("SELECT * FROM users WHERE email = :email")
result = await db.execute(query, {"email": email})

# ✅ BEST: Use ORM
result = await db.execute(
    select(User).where(User.email == email)
)
```

### A07: Authentication Failures
```python
# ❌ BAD: No rate limiting
@router.post("/auth/login")
async def login(credentials: LoginSchema):
    return await authenticate(credentials)

# ✅ GOOD: With rate limiting
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)

@router.post("/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, credentials: LoginSchema):
    return await authenticate(credentials)
```

## Performance Targets

| Metric | Target | Actual (avg) |
|--------|--------|--------------|
| Total execution time | < 240s | 180s |
| Dependency scan | < 40s | 30s |
| Code analysis | < 80s | 60s |
| Authentication review | < 50s | 40s |
| API security check | < 60s | 50s |
| Database review | < 40s | 30s |
| Configuration audit | < 30s | 20s |
| OWASP compliance | < 50s | 40s |

## Troubleshooting

### Issue: Safety/pip-audit not installed
```bash
Error: ModuleNotFoundError: No module named 'safety'

Solution:
source venv/bin/activate && pip install safety pip-audit bandit
```

### Issue: False positives in security scan
```bash
Warning: Bandit reports false positive

Solution:
# Add # nosec comment to suppress specific warnings
password = get_password_from_env()  # nosec B105
```

## Response Template

```
🔒 Security Audit Report: {project_name}

**Scan Date**: {timestamp}
**Scope**: {modules_scanned}

**Severity Breakdown**:
🔴 Critical: {critical_count}
🟠 High: {high_count}
🟡 Medium: {medium_count}
🟢 Low: {low_count}

**Dependency Vulnerabilities**:
{vulnerability_details}

**Code Security Issues**:
{code_issues_with_locations}

**OWASP Top 10 Compliance**:
{compliance_matrix}

**Security Score**: {score}/100

**Critical Issues** (Fix Immediately):
{critical_issues}

**High Priority** (Fix Soon):
{high_priority_issues}

**Recommendations**:
{improvement_suggestions}

Total Time: {total_time}s
```

## Project-Specific Notes

**Current Project (prepwise)**:
- FastAPI framework
- SQLAlchemy async ORM
- PostgreSQL database
- JWT authentication
- Docker deployment
- Redis caching
- Celery background tasks

**Security Priorities**:
1. Protect user authentication data
2. Prevent SQL injection (use ORM)
3. Validate all API inputs
4. Secure Docker configuration
5. Monitor dependency vulnerabilities
6. Enable production security headers

## Success Criteria

- ✅ No critical vulnerabilities
- ✅ OWASP Top 10 compliance ≥80%
- ✅ All dependencies up to date
- ✅ No hardcoded secrets
- ✅ Authentication properly implemented
- ✅ Input validation comprehensive
- ✅ Error handling secure
- ✅ Production configuration reviewed
- ✅ Security score ≥75/100
