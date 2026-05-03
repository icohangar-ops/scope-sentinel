-- Athena View: REIT Fundamentals
-- FFO/AFFO rankings, same-store NOI growth, dividend analysis

CREATE OR REPLACE VIEW scope_sentinel.reit_fundamentals_v AS
SELECT
    r.ticker,
    r.name,
    r.sector,
    r.sub_sector,
    fm.fiscal_year,
    fm.quarter,
    fm.ffo_per_share,
    fm.affo_per_share,
    fm.ffo_growth_yoy,
    fm.same_store_noi,
    fm.same_store_noi_growth,
    fm.dividend_per_share,
    fm.dividend_growth_yoy,
    fm.net_debt_to_ebitda,
    fm.interest_coverage,
    r.dividend_yield,
    r.payout_ratio,
    -- Derived metrics
    CASE
        WHEN fm.affo_per_share > 0 THEN ROUND(fm.dividend_per_share / fm.affo_per_share, 4)
        ELSE NULL
    END AS affo_payout_ratio,
    CASE
        WHEN fm.ffo_per_share > 0 THEN ROUND(fm.dividend_per_share / fm.ffo_per_share, 4)
        ELSE NULL
    END AS ffo_payout_ratio,
    CASE
        WHEN fm.net_debt_to_ebitda <= 3.0 THEN 'A'
        WHEN fm.net_debt_to_ebitda <= 5.0 THEN 'B'
        WHEN fm.net_debt_to_ebitda <= 7.0 THEN 'C'
        ELSE 'D'
    END AS leverage_rating,
    CASE
        WHEN fm.affo_per_share > 0 AND fm.dividend_per_share / fm.affo_per_share <= 0.60 THEN 'Very Safe'
        WHEN fm.affo_per_share > 0 AND fm.dividend_per_share / fm.affo_per_share <= 0.75 THEN 'Safe'
        WHEN fm.affo_per_share > 0 AND fm.dividend_per_share / fm.affo_per_share <= 0.85 THEN 'Moderate'
        WHEN fm.affo_per_share > 0 AND fm.dividend_per_share / fm.affo_per_share <= 0.95 THEN 'Risky'
        ELSE 'Unsafe'
    END AS dividend_safety,
    fm.created_at
FROM scope_sentinel.reits r
LEFT JOIN scope_sentinel.financial_metrics fm
    ON r.ticker = fm.reit_ticker
WHERE fm.quarter IS NOT NULL
ORDER BY r.sector, fm.ffo_per_share DESC;
