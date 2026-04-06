"""
seed.py - Populate the database with sample data for testing.

Run after init_db():
    python seed.py
"""

import sqlite3
from database import get_connection, init_db

def seed():
    init_db()
    conn = get_connection()

    # Clear existing data (for a clean seed)
    conn.execute("DELETE FROM records")
    conn.execute("DELETE FROM users")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('users','records')")
    conn.commit()

    # ── Seed users ────────────────────────────────────────────────────────────
    users = [
        (1, "Alice Admin",  "admin",   "active"),
        (2, "Bob Analyst",  "analyst", "active"),
        (3, "Vera Viewer",  "viewer",  "active"),
        (4, "Dave Analyst", "analyst", "inactive"),
    ]
    conn.executemany(
        "INSERT INTO users (id, name, role, status) VALUES (?, ?, ?, ?)", users
    )

    # ── Seed financial records ────────────────────────────────────────────────
    records = [
        # (amount, type, category, date, note, user_id)
        (5000.00, "income",  "Salary",      "2024-01-05", "January salary",     1),
        (1200.00, "expense", "Rent",         "2024-01-10", "Monthly rent",       1),
        (200.50,  "expense", "Groceries",   "2024-01-15", "Weekly groceries",   1),
        (3500.00, "income",  "Freelance",   "2024-01-20", "Website project",    2),
        (450.00,  "expense", "Utilities",   "2024-01-22", "Electricity & water",2),
        (5000.00, "income",  "Salary",      "2024-02-05", "February salary",    1),
        (1200.00, "expense", "Rent",         "2024-02-10", "Monthly rent",       1),
        (300.00,  "expense", "Travel",      "2024-02-18", "Train tickets",      2),
        (800.00,  "income",  "Bonus",       "2024-02-25", "Performance bonus",  1),
        (150.00,  "expense", "Groceries",   "2024-03-03", None,                 3),
        (60.00,   "expense", "Subscription","2024-03-10", "Streaming services", 3),
        (5000.00, "income",  "Salary",      "2024-03-05", "March salary",       1),
        (2000.00, "income",  "Consulting",  "2024-03-15", "Strategy workshop",  2),
        (900.00,  "expense", "Electronics", "2024-03-20", "Headphones",         2),
    ]
    conn.executemany(
        "INSERT INTO records (amount, type, category, date, note, user_id) VALUES (?,?,?,?,?,?)",
        records
    )

    conn.commit()
    conn.close()
    print("✅ Database seeded successfully!")
    print("   Users created:  4  (IDs 1–4)")
    print("   Records created: 14")
    print()
    print("   Use these user IDs in the X-User-ID header:")
    print("     1 → Alice Admin  (admin,   active)")
    print("     2 → Bob Analyst  (analyst, active)")
    print("     3 → Vera Viewer  (viewer,  active)")
    print("     4 → Dave Analyst (analyst, INACTIVE — will be rejected)")

if __name__ == "__main__":
    seed()