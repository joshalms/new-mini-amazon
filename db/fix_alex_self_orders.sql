-- Fix order items where Alex (user_id=1) is both buyer and seller
-- This updates each order item to use a different seller with inventory

UPDATE order_items oi
SET seller_id = (
    SELECT i.user_id
    FROM inventory i
    WHERE i.product_id = oi.product_id
      AND i.user_id != 1
      AND i.quantity > 0
    ORDER BY i.quantity DESC
    LIMIT 1
)
WHERE oi.seller_id = 1
  AND oi.order_id IN (
    SELECT o.id FROM orders o WHERE o.buyer_id = 1
  );
