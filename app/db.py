from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import psycopg

from . import config


@dataclass
class Result:
    columns: list[str]
    rows: list[list]
    truncated: bool


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def run_readonly(sql: str, max_rows: int = config.MAX_ROWS) -> Result:
    """Runs one query in a read-only transaction with a timeout, then rolls back."""
    with psycopg.connect(config.AGENT_DATABASE_URL, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(f"SET LOCAL statement_timeout = {int(config.STATEMENT_TIMEOUT_MS)}")
            cur.execute(f"SET LOCAL search_path = {config.SCHEMA}")
            cur.execute(sql)
            columns = [c.name for c in cur.description]
            rows = cur.fetchmany(max_rows + 1)
        conn.rollback()
    return Result(
        columns=columns,
        rows=[[_json_safe(v) for v in row] for row in rows[:max_rows]],
        truncated=len(rows) > max_rows,
    )


def describe_schema() -> tuple[str, set[str]]:
    """Builds a compact schema description for the prompt: tables, columns,
    types, keys, comments and the distinct values of small text columns."""
    with psycopg.connect(config.AGENT_DATABASE_URL) as conn:
        cols = conn.execute(
            """
            SELECT c.table_name, c.column_name, c.data_type,
                   col_description(format('%%I.%%I', c.table_schema, c.table_name)::regclass, c.ordinal_position),
                   obj_description(format('%%I.%%I', c.table_schema, c.table_name)::regclass, 'pg_class')
            FROM information_schema.columns c
            WHERE c.table_schema = %s
            ORDER BY c.table_name, c.ordinal_position
            """,
            (config.SCHEMA,),
        ).fetchall()
        # pg_constraint rather than information_schema: the latter only shows
        # constraints to the table owner, and this role only has SELECT.
        fks = conn.execute(
            """
            SELECT src.relname, sa.attname, dst.relname, da.attname
            FROM pg_constraint con
            JOIN pg_class src ON src.oid = con.conrelid
            JOIN pg_class dst ON dst.oid = con.confrelid
            JOIN pg_namespace n ON n.oid = src.relnamespace
            JOIN pg_attribute sa ON sa.attrelid = con.conrelid AND sa.attnum = con.conkey[1]
            JOIN pg_attribute da ON da.attrelid = con.confrelid AND da.attnum = con.confkey[1]
            WHERE con.contype = 'f' AND n.nspname = %s
            """,
            (config.SCHEMA,),
        ).fetchall()

        tables: dict[str, dict] = {}
        for table, column, dtype, col_comment, table_comment in cols:
            t = tables.setdefault(table, {"comment": table_comment, "columns": []})
            t["columns"].append((column, dtype, col_comment))

        # Small enumerations help the model use exact values ('completed', 'online', city names...)
        samples: dict[tuple[str, str], list[str]] = {}
        for table, t in tables.items():
            for column, dtype, _ in t["columns"]:
                if dtype != "text" or column in ("email", "full_name", "name"):
                    continue
                values = conn.execute(
                    f'SELECT DISTINCT "{column}" FROM {config.SCHEMA}."{table}" ORDER BY 1 LIMIT 21'
                ).fetchall()
                if len(values) <= 20:
                    samples[(table, column)] = [v[0] for v in values]

    fk_map = {(t, c): f"{rt}.{rc}" for t, c, rt, rc in fks}
    lines = []
    for table, t in tables.items():
        header = f"TABLE {table}" + (f"  -- {t['comment']}" if t["comment"] else "")
        lines.append(header)
        for column, dtype, comment in t["columns"]:
            notes = []
            if (table, column) in fk_map:
                notes.append(f"references {fk_map[(table, column)]}")
            if comment:
                notes.append(comment)
            if (table, column) in samples:
                notes.append("values: " + ", ".join(repr(v) for v in samples[(table, column)]))
            lines.append(f"  {column} {dtype}" + (f"  -- {'; '.join(notes)}" if notes else ""))
        lines.append("")
    return "\n".join(lines).strip(), set(tables)
