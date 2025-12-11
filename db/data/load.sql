\COPY users (id, email, full_name, address, password_hash, created_at, cart, purchases)
FROM 'Users.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');

SELECT pg_catalog.setval('public.users_id_seq',
       COALESCE((SELECT MAX(id)+1 FROM users), 1),
       false);


-- TEMP TABLES FOR PRODUCT DATA
CREATE TEMP TABLE tmp_products (
    id int,
    name text,
    price decimal(12,2),
    available boolean
);

CREATE TEMP TABLE tmp_images (
    product_id int,
    image_url text
);

CREATE TEMP TABLE tmp_desc (
    product_id int,
    description text
);

\COPY tmp_products FROM 'Products.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');
\COPY tmp_images FROM 'Product_images.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');
\COPY tmp_desc FROM 'Products_descriptions.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');

-- MERGE INTO REAL TABLE
INSERT INTO products (id, name, price, available, image_url, description)
SELECT p.id, p.name, p.price, p.available, i.image_url, d.description
FROM tmp_products p
LEFT JOIN tmp_images i ON p.id = i.product_id
LEFT JOIN tmp_desc   d ON p.id = d.product_id;

SELECT pg_catalog.setval('public.products_id_seq',
       COALESCE((SELECT MAX(id)+1 FROM products), 1),
       false);


\COPY inventory (user_id, product_id, quantity)
FROM 'Inventory.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');

\COPY orders (id, buyer_id, created_at, total_cents, fulfilled)
FROM 'Orders.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');

\COPY order_items (id, order_id, product_id, seller_id, quantity, unit_price_cents, fulfilled_at)
FROM 'OrderItems.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');

\COPY purchases (id, uid, pid, time_purchased)
FROM 'Purchases.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');

\COPY wishes (id, uid, pid, time_added)
FROM 'Wishes.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');

\COPY seller_review (id, user_id, seller_id, rating, body, created_at, updated_at)
FROM 'SellerReviews.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');

\COPY product_review (id, user_id, product_id, rating, body, created_at, updated_at)
FROM 'ProductReviews.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');

\COPY product_review_vote (user_id, review_id, vote_value, created_at)
FROM 'ProductReviewVotes.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');

\COPY seller_review_vote (user_id, review_id, vote_value, created_at)
FROM 'SellerReviewVotes.csv' WITH (FORMAT csv, HEADER false, DELIMITER ',', NULL '');
