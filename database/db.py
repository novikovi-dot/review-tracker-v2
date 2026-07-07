import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/reviews.db")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            product_name TEXT,
            product_url TEXT,
            matched_id TEXT,
            review_id TEXT,
            rating REAL,
            review_title TEXT,
            review_text TEXT,
            reviewer_name TEXT,
            location TEXT,
            created_date TEXT,
            helpful_votes INTEGER,
            not_helpful_votes INTEGER,
            hair_type TEXT,
            scrape_date TEXT,
            UNIQUE(source, review_id)
        )
    """)

    conn.commit()
    conn.close()


def save_reviews(df, source, product_name, product_url):
    if df is None or df.empty:
        return 0

    init_db()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    scrape_date = datetime.now().strftime("%Y-%m-%d")

    saved_count = 0

    for _, row in df.iterrows():
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO reviews (
                    source,
                    product_name,
                    product_url,
                    matched_id,
                    review_id,
                    rating,
                    review_title,
                    review_text,
                    reviewer_name,
                    location,
                    created_date,
                    helpful_votes,
                    not_helpful_votes,
                    hair_type,
                    scrape_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source,
                product_name,
                product_url,
                row.get("matched_id", ""),
                row.get("review_id", ""),
                row.get("rating", None),
                row.get("review_title", ""),
                row.get("review_text", ""),
                row.get("reviewer_name", ""),
                row.get("location", ""),
                row.get("created_date", ""),
                row.get("helpful_votes", None),
                row.get("not_helpful_votes", None),
                row.get("hair_type", ""),
                scrape_date
            ))

            if cursor.rowcount > 0:
                saved_count += 1

        except Exception:
            continue

    conn.commit()
    conn.close()

    return saved_count


def load_all_reviews():
    init_db()

    conn = sqlite3.connect(DB_PATH)
    df = __import__("pandas").read_sql_query("SELECT * FROM reviews", conn)
    conn.close()

    return df
