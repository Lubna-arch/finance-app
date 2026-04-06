"""
routes/auth.py - Session & Cookie based Authentication

How it works:
  1. POST /auth/login  → user sends their user_id + name
                         server verifies them in DB
                         stores user_id in a server-side Flask session
                         sets a remember_me cookie if requested
  2. GET  /auth/me     → returns current logged-in user from session
  3. POST /auth/logout → clears the session and cookie

Why sessions AND cookies?
  - Session  : stored SERVER-side (secure, can't be tampered with)
  - Cookie   : stored CLIENT-side (used to remember the user between browser restarts)
  - Together : session holds the truth, cookie holds a convenience token
"""

from flask import Blueprint, request, jsonify, session, make_response, g
from database import get_connection, row_to_dict
from datetime import timedelta

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# Cookie settings
COOKIE_NAME     = "finance_user"
COOKIE_MAX_AGE  = 60 * 60 * 24 * 7   # 7 days in seconds


# ── POST /auth/login ──────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Login with user_id.
    Body (JSON): { "user_id": 1, "remember_me": true }

    - Creates a server-side session
    - Optionally sets a persistent cookie (remember_me=true)

    Example:
      POST /auth/login
      { "user_id": 1, "remember_me": true }
    """
    data    = request.get_json(silent=True) or {}
    user_id = data.get("user_id")

    if not user_id or not isinstance(user_id, int) or user_id <= 0:
        return jsonify({"error": "user_id is required and must be a positive integer"}), 400

    # Look up the user in DB
    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ? AND status = 'active'", (user_id,)
    ).fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "User not found or account is inactive"}), 403

    user_dict = row_to_dict(user)

    # ── Store in server-side session ──────────────────────────────────────────
    session.clear()
    session["user_id"]   = user_dict["id"]
    session["user_name"] = user_dict["name"]
    session["role"]      = user_dict["role"]
    session.permanent    = True   # Respects PERMANENT_SESSION_LIFETIME in config

    # ── Build response ────────────────────────────────────────────────────────
    response_data = {
        "message"  : f"Welcome, {user_dict['name']}! You are logged in.",
        "user"     : {
            "id"    : user_dict["id"],
            "name"  : user_dict["name"],
            "role"  : user_dict["role"],
            "status": user_dict["status"]
        },
        "session"  : "active",
        "cookie"   : "set" if data.get("remember_me") else "not set"
    }

    resp = make_response(jsonify(response_data), 200)

    # ── Set cookie if remember_me=true ────────────────────────────────────────
    if data.get("remember_me"):
        resp.set_cookie(
            COOKIE_NAME,
            value    = str(user_dict["id"]),
            max_age  = COOKIE_MAX_AGE,      # Expires in 7 days
            httponly = True,                # JS cannot read it (XSS protection)
            samesite = "Lax"               # CSRF protection
        )

    return resp


# ── GET /auth/me ──────────────────────────────────────────────────────────────
@auth_bp.route("/me", methods=["GET"])
def get_me():
    """
    Returns the currently logged-in user based on session or cookie.
    No X-User-ID header needed — uses session/cookie automatically.

    Priority: session first → cookie fallback → 401
    """
    user_id = None

    # 1. Check server-side session first (most secure)
    if "user_id" in session:
        user_id = session["user_id"]

    # 2. Fall back to remember_me cookie
    elif request.cookies.get(COOKIE_NAME):
        cookie_val = request.cookies.get(COOKIE_NAME)
        if cookie_val and cookie_val.isdigit():
            user_id = int(cookie_val)
            # Restore session from cookie (re-login transparently)
            conn  = get_connection()
            user  = conn.execute(
                "SELECT * FROM users WHERE id = ? AND status = 'active'", (user_id,)
            ).fetchone()
            conn.close()
            if user:
                user_dict            = row_to_dict(user)
                session["user_id"]   = user_dict["id"]
                session["user_name"] = user_dict["name"]
                session["role"]      = user_dict["role"]
                session.permanent    = True

    if not user_id:
        return jsonify({
            "error" : "Not logged in. Please POST /auth/login first.",
            "hint"  : "Send { user_id: 1 } to /auth/login"
        }), 401

    # Fetch fresh user data from DB
    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ? AND status = 'active'", (user_id,)
    ).fetchone()
    conn.close()

    if not user:
        session.clear()
        return jsonify({"error": "Session user no longer exists or is inactive"}), 403

    u = row_to_dict(user)
    return jsonify({
        "logged_in"   : True,
        "auth_method" : "session" if "user_id" in session else "cookie",
        "user"        : {
            "id"    : u["id"],
            "name"  : u["name"],
            "role"  : u["role"],
            "status": u["status"]
        },
        "permissions" : _get_permissions(u["role"])
    }), 200


# ── POST /auth/logout ─────────────────────────────────────────────────────────
@auth_bp.route("/logout", methods=["POST"])
def logout():
    """
    Logs out the current user.
    - Clears the server-side session
    - Deletes the remember_me cookie
    """
    user_name = session.get("user_name", "User")

    # Clear server-side session
    session.clear()

    # Clear the cookie by setting it with max_age=0
    resp = make_response(jsonify({
        "message": f"{user_name} logged out successfully.",
        "session": "cleared",
        "cookie" : "deleted"
    }), 200)

    resp.set_cookie(
        COOKIE_NAME,
        value   = "",
        max_age = 0      # Immediately expire the cookie
    )

    return resp


# ── Helper ────────────────────────────────────────────────────────────────────
def _get_permissions(role: str) -> dict:
    """Return a human-readable permissions map for the given role."""
    perms = {
        "admin": {
            "create_users"   : True,
            "manage_users"   : True,
            "create_records" : True,
            "edit_records"   : True,
            "delete_records" : True,
            "view_records"   : True,
            "view_dashboard" : True,
            "export_csv"     : True,
        },
        "analyst": {
            "create_users"   : False,
            "manage_users"   : False,
            "create_records" : False,
            "edit_records"   : False,
            "delete_records" : False,
            "view_records"   : True,
            "view_dashboard" : True,
            "export_csv"     : True,
        },
        "viewer": {
            "create_users"   : False,
            "manage_users"   : False,
            "create_records" : False,
            "edit_records"   : False,
            "delete_records" : False,
            "view_records"   : True,   # own records only
            "view_dashboard" : False,
            "export_csv"     : False,
        }
    }
    return perms.get(role, {})