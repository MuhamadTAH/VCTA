#!/bin/bash
set -o errexit

pip install -r requirements.txt

mkdir -p static/voices static/outputs data

python -m app.core.database &
sleep 2

exec uvicorn app.main:app --host 0.0.0.0 --port $PORT