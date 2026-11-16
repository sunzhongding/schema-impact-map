-- name: refund_review
SELECT
  r.id,
  r.amount,
  o.status AS order_status
FROM shop.refunds r
JOIN shop.orders o ON o.id = r.order_id;
