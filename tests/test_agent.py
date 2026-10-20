"""Agent loop with the model mocked out. Needs the database from docker compose."""

import json

import httpx
import pytest

from app import agent


def model_returning(*replies):
    """A fake Ollama: each call returns the next reply (a dict) or an HTTP status (int)."""
    queue = list(replies)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["messages"])
        reply = queue.pop(0)
        if isinstance(reply, int):
            return httpx.Response(reply)
        return httpx.Response(200, json={"message": {"content": reply}})

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def sql(q):
    return f"-- test query\n{q}"


@pytest.fixture(autouse=True)
def _db_available():
    try:
        agent.schema_context()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"database not running: {e}")


def test_happy_path_returns_rows_and_a_chart():
    client, _ = model_returning(sql("SELECT channel, count(*) AS orders FROM orders GROUP BY channel ORDER BY channel"))
    a = agent.ask("orders per channel", client)
    assert a.error is None
    assert a.columns == ["channel", "orders"]
    assert [r[0] for r in a.rows] == ["in_store", "online"]
    assert a.chart == {"type": "bar", "x": ["channel"], "series": ["orders"]}
    assert "LIMIT 500" in a.sql


def test_guard_rejection_is_sent_back_and_repaired():
    client, seen = model_returning(sql("DELETE FROM orders"), sql("SELECT count(*) FROM orders"))
    a = agent.ask("how many orders", client)
    assert a.error is None and a.rows[0][0] > 0
    assert len(a.attempts) == 2 and "Only SELECT" in a.attempts[0].error
    assert "That query failed" in seen[1][-1]["content"]


def test_database_error_is_repaired():
    client, _ = model_returning(sql("SELECT nope FROM orders"), sql("SELECT count(*) FROM orders"))
    a = agent.ask("how many orders", client)
    assert a.error is None
    assert "nope" in a.attempts[0].error


def test_gives_up_after_one_repair():
    client, _ = model_returning(sql("DROP TABLE orders"), sql("DROP TABLE orders"))
    a = agent.ask("drop it", client)
    assert a.error and a.rows == []


def test_model_can_decline():
    client, _ = model_returning("CANNOT_ANSWER: Not a data question.")
    a = agent.ask("what's the weather", client)
    assert not a.answerable and a.sql is None
    assert a.explanation == "Not a data question."


def test_parse_reply_handles_fences_and_plain_text():
    assert agent.parse_reply("-- count\nSELECT 1") == (True, "SELECT 1", "count")
    assert agent.parse_reply("Here you go:\n```sql\nSELECT 1\nFROM stores\n```") == (True, "SELECT 1\nFROM stores", "Here you go:")
    assert agent.parse_reply("CANNOT_ANSWER: writes are not allowed")[0] is False


def test_model_http_error_counts_as_a_failed_attempt():
    client, _ = model_returning(500, sql("SELECT count(*) FROM stores"))
    a = agent.ask("how many stores", client)
    assert a.error is None and a.rows == [[10]]


def test_year_and_month_become_the_chart_label_not_a_series():
    from app.chart import suggest_chart
    chart = suggest_chart(["year", "month", "total_revenue"], [[2025, 1, 10.0], [2025, 2, 12.0]])
    assert chart == {"type": "line", "x": ["year", "month"], "series": ["total_revenue"]}
    assert suggest_chart(["store_id", "orders"], [[1, 5], [2, 7]]) is None
