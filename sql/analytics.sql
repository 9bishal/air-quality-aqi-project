-- Daily AQI analysis
CREATE TABLE IF NOT EXISTS mart_aqi_daily AS
SELECT
    DATE(timestamp) AS date,
    city,
    ROUND(AVG(aqi)::numeric, 2) AS average_aqi,
    MAX(aqi) AS maximum_aqi,
    MIN(aqi) AS minimum_aqi,
    COUNT(*) AS record_count
FROM aqi_data
GROUP BY
    DATE(timestamp),
    city
ORDER BY
    date;


-- Pollutant analysis
CREATE TABLE IF NOT EXISTS mart_pollutant_summary AS
SELECT
    city,
    pollutant,
    ROUND(AVG(value)::numeric, 2) AS average_value,
    ROUND(MAX(value)::numeric, 2) AS maximum_value,
    ROUND(MIN(value)::numeric, 2) AS minimum_value,
    COUNT(*) AS record_count
FROM pollution
GROUP BY
    city,
    pollutant
ORDER BY
    city,
    pollutant;