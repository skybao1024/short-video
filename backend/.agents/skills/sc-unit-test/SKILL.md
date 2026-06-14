---
name: sc:unit-test
description: Execute pytest unit tests with coverage analysis and automatic test generation
---

# Unit Testing Skill (sc:unit-test)

**Fast, comprehensive unit testing with pytest, coverage analysis, and intelligent test generation.**

## Purpose

Automate unit testing workflow for Python code with:
- Pytest test execution and reporting
- Code coverage analysis (≥80% target)
- Automatic test generation for untested functions
- Test quality validation
- Quick feedback loop for TDD workflow

## Core Differences from sc:api-test

| Feature | sc:unit-test | sc:api-test |
|---------|--------------|-------------|
| **Scope** | Function/class level | API endpoint level |
| **Speed** | Very fast (5-10s) | Medium (60s) |
| **Coverage** | Code coverage metrics | Database validation |
| **Environment** | Virtual env only | Docker + Database |
| **Focus** | Business logic | Integration testing |

## Auto-Trigger Detection

This skill automatically activates when:

```yaml
trigger_conditions:
  file_patterns:
    - "app/services/**/*.py"      # Service layer
    - "app/schemas/**/*.py"        # Pydantic schemas
    - "app/models/**/*.py"         # Database models
    - "app/utils/**/*.py"          # Utility functions

  keywords_in_conversation:
    - "write tests"
    - "unit test"
    - "test coverage"
    - "pytest"
    - "写测试"
    - "单元测试"

  context_signals:
    - New function/class created
    - Service layer modification
    - User mentions testing
    - Coverage below threshold
```

## Testing Workflow

### Step 1: Analyze Target Code (10s)
```python
# Read the file that was written/edited
# Identify:
- Functions to test (public methods, service methods)
- Dependencies and imports
- Expected behavior and edge cases
- Existing test file location (tests/test_*.py)
```

### Step 2: Check Existing Tests (5s)
```bash
# Check if test file exists
ls tests/test_services/test_auth_service.py

# If exists, analyze coverage gaps
source venv/bin/activate && pytest --cov=app.services.auth_service \
  --cov-report=term-missing tests/test_services/test_auth_service.py
```

### Step 3: Generate/Update Tests (30s)
```python
# For app/services/client/auth_service.py

# Test structure:
import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.services.client.auth_service import AuthService
from app.exceptions.http_exceptions import APIException

@pytest.fixture
def auth_service():
    """Create AuthService instance for testing"""
    return AuthService()

@pytest.fixture
def mock_db_session():
    """Mock database session"""
    return AsyncMock()

class TestAuthService:
    """Test suite for AuthService"""

    @pytest.mark.asyncio
    async def test_register_user_success(
        self, auth_service, mock_db_session
    ):
        """Test successful user registration"""
        # Arrange
        user_data = {
            "email": "test@example.com",
            "password": "Test123!",
            "first_name": "Test",
            "last_name": "User"
        }

        # Act
        result = await auth_service.register_user(
            mock_db_session, user_data
        )

        # Assert
        assert result is not None
        assert result.email == user_data["email"]
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_user_duplicate_email(
        self, auth_service, mock_db_session
    ):
        """Test user registration with duplicate email"""
        # Arrange
        user_data = {"email": "existing@example.com"}
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = Mock()

        # Act & Assert
        with pytest.raises(APIException) as exc_info:
            await auth_service.register_user(mock_db_session, user_data)

        assert exc_info.value.status_code == 400
        assert "already exists" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_login_user_invalid_credentials(
        self, auth_service, mock_db_session
    ):
        """Test login with invalid credentials"""
        # Arrange
        credentials = {
            "email": "test@example.com",
            "password": "wrong_password"
        }

        # Act & Assert
        with pytest.raises(APIException) as exc_info:
            await auth_service.login_user(mock_db_session, credentials)

        assert exc_info.value.status_code == 400
```

### Step 4: Run Tests (10s)
```bash
# Activate virtual environment and run pytest
source venv/bin/activate && pytest tests/test_services/test_auth_service.py -v \
  --cov=app.services.auth_service \
  --cov-report=term-missing \
  --cov-report=html

# Output example:
# test_register_user_success ✓
# test_register_user_duplicate_email ✓
# test_login_user_invalid_credentials ✓
#
# Coverage: 85%
# Missing lines: 45-48 (error handling)
```

### Step 5: Report Results (5s)
```
📊 Unit Test Report: app/services/client/auth_service.py

**Test Execution**:
✅ 3 tests passed
❌ 0 tests failed
⏭️  0 tests skipped

**Code Coverage**:
Overall: 85% (target: ≥80%)
✅ register_user: 92%
✅ login_user: 88%
⚠️  refresh_token: 65% (below threshold)

**Missing Coverage**:
- Lines 45-48: Exception handling for token refresh
- Lines 67-70: Edge case for expired refresh token

**Recommendations**:
1. Add test for refresh_token edge cases
2. Test exception handling paths
3. Add integration test for token expiration

Total Time: 60s
```

## Available Tools & Resources

### Primary Tools
- **pytest**: Test framework with async support
- **pytest-cov**: Coverage analysis
- **pytest-asyncio**: Async test support
- **unittest.mock**: Mocking framework
- **Bash**: Run tests in virtual environment
- **Read**: Analyze source code
- **Write/Edit**: Generate/update test files

### Testing Patterns

#### Pattern 1: Service Layer Testing
```python
# Test async service methods with database mocks
@pytest.mark.asyncio
async def test_service_method(mock_db):
    service = MyService()
    result = await service.method(mock_db, data)
    assert result.id is not None
```

#### Pattern 2: Schema Validation Testing
```python
# Test Pydantic schema validation
def test_schema_validation():
    with pytest.raises(ValidationError):
        UserSchema(email="invalid_email")
```

#### Pattern 3: Exception Testing
```python
# Test custom APIException handling
def test_exception_handling():
    with pytest.raises(APIException) as exc_info:
        raise_error()
    assert exc_info.value.status_code == 400
```

## Usage Examples

### Example 1: Manual Invocation After Implementation

```
User: I just implemented the user profile service, /unit-test

Codex: I'll create comprehensive unit tests for the user profile service.

**Step 1: Analyze Code**
[Reads: app/services/client/profile_service.py]
Found methods:
- get_user_profile(user_id)
- update_user_profile(user_id, data)
- delete_user_profile(user_id)

**Step 2: Check Existing Tests**
[Checks: tests/test_services/test_profile_service.py]
❌ Test file not found - creating new

**Step 3: Generate Tests**
[Writes: tests/test_services/test_profile_service.py]
Created 9 test cases:
- test_get_user_profile_success
- test_get_user_profile_not_found
- test_update_user_profile_success
- test_update_user_profile_invalid_data
- test_update_user_profile_not_found
- test_delete_user_profile_success
- test_delete_user_profile_not_found
- test_update_profile_duplicate_email
- test_profile_validation_edge_cases

**Step 4: Run Tests**
[Runs: pytest tests/test_services/test_profile_service.py -v --cov]
=========== test session starts ===========
collected 9 items

test_get_user_profile_success ✓
test_get_user_profile_not_found ✓
test_update_user_profile_success ✓
test_update_user_profile_invalid_data ✓
test_update_user_profile_not_found ✓
test_delete_user_profile_success ✓
test_delete_user_profile_not_found ✓
test_update_profile_duplicate_email ✓
test_profile_validation_edge_cases ✓

Coverage: 92%

📊 **Test Summary**: All tests passed ✅
Coverage exceeds 80% target ✅
```

### Example 2: Auto-Triggered for Low Coverage

```
User: [Modifies app/services/client/order_service.py]

Codex: [Detects service layer change]
I'll run unit tests to verify your changes.

**Step 2: Check Coverage**
[Runs: pytest --cov=app.services.order_service]
⚠️  Coverage: 65% (below 80% target)

**Missing Coverage**:
- calculate_order_total (not tested)
- apply_discount (not tested)
- validate_order_items (partially tested)

**Step 3: Generate Missing Tests**
[Writes additional test cases]
Added 5 new tests:
- test_calculate_order_total_basic
- test_calculate_order_total_with_tax
- test_apply_discount_percentage
- test_apply_discount_fixed_amount
- test_validate_order_items_empty

**Step 4: Re-run Tests**
[Runs: pytest with new tests]
Coverage: 88% ✅

📊 **Test Summary**: Coverage improved to 88% ✅
```

### Example 3: TDD Workflow

```
User: I need to implement a password reset service, write tests first

Codex: I'll create tests following TDD approach.

**Step 1: Define Test Cases**
Based on requirements:
1. Generate reset token for valid email
2. Reject reset for non-existent email
3. Validate token expiration (15 minutes)
4. Reset password with valid token
5. Reject expired/invalid tokens

**Step 2: Write Tests**
[Writes: tests/test_services/test_password_reset.py]
Created 5 failing tests (TDD red phase)

**Step 3: Run Tests**
[Runs: pytest tests/test_services/test_password_reset.py]
=========== 5 failed ===========

✅ Tests ready for implementation
Next: Implement password reset service to pass these tests
```

## Test Quality Standards

### Test Structure (AAA Pattern)
```python
def test_method_name():
    # Arrange - Setup test data and mocks
    data = {"key": "value"}
    mock = Mock()

    # Act - Execute the function being tested
    result = function_under_test(data, mock)

    # Assert - Verify the results
    assert result.expected_field == expected_value
    mock.method.assert_called_once()
```

### Coverage Requirements
- **Service Layer**: ≥85% coverage
- **Schemas**: ≥90% coverage (Pydantic validation)
- **Utility Functions**: ≥80% coverage
- **Models**: ≥70% coverage (basic CRUD)

### Test Categories
1. **Happy Path**: Normal successful execution
2. **Edge Cases**: Boundary values, empty inputs
3. **Error Handling**: Exceptions, validation failures
4. **Integration Points**: Mock external dependencies

## Integration with Development Workflow

### Workflow 1: TDD Development
```
1. User: "Implement feature X using TDD"
2. Codex: [Writes failing tests first]
3. Codex: [Implements minimum code to pass tests]
4. Codex: [Refactors with tests as safety net]
5. Codex: [Reports final coverage]
```

### Workflow 2: Post-Implementation Testing
```
1. User: [Implements new feature]
2. User: "/unit-test"
3. Codex: [Generates comprehensive tests]
4. Codex: [Runs tests and reports coverage]
5. Codex: [Suggests improvements if coverage low]
```

### Workflow 3: Regression Testing
```
1. User: "Run all unit tests"
2. Codex: [Runs: pytest tests/ -v]
3. Codex: [Reports any failures]
4. Codex: [Analyzes failed tests and suggests fixes]
```

## Performance Targets

| Metric | Target | Actual (avg) |
|--------|--------|--------------|
| Total execution time | < 90s | 60s |
| Code analysis | < 15s | 10s |
| Test generation | < 40s | 30s |
| Test execution | < 30s | 15s |
| Coverage analysis | < 10s | 5s |

## Best Practices

### DO ✅
- Follow AAA pattern (Arrange-Act-Assert)
- Use descriptive test names
- Mock external dependencies (DB, APIs)
- Test both success and failure paths
- Aim for ≥80% code coverage
- Use pytest fixtures for reusable setup
- Test edge cases and boundary values

### DON'T ❌
- Don't test framework code (SQLAlchemy, FastAPI)
- Don't skip error handling tests
- Don't use real database connections
- Don't write interdependent tests
- Don't ignore coverage warnings
- Don't test implementation details

## Pytest Configuration

### pytest.ini
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --cov=app
    --cov-report=term-missing
    --cov-report=html
    --cov-fail-under=80
markers =
    asyncio: async tests
    unit: unit tests
    integration: integration tests
```

### Coverage Configuration (.coveragerc)
```ini
[run]
source = app
omit =
    */tests/*
    */migrations/*
    */__init__.py
    */config.py

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
```

## Common Testing Patterns

### Pattern 1: Async Service Testing
```python
@pytest.mark.asyncio
async def test_async_service_method():
    mock_db = AsyncMock()
    service = MyService()
    result = await service.method(mock_db)
    assert result is not None
```

### Pattern 2: Database Transaction Testing
```python
@pytest.mark.asyncio
async def test_transaction_rollback():
    mock_db = AsyncMock()
    mock_db.rollback = AsyncMock()

    with pytest.raises(Exception):
        await service.failing_method(mock_db)

    mock_db.rollback.assert_called_once()
```

### Pattern 3: Pydantic Validation Testing
```python
def test_schema_validation_error():
    with pytest.raises(ValidationError) as exc_info:
        UserSchema(email="invalid", password="short")

    errors = exc_info.value.errors()
    assert len(errors) == 2
    assert errors[0]["loc"] == ("email",)
```

### Pattern 4: APIException Testing
```python
def test_api_exception_handling():
    with pytest.raises(APIException) as exc_info:
        service.method_that_raises()

    assert exc_info.value.status_code == 400
    assert "error message" in exc_info.value.message
```

## Troubleshooting

### Issue: ImportError in tests
```bash
Error: ModuleNotFoundError: No module named 'app'

Solution:
# Ensure virtual environment is activated
source venv/bin/activate
# Check PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Issue: Async tests not running
```bash
Error: SyntaxError: 'await' outside async function

Solution:
# Install pytest-asyncio
source venv/bin/activate && pip install pytest-asyncio
# Mark tests with @pytest.mark.asyncio
```

### Issue: Coverage not calculated
```bash
Error: Coverage.py warning: No data was collected

Solution:
# Check pytest.ini configuration
# Ensure source path is correct: source = app
# Run with explicit coverage flag
pytest --cov=app tests/
```

## Response Template

```
📊 Unit Test Report: {module_path}

**Test Execution**:
✅ Passed: {passed_count}
❌ Failed: {failed_count}
⏭️  Skipped: {skipped_count}

**Code Coverage**:
Overall: {overall_coverage}% (target: ≥80%)
{per_function_coverage}

**Missing Coverage**:
{missing_lines_and_branches}

**Test Quality**:
✅ AAA pattern: {aaa_compliance}
✅ Edge cases: {edge_case_coverage}
✅ Error handling: {error_test_coverage}
✅ Mocking: {mock_usage}

**Recommendations**:
{improvement_suggestions}

Total Time: {total_time}s
```

## Project-Specific Notes

**Current Project (prepwise)**:
- Python 3.9+ with async/await
- FastAPI framework
- SQLAlchemy async ORM
- Pydantic v2 schemas
- pytest + pytest-asyncio
- Virtual environment required

**Testing Conventions**:
- Test files in `tests/` directory
- Mirror source structure (tests/test_services/)
- Use AsyncMock for database sessions
- Test APIException status codes
- Validate Pydantic schemas
- Mock external services (AWS S3, Email)

## Success Criteria

- ✅ All tests pass
- ✅ Coverage ≥80% for service layer
- ✅ Coverage ≥90% for schemas
- ✅ All edge cases tested
- ✅ Error handling validated
- ✅ Mocks used for external dependencies
- ✅ AAA pattern followed
- ✅ Clear test documentation
