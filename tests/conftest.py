import os

# Safe test defaults so engine.py import does not require host dotenv files.
os.environ.setdefault("PUBLISH_STATUS", "DRAFT")
os.environ.setdefault("ONE_SOURCE_ONE_SITE", "1")
os.environ.setdefault("PER_RUN_LIMIT", "3")
os.environ.setdefault("DAILY_PUBLISH_LIMIT", "9")
os.environ.setdefault("PER_SITE_PER_RUN_LIMIT", "1")
os.environ.setdefault("ERUM_ENV", "test")
os.environ.setdefault("ERUM_API_BASE", "https://portal.test.example")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "erum_test")
