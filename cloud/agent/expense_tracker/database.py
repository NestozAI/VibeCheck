import sqlite3
from datetime import datetime, date
from typing import List, Optional, Tuple
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")

CATEGORIES = [
    "Food",
    "Transportation",
    "Shopping",
    "Culture/Leisure",
    "Utilities",
    "Medical",
    "Education",
    "Other"
]


def get_connection():
    """SQLite database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database and create tables"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def add_expense(expense_date: date, amount: float, category: str, description: str = "") -> int:
    """Add new transaction"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO expenses (date, amount, category, description)
        VALUES (?, ?, ?, ?)
    """, (expense_date.isoformat(), amount, category, description))

    expense_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return expense_id


def get_all_expenses() -> List[dict]:
    """Get all transactions"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, date, amount, category, description, created_at
        FROM expenses
        ORDER BY date DESC, id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_expenses_by_month(year: int, month: int) -> List[dict]:
    """Get transactions for a specific month"""
    conn = get_connection()
    cursor = conn.cursor()

    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"

    cursor.execute("""
        SELECT id, date, amount, category, description, created_at
        FROM expenses
        WHERE date >= ? AND date < ?
        ORDER BY date DESC, id DESC
    """, (start_date, end_date))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_recent_expenses(limit: int = 10) -> List[dict]:
    """Get recent transactions"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, date, amount, category, description, created_at
        FROM expenses
        ORDER BY date DESC, id DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def delete_expense(expense_id: int) -> bool:
    """Delete transaction"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))

    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return deleted


def update_expense(expense_id: int, expense_date: date, amount: float,
                   category: str, description: str = "") -> bool:
    """Update transaction"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE expenses
        SET date = ?, amount = ?, category = ?, description = ?
        WHERE id = ?
    """, (expense_date.isoformat(), amount, category, description, expense_id))

    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return updated


def get_category_totals(year: int, month: int) -> List[Tuple[str, float]]:
    """Monthly totals by category"""
    conn = get_connection()
    cursor = conn.cursor()

    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"

    cursor.execute("""
        SELECT category, SUM(amount) as total
        FROM expenses
        WHERE date >= ? AND date < ?
        GROUP BY category
        ORDER BY total DESC
    """, (start_date, end_date))

    rows = cursor.fetchall()
    conn.close()

    return [(row['category'], row['total']) for row in rows]


def get_daily_totals(year: int, month: int) -> List[Tuple[str, float]]:
    """Monthly daily totals"""
    conn = get_connection()
    cursor = conn.cursor()

    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"

    cursor.execute("""
        SELECT date, SUM(amount) as total
        FROM expenses
        WHERE date >= ? AND date < ?
        GROUP BY date
        ORDER BY date ASC
    """, (start_date, end_date))

    rows = cursor.fetchall()
    conn.close()

    return [(row['date'], row['total']) for row in rows]


def get_monthly_total(year: int, month: int) -> float:
    """Monthly total expenses"""
    conn = get_connection()
    cursor = conn.cursor()

    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"

    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) as total
        FROM expenses
        WHERE date >= ? AND date < ?
    """, (start_date, end_date))

    result = cursor.fetchone()
    conn.close()

    return result['total']


def add_sample_data():
    """Add sample data"""
    from datetime import timedelta
    import random

    # Skip if data already exists
    if len(get_all_expenses()) > 0:
        return

    today = date.today()

    sample_expenses = [
        # Food
        ("Food", "Lunch", 12000, 15000),
        ("Food", "Dinner", 15000, 25000),
        ("Food", "Coffee", 4500, 6000),
        ("Food", "Convenience store", 3000, 8000),
        ("Food", "Grocery shopping", 30000, 80000),
        # Transportation
        ("Transportation", "Subway", 1400, 2800),
        ("Transportation", "Bus", 1400, 2800),
        ("Transportation", "Taxi", 8000, 20000),
        # Shopping
        ("Shopping", "Clothing", 30000, 100000),
        ("Shopping", "Household items", 10000, 30000),
        # Culture/Leisure
        ("Culture/Leisure", "Movie", 14000, 16000),
        ("Culture/Leisure", "Netflix", 13500, 17000),
        ("Culture/Leisure", "Book purchase", 15000, 25000),
        # Utilities
        ("Utilities", "Electricity", 30000, 60000),
        ("Utilities", "Water", 15000, 30000),
        ("Utilities", "Phone/Internet", 50000, 70000),
        # Medical
        ("Medical", "Hospital", 10000, 50000),
        ("Medical", "Pharmacy", 5000, 20000),
        # Education
        ("Education", "Online course", 30000, 100000),
        ("Education", "Books", 20000, 40000),
    ]

    # Generate about 30 random transactions for this month
    for day in range(1, min(today.day + 1, 28)):
        # 1-4 transactions per day
        num_expenses = random.randint(1, 4)
        expense_date = date(today.year, today.month, day)

        for _ in range(num_expenses):
            category, desc, min_amt, max_amt = random.choice(sample_expenses)
            amount = random.randint(min_amt // 100, max_amt // 100) * 100
            add_expense(expense_date, amount, category, desc)


# Initialize DB on module load
init_db()
