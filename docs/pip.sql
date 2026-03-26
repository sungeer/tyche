
pip cache purge  # 清除缓存

pip freeze > requirements.txt
pip install -r requirements.txt




python -m pip install asyncmy httpx sqlalchemy starlette orjson uvicorn loguru cryptography

python -m pip install huey



uvicorn hostess:app --host 0.0.0.0 --port 8000


uvicorn hostess:app --port 7788


# 多 worker 进程 充分利用多核 CPU
uvicorn app:app --workers 4 --host 0.0.0.0 --port 8000

# 或者用 gunicorn 管理 uvicorn workers（更稳健）
gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000


uvicorn app:app

huey_consumer worker.huey



ps -ef | grep -v grep | grep uvicorn


# -------------------------
# App / State (Starlette-ish)
# -------------------------

TRUNCATE TABLE job_log;





