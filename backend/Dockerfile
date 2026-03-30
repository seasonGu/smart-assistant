FROM python:3.11-slim

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

WORKDIR /app

# 安装系统依赖（编译器 + OCR 等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make pkg-config \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 先升级 pip setuptools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
