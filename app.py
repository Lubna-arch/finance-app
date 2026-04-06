"""
app.py - Main Flask application entry point

Run with:
    python app.py
"""

from flask import Flask, jsonify
from datetime import timedelta
from database import init_db
from routes.users   import users_bp
from routes.records import records_bp
from routes.summary import summary_bp
from routes.auth    import auth_bp


def create_app():
    app = Flask(__name__)

    # ── Security config ───────────────────────────────────────────────────────
    # SECRET_KEY signs the session cookie so it can't be tampered with.
    # Change this to a long random string in production!
    app.config["SECRET_KEY"]               = "finance-app-secret-key-change-in-production"
    app.config["SESSION_COOKIE_HTTPONLY"]  = True    # JS can't read the session cookie
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"   # CSRF protection
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)  # Session lasts 7 days
    app.config["JSON_SORT_KEYS"]           = False

    # ── Register blueprints ───────────────────────────────────────────────────
    app.register_blueprint(auth_bp)       # /auth/login, /auth/me, /auth/logout
    app.register_blueprint(users_bp)      # /users
    app.register_blueprint(records_bp)    # /records
    app.register_blueprint(summary_bp)    # /summary

    # ── Health check ──────────────────────────────────────────────────────────
    @app.route("/", methods=["GET"])
    def health():
        return jsonify({
            "status" : "ok",
            "service": "Finance Data Processing & Access Control System",
            "version": "2.0.0",
            "auth"   : [
                "POST /auth/login   → login and start session",
                "GET  /auth/me      → who am I?",
                "POST /auth/logout  → logout and clear session"
            ],
            "endpoints": {
                "users"  : ["POST /users", "GET /users", "PUT /users/<id>"],
                "records": ["POST /records", "GET /records", "PUT /records/<id>",
                            "DELETE /records/<id>", "GET /records/export"],
                "summary": ["GET /summary/totals", "GET /summary/balance",
                            "GET /summary/categories", "GET /summary/monthly",
                            "GET /summary/alerts", "GET /summary/top-spenders",
                            "GET /summary/overview"]
            }
        }), 200

    # ── Global error handlers ─────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Endpoint not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "Internal server error"}), 500

    return app


if __name__ == "__main__":
    init_db()
    app = create_app()

    from waitress import serve
    print("\n🚀 Finance API running at http://127.0.0.1:8000")
    serve(app, host="0.0.0.0", port=8000)