"""
routes/records.py - Financial records endpoints

Endpoints:
  POST   /records         → Create a record          [admin only]
  GET    /records         → List/filter records       [admin, analyst, viewer]
  PUT    /records/<id>    → Update a record           [admin only]
  DELETE /records/<id>    → Soft-delete a record      [admin only]
  GET    /records/export  → Export records as CSV     [admin, analyst]
"""

import csv
import io
from flask import Blueprint, request, jsonify, g, Response
from database import get_connection, row_to_dict, rows_to_list
from middleware import admin_only, any_role, admin_or_analyst, validate_fields, validate_amount, validate_date

records_bp = Blueprint("records", __name__, url_prefix="/records")

VALID_TYPES = {"income", "expense"}
DEFAULT_PAGE_SIZE = 20


# ── POST /records ─────────────────────────────────────────────────────────────
@records_bp.route("", methods=["POST"])
@admin_only
def create_record():
    """
    Create a new financial record.
    Body (JSON): { amount, type, category, date, user_id, note? }
    """
    data = request.get_json(silent=True) or {}

    ok, err = validate_fields(data, ["amount", "type", "category", "date", "user_id"])
    if not ok:
        return jsonify({"error": err}), 400

    # Validate amount
    amount, err = validate_amount(data["amount"])
    if err:
        return jsonify({"error": err}), 400

    # Validate type
    rec_type = str(data["type"]).strip().lower()
    if rec_type not in VALID_TYPES:
        return jsonify({"error": f"type must be one of: {sorted(VALID_TYPES)}"}), 400

    # Validate date
    date, err = validate_date(data["date"])
    if err:
        return jsonify({"error": err}), 400

    category = str(data["category"]).strip()
    note     = str(data.get("note", "")).strip() or None
    user_id  = data["user_id"]

    if not isinstance(user_id, int) or user_id <= 0:
        return jsonify({"error": "user_id must be a positive integer"}), 400

    conn = get_connection()
    try:
        # Verify the target user exists
        user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return jsonify({"error": f"User {user_id} not found"}), 404

        cursor = conn.execute(
            """INSERT INTO records (amount, type, category, date, note, user_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (amount, rec_type, category, date, note, user_id)
        )
        conn.commit()
        new_id = cursor.lastrowid

        record = conn.execute(
            "SELECT * FROM records WHERE id = ?", (new_id,)
        ).fetchone()
        return jsonify(row_to_dict(record)), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# ── GET /records ──────────────────────────────────────────────────────────────
@records_bp.route("", methods=["GET"])
@any_role
def get_records():
    """
    Retrieve records with optional filters and pagination.
    Query params:
      - user_id    : filter by user
      - type       : income | expense
      - category   : text filter (exact match)
      - date_from  : YYYY-MM-DD
      - date_to    : YYYY-MM-DD
      - page       : page number (default 1)
      - page_size  : records per page (default 20, max 100)

    Viewer restriction: viewers can only see their OWN records.
    """
    current_user = g.current_user

    # -- Parse filters --
    user_id_filter   = request.args.get("user_id",   type=int)
    type_filter      = request.args.get("type")
    category_filter  = request.args.get("category")
    date_from        = request.args.get("date_from")
    date_to          = request.args.get("date_to")
    page             = max(1, request.args.get("page", 1, type=int))
    page_size        = min(100, max(1, request.args.get("page_size", DEFAULT_PAGE_SIZE, type=int)))
    offset           = (page - 1) * page_size

    query  = "SELECT * FROM records WHERE is_deleted = 0"
    params = []

    # Viewers are locked to their own records only
    if current_user["role"] == "viewer":
        query  += " AND user_id = ?"
        params.append(current_user["id"])
    elif user_id_filter:
        query  += " AND user_id = ?"
        params.append(user_id_filter)

    if type_filter:
        if type_filter not in VALID_TYPES:
            return jsonify({"error": f"type must be one of: {sorted(VALID_TYPES)}"}), 400
        query  += " AND type = ?"
        params.append(type_filter)

    if category_filter:
        query  += " AND LOWER(category) = LOWER(?)"
        params.append(category_filter)

    if date_from:
        _, err = validate_date(date_from)
        if err:
            return jsonify({"error": f"date_from: {err}"}), 400
        query  += " AND date >= ?"
        params.append(date_from)

    if date_to:
        _, err = validate_date(date_to)
        if err:
            return jsonify({"error": f"date_to: {err}"}), 400
        query  += " AND date <= ?"
        params.append(date_to)

    query += " ORDER BY date DESC, id DESC"

    conn = get_connection()
    try:
        # Count total matching records (for pagination metadata)
        count_query = query.replace("SELECT *", "SELECT COUNT(*)", 1)
        total = conn.execute(count_query, params).fetchone()[0]

        # Paginated results
        paginated_query = query + " LIMIT ? OFFSET ?"
        records = conn.execute(paginated_query, params + [page_size, offset]).fetchall()

        return jsonify({
            "total"      : total,
            "page"       : page,
            "page_size"  : page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "records"    : rows_to_list(records)
        }), 200
    finally:
        conn.close()


# ── GET /records/<id> ────────────────────────────────────────────────────────
@records_bp.route("/<int:record_id>", methods=["GET"])
@any_role
def get_record(record_id):
    """
    Get a single record by its ID.
    Viewer restriction: viewers can only fetch their own records.

    Example: GET /records/1
    """
    current_user = g.current_user

    conn = get_connection()
    try:
        record = conn.execute(
            """SELECT r.*, u.name AS user_name, u.role AS user_role
               FROM records r
               JOIN users u ON r.user_id = u.id
               WHERE r.id = ? AND r.is_deleted = 0""",
            (record_id,)
        ).fetchone()

        if not record:
            return jsonify({"error": f"Record {record_id} not found"}), 404

        record_dict = row_to_dict(record)

        # Viewers can only see their own records
        if current_user["role"] == "viewer" and record_dict["user_id"] != current_user["id"]:
            return jsonify({"error": "Access denied. You can only view your own records."}), 403

        return jsonify(record_dict), 200
    finally:
        conn.close()


# ── PUT /records/<id> ─────────────────────────────────────────────────────────
@records_bp.route("/<int:record_id>", methods=["PUT"])
@admin_only
def update_record(record_id):
    """
    Update any field of an existing record.
    Body (JSON): any subset of { amount, type, category, date, note }
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "Request body is empty"}), 400

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM records WHERE id = ? AND is_deleted = 0", (record_id,)
        ).fetchone()
        if not existing:
            return jsonify({"error": f"Record {record_id} not found"}), 404

        # Build dynamic SET clause from provided fields
        updates = {}

        if "amount" in data:
            amount, err = validate_amount(data["amount"])
            if err:
                return jsonify({"error": err}), 400
            updates["amount"] = amount

        if "type" in data:
            rec_type = str(data["type"]).strip().lower()
            if rec_type not in VALID_TYPES:
                return jsonify({"error": f"type must be one of: {sorted(VALID_TYPES)}"}), 400
            updates["type"] = rec_type

        if "category" in data:
            updates["category"] = str(data["category"]).strip()

        if "date" in data:
            date, err = validate_date(data["date"])
            if err:
                return jsonify({"error": err}), 400
            updates["date"] = date

        if "note" in data:
            updates["note"] = str(data["note"]).strip() or None

        if not updates:
            return jsonify({"error": "No valid fields provided for update"}), 400

        updates["updated_at"] = "CURRENT_TIMESTAMP"
        set_clause = ", ".join(
            f"{col} = CURRENT_TIMESTAMP" if val == "CURRENT_TIMESTAMP" else f"{col} = ?"
            for col, val in updates.items()
        )
        values = [v for v in updates.values() if v != "CURRENT_TIMESTAMP"]
        values.append(record_id)

        conn.execute(f"UPDATE records SET {set_clause} WHERE id = ?", values)
        conn.commit()

        updated = conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        return jsonify(row_to_dict(updated)), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# ── GET /records/export ───────────────────────────────────────────────────────
@records_bp.route("/export", methods=["GET"])
@admin_or_analyst
def export_records_csv():
    """
    Export records as a downloadable CSV file.
    Supports the same filters as GET /records:
      - user_id, type, category, date_from, date_to

    Example: GET /records/export?type=expense&date_from=2024-01-01
    """
    current_user = g.current_user

    # Parse filters (same logic as GET /records)
    user_id_filter  = request.args.get("user_id",  type=int)
    type_filter     = request.args.get("type")
    category_filter = request.args.get("category")
    date_from       = request.args.get("date_from")
    date_to         = request.args.get("date_to")

    query  = """
        SELECT r.id, u.name AS user_name, u.role, r.amount, r.type,
               r.category, r.date, r.note, r.created_at
        FROM records r
        JOIN users u ON r.user_id = u.id
        WHERE r.is_deleted = 0
    """
    params = []

    if user_id_filter:
        query  += " AND r.user_id = ?"
        params.append(user_id_filter)

    if type_filter:
        if type_filter not in ("income", "expense"):
            return jsonify({"error": "type must be 'income' or 'expense'"}), 400
        query  += " AND r.type = ?"
        params.append(type_filter)

    if category_filter:
        query  += " AND LOWER(r.category) = LOWER(?)"
        params.append(category_filter)

    if date_from:
        _, err = validate_date(date_from)
        if err:
            return jsonify({"error": f"date_from: {err}"}), 400
        query  += " AND r.date >= ?"
        params.append(date_from)

    if date_to:
        _, err = validate_date(date_to)
        if err:
            return jsonify({"error": f"date_to: {err}"}), 400
        query  += " AND r.date <= ?"
        params.append(date_to)

    query += " ORDER BY r.date DESC"

    conn    = get_connection()
    records = conn.execute(query, params).fetchall()
    conn.close()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow(["ID", "User", "Role", "Amount", "Type", "Category", "Date", "Note", "Created At"])

    # Data rows
    for r in records:
        writer.writerow([
            r["id"], r["user_name"], r["role"],
            r["amount"], r["type"], r["category"],
            r["date"], r["note"] or "", r["created_at"]
        ])

    # Send as downloadable file
    output.seek(0)
    filename = f"finance_records_export.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ── DELETE /records/<id> ──────────────────────────────────────────────────────
@records_bp.route("/<int:record_id>", methods=["DELETE"])
@admin_only
def delete_record(record_id):
    """
    Soft-delete a record (sets is_deleted = 1, data is preserved in DB).
    """
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM records WHERE id = ? AND is_deleted = 0", (record_id,)
        ).fetchone()
        if not existing:
            return jsonify({"error": f"Record {record_id} not found"}), 404

        conn.execute(
            "UPDATE records SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (record_id,)
        )
        conn.commit()
        return jsonify({"message": f"Record {record_id} deleted successfully"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()