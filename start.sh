#!/bin/bash
set -e

apt-get update && apt-get install -y ffmpeg > /dev/null 2>&1

mkdir -p static/voices static/outputs data

python -c "from app.core.config import get_settings; s=get_settings(); print('MINIMAX:', bool(s.MINIMAX_API_KEY))"

exec uvicorn app.main:app --host 0.0.0.0 --port $PORT