PROJECT 2

Air Quality Index Analysis and Prediction
Course: Data Engineering and MLOps | Mode: Individual Project | Total Marks: 100
Assignment Part 1 Submission Deadline: On or before 7 September 2026 (First Week of

September)

1. Understanding the Project
   Develop a pipeline that collects air-pollution and weather data, prepares an analytical warehouse, and produces
   dashboards for pollution trends. In Part 2, the system should predict AQI values or AQI categories for a selected
   city or monitoring station.
   Project objectives
   ● Ingest pollution and weather data from free public sources.
   ● Create a time-series ETL pipeline with quality checks.
   ● Store station-wise and city-wise air-quality data.
   ● Build an MLOps pipeline for AQI forecasting or classification.
2. Data Source Information
   Data source Information available Suggested use
   OpenAQ API Open air-quality measurements for pollutants and monitoring

locations.

Primary API source

CPCB historical data India-specific AQI and pollutant observations where

downloadable data is available.

Optional national source

Open-Meteo API Free weather variables such as temperature, humidity, rainfall,

and wind.

Weather enrichment
Kaggle AQI datasets Historical CSV datasets for rapid prototyping. Fallback dataset
Dataset rule: Use only free, legally accessible, public, institutional, or instructor-approved datasets. Include the
source name and access instructions in the report. 3. Data Ingestion Tool Information
Use Python requests for REST API extraction, Pandas for CSV processing, and Apache Airflow for scheduled daily
or hourly ingestion. API responses should be stored first in a raw landing area before transformation.
Minimum ingestion expectations
● Maintain a raw copy of the extracted data.
● Record extraction date, source, file/API status, and row count.
● Handle extraction errors and log failed records.
● Support at least one repeatable or scheduled ingestion workflow.
● Do not manually edit the final analytical dataset. 4. Suggested Data Architecture Design

Individual Project Assignment - Data Engineering and MLOps Page 2
OpenAQ/CPCB/Open-Meteo -> Python API collectors -> raw JSON/CSV landing zone -> Airflow ETL ->
cleaned PostgreSQL time-series tables -> analytics layer -> Tableau Public or Streamlit.
Students should prepare their own architecture diagram showing the source layer, ingestion layer, raw/staging
layer, transformation layer, storage layer, analytics layer, and later the MLOps layer. 5. ETL and Data Engineering Requirements
● Normalize timestamps, station names, and pollutant units.
● Remove duplicate observations.
● Validate pollutant ranges and identify missing periods.
● Join pollution and weather data by station and timestamp.
● Calculate hourly/daily pollutant averages and AQI categories.
● Create gold-layer tables for city, station, pollutant, and date analysis. 6. Suggested Data Visualization
Use Tableau Public for business-oriented dashboards and comparative analysis, or Streamlit when interactive
filtering, user input, or future model prediction is central to the application.
● AQI trend by date and station
● Pollutant contribution analysis
● City or station comparison
● Hourly and monthly AQI patterns
● Weather impact on AQI

Individual Project Assignment - Data Engineering and MLOps Page 3 7. Assignment Part 1 - Data Pipeline Implementation
Deadline: On or before 7 September 2026, which falls in the first week of September.
Students must build a complete data pipeline without adding the final machine-learning deployment at this stage.
Required implementation
● Acquire and document the selected dataset(s).
● Create automated or reproducible ingestion scripts.
● Implement an Apache Airflow DAG, or an approved equivalent ETL workflow.
● Create raw, staging, cleaned, and analytical data layers.
● Apply data-quality checks and produce a rejected-record or error log.
● Load the transformed data into PostgreSQL or another approved open-source database.
● Create at least one analytical table or data mart.
● Develop a Tableau Public or Streamlit dashboard with at least five meaningful views or indicators.
● Prepare an architecture diagram and data dictionary.
● Demonstrate one successful end-to-end pipeline execution.
Part 1 submission package
Item Required submission
1 Source code and ETL scripts
2 Airflow DAG or approved orchestration workflow
3 Database schema and sample populated tables
4 Dataset source information and access instructions
5 Architecture diagram and pipeline flow
6 Data dictionary and validation rules
7 Tableau Public link/file or Streamlit application
8 Project report of approximately 8-10 pages
9 Screenshots or execution evidence
10 README with setup and run instructions 8. Assignment Part 2 - MLOps Pipeline Extension
After completing Part 1, students will extend the same project into an end-to-end MLOps solution. The Part 2
deadline will be announced separately.
● Predict next-day AQI or classify the AQI category.
● Compare regression and classification models.
● Track RMSE/MAE or precision/recall/F1 with MLflow.
● Create a reusable feature pipeline for lag and rolling features.
● Deploy the best model with FastAPI and Docker.
● Monitor missing data, feature drift, and forecasting error.
Common Part 2 requirements
● Create reproducible feature-engineering and model-training pipelines.

Individual Project Assignment - Data Engineering and MLOps Page 4
● Use a chronological or problem-appropriate train/validation/test split.
● Track experiments, parameters, metrics, and artifacts using MLflow.
● Register and version the selected model.
● Serve predictions through FastAPI or an approved API framework.
● Containerize the inference service using Docker.
● Integrate model output into the Streamlit or Tableau-supported workflow where appropriate.
● Monitor input-data quality, drift, model performance, latency, and failures.
● Define retraining criteria and document the model lifecycle. 9. Suggested Mark Distribution
Component Part 1 Part 2
Problem understanding and design 5 5
Data source and ingestion 10 5
ETL, validation, and storage 20 5
Visualization and interpretation 10 5
Documentation and demonstration 5 5
Model development and evaluation - 10
MLflow, registry, deployment, and Docker - 10
Monitoring and retraining design - 5
Total 50 50 10. General Instructions
● The project must be completed individually.
● All source code must be written, organized, and explained by the student.
● Public code may be consulted, but copied work without attribution will not be accepted.
● Use environment variables for database credentials and API keys.
● Do not upload private, personally identifiable, or confidential data.
● The final demonstration must show the pipeline from data ingestion to dashboard output.
● Late submissions will be handled according to course policy.
