"""
middleware.py - Role-Based Access Control (RBAC) and validation utilities

Authentication priority (checked in this order):
  1. Server-side SESSION  → set by POST /auth/login
  2. Remember-me COOKIE   → set when remember_me=true on login
  3. X-User-ID HEADER     → original method, still works for API clients / Postman

This means:
  - Browser users   → login once via /auth/login, session handles everything
  - API/Postman users → can still pass X-User-ID header directly (no login needed)

Role permissions:
  admin   → full access
  analyst → read records + dashboard, no writes
  viewer  → own records only, no dashboard, no writes
"""

from functools import wraps
from flask import request, jsonify, g, session
from database import get_connection, row_to_dict

# ── Role constants ────────────────────────────────────────────────────────────
ADMIN   = "admin"
ANALYST = "analyst"
VIEWER  = "viewer"

COOKIE_NAME = "finance_user"


def load_current_user():
    """
    Resolve the current user from session, cookie, or X-User-ID header.
    Returns (user_dict, None) on success, or (None, error_response) on failure.

    Priority: session → cookie → X-User-ID header
    """
    user_id = None
    auth_method = None

    # 1. Check server-side session (most secure)
    if "user_id" in session:
        user_id     = session["user_id"]
        auth_method = "session"

    # 2. Check remember_me cookie
    elif request.cookies.get(COOKIE_NAME):
        cookie_val = request.cookies.get(COOKIE_NAME)
        if cookie_val and cookie_val.isdigit():
            user_id     = int(cookie_val)
            auth_method = "cookie"

    # 3. Fall back to X-User-ID header (Postman / API clients)
    elif request.headers.get("X-User-ID"):
        header_val = request.headers.get("X-User-ID")
        if not header_val.isdigit():
            return None, (jsonify({"error": "X-User-ID must be a positive integer"}), 400)
        user_id     = int(header_val)
        auth_method = "header"

    # 4. Nothing found
    if not user_id:
        return None, (jsonify({
            "error"  : "Authentication required.",
            "options": [
                "Login via POST /auth/login (sets session + optional cookie)",
                "Pass X-User-ID header directly (for API/Postman use)"
            ]
        }), 401)

    # Look up user in database
    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ? AND status = 'active'", (user_id,)
    ).fetchone()
    conn.close()

    if not user:
        if auth_method == "session":
            session.clear()
        return None, (jsonify({"error": "User not found or account is inactive"}), 403)

    user_dict = row_to_dict(user)
    user_dict["_auth_method"] = auth_method
    return user_dict, None


def require_roles(*allowed_roles):
    """
    Decorator: restricts a route to users whose role is in allowed_roles.
    Checks session → cookie → X-User-ID header automatically.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user, err = load_current_user()
            if err:
                return err
            if user["role"] not in allowed_roles:
                return jsonify({
                    "error"         : "Access denied.",
                    "your_role"     : user["role"],
                    "required_roles": list(allowed_roles)
                }), 403
            g.current_user = user
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── Convenience decorators ────────────────────────────────────────────────────

def admin_only(f):
    return require_roles(ADMIN)(f)

def admin_or_analyst(f):
    return require_roles(ADMIN, ANALYST)(f)

def any_role(f):
    return require_roles(ADMIN, ANALYST, VIEWER)(f)


# ── Input validation helpers ──────────────────────────────────────────────────

def validate_fields(data, required_fields):
    missing = [
        f for f in required_fields
        if f not in data or data[f] is None or str(data[f]).strip() == ""
    ]
    if missing:
        return False, f"Missing or empty required fields: {missing}"
    return True, None


def validate_amount(value):
    try:
        amount = float(value)
        if amount <= 0:
            raise ValueError()
        return amount, None
    except (TypeError, ValueError):
        return None, "amount must be a positive number"


def validate_date(value):
    from datetime import datetime
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value, None
    except (TypeError, ValueError):
        return None, "date must be in YYYY-MM-DD format"