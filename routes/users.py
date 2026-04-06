"""
routes/users.py - User management endpoints

Endpoints:
  POST   /users          → Create a new user         [admin only]
  GET    /users          → List all users             [admin only]
  PUT    /users/<id>     → Update user status         [admin only]
"""

from flask import Blueprint, request, jsonify
from database import get_connection, row_to_dict, rows_to_list
from middleware import admin_only, validate_fields

users_bp = Blueprint("users", __name__, url_prefix="/users")

VALID_ROLES    = {"admin", "analyst", "viewer"}
VALID_STATUSES = {"active", "inactive"}


# ── POST /users ───────────────────────────────────────────────────────────────
@users_bp.route("", methods=["POST"])
@admin_only
def create_user():
    """
    Create a new user.
    Body (JSON): { "name": str, "role": str }
    Role must be one of: admin, analyst, viewer
    """
    data = request.get_json(silent=True) or {}

    # Validate required fields
    ok, err = validate_fields(data, ["name", "role"])
    if not ok:
        return jsonify({"error": err}), 400

    name = str(data["name"]).strip()
    role = str(data["role"]).strip().lower()

    if role not in VALID_ROLES:
        return jsonify({"error": f"role must be one of: {sorted(VALID_ROLES)}"}), 400

    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, role) VALUES (?, ?)",
            (name, role)
        )
        conn.commit()
        new_id = cursor.lastrowid

        # Return the newly created user
        user = conn.execute("SELECT * FROM users WHERE id = ?", (new_id,)).fetchone()
        return jsonify(row_to_dict(user)), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# ── GET /users ────────────────────────────────────────────────────────────────
@users_bp.route("", methods=["GET"])
@admin_only
def get_users():
    """
    Retrieve all users.
    Optional query params:
      - role   : filter by role   (admin/analyst/viewer)
      - status : filter by status (active/inactive)
    """
    role_filter   = request.args.get("role")
    status_filter = request.args.get("status")

    query  = "SELECT * FROM users WHERE 1=1"
    params = []

    if role_filter:
        if role_filter not in VALID_ROLES:
            return jsonify({"error": f"role must be one of: {sorted(VALID_ROLES)}"}), 400
        query  += " AND role = ?"
        params.append(role_filter)

    if status_filter:
        if status_filter not in VALID_STATUSES:
            return jsonify({"error": f"status must be one of: {sorted(VALID_STATUSES)}"}), 400
        query  += " AND status = ?"
        params.append(status_filter)

    query += " ORDER BY id ASC"

    conn  = get_connection()
    users = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify({
        "total": len(users),
        "users": rows_to_list(users)
    }), 200


# ── PUT /users/<id> ───────────────────────────────────────────────────────────
@users_bp.route("/<int:user_id>", methods=["PUT"])
@admin_only
def update_user_status(user_id):
    """
    Update a user's status (active / inactive).
    Body (JSON): { "status": "active" | "inactive" }
    Admins cannot deactivate themselves.
    """
    from flask import g

    data = request.get_json(silent=True) or {}

    ok, err = validate_fields(data, ["status"])
    if not ok:
        return jsonify({"error": err}), 400

    status = str(data["status"]).strip().lower()
    if status not in VALID_STATUSES:
        return jsonify({"error": f"status must be one of: {sorted(VALID_STATUSES)}"}), 400

    # Prevent admin from deactivating their own account
    if user_id == g.current_user["id"] and status == "inactive":
        return jsonify({"error": "You cannot deactivate your own account"}), 403

    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not existing:
            return jsonify({"error": f"User {user_id} not found"}), 404

        conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
        conn.commit()

        updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return jsonify(row_to_dict(updated)), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()