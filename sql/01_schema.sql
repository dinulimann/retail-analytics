DROP SCHEMA IF EXISTS retail CASCADE;
CREATE SCHEMA retail;
SET search_path TO retail;

-- Product lines that were actually sold (see src/clean.py for the rules).
CREATE TABLE sales (
    invoice       text          NOT NULL,
    stock_code    text          NOT NULL,
    description   text          NOT NULL,
    quantity      integer       NOT NULL CHECK (quantity > 0),
    invoice_date  timestamp     NOT NULL,
    unit_price    numeric(10,2) NOT NULL CHECK (unit_price > 0),
    customer_id   integer,                 -- NULL for guest checkouts (~23% of lines)
    country       text          NOT NULL,
    line_revenue  numeric(12,2) NOT NULL
);

-- Lines on cancellation invoices ("C..."), quantity is negative.
CREATE TABLE cancellations (
    invoice       text          NOT NULL,
    stock_code    text          NOT NULL,
    description   text,
    quantity      integer       NOT NULL,
    invoice_date  timestamp     NOT NULL,
    unit_price    numeric(10,2) NOT NULL,
    customer_id   integer,
    country       text          NOT NULL
);

-- What each cleaning rule removed, for the data quality report and dashboard.
CREATE TABLE data_quality (
    step       integer PRIMARY KEY,
    rule       text    NOT NULL,
    removed    integer NOT NULL,
    remaining  integer NOT NULL
);
