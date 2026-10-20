"""Cleaning rules for the UCI Online Retail II dataset.

Every rule is a named step that reports how many rows it removed, so the data
quality report can say exactly what happened between the raw file and the
numbers on the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Stock codes that are not products: postage, fees, manual adjustments, samples...
NON_PRODUCT_CODES = {
    "POST", "DOT", "M", "C2", "D", "S", "BANK CHARGES", "ADJUST", "ADJUST2", "AMAZONFEE",
    "PADS", "CRUK", "B", "TEST001", "TEST002",  # "B" = bad-debt adjustment ("A" invoices)
}
NON_PRODUCT_PREFIXES = ("gift_", "DCGS")


@dataclass
class Step:
    rule: str
    removed: int
    remaining: int


@dataclass
class CleanResult:
    sales: pd.DataFrame          # product lines that were actually sold
    cancellations: pd.DataFrame  # product lines on cancellation ("C") invoices
    steps: list[Step] = field(default_factory=list)
    reversals_matched: int = 0


def load_raw(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"Invoice": str, "StockCode": str, "Description": str},
                     parse_dates=["InvoiceDate"])
    return df.rename(columns={
        "Invoice": "invoice", "StockCode": "stock_code", "Description": "description",
        "Quantity": "quantity", "InvoiceDate": "invoice_date", "Price": "unit_price",
        "Customer ID": "customer_id", "Country": "country",
    })


def is_product(stock_code: pd.Series) -> pd.Series:
    code = stock_code.astype(str).str.strip()
    return ~code.isin(NON_PRODUCT_CODES) & ~code.str.startswith(NON_PRODUCT_PREFIXES)


def clean(raw: pd.DataFrame) -> CleanResult:
    steps: list[Step] = []
    df = raw.copy()

    def step(rule: str, keep: pd.Series) -> None:
        nonlocal df
        before = len(df)
        df = df[keep]
        steps.append(Step(rule, before - len(df), len(df)))

    steps.append(Step("raw rows (both sheets)", 0, len(df)))
    step("exact duplicate rows (incl. the 2010-12-01..09 overlap between the two sheets)", ~df.duplicated())
    step("non-product lines (postage, fees, manual adjustments, samples, vouchers)", is_product(df["stock_code"]))

    cancelled = df["invoice"].str.startswith("C")
    cancellations = df[cancelled].copy()
    df = df[~cancelled]
    steps.append(Step("cancellation lines, kept in a separate table", len(cancellations), len(df)))

    step("stock adjustments (quantity <= 0 on a normal invoice)", df["quantity"] > 0)
    step("zero or negative price", df["unit_price"] > 0)

    # Orders entered by mistake and immediately cancelled with the exact same
    # quantity (e.g. 80,995 units) would dominate any per-customer analysis.
    sales, reversals = _drop_exact_reversals(df, cancellations)
    steps.append(Step("orders reversed by an identical cancellation", len(df) - len(sales), len(sales)))

    sales = sales.assign(
        customer_id=sales["customer_id"].astype("Int64"),
        line_revenue=(sales["quantity"] * sales["unit_price"]).round(2),
        description=sales["description"].fillna("").str.strip(),
    )
    cancellations = cancellations.assign(customer_id=cancellations["customer_id"].astype("Int64"))
    return CleanResult(sales=sales.reset_index(drop=True), cancellations=cancellations.reset_index(drop=True),
                       steps=steps, reversals_matched=reversals)


def _drop_exact_reversals(sales: pd.DataFrame, cancellations: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Removes sale lines that have a later cancellation for the same customer,
    product and absolute quantity. Each cancellation cancels at most one sale."""
    c = cancellations.dropna(subset=["customer_id"]).assign(quantity=lambda x: -x["quantity"])
    s = sales.dropna(subset=["customer_id"])
    keys = ["customer_id", "stock_code", "quantity"]
    c = c.assign(n=c.groupby(keys).cumcount())
    s = s.reset_index().assign(n=lambda x: x.groupby(keys).cumcount())
    matched = s.merge(c[keys + ["n", "invoice_date"]], on=keys + ["n"], suffixes=("", "_cancel"))
    matched = matched[matched["invoice_date_cancel"] >= matched["invoice_date"]]
    return sales.drop(index=matched["index"]), len(matched)
