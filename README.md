# Finance Data Processing & Access Control System

A RESTful backend API built with **Python Flask** and **SQLite** for managing users, financial records, and dashboard analytics with strict role-based access control (RBAC) and session/cookie-based authentication.

---

## Project Structure

```
finance_app/
├── app.py            # Flask app factory + entry point
├── database.py       # SQLite connection, schema init, helpers
├── middleware.py     # RBAC decorators + session/cookie/header auth + validators
├── seed.py           # Sample data loader
├── requirements.txt
├── finance.db        # Auto-created on first run
└── routes/
    ├── __init__.py
    ├── auth.py       # Login, logout, session, cookies
    ├── users.py      # User management endpoints
    ├── records.py    # Financial record endpoints + CSV export
    └── summary.py    # Dashboard / analytics endpoints
```

---

## Setup

### 1. Prerequisites
- Python 3.9+ (SQLite is built into Python — nothing else to install)

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Seed sample data
```bash
python seed.py
```

### 4. Run the server
```bash
python app.py
```
Server starts at `http://127.0.0.1:8000`

---

## Authentication

The system supports **3 ways** to authenticate, checked in this priority order:

### Option 1 — Session (recommended for browsers)
Login once and the server remembers you for 7 days.
```
POST /auth/login
Body: { "user_id": 1, "remember_me": true }
```
After logging in, no header is needed — the session handles every request automatically.

### Option 2 — Cookie
When `remember_me: true` is sent on login, a `finance_user` cookie is set on the client. Even if the session expires, the cookie can restore it transparently.

### Option 3 — X-User-ID Header (for Postman / API clients)
Pass the header directly on every request. No login needed. Works exactly as before.
```
X-User-ID: 1
```

---

## Role-Based Access Control

| Permission                      | admin | analyst | viewer |
|---------------------------------|:-----:|:-------:|:------:|
| Login / logout                  | ✅    | ✅      | ✅     |
| Create users                    | ✅    | ❌      | ❌     |
| Get all users                   | ✅    | ❌      | ❌     |
| Update user status              | ✅    | ❌      | ❌     |
| Create financial records        | ✅    | ❌      | ❌     |
| View all records (any user)     | ✅    | ✅      | ❌     |
| View own records only           | ✅    | ✅      | ✅     |
| Update records                  | ✅    | ❌      | ❌     |
| Delete records (soft)           | ✅    | ❌      | ❌     |
| Export records as CSV           | ✅    | ✅      | ❌     |
| Access dashboard/summary APIs   | ✅    | ✅      | ❌     |

---

## Seed Users (for testing)

| ID | Name         | Role    | Status   |
|----|-------------|---------|----------|
| 1  | Alice Admin  | admin   | active   |
| 2  | Bob Analyst  | analyst | active   |
| 3  | Vera Viewer  | viewer  | active   |
| 4  | Dave Analyst | analyst | inactive |

---

## API Reference

### Base URL: `http://localhost:8000`

---

### Auth

#### `POST /auth/login` — Login and start a session
**Request:**
```json
{ "user_id": 1, "remember_me": true }
```
**Response `200`:**
```json
{
  "message": "Welcome, Alice Admin! You are logged in.",
  "user": { "id": 1, "name": "Alice Admin", "role": "admin", "status": "active" },
  "session": "active",
  "cookie": "set"
}
```

---

#### `GET /auth/me` — Who am I?
Returns the currently logged-in user, how they authenticated, and their full permissions map.

**Response `200`:**
```json
{
  "logged_in": true,
  "auth_method": "session",
  "user": { "id": 1, "name": "Alice Admin", "role": "admin", "status": "active" },
  "permissions": {
    "create_users": true, "manage_users": true, "create_records": true,
    "edit_records": true, "delete_records": true, "view_records": true,
    "view_dashboard": true, "export_csv": true
  }
}
```

---

#### `POST /auth/logout` — Logout
Clears the server-side session and deletes the cookie.

**Response `200`:**
```json
{ "message": "Alice Admin logged out successfully.", "session": "cleared", "cookie": "deleted" }
```

---

### Users

#### `POST /users` — Create a user *(admin only)*
**Request:** `{ "name": "Jane Doe", "role": "analyst" }`
**Response `201`:** Created user object.

#### `GET /users` — List all users *(admin only)*
**Query params:** `role`, `status`
**Response `200`:** `{ "total": 2, "users": [...] }`

#### `PUT /users/<id>` — Update user status *(admin only)*
**Request:** `{ "status": "inactive" }`
**Response `200`:** Updated user object.

---

### Financial Records

#### `POST /records` — Create a record *(admin only)*
**Request:**
```json
{
  "amount": 1500.00, "type": "income", "category": "Freelance",
  "date": "2024-03-20", "user_id": 2, "note": "Logo design project"
}
```
**Response `201`:** Created record object.

#### `GET /records` — List records with filters *(admin/analyst: all; viewer: own only)*
**Query params:** `user_id`, `type`, `category`, `date_from`, `date_to`, `page`, `page_size`
**Response `200`:** `{ "total": 14, "page": 1, "page_size": 20, "total_pages": 1, "records": [...] }`

#### `PUT /records/<id>` — Update a record *(admin only)*
Provide any subset of: `amount`, `type`, `category`, `date`, `note`

#### `DELETE /records/<id>` — Soft-delete a record *(admin only)*
Sets `is_deleted = 1`. Data is kept in DB for audit history.
**Response `200`:** `{ "message": "Record 5 deleted successfully" }`

#### `GET /records/export` — Export as CSV *(admin, analyst)* ⭐
Downloads all matching records as a `.csv` file (opens in Excel).
**Query params:** `user_id`, `type`, `category`, `date_from`, `date_to`
In Postman: Send → Save Response → Save to a file.

---

### Dashboard / Summary *(admin and analyst only)*

#### `GET /summary/totals`
Total income and expense per user.
**Query params:** `user_id`, `date_from`, `date_to`

#### `GET /summary/balance`
Net balance (income − expense) per user, sorted highest to lowest.
**Query params:** `user_id`, `date_from`, `date_to`

#### `GET /summary/categories`
Totals broken down by category and type, with averages.
**Query params:** `user_id`, `type`, `date_from`, `date_to`

#### `GET /summary/monthly`
Income, expense, and net balance grouped by month.
**Query params:** `user_id`, `year`, `date_from`, `date_to`

#### `GET /summary/alerts` ⭐ — Spending Alerts
Flags users whose total expenses exceed a threshold you set.
**Query params:** `threshold` (required), `date_from`, `date_to`

```
GET /summary/alerts?threshold=1000
```
**Response `200`:**
```json
{
  "threshold": 1000.0,
  "alerts_count": 2,
  "message": "2 user(s) exceeded the ₹1,000.00 expense threshold",
  "users_flagged": [
    { "user_id": 1, "user_name": "Alice Admin", "total_expense": 2400.0, "exceeded_by": 1400.0 }
  ]
}
```

#### `GET /summary/top-spenders` ⭐ — Top Spenders Leaderboard
Ranks users by highest spending with optional category filter.
**Query params:** `category`, `limit` (default 5), `date_from`, `date_to`

```
GET /summary/top-spenders
GET /summary/top-spenders?category=Rent&limit=3
```
**Response `200`:**
```json
{
  "filter_category": "all",
  "limit": 5,
  "top_spenders": [
    {
      "rank": 1, "user_name": "Alice Admin", "category": "Rent",
      "total_spent": 2400.0, "avg_per_transaction": 1200.0,
      "last_transaction_date": "2024-02-10"
    }
  ]
}
```

#### `GET /summary/overview` ⭐ — Full Dashboard in One Call
Returns a complete financial snapshot in a single request.
**Query params:** `user_id` (optional, to scope to one user)

```
GET /summary/overview
GET /summary/overview?user_id=2
```
**Response `200`:**
```json
{
  "scope": "all_users",
  "financials": {
    "total_income": 21300.0, "total_expense": 4460.5,
    "net_balance": 16839.5, "status": "surplus"
  },
  "highlights": {
    "top_expense_category": { "category": "Rent", "total": 2400.0 },
    "best_income_month": { "month": "2024-01", "total_income": 8500.0 }
  },
  "recent_transactions": [...],
  "users": { "total_users": 4, "active_users": 3, "inactive_users": 1 },
  "record_health": { "active_records": 14, "deleted_records": 0 }
}
```

---

## HTTP Status Codes

| Code | Meaning                           |
|------|-----------------------------------|
| 200  | OK                                |
| 201  | Created                           |
| 400  | Bad Request (validation error)    |
| 401  | Unauthorized (not logged in)      |
| 403  | Forbidden (wrong role / inactive) |
| 404  | Not Found                         |
| 405  | Method Not Allowed                |
| 500  | Internal Server Error             |

---

## Example cURL Commands

```bash
# Login and save session cookie
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{"user_id": 1, "remember_me": true}'

# Use session cookie for all requests
curl http://localhost:8000/auth/me -b cookies.txt
curl http://localhost:8000/summary/overview -b cookies.txt

# Logout
curl -X POST http://localhost:8000/auth/logout -b cookies.txt

# --- OR use X-User-ID header directly (no login needed) ---

curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" -H "X-User-ID: 1" \
  -d '{"name": "Jane Doe", "role": "analyst"}'

curl "http://localhost:8000/records/export?type=expense" \
  -H "X-User-ID: 1" -o expenses.csv

curl "http://localhost:8000/summary/alerts?threshold=1000" -H "X-User-ID: 1"
curl "http://localhost:8000/summary/top-spenders?limit=3" -H "X-User-ID: 2"
curl "http://localhost:8000/summary/overview" -H "X-User-ID: 1"
```

---

## Design Decisions

- **Three auth methods**: session (browser), cookie (remember me), header (Postman/API) — all work simultaneously, checked in priority order.
- **Soft deletes**: Records are never physically removed — `is_deleted = 1` hides them while preserving audit history.
- **Pagination**: All list endpoints support `page` and `page_size`.
- **COALESCE in SQL**: Aggregate queries return `0` instead of `NULL` for users with no records.
- **httponly cookies**: The `finance_user` cookie cannot be read by JavaScript, protecting against XSS.
- **Session lifetime**: Sessions last 7 days by default (configurable in `app.py`).
- **Modular structure**: Logic is separated into blueprints (`routes/`), shared utilities (`database.py`, `middleware.py`) for clean, maintainable code.