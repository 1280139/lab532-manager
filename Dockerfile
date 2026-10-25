# Docker 部署
# 用法：
#   docker build -t lab532 .
#   docker run -d -p 8000:8000 \
#     -e SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))") \
#     -v lab532-data:/data \
#     lab532

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_ENV=prod
ENV DATA_DIR=/data
ENV HTTPS_ONLY=1
RUN mkdir -p /data

# 启动前跑迁移，保证表结构最新
CMD ["sh", "-c", "python manage.py migrate && python wsgi.py"]

EXPOSE 8000
