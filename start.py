from database import init_db
from app import create_app
from waitress import serve
import os

# Initialize database on startup
init_db()

# Run seed only if database is empty
from database import get_connection
conn = get_connection()
user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
conn.close()

if user_count == 0:
    from seed import seed
    seed()

app = create_app()
port = int(os.environ.get("PORT", 8000))
print(f"🚀 Server running on port {port}")
serve(app, host="0.0.0.0", port=port)