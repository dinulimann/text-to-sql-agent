-- Fictional retail chain. Everything here is synthetic.
-- Table and column comments are sent to the model as documentation.

CREATE SCHEMA shop;
SET search_path TO shop;

CREATE TABLE stores (
    id         int PRIMARY KEY,
    name       text NOT NULL,
    city       text NOT NULL,
    province   text NOT NULL,
    opened_on  date NOT NULL
);
COMMENT ON TABLE stores IS 'Physical stores. Online orders are also attributed to a store (the fulfilling store).';

CREATE TABLE customers (
    id          int PRIMARY KEY,
    full_name   text NOT NULL,
    email       text NOT NULL UNIQUE,
    city        text NOT NULL,
    segment     text NOT NULL CHECK (segment IN ('consumer', 'business')),
    signup_date date NOT NULL
);
COMMENT ON TABLE customers IS 'Registered customers.';
COMMENT ON COLUMN customers.segment IS 'consumer or business';

CREATE TABLE categories (
    id   int PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE products (
    id          int PRIMARY KEY,
    name        text NOT NULL,
    category_id int NOT NULL REFERENCES categories,
    unit_price  numeric(12,2) NOT NULL,
    unit_cost   numeric(12,2) NOT NULL
);
COMMENT ON COLUMN products.unit_price IS 'Current list price in IDR';
COMMENT ON COLUMN products.unit_cost IS 'Purchase cost per unit in IDR';

CREATE TABLE orders (
    id          int PRIMARY KEY,
    customer_id int NOT NULL REFERENCES customers,
    store_id    int NOT NULL REFERENCES stores,
    order_date  date NOT NULL,
    channel     text NOT NULL CHECK (channel IN ('online', 'in_store')),
    status      text NOT NULL CHECK (status IN ('completed', 'cancelled', 'returned'))
);
COMMENT ON TABLE orders IS 'One row per order. Only status = ''completed'' counts as revenue.';

CREATE TABLE order_items (
    order_id   int NOT NULL REFERENCES orders,
    product_id int NOT NULL REFERENCES products,
    quantity   int NOT NULL CHECK (quantity > 0),
    unit_price numeric(12,2) NOT NULL,
    discount   numeric(4,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (order_id, product_id)
);
COMMENT ON TABLE order_items IS 'Order lines. Line revenue = quantity * unit_price * (1 - discount).';
COMMENT ON COLUMN order_items.unit_price IS 'Price actually charged per unit in IDR, at the time of the order';
COMMENT ON COLUMN order_items.discount IS 'Fraction between 0 and 1, e.g. 0.10 = 10% off';

CREATE INDEX ON orders (order_date);
CREATE INDEX ON orders (customer_id);
CREATE INDEX ON orders (store_id);
CREATE INDEX ON order_items (product_id);
