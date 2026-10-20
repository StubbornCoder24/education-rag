FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY suite ./suite
COPY static ./static
COPY samples ./samples
COPY 启动项目.py 初始化样例.py ./
ENV APP_MODE=demo APP_DATA=/data
VOLUME ["/data"]
EXPOSE 8001
CMD ["python", "启动项目.py", "--host", "0.0.0.0", "--port", "8001"]
