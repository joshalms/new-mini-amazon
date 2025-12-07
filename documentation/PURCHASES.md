# Purchases module (canonical references)

- **Data access:** `app/models/purchases.py` now contains all purchase/purchase-history helpers:
  - `get_purchases_for_user(user_id, ...)` for paginated history and filters.
  - `get_order_detail(order_id)` for order header + line items with seller/product names.
  - `get_recent_line_items_for_user(user_id, limit)` used on the home page.
  - `get_purchase_summary(user_id)` for the public profile stats.
- **Routes (canonical):**
  - Account blueprint: `account.account_purchases` (HTML), `account.order_detail` (HTML), `api_user_purchases` (JSON).
  - Users blueprint: `users.users_purchases` and `users.order_detail` reuse the same helpers/templates and enforce ownership checks.
- **Templates:** Shared, accessible views live under `app/templates/purchases/`:
  - `list.html` renders filtered purchase history with empty-state feedback.
  - `detail.html` renders order details (with optional review actions when `show_reviews=True`).
  - Both account and users blueprints render these templates directly.
- **Schema/indexes:** `db/create.sql` declares indexes for purchases pagination/filtering:
  - `orders (buyer_id, created_at DESC)` plus `created_at` only,
  - `order_items (order_id)` and `(seller_id)`,
  - `products (lower(name))` to accelerate item-name filters.
- **CSRF:** Server-rendered POST forms include a `csrf_token` hidden input. The app-wide CSRF guard lives in `app/__init__.py` and exempts JSON API calls; use `csrf_token()` in any new form.
