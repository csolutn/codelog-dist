FROM python:3.9-slim
WORKDIR /app

# 1. app 폴더 내의 requirements.txt를 현재 WORKDIR(./)로 복사
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# 2. app 폴더의 모든 내용을 현재 WORKDIR(./)로 복사
COPY app/ .

# 3. 실행 (파일이 /app/app.py에 있으므로 바로 호출)
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "app:app"]