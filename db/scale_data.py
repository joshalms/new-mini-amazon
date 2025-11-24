import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

# Target sizes for scaled seed data
TARGET_USERS = 10_000
TARGET_PRODUCTS = 10_000
TARGET_ORDERS = 50_000

# Derived targets
ORDER_ITEMS_PER_ORDER = 3
PURCHASES_PER_ORDER = 3
WISHES_PER_USER = 0.25
INVENTORY_PER_USER = 5
REVIEWS_PER_USER = 2.2
BALANCE_TX_PER_USER = 4

DATA_DIR = Path(__file__).parent / "data"
random.seed(0)

FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn",
    "Harper", "Jamie", "Skyler", "Reese", "Hayden", "Logan", "Peyton",
]

LAST_NAMES = [
    "Rivera", "Patel", "Chen", "Garcia", "Singh", "Brown", "Nguyen", "Davis",
    "Martinez", "Lopez", "Hernandez", "Kim", "Clark", "Lewis", "Walker",
]

STREET_NAMES = [
    "Oak", "Maple", "Pine", "Cedar", "Elm", "Birch", "Willow", "Sunset",
    "Riverside", "Hillcrest", "Lakeview", "Meadow", "Brookside", "Highland",
]

CITIES = [
    "Springfield", "Fairview", "Franklin", "Greenville", "Madison", "Georgetown",
    "Clinton", "Arlington", "Ashland", "Milford", "Burlington", "Dayton",
]

STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "IA", "ID",
    "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS",
    "MT", "NC", "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "OH", "OK", "OR",
    "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV",
]

NOTES = ["top up", "withdraw", "purchase", "refund", "adjustment", "promo credit"]
REVIEW_PHRASES = [
    "Great experience overall.",
    "Item arrived as expected.",
    "Would buy again from this seller.",
    "Communication could be better but order was fine.",
    "Packaging was excellent.",
    "Had a small delay but was resolved quickly.",
]


def read_rows(name: str):
    path = DATA_DIR / name
    with path.open(newline="", encoding="utf-8") as f:
        return [row for row in csv.reader(f)]


def write_rows(name: str, rows):
    path = DATA_DIR / name
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def random_dt(start_year=2020, end_year=2024):
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31, 23, 59, 59)
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def fmt_dt(dt: datetime):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def expand_users(rows, target_users):
    current = len(rows)
    if current >= target_users:
        return rows
    max_id = max(int(r[0]) for r in rows)
    password_pool = [r[4] for r in rows if len(r) > 4 and r[4]]

    for new_id in range(max_id + 1, target_users + 1):
        email = f"user{new_id}@example.com"
        full_name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        address = (
            f"{random.randint(10, 99999)} {random.choice(STREET_NAMES)} St, "
            f"{random.choice(CITIES)}, {random.choice(STATES)} {random.randint(10000, 99999)}"
        )
        password_hash = random.choice(password_pool) if password_pool else ""
        created_at = fmt_dt(random_dt())
        rows.append([str(new_id), email, full_name, address, password_hash, created_at, "", ""])
    return rows


def expand_products(rows, target_products):
    current = len(rows)
    if current >= target_products:
        return rows
    max_id = max(int(r[0]) for r in rows)

    for new_id in range(max_id + 1, target_products + 1):
        name = f"Product {new_id}"
        price = f"{random.randint(199, 99999) / 100:.2f}"
        available = random.choice(["true", "false"])
        rows.append([str(new_id), name, price, available])
    return rows


def expand_account_balance(rows, total_users):
    existing_user_ids = {int(r[0]) for r in rows}
    for uid in range(1, total_users + 1):
        if uid not in existing_user_ids:
            balance = random.randint(0, 200_000)
            rows.append([str(uid), str(balance)])
    return rows


def expand_balance_tx(rows, total_users, target_count):
    current = len(rows)
    target = max(current, target_count)
    max_id = max(int(r[0]) for r in rows) if rows else 0

    for tx_id in range(max_id + 1, max_id + (target - current) + 1):
        user_id = random.randint(1, total_users)
        amount = random.randint(-50_000, 80_000) or 1000
        created_at = fmt_dt(random_dt())
        note = random.choice(NOTES)
        rows.append([str(tx_id), str(user_id), str(amount), created_at, note])
    return rows


def expand_orders(rows, total_users, target_orders):
    current = len(rows)
    target = max(current, target_orders)
    max_id = max(int(r[0]) for r in rows) if rows else 0
    order_created = {int(r[0]): datetime.fromisoformat(r[2]) for r in rows}

    for order_id in range(max_id + 1, max_id + (target - current) + 1):
        buyer_id = random.randint(1, total_users)
        created_at = random_dt()
        total_cents = random.randint(1_000, 300_000)
        fulfilled = random.choice(["true", "false"])
        rows.append([str(order_id), str(buyer_id), fmt_dt(created_at), str(total_cents), fulfilled])
        order_created[order_id] = created_at
    return rows, order_created


def expand_order_items(rows, order_created, product_prices, total_products, total_users, target_orders):
    current = len(rows)
    target = max(current, int(target_orders * ORDER_ITEMS_PER_ORDER))
    max_id = max(int(r[0]) for r in rows) if rows else 0
    order_ids = list(order_created.keys())

    for item_id in range(max_id + 1, max_id + (target - current) + 1):
        order_id = random.choice(order_ids)
        product_id = random.randint(1, total_products)
        seller_id = random.randint(1, total_users)
        quantity = random.randint(1, 5)
        unit_price_cents = product_prices.get(product_id, random.randint(500, 200_000))
        created = order_created.get(order_id, random_dt())
        fulfilled_at = ""
        if random.random() < 0.6:
            fulfilled_time = created + timedelta(hours=random.randint(1, 96))
            fulfilled_at = fmt_dt(fulfilled_time)
        rows.append([
            str(item_id),
            str(order_id),
            str(product_id),
            str(seller_id),
            str(quantity),
            str(unit_price_cents),
            fulfilled_at,
        ])
    return rows


def expand_purchases(rows, total_users, total_products, target_orders):
    current = len(rows)
    target = max(current, int(target_orders * PURCHASES_PER_ORDER))
    max_id = max(int(r[0]) for r in rows) if rows else 0

    for purchase_id in range(max_id + 1, max_id + (target - current) + 1):
        uid = random.randint(1, total_users)
        pid = random.randint(1, total_products)
        time_purchased = fmt_dt(random_dt())
        rows.append([str(purchase_id), str(uid), str(pid), time_purchased])
    return rows


def expand_wishes(rows, total_users, total_products):
    current = len(rows)
    target = max(current, int(total_users * WISHES_PER_USER))
    max_id = max(int(r[0]) for r in rows) if rows else 0

    for wish_id in range(max_id + 1, max_id + (target - current) + 1):
        uid = random.randint(1, total_users)
        pid = random.randint(1, total_products)
        time_added = fmt_dt(random_dt())
        rows.append([str(wish_id), str(uid), str(pid), time_added])
    return rows


def expand_inventory(rows, total_users, total_products):
    target = max(len(rows), int(total_users * INVENTORY_PER_USER))
    existing_pairs = {(int(r[0]), int(r[1])) for r in rows}
    attempts = 0
    while len(rows) < target and attempts < target * 40:
        attempts += 1
        user_id = random.randint(1, total_users)
        product_id = random.randint(1, total_products)
        pair = (user_id, product_id)
        if pair in existing_pairs:
            continue
        quantity = random.randint(0, 500)
        rows.append([str(user_id), str(product_id), str(quantity)])
        existing_pairs.add(pair)
    return rows


def expand_seller_reviews(rows, total_users):
    target = max(len(rows), int(total_users * REVIEWS_PER_USER))
    max_id = max(int(r[0]) for r in rows) if rows else 0
    existing_pairs = {(int(r[1]), int(r[2])) for r in rows}
    attempts = 0
    while len(rows) < target and attempts < target * 40:
        attempts += 1
        user_id = random.randint(1, total_users)
        seller_id = random.randint(1, total_users)
        if user_id == seller_id:
            continue
        pair = (user_id, seller_id)
        if pair in existing_pairs:
            continue
        rating = random.randint(1, 5)
        created_at = random_dt()
        updated_at = created_at + timedelta(hours=random.randint(0, 48))
        body = random.choice(REVIEW_PHRASES)
        rows.append([
            str(max_id + 1),
            str(user_id),
            str(seller_id),
            str(rating),
            body,
            fmt_dt(created_at),
            fmt_dt(updated_at),
        ])
        existing_pairs.add(pair)
        max_id += 1
    return rows


def main():
    users = expand_users(read_rows("Users.csv"), TARGET_USERS)
    total_users = len(users)

    products = expand_products(read_rows("Products.csv"), TARGET_PRODUCTS)
    total_products = len(products)
    product_prices = {int(r[0]): int(float(r[2]) * 100) for r in products if r[2]}

    account_balance = expand_account_balance(read_rows("AccountBalance.csv"), total_users)
    balance_tx = expand_balance_tx(
        read_rows("BalanceTx.csv"),
        total_users,
        int(total_users * BALANCE_TX_PER_USER),
    )

    orders, order_created = expand_orders(read_rows("Orders.csv"), total_users, TARGET_ORDERS)
    order_items = expand_order_items(
        read_rows("OrderItems.csv"),
        order_created,
        product_prices,
        total_products,
        total_users,
        TARGET_ORDERS,
    )

    purchases = expand_purchases(read_rows("Purchases.csv"), total_users, total_products, TARGET_ORDERS)
    wishes = expand_wishes(read_rows("Wishes.csv"), total_users, total_products)
    inventory = expand_inventory(read_rows("Inventory.csv"), total_users, total_products)
    seller_reviews = expand_seller_reviews(read_rows("SellerReviews.csv"), total_users)

    write_rows("Users.csv", users)
    write_rows("Products.csv", products)
    write_rows("AccountBalance.csv", account_balance)
    write_rows("BalanceTx.csv", balance_tx)
    write_rows("Orders.csv", orders)
    write_rows("OrderItems.csv", order_items)
    write_rows("Purchases.csv", purchases)
    write_rows("Wishes.csv", wishes)
    write_rows("Inventory.csv", inventory)
    write_rows("SellerReviews.csv", seller_reviews)

    print("Scaled data written to db/data")
    print(f"Users: {len(users)} | Products: {len(products)} | Orders: {len(orders)}")
    print(f"Order items: {len(order_items)} | Purchases: {len(purchases)} | Wishes: {len(wishes)}")
    print(f"Inventory: {len(inventory)} | BalanceTx: {len(balance_tx)} | Seller reviews: {len(seller_reviews)}")


if __name__ == "__main__":
    main()
