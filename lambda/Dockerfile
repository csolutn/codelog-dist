FROM python:3.9-slim

# 1. gcc 및 필수 도구 설치 (C언어 컴파일용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /var/task

# 2. FastAPI 관련 패키지 설치
RUN pip install --no-cache-dir fastapi uvicorn

# 3. 람다 소스 코드(app.py 등) 복사
COPY . .

# 4. 임시 파일 경로 권한 부여
RUN chmod 777 /tmp

EXPOSE 8080

# 5. 실행 명령: 파일명이 app.py이므로 app:app으로 설정
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]