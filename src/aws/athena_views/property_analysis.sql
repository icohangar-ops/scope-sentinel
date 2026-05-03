-- Athena View: Property Analysis
-- Portfolio composition, geographic diversification, occupancy trends

CREATE OR REPLACE VIEW scope_sentinel.property_analysis_v AS
SELECT
    r.ticker,
    r.name,
    r.sector,
    COUNT(*) AS total_properties,
    SUM(p.sqft) AS total_sqft,
    AVG(p.occupancy_rate) AS avg_occupancy_rate,
    AVG(p.annual_rent_psf) AS avg_rent_psf,
    AVG(p.cap_rate) AS avg_cap_rate,
    AVG(p.lease_expiry_weighted_avg) AS avg_lease_expiry_years,
    SUM(CASE WHEN p.occupancy_rate >= 0.95 THEN 1 ELSE 0 END) AS high_occupancy_count,
    SUM(CASE WHEN p.occupancy_rate < 0.85 THEN 1 ELSE 0 END) AS low_occupancy_count,
    COUNT(DISTINCT p.state) AS state_count,
    COUNT(DISTINCT p.msa) AS msa_count,
    -- Geographic concentration (top MSA %)
    (SELECT MAX(cnt) FROM (
        SELECT COUNT(*) AS cnt FROM scope_sentinel.properties p2
        WHERE p2.reit_ticker = r.ticker GROUP BY p2.msa
    ) sub) AS max_msa_concentration
FROM scope_sentinel.reits r
LEFT JOIN scope_sentinel.properties p
    ON r.ticker = p.reit_ticker
WHERE p.status = 'Operating'
GROUP BY r.ticker, r.name, r.sector
ORDER BY r.sector, total_sqft DESC;
