from database import init_db, get_connection
from app import create_app
from waitress import serve
import os

# Initialize database on startup
init_db()

# Seed if no users exist
conn = get_connection()
try:
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
finally:
    conn.close()

if user_count == 0:
    print("🌱 No users found — seeding database...")
    from seed import seed
    seed()
else:
    print(f"✅ Database already has {user_count} users")

app = create_app()
port = int(os.environ.get("PORT", 8000))
print(f"🚀 Server running on port {port}")
serve(app, host="0.0.0.0", port=port)