import pytest

from app.guard import GuardError, check

TABLES = {"orders", "order_items", "customers", "products", "categories", "stores"}


def ok(sql: str, max_rows: int = 500):
    return check(sql, TABLES, "shop", max_rows)


def rejected(sql: str) -> str:
    with pytest.raises(GuardError) as e:
        ok(sql)
    return str(e.value)


def test_plain_select_passes_and_gets_a_limit():
    q = ok("SELECT city, count(*) FROM customers GROUP BY city")
    assert q.tables == ["customers"]
    assert q.limited and "LIMIT 500" in q.sql


def test_existing_small_limit_is_kept_and_large_one_is_capped():
    assert not ok("SELECT * FROM stores LIMIT 5").limited
    assert "LIMIT 500" in ok("SELECT * FROM orders LIMIT 100000").sql


def test_cte_and_schema_qualified_tables_pass():
    q = ok("WITH t AS (SELECT * FROM shop.orders) SELECT count(*) FROM t")
    assert q.tables == ["orders"]


def test_trailing_semicolon_is_fine():
    ok("SELECT 1 FROM stores;")


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "UPDATE products SET unit_price = 0",
    "INSERT INTO categories VALUES (9, 'x')",
    "DROP TABLE orders",
    "TRUNCATE orders",
    "ALTER TABLE orders ADD COLUMN x int",
    "CREATE TABLE x AS SELECT * FROM orders",
    "COPY orders TO '/tmp/x.csv'",
    "SET statement_timeout = 0",
    "GRANT ALL ON orders TO public",
])
def test_non_select_statements_are_rejected(sql):
    rejected(sql)


def test_stacked_statements_are_rejected():
    assert "one statement" in rejected("SELECT 1 FROM orders; DELETE FROM orders")


def test_writes_hidden_in_a_cte_are_rejected():
    rejected("WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d")


def test_select_into_and_row_locks_are_rejected():
    rejected("SELECT * INTO backup FROM orders")
    rejected("SELECT * FROM orders FOR UPDATE")


@pytest.mark.parametrize("fn", ["pg_sleep(10)", "pg_read_file('/etc/passwd')", "set_config('a','b',false)",
                                "query_to_xml('delete from orders', true, true, '')", "dblink('x','y')",
                                "current_setting('data_directory')"])
def test_dangerous_functions_are_rejected(fn):
    assert "not allowed" in rejected(f"SELECT {fn} FROM orders")


def test_other_schemas_and_unknown_tables_are_rejected():
    assert "schema" in rejected("SELECT * FROM pg_catalog.pg_authid")
    assert "schema" in rejected("SELECT * FROM information_schema.tables")
    # pg_catalog is on the search path even when not written out
    assert "forbidden table" in rejected("SELECT * FROM pg_user")
    assert "forbidden table" in rejected("SELECT * FROM users")


def test_garbage_is_rejected():
    rejected("")
    rejected("please show me revenue")


def test_current_date_is_pinned_to_the_configured_today():
    q = check("SELECT count(*) FROM orders WHERE order_date >= CURRENT_DATE - INTERVAL '1 month' AND order_date < now()",
              TABLES, "shop", 500, today="2026-01-01")
    assert "CURRENT_DATE" not in q.sql.upper() and "NOW()" not in q.sql.upper()
    assert q.sql.count("'2026-01-01'") == 2
