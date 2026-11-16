-- name: order_detail
-- A cross-database join: commerce order -> CRM customer -> order lines.
SELECT
  o.id,
  o.status,
  c.name AS customer_name,
  i.sku,
  i.qty
FROM shop.orders o
JOIN crm.customers c ON c.id = o.customer_id
JOIN shop.order_items i ON i.order_id = o.id;
