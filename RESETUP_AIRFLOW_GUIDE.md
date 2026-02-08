﻿# Гайд переустановки Airflow (просто, повторяемо, без DevOps‑инструментов)

Цель: локальный код → git push → сервер git pull → Airflow подхватывает DAG-и.

Предположения:
- Сервер Linux, доступ к root/VNC есть хотя бы один раз.
- Airflow уже установлен и управляется systemd.
- Не используем Kubernetes/Ansible/Terraform/Helm.

Что нужно подставить:
- SERVER_IP
- SSH_USER (не root)
- GIT_REPO_SSH_URL (пример: git@github.com:username/airflow-repo.git)
- AIRFLOW_HOME (пример: /home/airflow/airflow)
- AIRFLOW_DAGS_DIR (пример: /home/airflow/airflow/dags)
- AIRFLOW_DB_CONN (строка подключения к PostgreSQL)
- S3 параметры (endpoint, region, ключи)

---

## 0) Одноразово: подключение к серверу
С локального терминала:

    ssh SSH_USER@SERVER_IP

Если сначала есть только VNC/root — создайте обычного пользователя с sudo и подключайтесь уже под ним.

---

## 1) Создать обычного пользователя с sudo (в VNC под root)
Это самый простой и безопасный вариант.

    adduser airflow
    usermod -aG sudo airflow

Затем выйти и подключиться под ним:

    ssh airflow@SERVER_IP

Проверить sudo:

    sudo -v

---

## 2) Найти AIRFLOW_HOME и папку DAG‑ов
Запустить:

    airflow config get-value core dags_folder

Пример:

    /home/airflow/airflow/dags

Сохранить:
- AIRFLOW_HOME=/home/airflow/airflow
- AIRFLOW_DAGS_DIR=/home/airflow/airflow/dags

---

## 3) Подготовить локальный git‑репозиторий
В папке проекта:

    mkdir -p dags plugins requirements
    git init
    git add .
    git commit -m "init airflow repo"
    git branch -M main
    git remote add origin GIT_REPO_SSH_URL
    git push -u origin main

Если на Windows нет git:
- Установить Git for Windows и включить "Git from the command line".

---

## 4) Настроить SSH‑доступ сервера к GitHub (Deploy key)
На сервере:

    ssh-keygen -t ed25519 -C "airflow-server"
    cat ~/.ssh/id_ed25519.pub

Скопировать ключ в GitHub:
- Repo → Settings → Deploy keys → Add deploy key → вставить → Allow write access.

Проверка:

    ssh -T git@github.com

---

## 5) Клонировать репозиторий на сервер и сделать symlink DAG‑ов

    sudo mkdir -p /opt/airflow-repo
    sudo -u airflow git clone GIT_REPO_SSH_URL /opt/airflow-repo
    sudo chown -R airflow:airflow /opt/airflow-repo

Бэкап старых DAG‑ов (если папка существует):

    if [ -d AIRFLOW_DAGS_DIR ]; then
      sudo mv AIRFLOW_DAGS_DIR ${AIRFLOW_DAGS_DIR}.bak
    fi

Сделать симлинк:

    sudo ln -s /opt/airflow-repo/dags AIRFLOW_DAGS_DIR

Проверка:

    ls -la AIRFLOW_DAGS_DIR

Ожидаемый результат:
- AIRFLOW_DAGS_DIR -> /opt/airflow-repo/dags

---

## 6) Создать deploy.sh на сервере (только git pull)

    cd /opt/airflow-repo
    sudo tee deploy.sh > /dev/null <<'SH'
    #!/usr/bin/env bash
    set -e
    git pull
    SH
    sudo chmod +x deploy.sh

Использование:

    cd /opt/airflow-repo
    ./deploy.sh

---

## 7) Создать тестовый DAG локально
Файл: dags/healthcheck_dag.py

    from datetime import datetime
    from airflow import DAG
    from airflow.operators.empty import EmptyOperator

    with DAG(
        dag_id="healthcheck_dag",
        start_date=datetime(2024, 1, 1),
        schedule="@daily",
        catchup=False,
        tags=["healthcheck"],
    ) as dag:
        start = EmptyOperator(task_id="start")
        end = EmptyOperator(task_id="end")
        start >> end

Пуш:

    git add dags/healthcheck_dag.py
    git commit -m "add healthcheck dag"
    git push

Деплой на сервере:

    cd /opt/airflow-repo
    ./deploy.sh

---

## 8) Админ‑пользователь Airflow UI (PostgreSQL)
Если Airflow использует Postgres, нужно работать в той же БД, что и webserver.

Задать переменные:

    export AIRFLOW_HOME=/home/airflow/airflow
    export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN='AIRFLOW_DB_CONN'

Проверить список:

    airflow users list

Создать админа:

    airflow users create \
      --username admin \
      --password 'NEW_PASSWORD' \
      --firstname Admin \
      --lastname User \
      --role Admin \
      --email admin@example.com

Сбросить пароль:

    airflow users reset-password -u admin -p 'NEW_PASSWORD'

После ввода секретов очистить историю:

    history -c

---

## 9) Отключить example DAG-и
Шаги:
1) Изменить config
2) Перезапустить сервисы
3) Удалить уже созданные example DAG-и из БД

Config:

    sudo sed -i 's/^load_examples *= *.*/load_examples = False/' /home/airflow/airflow/airflow.cfg

Проверить окружение systemd (важно, если задан AIRFLOW_HOME):

    systemctl show -p Environment airflow-webserver
    systemctl show -p Environment airflow-scheduler

Перезапуск:

    sudo systemctl restart airflow-webserver
    sudo systemctl restart airflow-scheduler

Удалить example DAG-и из БД (Postgres):

    export AIRFLOW_HOME=/home/airflow/airflow
    export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN='AIRFLOW_DB_CONN'
    airflow dags list | awk '{print $1}' | grep '^example_' | xargs -r -n1 airflow dags delete -y -v

---

## 10) Установить Amazon provider для S3‑совместимого хранилища
Если в UI нет типа "Amazon S3":

    sudo -H python3 -m pip install apache-airflow-providers-amazon --break-system-packages
    sudo systemctl restart airflow-webserver
    sudo systemctl restart airflow-scheduler

Проверка:

    airflow providers list | grep amazon

---

## 11) Создать S3‑совместимый Connection в UI
UI → Admin → Connections → +

Поля:
- Connection Id: s3_twc (пример)
- Connection Type: Amazon S3
- AWS Access Key ID: (ваш ключ)
- AWS Secret Access Key: (ваш секрет)
- Extra:

    {
      "endpoint_url": "https://s3.twcstorage.ru",
      "region_name": "ru-1"
    }

Если только HTTP:

    {
      "endpoint_url": "http://s3.twcstorage.ru",
      "region_name": "ru-1",
      "verify": false
    }

Bucket обычно указывается в коде DAG.

---

## 12) Systemd заметки (Airflow 3.x)
В Airflow 3 удалена команда `airflow webserver`. Используется `airflow api-server`.

Правка unit (если нужно):

    sudo sed -i 's#airflow webserver --port 8080#airflow api-server --port 8080#g' /etc/systemd/system/airflow-webserver.service
    sudo systemctl daemon-reload
    sudo systemctl restart airflow-webserver

---

## 13) Быстрые проверки

Статус:

    sudo systemctl status airflow-webserver --no-pager
    sudo systemctl status airflow-scheduler --no-pager

Порт:

    ss -lntp | grep 8080

---

## 14) Стандартный деплой (повторяемый)

Локально:
    - правка DAG‑ов
    - git add / commit / push

Сервер:

    cd /opt/airflow-repo
    ./deploy.sh

---

## 15) Напоминания по безопасности
- Не хранить пароли в файлах типа `Host airflow-server.txt`.
- Очищать историю после ввода секретов: `history -c`.
- Предпочитать обычного пользователя с sudo вместо root.
