"""The model writes the SQL, so these guard what it is allowed to run."""
import duckdb
import pytest

from engine import MAX_ROWS, check, connect, run


@pytest.mark.parametrize("sql", [
    "SELECT count(*) FROM orders",
    "WITH o AS (SELECT * FROM orders) SELECT count(*) FROM o",
    "SELECT 1 UNION SELECT 2",
])
def test_allows_a_single_select(sql):
    check(sql)


@pytest.mark.parametrize("sql", [
    "DROP TABLE orders",
    "DELETE FROM orders",
    "INSERT INTO sellers VALUES ('x', '1', 'x', 'SP')",
    "CREATE TABLE t (x INT)",
    "UPDATE orders SET order_status = 'x'",
    "SELECT 1; DROP TABLE orders",
    "ATTACH 'other.db'",
    "COPY orders TO 'out.csv'",
    "PRAGMA database_list",
])
def test_rejects_anything_else(sql):
    with pytest.raises(ValueError):
        check(sql)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM '/etc/passwd'",
    "SELECT * FROM read_text('https://example.com')",
])
def test_cannot_read_files_or_urls(sql):
    with pytest.raises(duckdb.Error):
        run(sql)


def test_database_is_read_only():
    with pytest.raises(duckdb.Error):
        connect().execute("CREATE TABLE t (x INT)")


def test_results_are_capped():
    assert len(run("SELECT * FROM order_items")) == MAX_ROWS
