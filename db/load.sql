\COPY users (id, email, full_name, address, password_hash, created_at, cart, purchases) FROM 'Users.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');
SELECT pg_catalog.setval('public.users_id_seq',
                         COALESCE((SELECT MAX(id)+1 FROM users), 1),
                         false);

\COPY account_balance (user_id, balance_cents) FROM 'AccountBalance.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');

\COPY balance_tx (id, user_id, amount_cents, created_at, note) FROM 'BalanceTx.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');
SELECT pg_catalog.setval('public.balance_tx_id_seq',
                         COALESCE((SELECT MAX(id)+1 FROM balance_tx), 1),
                         false);

\COPY products (id, name, price, available) FROM 'Products.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');
SELECT pg_catalog.setval('public.products_id_seq',
                         COALESCE((SELECT MAX(id)+1 FROM products), 1),
                         false);

\COPY inventory (user_id, product_id, quantity) FROM 'Inventory.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');
SELECT pg_catalog.setval('public.inventory_id_seq',
                         COALESCE((SELECT MAX(id)+1 FROM inventory), 1),
                         false);

\COPY orders (id, buyer_id, created_at, total_cents, fulfilled) FROM 'Orders.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');
SELECT pg_catalog.setval('public.orders_id_seq',
                         COALESCE((SELECT MAX(id)+1 FROM orders), 1),
                         false);

\COPY order_items (id, order_id, product_id, seller_id, quantity, unit_price_cents, fulfilled_at) FROM 'OrderItems.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');
SELECT pg_catalog.setval('public.order_items_id_seq',
                         COALESCE((SELECT MAX(id)+1 FROM order_items), 1),
                         false);

\COPY purchases (id, uid, pid, time_purchased) FROM 'Purchases.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');
SELECT pg_catalog.setval('public.purchases_id_seq',
                         COALESCE((SELECT MAX(id)+1 FROM purchases), 1),
                         false);

\COPY wishes (id, uid, pid, time_added) FROM 'Wishes.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');
SELECT pg_catalog.setval('public.wishes_id_seq',
                         COALESCE((SELECT MAX(id)+1 FROM wishes), 1),
                         false);

\COPY seller_review (id, user_id, seller_id, rating, body, created_at, updated_at) FROM 'SellerReviews.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');
SELECT pg_catalog.setval('public.seller_review_id_seq',
                         COALESCE((SELECT MAX(id)+1 FROM seller_review), 1),
                         false);

INSERT INTO cart (user_id)
SELECT v.uid
FROM (VALUES (1), (4)) AS v(uid)
WHERE NOT EXISTS (SELECT 1 FROM cart WHERE user_id = v.uid);

INSERT INTO cartitem (cart_id, product_id, quantity)
SELECT c.id, v.pid, v.quantity
FROM (VALUES
    (1, 1, 2),
    (1, 2, 1),
    (4, 1, 1),
    (4, 2, 3)
) AS v(uid, pid, quantity)
JOIN cart c ON c.user_id = v.uid
WHERE NOT EXISTS (
    SELECT 1 FROM cartitem ci
    WHERE ci.cart_id = c.id AND ci.product_id = v.pid
);
