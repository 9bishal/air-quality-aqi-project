-- Pollution measurements
CREATE TABLE IF NOT EXISTS pollution (
    station_id INTEGER,
    station_name VARCHAR(255),
    sensor_id INTEGER,
    pollutant VARCHAR(100),
    value FLOAT,
    unit VARCHAR(50),
    timestamp TIMESTAMP,
    city VARCHAR(100)
);


-- Weather measurements
CREATE TABLE IF NOT EXISTS weather (
    timestamp TIMESTAMP,
    temperature FLOAT,
    humidity FLOAT,
    rainfall FLOAT,
    wind_speed FLOAT
);


-- Final AQI data
CREATE TABLE IF NOT EXISTS aqi_data (
    station_id INTEGER,
    timestamp TIMESTAMP,
    aqi INTEGER,
    aqi_category VARCHAR(50),
    city VARCHAR(100)
);