FROM python:3.11-slim

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

WORKDIR /app

# 安装系统依赖（编译器 + OCR 等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make pkg-config \
    libgl1 libglib2.0-0 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip wheel

COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# milvus-lite 用了已废弃的 pkg_resources（来自旧版 setuptools）
# 新版 setuptools(>=71) 已移除 pkg_resources，导致 import 失败
# 直接把 milvus_lite 的 import 改成 Python 3.8+ 内置的 importlib.metadata
RUN sed -i 's/from pkg_resources import DistributionNotFound, get_distribution/from importlib.metadata import version as _get_dist_version, PackageNotFoundError as DistributionNotFound/' \
    /usr/local/lib/python3.11/site-packages/milvus_lite/__init__.py \
    && sed -i 's/get_distribution("\(.*\)")\.version/_get_dist_version("\1")/g' \
    /usr/local/lib/python3.11/site-packages/milvus_lite/__init__.py

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
