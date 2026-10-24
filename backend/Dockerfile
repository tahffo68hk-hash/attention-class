FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 先装依赖，利用镜像层缓存；镜像源可用 --build-arg 覆盖（默认国内镜像）
ARG PIP_INDEX=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_HOST=mirrors.aliyun.com
COPY requirements.txt ./
RUN pip install --no-cache-dir -i "${PIP_INDEX}" --trusted-host "${PIP_HOST}" -r requirements.txt

COPY . .

EXPOSE 8000

# 迁移 -> 空库时写演示数据 -> 起服务，见 docker-entrypoint.sh
CMD ["sh", "docker-entrypoint.sh"]
