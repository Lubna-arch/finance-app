"""
routes/summary.py - Dashboard and analytics endpoints

Endpoints:
  GET /summary/totals          → Income & expense totals per user
  GET /summary/balance         → Net balance (income - expense) per user
  GET /summary/categories      → Category-wise totals
  GET /summary/monthly         → Monthly summary grouped by month
  GET /summary/alerts          → Flag users exceeding expense threshold  ⭐ NEW
  GET /summary/top-spenders    → Highest spenders per category           ⭐ NEW
  GET /summary/overview        → Full dashboard in one single call       ⭐ NEW

Access: admin and analyst only (viewers are restricted from dashboard APIs)
"""

from flask import Blueprint, request, jsonify
from database import get_connection, rows_to_list
from middleware import admin_or_analyst, validate_date

summary_bp = Blueprint("summary", __name__, url_prefix="/summary")


def _date_filters(params: list):
    """
    Helper: parse optional date_from / date_to from request.args.
    Returns (extra_sql_fragment, updated_params, error_response_or_None).
    """
    date_from = request.args.get("date_from")
    date_to   = request.args.get("date_to")
    sql       = ""

    if date_from:
        _, err = validate_date(date_from)
        if err:
            return "", params, ({"error": f"date_from: {err}"}, 400)
        sql += " AND r.date >= ?"
        params.append(date_from)

    if date_to:
        _, err = validate_date(date_to)
        if err:
            return "", params, ({"error": f"date_to: {err}"}, 400)
        sql += " AND r.date <= ?"
        params.append(date_to)

    return sql, params, None


# ── GET /summary/totals ───────────────────────────────────────────────────────
@summary_bp.route("/totals", methods=["GET"])
@admin_or_analyst
def get_totals():
    """
    Total income and total expense per user.
    Optional query params: user_id, date_from, date_to
    """
    params    = []
    where     = "WHERE r.is_deleted = 0"
    user_id   = request.args.get("user_id", type=int)

    if user_id:
        where  += " AND r.user_id = ?"
        params.append(user_id)

    date_sql, params, err = _date_filters(params)
    if err:
        return jsonify(err[0]), err[1]
    where += date_sql

    query = f"""
        SELECT
            u.id        AS user_id,
            u.name      AS user_name,
            u.role,
            COALESCE(SUM(CASE WHEN r.type = 'income'  THEN r.amount ELSE 0 END), 0) AS total_income,
            COALESCE(SUM(CASE WHEN r.type = 'expense' THEN r.amount ELSE 0 END), 0) AS total_expense,
            COUNT(r.id) AS total_records
        FROM users u
        LEFT JOIN records r ON u.id = r.user_id {where}
        GROUP BY u.id, u.name, u.role
        ORDER BY u.id ASC
    """

    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows)), 200


# ── GET /summary/balance ──────────────────────────────────────────────────────
@summary_bp.route("/balance", methods=["GET"])
@admin_or_analyst
def get_balance():
    """
    Net balance (income - expense) per user.
    Optional query params: user_id, date_from, date_to
    """
    params  = []
    where   = "WHERE r.is_deleted = 0"
    user_id = request.args.get("user_id", type=int)

    if user_id:
        where  += " AND r.user_id = ?"
        params.append(user_id)

    date_sql, params, err = _date_filters(params)
    if err:
        return jsonify(err[0]), err[1]
    where += date_sql

    query = f"""
        SELECT
            u.id   AS user_id,
            u.name AS user_name,
            COALESCE(SUM(CASE WHEN r.type = 'income'  THEN r.amount ELSE 0 END), 0) AS total_income,
            COALESCE(SUM(CASE WHEN r.type = 'expense' THEN r.amount ELSE 0 END), 0) AS total_expense,
            COALESCE(SUM(CASE WHEN r.type = 'income'  THEN r.amount
                              WHEN r.type = 'expense' THEN -r.amount
                              ELSE 0 END), 0) AS net_balance
        FROM users u
        LEFT JOIN records r ON u.id = r.user_id {where}
        GROUP BY u.id, u.name
        ORDER BY net_balance DESC
    """

    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows)), 200


# ── GET /summary/categories ───────────────────────────────────────────────────
@summary_bp.route("/categories", methods=["GET"])
@admin_or_analyst
def get_category_totals():
    """
    Totals broken down by category and type.
    Optional query params: user_id, type (income/expense), date_from, date_to
    """
    params      = []
    conditions  = ["r.is_deleted = 0"]
    user_id     = request.args.get("user_id", type=int)
    type_filter = request.args.get("type")

    if user_id:
        conditions.append("r.user_id = ?")
        params.append(user_id)

    if type_filter:
        if type_filter not in ("income", "expense"):
            return jsonify({"error": "type must be 'income' or 'expense'"}), 400
        conditions.append("r.type = ?")
        params.append(type_filter)

    where = "WHERE " + " AND ".join(conditions)
    date_sql, params, err = _date_filters(params)
    if err:
        return jsonify(err[0]), err[1]
    where += date_sql

    query = f"""
        SELECT
            r.category,
            r.type,
            COUNT(r.id)    AS record_count,
            SUM(r.amount)  AS total_amount,
            AVG(r.amount)  AS average_amount
        FROM records r
        {where}
        GROUP BY r.category, r.type
        ORDER BY total_amount DESC
    """

    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    # Round floats for cleaner output
    result = []
    for row in rows:
        d = dict(row)
        d["total_amount"]   = round(d["total_amount"], 2)
        d["average_amount"] = round(d["average_amount"], 2)
        result.append(d)

    return jsonify(result), 200


# ── GET /summary/monthly ──────────────────────────────────────────────────────
@summary_bp.route("/monthly", methods=["GET"])
@admin_or_analyst
def get_monthly_summary():
    """
    Monthly summary: income, expense, and net balance grouped by year-month.
    Optional query params: user_id, year (e.g., 2024), date_from, date_to
    """
    params     = []
    conditions = ["r.is_deleted = 0"]
    user_id    = request.args.get("user_id", type=int)
    year       = request.args.get("year", type=int)

    if user_id:
        conditions.append("r.user_id = ?")
        params.append(user_id)

    if year:
        conditions.append("strftime('%Y', r.date) = ?")
        params.append(str(year))

    where = "WHERE " + " AND ".join(conditions)
    date_sql, params, err = _date_filters(params)
    if err:
        return jsonify(err[0]), err[1]
    where += date_sql

    query = f"""
        SELECT
            strftime('%Y-%m', r.date) AS month,
            COUNT(r.id) AS record_count,
            COALESCE(SUM(CASE WHEN r.type = 'income'  THEN r.amount ELSE 0 END), 0) AS total_income,
            COALESCE(SUM(CASE WHEN r.type = 'expense' THEN r.amount ELSE 0 END), 0) AS total_expense,
            COALESCE(SUM(CASE WHEN r.type = 'income'  THEN  r.amount
                              WHEN r.type = 'expense' THEN -r.amount
                              ELSE 0 END), 0)                                         AS net_balance
        FROM records r
        {where}
        GROUP BY month
        ORDER BY month ASC
    """

    conn = get_connection()
    rows = conn.execute(query, params).fetchall()

    # Fetch user info if filtered by user_id
    scope_label = "all_users"
    user_info   = None
    if user_id:
        u = conn.execute(
            "SELECT id, name, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if u:
            user_info   = {"id": u["id"], "name": u["name"], "role": u["role"]}
            scope_label = f"{u['name']} (ID: {u['id']})"

    conn.close()

    result = []
    for row in rows:
        d = dict(row)
        d["total_income"]  = round(d["total_income"],  2)
        d["total_expense"] = round(d["total_expense"], 2)
        d["net_balance"]   = round(d["net_balance"],   2)
        result.append(d)

    return jsonify({
        "scope" : scope_label,
        "user"  : user_info,        # None if showing all users
        "months": len(result),
        "data"  : result
    }), 200


# ── GET /summary/alerts ───────────────────────────────────────────────────────
@summary_bp.route("/alerts", methods=["GET"])
@admin_or_analyst
def get_spending_alerts():
    """
    ⭐ NEW — Spending Alerts
    Flag users whose total expenses exceed a given threshold.
    Query params:
      - threshold : amount to compare against (required)
      - date_from : YYYY-MM-DD (optional)
      - date_to   : YYYY-MM-DD (optional)

    Example: GET /summary/alerts?threshold=1000
    """
    threshold = request.args.get("threshold", type=float)
    if threshold is None or threshold <= 0:
        return jsonify({"error": "threshold is required and must be a positive number"}), 400

    params     = []
    conditions = ["r.is_deleted = 0", "r.type = 'expense'"]

    where = "WHERE " + " AND ".join(conditions)
    date_sql, params, err = _date_filters(params)
    if err:
        return jsonify(err[0]), err[1]
    where += date_sql

    query = f"""
        SELECT
            u.id            AS user_id,
            u.name          AS user_name,
            u.role,
            ROUND(SUM(r.amount), 2)  AS total_expense,
            COUNT(r.id)              AS expense_records,
            ROUND(SUM(r.amount) - ?, 2) AS exceeded_by
        FROM users u
        JOIN records r ON u.id = r.user_id {where}
        GROUP BY u.id, u.name, u.role
        HAVING total_expense > ?
        ORDER BY total_expense DESC
    """
    # threshold appears twice: once for exceeded_by calc, once for HAVING
    params = [threshold] + params + [threshold]

    conn  = get_connection()
    rows  = conn.execute(query, params).fetchall()
    conn.close()

    result = rows_to_list(rows)
    return jsonify({
        "threshold"    : threshold,
        "alerts_count" : len(result),
        "message"      : f"{len(result)} user(s) exceeded the ₹{threshold:,.2f} expense threshold",
        "users_flagged": result
    }), 200


# ── GET /summary/top-spenders ─────────────────────────────────────────────────
@summary_bp.route("/top-spenders", methods=["GET"])
@admin_or_analyst
def get_top_spenders():
    """
    ⭐ NEW — Top Spenders
    Ranks users by total expense, optionally filtered by category.
    Query params:
      - category  : filter to a specific category (optional)
      - limit     : how many top spenders to return (default: 5)
      - date_from : YYYY-MM-DD (optional)
      - date_to   : YYYY-MM-DD (optional)

    Example: GET /summary/top-spenders?category=Groceries&limit=3
    """
    category = request.args.get("category")
    limit    = min(50, max(1, request.args.get("limit", 5, type=int)))

    params     = []
    conditions = ["r.is_deleted = 0", "r.type = 'expense'"]

    if category:
        conditions.append("LOWER(r.category) = LOWER(?)")
        params.append(category)

    where = "WHERE " + " AND ".join(conditions)
    date_sql, params, err = _date_filters(params)
    if err:
        return jsonify(err[0]), err[1]
    where += date_sql

    query = f"""
        SELECT
            u.id                     AS user_id,
            u.name                   AS user_name,
            u.role,
            r.category,
            COUNT(r.id)              AS transaction_count,
            ROUND(SUM(r.amount), 2)  AS total_spent,
            ROUND(AVG(r.amount), 2)  AS avg_per_transaction,
            MAX(r.date)              AS last_transaction_date
        FROM users u
        JOIN records r ON u.id = r.user_id {where}
        GROUP BY u.id, u.name, u.role, r.category
        ORDER BY total_spent DESC
        LIMIT ?
    """
    params.append(limit)

    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    result = rows_to_list(rows)

    # Add rank to each entry
    for i, row in enumerate(result):
        row["rank"] = i + 1

    return jsonify({
        "filter_category": category or "all",
        "limit"          : limit,
        "top_spenders"   : result
    }), 200


# ── GET /summary/overview ─────────────────────────────────────────────────────
@summary_bp.route("/overview", methods=["GET"])
@admin_or_analyst
def get_overview():
    """
    ⭐ NEW — Full Dashboard Overview (everything in one call)
    Returns a complete snapshot: totals, balances, top category,
    best month, recent activity, and record health stats.
    Query params:
      - user_id : scope to a single user (optional)

    Example: GET /summary/overview
             GET /summary/overview?user_id=2
    """
    user_id = request.args.get("user_id", type=int)
    params  = []
    where   = "WHERE r.is_deleted = 0"

    if user_id:
        where  += " AND r.user_id = ?"
        params.append(user_id)

    conn = get_connection()

    # ── 1. Overall totals ─────────────────────────────────────────────────────
    totals = conn.execute(f"""
        SELECT
            COUNT(r.id)  AS total_records,
            ROUND(COALESCE(SUM(CASE WHEN r.type='income'  THEN r.amount ELSE 0 END), 0), 2) AS total_income,
            ROUND(COALESCE(SUM(CASE WHEN r.type='expense' THEN r.amount ELSE 0 END), 0), 2) AS total_expense,
            ROUND(COALESCE(SUM(CASE WHEN r.type='income'  THEN  r.amount
                                    WHEN r.type='expense' THEN -r.amount ELSE 0 END), 0), 2) AS net_balance
        FROM records r {where}
    """, params).fetchone()

    # ── 2. Top spending category ──────────────────────────────────────────────
    top_category = conn.execute(f"""
        SELECT r.category, ROUND(SUM(r.amount), 2) AS total
        FROM records r {where} AND r.type = 'expense'
        GROUP BY r.category
        ORDER BY total DESC
        LIMIT 1
    """, params).fetchone()

    # ── 3. Best income month ──────────────────────────────────────────────────
    best_month = conn.execute(f"""
        SELECT strftime('%Y-%m', r.date) AS month,
               ROUND(SUM(r.amount), 2)   AS total_income
        FROM records r {where} AND r.type = 'income'
        GROUP BY month
        ORDER BY total_income DESC
        LIMIT 1
    """, params).fetchone()

    # ── 4. Most recent 5 transactions ────────────────────────────────────────
    recent = conn.execute(f"""
        SELECT r.id, u.name AS user_name, r.amount, r.type, r.category, r.date, r.note
        FROM records r
        JOIN users u ON r.user_id = u.id
        {where}
        ORDER BY r.date DESC, r.id DESC
        LIMIT 5
    """, params).fetchall()

    # ── 5. Users summary ──────────────────────────────────────────────────────
    users_summary = conn.execute(f"""
        SELECT
            COUNT(DISTINCT u.id)                        AS total_users,
            SUM(CASE WHEN u.status = 'active'   THEN 1 ELSE 0 END) AS active_users,
            SUM(CASE WHEN u.status = 'inactive' THEN 1 ELSE 0 END) AS inactive_users
        FROM users u
    """).fetchone()

    # ── 6. Record health (soft delete stats) ─────────────────────────────────
    health = conn.execute("""
        SELECT
            SUM(CASE WHEN is_deleted = 0 THEN 1 ELSE 0 END) AS active_records,
            SUM(CASE WHEN is_deleted = 1 THEN 1 ELSE 0 END) AS deleted_records,
            COUNT(*) AS total_records_including_deleted
        FROM records
    """).fetchone()

    conn.close()

    return jsonify({
        "scope": f"user_id={user_id}" if user_id else "all_users",
        "financials": {
            "total_records" : totals["total_records"],
            "total_income"  : totals["total_income"],
            "total_expense" : totals["total_expense"],
            "net_balance"   : totals["net_balance"],
            "status"        : "surplus" if totals["net_balance"] >= 0 else "deficit"
        },
        "highlights": {
            "top_expense_category": dict(top_category) if top_category else None,
            "best_income_month"   : dict(best_month)   if best_month   else None,
        },
        "recent_transactions": rows_to_list(recent),
        "users": dict(users_summary),
        "record_health": dict(health)
    }), 200