import os
from database import init_db, get_connection
from app import create_app
from waitress import serve

# Step 1 - Initialize DB tables
init_db()

# Step 2 - Always check and seed if empty
conn = get_connection()
try:
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"👥 Users in database: {user_count}")
finally:
    conn.close()

if user_count == 0:
    print("🌱 Database is empty — seeding now...")
    # Seed directly here without importing seed.py
    conn = get_connection()
    try:
        users = [
            (1, "Alice Admin",  "admin",   "active"),
            (2, "Bob Analyst",  "analyst", "active"),
            (3, "Vera Viewer",  "viewer",  "active"),
            (4, "Dave Analyst", "analyst", "inactive"),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO users (id, name, role, status) VALUES (?, ?, ?, ?)", users
        )

        records = [
            (5000.00, "income",  "Salary",      "2024-01-05", "January salary",      1),
            (1200.00, "expense", "Rent",         "2024-01-10", "Monthly rent",        1),
            (200.50,  "expense", "Groceries",   "2024-01-15", "Weekly groceries",    1),
            (3500.00, "income",  "Freelance",   "2024-01-20", "Website project",     2),
            (450.00,  "expense", "Utilities",   "2024-01-22", "Electricity & water", 2),
            (5000.00, "income",  "Salary",      "2024-02-05", "February salary",     1),
            (1200.00, "expense", "Rent",         "2024-02-10", "Monthly rent",        1),
            (300.00,  "expense", "Travel",      "2024-02-18", "Train tickets",       2),
            (800.00,  "income",  "Bonus",       "2024-02-25", "Performance bonus",   1),
            (150.00,  "expense", "Groceries",   "2024-03-03", None,                  3),
            (60.00,   "expense", "Subscription","2024-03-10", "Streaming services",  3),
            (5000.00, "income",  "Salary",      "2024-03-05", "March salary",        1),
            (2000.00, "income",  "Consulting",  "2024-03-15", "Strategy workshop",   2),
            (900.00,  "expense", "Electronics", "2024-03-20", "Headphones",          2),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO records (amount, type, category, date, note, user_id) VALUES (?,?,?,?,?,?)",
            records
        )
        conn.commit()
        print("✅ Database seeded successfully!")
        print("   Users: Alice Admin (1), Bob Analyst (2), Vera Viewer (3), Dave Analyst (4)")
    except Exception as e:
        print(f"❌ Seed error: {e}")
        conn.rollback()
    finally:
        conn.close()
else:
    print("✅ Database already has data — skipping seed")

# Step 3 - Start server
app = create_app()
port = int(os.environ.get("PORT", 8000))
print(f"🚀 Server running on port {port}")
serve(app, host="0.0.0.0", port=port)