"""
Database layer for the Alpaca Trading Skill.
SQLite, zero dependencies beyond stdlib.
"""
import sqlite3
import os
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
DB_PATH = SKILL_DIR / "data" / "trading.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # safe concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                api_key     TEXT    NOT NULL,
                api_secret  TEXT    NOT NULL,
                paper       INTEGER NOT NULL DEFAULT 1,
                enabled     INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS trades (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                account_name TEXT    NOT NULL,
                symbol       TEXT    NOT NULL,
                side         TEXT    NOT NULL CHECK(side IN ('buy','sell')),
                qty          REAL    NOT NULL,
                price        REAL,
                timestamp    TEXT    NOT NULL DEFAULT (datetime('now')),
                strategy     TEXT,
                order_id     TEXT,
                pnl          REAL,
                notes        TEXT
            );

            CREATE TABLE IF NOT EXISTS strategy_params (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT    NOT NULL,
                param_key     TEXT    NOT NULL,
                param_value   TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_by    TEXT    NOT NULL DEFAULT 'system',
                UNIQUE(strategy_name, param_key)
            );

            CREATE TABLE IF NOT EXISTS performance_snapshots (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                account_name   TEXT    NOT NULL,
                snapshot_date  TEXT    NOT NULL,
                equity         REAL,
                cash           REAL,
                sharpe_ratio   REAL,
                max_drawdown   REAL,
                win_rate       REAL,
                total_trades   INTEGER,
                profit_factor  REAL,
                notes          TEXT,
                UNIQUE(account_name, snapshot_date)
            );

            CREATE TABLE IF NOT EXISTS analysis_log (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at         TEXT    NOT NULL DEFAULT (datetime('now')),
                account_name   TEXT    NOT NULL,
                strategy_name  TEXT    NOT NULL,
                param_changed  TEXT,
                old_value      TEXT,
                new_value      TEXT,
                metric_trigger TEXT,
                reasoning      TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_trades_account   ON trades(account_name);
            CREATE INDEX IF NOT EXISTS idx_trades_symbol    ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
            CREATE INDEX IF NOT EXISTS idx_snapshots_account ON performance_snapshots(account_name, snapshot_date);
        """)
    conn.close()


# ── Accounts ──────────────────────────────────────────────────────────────────

def save_account(name: str, api_key: str, api_secret: str, paper: bool = True):
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO accounts (name, api_key, api_secret, paper)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                api_key    = excluded.api_key,
                api_secret = excluded.api_secret,
                paper      = excluded.paper,
                enabled    = 1
        """, (name, api_key, api_secret, int(paper)))
    conn.close()


def get_accounts(enabled_only: bool = True) -> list[dict]:
    conn = get_connection()
    q = "SELECT * FROM accounts"
    if enabled_only:
        q += " WHERE enabled = 1"
    rows = conn.execute(q).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_account(name: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Trades ─────────────────────────────────────────────────────────────────────

def log_trade(account_name: str, symbol: str, side: str, qty: float,
              price: float = None, strategy: str = None, order_id: str = None,
              pnl: float = None, notes: str = None):
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO trades (account_name, symbol, side, qty, price, strategy, order_id, pnl, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (account_name, symbol, side, qty, price, strategy, order_id, pnl, notes))
    conn.close()


def get_trades(account_name: str = None, symbol: str = None,
               days: int = None, limit: int = 500) -> list[dict]:
    conn = get_connection()
    q = "SELECT * FROM trades WHERE 1=1"
    params = []
    if account_name:
        q += " AND account_name = ?"
        params.append(account_name)
    if symbol:
        q += " AND symbol = ?"
        params.append(symbol)
    if days:
        q += " AND timestamp >= datetime('now', ?)"
        params.append(f"-{days} days")
    q += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Strategy Params ────────────────────────────────────────────────────────────

def get_param(strategy_name: str, param_key: str, default=None):
    conn = get_connection()
    row = conn.execute(
        "SELECT param_value FROM strategy_params WHERE strategy_name=? AND param_key=?",
        (strategy_name, param_key)
    ).fetchone()
    conn.close()
    return row["param_value"] if row else default


def set_param(strategy_name: str, param_key: str, value, updated_by: str = "system"):
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO strategy_params (strategy_name, param_key, param_value, updated_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(strategy_name, param_key) DO UPDATE SET
                param_value = excluded.param_value,
                updated_at  = datetime('now'),
                updated_by  = excluded.updated_by
        """, (strategy_name, param_key, str(value), updated_by))
    conn.close()


def get_all_params(strategy_name: str) -> dict:
    conn = get_connection()
    rows = conn.execute(
        "SELECT param_key, param_value FROM strategy_params WHERE strategy_name=?",
        (strategy_name,)
    ).fetchall()
    conn.close()
    return {r["param_key"]: r["param_value"] for r in rows}


# ── Performance Snapshots ──────────────────────────────────────────────────────

def save_snapshot(account_name: str, equity: float, cash: float,
                  sharpe_ratio: float = None, max_drawdown: float = None,
                  win_rate: float = None, total_trades: int = None,
                  profit_factor: float = None, notes: str = None,
                  snapshot_date: str = None):
    date = snapshot_date or datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO performance_snapshots
                (account_name, snapshot_date, equity, cash, sharpe_ratio, max_drawdown,
                 win_rate, total_trades, profit_factor, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_name, snapshot_date) DO UPDATE SET
                equity        = excluded.equity,
                cash          = excluded.cash,
                sharpe_ratio  = excluded.sharpe_ratio,
                max_drawdown  = excluded.max_drawdown,
                win_rate      = excluded.win_rate,
                total_trades  = excluded.total_trades,
                profit_factor = excluded.profit_factor,
                notes         = excluded.notes
        """, (account_name, date, equity, cash, sharpe_ratio, max_drawdown,
              win_rate, total_trades, profit_factor, notes))
    conn.close()


def get_snapshots(account_name: str, days: int = 90) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM performance_snapshots
        WHERE account_name = ?
          AND snapshot_date >= date('now', ?)
        ORDER BY snapshot_date ASC
    """, (account_name, f"-{days} days")).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Analysis Log ──────────────────────────────────────────────────────────────

def log_analysis(account_name: str, strategy_name: str, reasoning: str,
                 param_changed: str = None, old_value=None, new_value=None,
                 metric_trigger: str = None):
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO analysis_log
                (account_name, strategy_name, param_changed, old_value, new_value,
                 metric_trigger, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (account_name, strategy_name, param_changed,
              str(old_value) if old_value is not None else None,
              str(new_value) if new_value is not None else None,
              metric_trigger, reasoning))
    conn.close()


def get_analysis_log(account_name: str = None, limit: int = 50) -> list[dict]:
    conn = get_connection()
    q = "SELECT * FROM analysis_log"
    params = []
    if account_name:
        q += " WHERE account_name = ?"
        params.append(account_name)
    q += " ORDER BY run_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at: {DB_PATH}")
