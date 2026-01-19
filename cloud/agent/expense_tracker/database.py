import sqlite3
from datetime import datetime, date
from typing import List, Optional, Tuple
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")

CATEGORIES = [
    "식비",
    "교통",
    "쇼핑",
    "문화/여가",
    "공과금",
    "의료",
    "교육",
    "기타"
]


def get_connection():
    """SQLite 데이터베이스 연결"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """데이터베이스 초기화 및 테이블 생성"""
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
    """새 거래 추가"""
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
    """모든 거래 조회"""
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
    """특정 월의 거래 조회"""
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
    """최근 거래 조회"""
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
    """거래 삭제"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))

    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return deleted


def update_expense(expense_id: int, expense_date: date, amount: float,
                   category: str, description: str = "") -> bool:
    """거래 수정"""
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
    """월별 카테고리별 합계"""
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
    """월별 일별 합계"""
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
    """월별 총 지출"""
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
    """샘플 데이터 추가"""
    from datetime import timedelta
    import random

    # 이미 데이터가 있으면 스킵
    if len(get_all_expenses()) > 0:
        return

    today = date.today()

    sample_expenses = [
        # 식비
        ("식비", "점심 식사", 12000, 15000),
        ("식비", "저녁 식사", 15000, 25000),
        ("식비", "커피", 4500, 6000),
        ("식비", "편의점", 3000, 8000),
        ("식비", "마트 장보기", 30000, 80000),
        # 교통
        ("교통", "지하철", 1400, 2800),
        ("교통", "버스", 1400, 2800),
        ("교통", "택시", 8000, 20000),
        # 쇼핑
        ("쇼핑", "옷 구매", 30000, 100000),
        ("쇼핑", "생활용품", 10000, 30000),
        # 문화/여가
        ("문화/여가", "영화", 14000, 16000),
        ("문화/여가", "넷플릭스", 13500, 17000),
        ("문화/여가", "책 구매", 15000, 25000),
        # 공과금
        ("공과금", "전기세", 30000, 60000),
        ("공과금", "수도세", 15000, 30000),
        ("공과금", "통신비", 50000, 70000),
        # 의료
        ("의료", "병원", 10000, 50000),
        ("의료", "약국", 5000, 20000),
        # 교육
        ("교육", "온라인 강의", 30000, 100000),
        ("교육", "책", 20000, 40000),
    ]

    # 이번 달에 랜덤하게 30개 정도의 거래 생성
    for day in range(1, min(today.day + 1, 28)):
        # 하루에 1~4개 거래
        num_expenses = random.randint(1, 4)
        expense_date = date(today.year, today.month, day)

        for _ in range(num_expenses):
            category, desc, min_amt, max_amt = random.choice(sample_expenses)
            amount = random.randint(min_amt // 100, max_amt // 100) * 100
            add_expense(expense_date, amount, category, desc)


# 모듈 로드 시 DB 초기화
init_db()
