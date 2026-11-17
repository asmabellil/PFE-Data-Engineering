# Image Airflow + Spark (PySpark local) + code du pipeline JobCompass
FROM apache/airflow:2.10.4-python3.11

USER root
# Java est requis par Apache Spark
RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-17-jre-headless procps \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

COPY --chown=airflow:root pipeline /opt/jobinsight/pipeline
RUN mkdir -p /opt/jobinsight/exports /opt/jobinsight/models /opt/jobinsight/data \
 && chown -R airflow:root /opt/jobinsight

USER airflow
# installation "editable" : le dossier ./pipeline est monté en volume en dev,
# une modification du code est donc prise en compte sans reconstruire l'image
RUN pip install --no-cache-dir "apache-airflow==2.10.4" -e "/opt/jobinsight/pipeline[pipeline,ml]"
