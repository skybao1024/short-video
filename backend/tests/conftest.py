import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-enough-length")
os.environ.setdefault("DATA_REGION", "EU")
os.environ.setdefault(
    "API_KEYS_JSON",
    '{"partner-eu-1":{"secret":"test-secret","enabled":true}}',
)
