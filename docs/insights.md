# Findings and recommendations

Source: UCI Online Retail II, a UK online gift wholesaler (many customers are small shops), December 2009 – December 2011, after the cleaning described in the README. "Year 1" = Dec 2009 – Nov 2010, "Year 2" = Dec 2010 – Nov 2011 (December 2011 has only 9 days and is left out of trends). Every number below comes from the SQL views in [`sql/02_analytics.sql`](../sql/02_analytics.sql).

## 1. Growth came from bigger orders, not more orders

| | Year 1 | Year 2 | Change |
|---|---:|---:|---:|
| Revenue | £9.20M | £9.43M | **+2.5%** |
| Orders | 19,630 | 18,894 | −3.7% |
| Average order value | £468.69 | £498.96 | **+6.5%** |
| Customers who ordered | 4,226 | 4,284 | +1.4% |

The business grew slightly while placing fewer orders. **Recommendation:** order frequency is the lever that hasn't moved; see the reactivation and repeat-order ideas below.

## 2. A quarter of customers bring 70% of revenue

| Segment (RFM) | Customers | Share of revenue | Avg. days since last order |
|---|---:|---:|---:|
| Champions | 1,469 (25%) | **70.4%** | 20 |
| Loyal | 1,227 | 14.8% | 79 |
| At risk (were loyal) | 350 | 6.3% | **345** |
| Needs attention | 1,162 | 4.7% | 417 |
| Hibernating, new, potential | 1,631 | 3.7% | — |

- Losing a few Champions hurts more than winning many new customers. **Recommendation:** an account-manager style service for the top segment (early access to the Christmas range, volume pricing).
- **350 "At risk" customers** used to order often (7.7 orders on average) and have been silent for almost a year; together they spent £1.04M. **Recommendation:** a targeted win-back campaign; recovering even 10% of their past spend is worth about £100k.
- 27.6% of customers ordered only once.

## 3. Repeat buying is steady at about 20%

On average **21%** of a month's new customers order again in the next month, and the share stays around **19–23%** for the following year (cohorts Dec 2009 – Nov 2010). The very first cohort (Dec 2009, which also contains every customer who already existed before the data starts) keeps **33–50%**.

Retention doesn't decay much after month 1, which is typical of trade buyers: those who stay, stay. **Recommendation:** focus on the first 30 days after a first order (welcome series, reorder reminder, a small second-order incentive) because that is where most customers are lost.

## 4. Strong Christmas seasonality

September to November is **36%** (Year 1) and **37%** (Year 2) of the year's revenue; November alone is the peak month in both years (£1.40M and £1.44M). **Recommendation:** plan stock and marketing from August, and launch the Christmas range by early September.

## 5. When customers order

- Orders peak at **12:00–13:00** and **97.7%** arrive between 08:00 and 18:00, like a business-hours B2B shop.
- **Saturday has 30 orders out of 38,524**, so the shop is effectively closed on Saturdays while Sunday is open. **Recommendation:** time email campaigns for Tuesday–Thursday late morning, the busiest window.

## 6. Products and markets

- The top **20% of products bring 78% of revenue** (classic Pareto). The best sellers are the Regency cake stand, the white hanging heart T-light holder and the Jumbo bags.
- Strong "bought together" pairs: teacup colour variants (lift up to 21), hand warmer designs, Bakelike alarm clock colours, lunch boxes. **Recommendation:** "complete the set" bundles and cross-sell on product pages.
- The UK is **85%** of revenue. Abroad, the top two markets hang on very few accounts: **Ireland (EIRE) is 3 customers** and the **Netherlands 22 customers** with an average order of **£2,553**. Germany (107 customers) and France (93) are broader. **Recommendation:** treat the Irish and Dutch accounts as key accounts; losing one of them would visibly dent export revenue.

## 7. Data quality notes that affect the numbers

- **23% of transaction lines have no customer ID** (guest checkout). They are 7.4% of orders but 13.5% of revenue: a guest order averages **£881** against **£453** for a registered one. Customer-level analysis (RFM, cohorts) can't include them. **Recommendation:** encourage account creation at checkout, since these are valuable buyers the business currently can't follow up.
- Cancellations are **2.9%** of sales value; they are analysed separately instead of netted into revenue.
- 6,180 lines were orders entered by mistake and cancelled with the exact same quantity (one of them 80,995 units). Leaving them in would have made two customers look like the biggest buyers in the dataset.

## Caveats

- The data is from 2009–2011 and from one wholesaler; it shows how the analysis works, not what any other business should do.
- RFM uses quintiles and fixed rules (see `sql/02_analytics.sql`). Other thresholds give somewhat different segment sizes; the 70% concentration does not change much.
- The dataset has no costs, so this is about revenue, not profit.
