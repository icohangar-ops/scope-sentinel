-- Athena View: Market Correlation
-- REIT prices vs interest rates, CPI correlation, sector rotation signals

CREATE OR REPLACE VIEW scope_sentinel.market_correlation_v AS
SELECT
    pd.ticker,
    r.sector,
    r.sub_sector,
    pd.date,
    pd.close AS price,
    pd.volume,
    -- Rate correlation data (latest available)
    (SELECT value FROM scope_sentinel.market_indicators
     WHERE series_id = 'FEDFUNDS' AND date <= pd.date
     ORDER BY date DESC LIMIT 1) AS fed_funds_rate,
    (SELECT value FROM scope_sentinel.market_indicators
     WHERE series_id = 'DGS10' AND date <= pd.date
     ORDER BY date DESC LIMIT 1) AS treasury_10y,
    (SELECT value FROM scope_sentinel.market_indicators
     WHERE series_id = 'DGS2' AND date <= pd.date
     ORDER BY date DESC LIMIT 1) AS treasury_2y,
    -- Returns
    LAG(pd.close) OVER (PARTITION BY pd.ticker ORDER BY pd.date) AS prev_close,
    CASE
        WHEN LAG(pd.close) OVER (PARTITION BY pd.ticker ORDER BY pd.date) > 0
        THEN ROUND((pd.close - LAG(pd.close) OVER (PARTITION BY pd.ticker ORDER BY pd.date))
                   / LAG(pd.close) OVER (PARTITION BY pd.ticker ORDER BY pd.date) * 100, 4)
        ELSE NULL
    END AS daily_return_pct,
    -- 20-day moving average
    ROUND(AVG(pd.close) OVER (
        PARTITION BY pd.ticker
        ORDER BY pd.date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ), 2) AS ma_20,
    -- 50-day moving average
    ROUND(AVG(pd.close) OVER (
        PARTITION BY pd.ticker
        ORDER BY pd.date
        ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
    ), 2) AS ma_50
FROM scope_sentinel.price_data pd
JOIN scope_sentinel.reits r ON pd.ticker = r.ticker
ORDER BY pd.date DESC, pd.ticker;
