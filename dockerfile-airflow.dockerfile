# Dockerfile-airflow
FROM apache/airflow:3.0.0

# Switch to airflow user first
USER airflow

# Install dbt packages
RUN pip install --no-cache-dir dbt-core dbt-snowflake
RUN pip install apache-airflow-providers-fab