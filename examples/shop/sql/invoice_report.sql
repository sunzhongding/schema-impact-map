-- name: invoice_report
-- Billing reads orders and customers from two other databases.
SELECT
  i.id,
  i.amount,
  o.status AS order_status,
  c.customer_code
FROM billing.invoices i
JOIN shop.orders o ON o.id = i.order_id
JOIN crm.customers c ON c.id = i.customer_id;
