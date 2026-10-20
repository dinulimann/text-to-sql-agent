import os

from dotenv import load_dotenv

load_dotenv()

# The agent runs queries as a read-only role; schema introspection uses the same role.
AGENT_DATABASE_URL = os.getenv("AGENT_DATABASE_URL", "postgresql://agent_ro:agent_ro@localhost:5550/shop")
SCHEMA = os.getenv("DB_SCHEMA", "shop")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("MODEL", "qwen2.5-coder:3b")

MAX_ROWS = int(os.getenv("MAX_ROWS", "500"))
STATEMENT_TIMEOUT_MS = int(os.getenv("STATEMENT_TIMEOUT_MS", "5000"))
# 1 = one retry after a guard rejection or database error
MAX_REPAIRS = int(os.getenv("MAX_REPAIRS", "1"))

# The synthetic data ends on 2025-12-31; relative dates ("last month") use this.
TODAY = os.getenv("TODAY", "2026-01-01")
