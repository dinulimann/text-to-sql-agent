-- Deterministic synthetic data: 2 years of orders (2024-2025).
SET search_path TO shop;
SELECT setseed(0.2026);

INSERT INTO stores VALUES
 (1, 'Sudirman Flagship',  'Jakarta',    'DKI Jakarta',      '2019-03-01'),
 (2, 'Kemang Store',       'Jakarta',    'DKI Jakarta',      '2021-07-15'),
 (3, 'Dago Store',         'Bandung',    'Jawa Barat',       '2020-02-10'),
 (4, 'Tunjungan Store',    'Surabaya',   'Jawa Timur',       '2019-11-20'),
 (5, 'Malioboro Store',    'Yogyakarta', 'DI Yogyakarta',    '2022-01-05'),
 (6, 'Simpang Lima Store', 'Semarang',   'Jawa Tengah',      '2022-06-18'),
 (7, 'Kuta Store',         'Denpasar',   'Bali',             '2023-04-01'),
 (8, 'Merdeka Store',      'Medan',      'Sumatera Utara',   '2021-09-09'),
 (9, 'Losari Store',       'Makassar',   'Sulawesi Selatan', '2024-03-15'),
 (10,'Balikpapan Store',   'Balikpapan', 'Kalimantan Timur', '2025-02-01');

INSERT INTO categories VALUES
 (1,'Electronics'),(2,'Home & Kitchen'),(3,'Fashion'),(4,'Sports'),
 (5,'Beauty'),(6,'Books'),(7,'Toys'),(8,'Groceries');

-- 120 products; price level depends on category
INSERT INTO products (id, name, category_id, unit_price, unit_cost)
SELECT p,
       c.name || ' Item ' || lpad(p::text, 3, '0'),
       c.id,
       price,
       round((price * (0.55 + random() * 0.2))::numeric, -2)
FROM generate_series(1, 120) p
JOIN categories c ON c.id = 1 + (p % 8)
CROSS JOIN LATERAL (
    SELECT round(((CASE c.id WHEN 1 THEN 1500000 WHEN 2 THEN 350000 WHEN 3 THEN 250000 WHEN 4 THEN 400000
                             WHEN 5 THEN 120000 WHEN 6 THEN 90000 WHEN 7 THEN 180000 ELSE 45000 END)
                  * (0.4 + random() * 1.6))::numeric, -3) AS price
) x;

-- 3,000 customers
INSERT INTO customers (id, full_name, email, city, segment, signup_date)
SELECT i,
       (ARRAY['Adi','Budi','Citra','Dewi','Eka','Fajar','Gita','Hadi','Indah','Joko','Kartika','Lestari','Made','Nia','Putu','Rina','Sari','Tono','Wulan','Yudi'])[1 + (random()*19)::int]
       || ' ' ||
       (ARRAY['Santoso','Wijaya','Pratama','Saputra','Hidayat','Lubis','Nugroho','Kurniawan','Siregar','Halim','Gunawan','Putri'])[1 + (random()*11)::int],
       'customer' || i || '@example.com',
       (ARRAY['Jakarta','Jakarta','Jakarta','Bandung','Surabaya','Surabaya','Yogyakarta','Semarang','Denpasar','Medan','Makassar','Balikpapan'])[1 + (random()*11)::int],
       CASE WHEN random() < 0.15 THEN 'business' ELSE 'consumer' END,
       date '2022-01-01' + (random() * 1400)::int
FROM generate_series(1, 3000) i;

-- Orders: more in Q4 and on weekends; stores only sell after they opened
INSERT INTO orders (id, customer_id, store_id, order_date, channel, status)
SELECT row_number() OVER (ORDER BY d, r1),
       c.id, s.id, d,
       CASE WHEN random() < 0.35 THEN 'online' ELSE 'in_store' END,
       CASE WHEN r2 < 0.05 THEN 'cancelled' WHEN r2 < 0.08 THEN 'returned' ELSE 'completed' END
FROM (
    SELECT d::date AS d,
           random() AS r1, random() AS r2,
           1 + (random() * 2999)::int AS cust,
           1 + (random() * 9)::int AS store
    FROM generate_series(date '2024-01-01', date '2025-12-31', interval '1 day') d
    CROSS JOIN LATERAL generate_series(1, 30 + (CASE WHEN extract(month FROM d) IN (11, 12) THEN 20 ELSE 0 END)
                                           + (CASE WHEN extract(isodow FROM d) IN (6, 7) THEN 12 ELSE 0 END)
                                           + (extract(year FROM d) - 2024)::int * 8) n
) o
JOIN customers c ON c.id = o.cust
JOIN stores s ON s.id = o.store
WHERE o.d >= s.opened_on AND o.d >= c.signup_date;

-- 1 to 4 lines per order. The line count must reference o.id,
-- otherwise Postgres evaluates it only once for all orders.
INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount)
SELECT DISTINCT ON (o.id, pr.id)
       o.id, pr.id,
       1 + (random() * 3)::int,
       pr.unit_price,
       CASE WHEN random() < 0.2 THEN 0.10 WHEN random() < 0.05 THEN 0.25 ELSE 0 END
FROM orders o
CROSS JOIN LATERAL generate_series(1, (1 + (o.id::bigint * 2654435761) % 4)::int) n
CROSS JOIN LATERAL (SELECT 1 + ((o.id * 7 + n * 31 + (random() * 119)::int) % 120) AS pid) x
JOIN products pr ON pr.id = x.pid
ORDER BY o.id, pr.id;

ANALYZE;
