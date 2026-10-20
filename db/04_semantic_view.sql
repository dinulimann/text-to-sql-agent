-- A small semantic layer: business rules live in the database, not in the
-- model's memory. "Revenue" and "units sold" questions become a simple
-- aggregate over this view.
SET search_path TO shop;

CREATE VIEW sales AS
SELECT oi.order_id,
       o.order_date,
       o.store_id,
       o.customer_id,
       o.channel,
       oi.product_id,
       p.category_id,
       oi.quantity,
       oi.unit_price,
       oi.discount,
       round(oi.quantity * oi.unit_price * (1 - oi.discount), 2) AS revenue,
       round(oi.quantity * (oi.unit_price * (1 - oi.discount) - p.unit_cost), 2) AS gross_profit
FROM order_items oi
JOIN orders o   ON o.id = oi.order_id
JOIN products p ON p.id = oi.product_id
WHERE o.status = 'completed';

COMMENT ON VIEW sales IS 'Completed order lines only, with revenue already computed. Use this for any question about revenue, sales, units sold or profit.';
COMMENT ON COLUMN sales.revenue IS 'quantity * unit_price * (1 - discount), in IDR';
COMMENT ON COLUMN sales.gross_profit IS 'revenue minus quantity * product unit_cost, in IDR';

GRANT SELECT ON sales TO agent_ro;
