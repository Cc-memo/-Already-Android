FROM selenium/standalone-chromium:latest

USER root
WORKDIR /app

# 用镜像自带的 venv python/pip（避免 apt 装 python 破坏环境）
# 有些版本 venv 在 /home/seluser/venv
ENV VIRTUAL_ENV=/home/seluser/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt /app/requirements.txt

# 关掉进度条，避免 rich 线程问题 + 网络卡住
RUN python -V && pip -V \
 && PIP_NO_PROGRESS_BAR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    pip install --no-cache-dir --progress-bar off -r /app/requirements.txt

COPY . /app

CMD ["sleep", "infinity"]
