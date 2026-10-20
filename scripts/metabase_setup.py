"""Builds the Metabase dashboard through the API, so it is reproducible.

    python scripts/metabase_setup.py

Creates the admin user on first run, connects the retail database, then
(re)creates every question and the dashboard.
"""

import os
import sys

import requests

MB = os.getenv("METABASE_URL", "http://localhost:3001")
EMAIL = os.getenv("MB_ADMIN_EMAIL", "admin@example.com")
PASSWORD = os.getenv("MB_ADMIN_PASSWORD", "Retail-Analytics-2026")
DB = {"host": "db", "port": 5432, "dbname": "retail", "user": "retail", "password": "retail"}
DASHBOARD = "Online Retail: Sales & Customers"

s = requests.Session()


def api(method: str, path: str, **kw):
    r = s.request(method, f"{MB}/api{path}", timeout=120, **kw)
    if r.status_code >= 400:
        sys.exit(f"{method} {path}: {r.status_code} {r.text[:300]}")
    return r.json() if r.content else None


def login() -> None:
    token = api("GET", "/session/properties").get("setup-token")
    if token:
        try:
            api("POST", "/setup", json={
                "token": token,
                "user": {"email": EMAIL, "password": PASSWORD, "first_name": "Admin", "last_name": "User",
                         "site_name": "Retail Analytics"},
                "prefs": {"site_name": "Retail Analytics", "site_locale": "en", "allow_tracking": False},
            })
        except SystemExit:
            pass  # already set up
    session = api("POST", "/session", json={"username": EMAIL, "password": PASSWORD})
    s.headers["X-Metabase-Session"] = session["id"]


def database_id() -> int:
    for d in api("GET", "/database")["data"]:
        if d["name"] == "Retail":
            return d["id"]
    d = api("POST", "/database", json={"engine": "postgres", "name": "Retail", "details": DB})
    return d["id"]


def card(db: int, name: str, sql: str, display: str, viz: dict | None = None, description: str = "") -> int:
    return api("POST", "/card", json={
        "name": name, "description": description or None, "display": display,
        "visualization_settings": viz or {},
        "dataset_query": {"type": "native", "database": db, "native": {"query": sql}},
    })["id"]


def money(col: str) -> dict:
    return {"column_settings": {f'["name","{col}"]': {"prefix": "£", "number_style": "decimal", "decimals": 0}}}


def build(db: int) -> int:
    for d in api("GET", "/dashboard/"):
        if d["name"] == DASHBOARD:
            api("DELETE", f"/dashboard/{d['id']}")

    period = "invoice_date < (SELECT last_full_month + interval '1 month' FROM retail.period)"
    cards = [
        # (card id, row, col, width, height)
        (card(db, "Revenue (Dec 2009 – Nov 2011)", f"SELECT round(sum(line_revenue)) AS revenue FROM retail.sales WHERE {period}",
              "scalar", {"scalar.prefix": "£", "scalar.compact_primary_number": True}), 0, 0, 6, 3),
        (card(db, "Orders", f"SELECT count(DISTINCT invoice) AS orders FROM retail.sales WHERE {period}", "scalar"), 0, 6, 6, 3),
        (card(db, "Customers", f"SELECT count(DISTINCT customer_id) AS customers FROM retail.sales WHERE {period}", "scalar"), 0, 12, 6, 3),
        (card(db, "Average order value", f"SELECT round(sum(line_revenue) / count(DISTINCT invoice), 2) AS aov FROM retail.sales WHERE {period}",
              "scalar", {"scalar.prefix": "£"}), 0, 18, 6, 3),

        (card(db, "Monthly revenue", "SELECT month, revenue FROM retail.monthly_kpis ORDER BY month", "line",
              {"graph.dimensions": ["month"], "graph.metrics": ["revenue"], **money("revenue")},
              "Complete months only. Strong November peak in both years (Christmas stock-up by wholesale buyers)."), 3, 0, 16, 7),
        (card(db, "New vs returning customers", "SELECT month, new_customers, returning_customers FROM retail.new_vs_returning ORDER BY month",
              "bar", {"graph.dimensions": ["month"], "graph.metrics": ["new_customers", "returning_customers"], "stackable.stack_type": "stacked"}),
         3, 16, 8, 7),

        (card(db, "Revenue by customer segment (RFM)", "SELECT segment, revenue, customers, revenue_pct FROM retail.rfm_segments ORDER BY revenue DESC",
              "row", {"graph.dimensions": ["segment"], "graph.metrics": ["revenue"], **money("revenue")},
              "Recency / frequency / monetary quintiles. Champions = bought recently and often."), 10, 0, 12, 7),
        (card(db, "Segments: who they are", """SELECT segment, customers, revenue_pct AS "% of revenue",
              avg_recency_days AS "days since last order", avg_orders AS "avg orders" FROM retail.rfm_segments ORDER BY revenue DESC""",
              "table"), 10, 12, 12, 7),

        (card(db, "Cohort retention (% of first-month buyers who came back)", """
            SELECT to_char(cohort_month, 'YYYY-MM') AS cohort, max(cohort_size) AS customers,
                   """ + ",\n                   ".join(
                f"max(CASE WHEN months_since = {i} THEN round(100 * retention) END) AS \"M{i}\"" for i in range(1, 13)) + """
            FROM retail.cohort_retention
            WHERE cohort_month <= '2011-06-01'
            GROUP BY cohort_month ORDER BY cohort_month""",
              "table", {"table.column_formatting": [{
                  "columns": [f"M{i}" for i in range(1, 13)], "type": "range", "colors": ["#ffffff", "#2563eb"],
                  "min_type": "custom", "min_value": 0, "max_type": "custom", "max_value": 50,
                  "highlight_row": False, "operator": "=", "value": 0, "color": "#2563eb", "id": 0}]},
              "Each row is the month of a customer's first purchase; M3 = % still buying three months later."), 17, 0, 24, 8),

        (card(db, "Top 10 products by revenue", "SELECT description AS product, revenue FROM retail.top_products ORDER BY revenue DESC LIMIT 10",
              "row", {"graph.dimensions": ["product"], "graph.metrics": ["revenue"], **money("revenue")}), 25, 0, 12, 8),
        (card(db, "Top countries outside the UK", "SELECT country, revenue FROM retail.country_summary WHERE country <> 'United Kingdom' ORDER BY revenue DESC LIMIT 10",
              "row", {"graph.dimensions": ["country"], "graph.metrics": ["revenue"], **money("revenue")}), 25, 12, 12, 8),

        (card(db, "Bought together (highest lift)", """
            SELECT a.description AS "product A", b.description AS "product B", p.orders_together AS orders,
                   round(100 * p.confidence_a_to_b) AS "% of A orders with B", p.lift
            FROM retail.product_pairs p
            JOIN retail.top_products a ON a.stock_code = p.product_a
            JOIN retail.top_products b ON b.stock_code = p.product_b
            ORDER BY p.lift DESC LIMIT 12""", "table",
              description="Lift = how much more often the pair is bought together than by chance."), 33, 0, 16, 8),
        (card(db, "Orders by hour of day", "SELECT hour, sum(orders) AS orders FROM retail.order_timing GROUP BY hour ORDER BY hour",
              "bar", {"graph.dimensions": ["hour"], "graph.metrics": ["orders"]}), 33, 16, 8, 8),

        (card(db, "Data quality: what cleaning removed", "SELECT step, rule, removed, remaining FROM retail.data_quality ORDER BY step",
              "table"), 41, 0, 24, 8),
    ]

    dash = api("POST", "/dashboard", json={
        "name": DASHBOARD,
        "description": "UCI Online Retail II, a UK online gift wholesaler, Dec 2009 – Dec 2011.",
    })
    api("PUT", f"/dashboard/{dash['id']}", json={"dashcards": [
        {"id": -(i + 1), "card_id": cid, "row": r, "col": c, "size_x": w, "size_y": h}
        for i, (cid, r, c, w, h) in enumerate(cards)
    ]})
    return dash["id"]


if __name__ == "__main__":
    login()
    dash_id = build(database_id())
    print(f"Dashboard: {MB}/dashboard/{dash_id}  (login {EMAIL} / {PASSWORD})")
