"""Static checks on model-written SQL before it reaches the database.

The database role is already read-only; this is the first layer, so that bad
queries are rejected with a clear reason (which is fed back to the model)
instead of a database error.
"""

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

# Functions that read files, sleep, signal other sessions, change settings,
# open remote connections, or run a SQL string passed as an argument.
BLOCKED_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink")
BLOCKED_FUNCTIONS = {
    "set_config", "current_setting", "query_to_xml", "query_to_xml_and_xmlschema",
    "query_to_xmlschema", "table_to_xml", "table_to_xml_and_xmlschema", "cursor_to_xml",
    "database_to_xml", "schema_to_xml", "txid_current", "version",
}


class GuardError(ValueError):
    pass


@dataclass
class CheckedQuery:
    sql: str
    tables: list[str]
    limited: bool  # True when the guard added or lowered the LIMIT


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.this).lower()
    return node.sql_name().lower()


def _pin_today(tree: exp.Expression, today: str) -> exp.Expression:
    """Replaces CURRENT_DATE / NOW() / CURRENT_TIMESTAMP with a fixed date, so
    "last month" means the same thing as in the prompt, whatever the server clock says."""
    def swap(node):
        is_now = isinstance(node, exp.Anonymous) and str(node.this).lower() == "now"
        if isinstance(node, (exp.CurrentDate, exp.CurrentTimestamp)) or is_now:
            return exp.cast(exp.Literal.string(today), "date")
        return node
    return tree.transform(swap)


def check(sql: str, allowed_tables: set[str], schema: str, max_rows: int, today: str | None = None) -> CheckedQuery:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise GuardError("Empty query.")

    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise GuardError(f"Could not parse the SQL: {str(e).splitlines()[0]}") from None

    if len(statements) != 1:
        raise GuardError("Exactly one statement is allowed.")
    tree = statements[0]

    if not isinstance(tree, exp.Query):
        raise GuardError(f"Only SELECT queries are allowed, got {tree.key.upper()}.")

    for node in tree.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop,
                             exp.Alter, exp.Command, exp.TruncateTable, exp.Copy, exp.Set)):
            raise GuardError(f"{node.key.upper()} is not allowed.")
        if isinstance(node, exp.Into):
            raise GuardError("SELECT ... INTO is not allowed.")
        if isinstance(node, exp.Lock):
            raise GuardError("Row locking (FOR UPDATE/SHARE) is not allowed.")
        if isinstance(node, exp.Func):
            name = _function_name(node)
            if name in BLOCKED_FUNCTIONS or name.startswith(BLOCKED_FUNCTION_PREFIXES):
                raise GuardError(f"Function {name}() is not allowed.")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables = []
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_names and not table.db:
            continue
        if table.db and table.db.lower() != schema:
            raise GuardError(f"Only tables in schema '{schema}' are allowed, got {table.db}.{table.name}.")
        if name not in allowed_tables:
            raise GuardError(f"Unknown or forbidden table '{table.name}'. Allowed: {', '.join(sorted(allowed_tables))}.")
        tables.append(name)

    if not tables:
        raise GuardError("The query must read from at least one table.")

    if today:
        tree = _pin_today(tree, today)

    limited = False
    limit = tree.args.get("limit")
    current = None
    if limit is not None:
        value = limit.expression if isinstance(limit, exp.Limit) else None
        if isinstance(value, exp.Literal) and value.is_int:
            current = int(value.this)
    if current is None or current > max_rows:
        tree = tree.limit(max_rows, copy=True)
        limited = True

    return CheckedQuery(sql=tree.sql(dialect="postgres", pretty=True), tables=sorted(set(tables)), limited=limited)
