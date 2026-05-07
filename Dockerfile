FROM python:3.11-slim

WORKDIR /app

# 安装 Chromium 系统依赖
RUN apt-get update && apt-get install -y \
    libnss3 libnspr4 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libcups2 libasound2 libatspi2.0-0 libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

# 安装 Playwright 的 Chromium 浏览器
RUN python3 -m playwright install chromium --with-deps

# 将 Playwright 自带的 Chromium 链接到 PATH，使 _detect_browser_path() 能找到
RUN CHROME_PATH=$(find /root/.cache/ms-playwright -name "chrome" -type f 2>/dev/null | head -1) && \
    if [ -n "$CHROME_PATH" ]; then \
        ln -sf "$CHROME_PATH" /usr/local/bin/chromium && \
        echo "Linked Chromium: $CHROME_PATH"; \
    else \
        echo "WARNING: Chromium binary not found!"; \
    fi

# 复制项目代码
COPY . .

# 设置默认环境变量（容器内必须无头模式）
ENV XHS_INTERFACE_BROWSER_HEADLESS=true

# 暴露端口
EXPOSE 8000

# 启动
CMD ["python3", "run.py", "--host", "0.0.0.0"]
