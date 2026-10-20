import pandas as pd

from src.clean import clean, is_product


def frame(rows):
    return pd.DataFrame(rows, columns=["invoice", "stock_code", "description", "quantity", "invoice_date",
                                       "unit_price", "customer_id", "country"]).assign(
        invoice_date=lambda d: pd.to_datetime(d["invoice_date"]))


def test_product_codes():
    codes = pd.Series(["85123A", "POST", "DOT", "M", "gift_0001_20", "DCGSSBOY", "BANK CHARGES", "21730"])
    assert is_product(codes).tolist() == [True, False, False, False, False, False, False, True]


def test_rules_remove_what_they_should():
    raw = frame([
        ["500001", "85123A", "HEART HOLDER", 6, "2010-01-04 10:00", 2.55, 17850, "United Kingdom"],
        ["500001", "85123A", "HEART HOLDER", 6, "2010-01-04 10:00", 2.55, 17850, "United Kingdom"],  # duplicate
        ["500002", "POST", "POSTAGE", 1, "2010-01-04 11:00", 18.0, 12583, "France"],                 # postage
        ["C500003", "21730", "LANTERN", -2, "2010-01-05 09:00", 4.25, 17850, "United Kingdom"],       # cancellation
        ["500004", "21733", "short", -96, "2010-01-05 12:00", 0.0, None, "United Kingdom"],          # stock adjustment
        ["500005", "22423", "CAKESTAND", 1, "2010-01-06 12:00", 0.0, 13047, "United Kingdom"],        # free item
        ["500006", "22688", "BOWL", 3, "2010-01-06 13:00", 1.25, None, "EIRE"],                       # guest, kept
    ])
    r = clean(raw)
    removed = {s.rule.split(" (")[0]: s.removed for s in r.steps}
    assert removed["exact duplicate rows"] == 1
    assert removed["non-product lines"] == 1
    assert removed["stock adjustments"] == 1
    assert removed["zero or negative price"] == 1
    assert len(r.cancellations) == 1
    assert sorted(r.sales["invoice"]) == ["500001", "500006"]
    assert r.sales.loc[r.sales["invoice"] == "500001", "line_revenue"].item() == 15.30
    assert r.sales["customer_id"].isna().sum() == 1


def test_an_order_cancelled_with_the_same_quantity_is_removed():
    raw = frame([
        ["541431", "23166", "STORAGE JAR", 74215, "2011-01-18 10:01", 1.04, 12346, "United Kingdom"],
        ["C541433", "23166", "STORAGE JAR", -74215, "2011-01-18 10:17", 1.04, 12346, "United Kingdom"],
        # same product and customer, different quantity: a normal sale, kept
        ["541500", "23166", "STORAGE JAR", 12, "2011-01-20 10:00", 1.04, 12346, "United Kingdom"],
    ])
    r = clean(raw)
    assert r.reversals_matched == 1
    assert r.sales["quantity"].tolist() == [12]


def test_a_cancellation_before_the_sale_does_not_remove_it():
    raw = frame([
        ["C500001", "23166", "JAR", -5, "2010-01-01 10:00", 1.0, 1, "United Kingdom"],
        ["500002", "23166", "JAR", 5, "2010-01-02 10:00", 1.0, 1, "United Kingdom"],
    ])
    r = clean(raw)
    assert r.reversals_matched == 0 and len(r.sales) == 1
