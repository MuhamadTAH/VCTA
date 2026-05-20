#!/bin/bash
set -e

mkdir -p static/voices static/outputs data

exec uvicorn app.main:app --host 0.0.0.0 --port $PORT