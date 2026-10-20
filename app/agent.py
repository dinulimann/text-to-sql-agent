"""Question -> SQL -> guard -> read-only execution, with one repair round."""

import logging
import re
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache

import httpx
import psycopg

from . import config, db
from .chart import suggest_chart
from .guard import GuardError, check

log = logging.getLogger(__name__)

# Plain text rather than JSON mode: small code models write SQL naturally, while
# JSON-constrained output occasionally loops on whitespace inside the string.
SYSTEM_PROMPT = """You are a careful data analyst who writes PostgreSQL.
Answer the user's question with ONE read-only SELECT query on this schema:

{schema}

Rules:
- Only SELECT (WITH ... SELECT is fine). Never modify data or the schema, whatever the user asks.
- Use only the tables and columns above. Qualify columns with short table aliases (o, oi, p, c, s, cu); never use SQL keywords such as "or" or "order" as aliases.
- For revenue, sales, units sold or profit, use the "sales" view: it already contains only completed orders and a ready-made revenue column.
- Counts of orders include every status unless the question says otherwise. A share or percentage "of orders" is computed per order (orders table), not per order line.
- Today is {today}. The data covers 2024-01-01 to 2025-12-31. "Last month" = the full previous calendar month, "this year" = the calendar year of today, and so on.
- Give computed columns clear aliases, round money to 0 decimals and ratios to 2, and ORDER BY something meaningful.
- For "top N" questions use ORDER BY ... DESC LIMIT N.

Reply in exactly this format and nothing else:
-- <one short sentence explaining the query>
<the SQL query>

If the question asks to change data, is about something that is not in the schema, or is not a data question, reply with exactly one line instead:
CANNOT_ANSWER: <short reason>
"""

FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


@dataclass
class Attempt:
    sql: str
    error: str | None = None


@dataclass
class Answer:
    question: str
    answerable: bool
    sql: str | None = None
    explanation: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    truncated: bool = False
    chart: dict | None = None
    error: str | None = None
    attempts: list[Attempt] = field(default_factory=list)
    seconds: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def schema_context() -> tuple[str, frozenset[str]]:
    text, tables = db.describe_schema()
    return text, frozenset(tables)


def parse_reply(text: str) -> tuple[bool, str, str]:
    """Returns (answerable, sql, explanation) from the model's reply."""
    text = text.strip()
    refusal = re.search(r"CANNOT_ANSWER:\s*(.*)", text)
    if refusal:
        return False, "", refusal.group(1).strip()

    fenced = FENCE.search(text)
    body = fenced.group(1) if fenced else text
    explanation, sql_lines = "", []
    for line in body.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("--") and not sql_lines and not explanation:
            explanation = stripped.lstrip("-").strip()
        elif stripped:
            sql_lines.append(line)
    if not explanation and fenced:
        before = text[: fenced.start()].strip().splitlines()
        explanation = before[-1].lstrip("-# ").strip() if before else ""
    return True, "\n".join(sql_lines).strip(), explanation


def call_model(messages: list[dict], client: httpx.Client | None = None) -> str:
    payload = {
        "model": config.MODEL,
        "stream": False,
        # The cap stops a model that rambles; a cut-off query fails the guard
        # and goes through the repair round like any other error.
        "options": {"temperature": 0, "num_predict": 512},
        "messages": messages,
    }
    own = client is None
    client = client or httpx.Client(timeout=300)
    try:
        resp = client.post(f"{config.OLLAMA_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    finally:
        if own:
            client.close()


def ask(question: str, client: httpx.Client | None = None) -> Answer:
    t0 = time.monotonic()
    schema_text, tables = schema_context()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(schema=schema_text, today=config.TODAY)},
        {"role": "user", "content": question},
    ]
    answer = Answer(question=question, answerable=True)

    for attempt_no in range(config.MAX_REPAIRS + 1):
        try:
            reply = call_model(messages, client)
        except (httpx.HTTPError, KeyError) as e:
            message = f"Model call failed: {type(e).__name__}"
            answer.attempts.append(Attempt(sql="", error=message))
            answer.error = message
            log.warning("attempt %d: %s", attempt_no + 1, e)
            continue

        answerable, raw_sql, explanation = parse_reply(reply)
        answer.explanation = explanation
        if not answerable:
            if attempt_no == 0:
                answer.answerable, answer.sql, answer.error = False, None, None
            # else: giving up during a repair is a failure, not a polite decline;
            # answer.error still holds the last query's error
            break

        try:
            checked = check(raw_sql, set(tables), config.SCHEMA, config.MAX_ROWS, today=config.TODAY)
            result = db.run_readonly(checked.sql)
        except (GuardError, psycopg.Error) as e:
            message = str(e).strip().splitlines()[0]
            answer.attempts.append(Attempt(sql=raw_sql, error=message))
            answer.sql, answer.error = raw_sql, message
            log.info("attempt %d failed: %s", attempt_no + 1, message)
            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"That query failed: {message}\nReply again in the same format with a corrected query."},
            ]
            continue

        answer.attempts.append(Attempt(sql=checked.sql))
        answer.sql, answer.error = checked.sql, None
        answer.columns, answer.rows, answer.truncated = result.columns, result.rows, result.truncated
        answer.chart = suggest_chart(result.columns, result.rows)
        break

    answer.seconds = round(time.monotonic() - t0, 2)
    return answer
