FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend /app

EXPOSE 8000

# 建表/迁移/种子数据由 lifespan 内的 init_db() 统一执行
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
