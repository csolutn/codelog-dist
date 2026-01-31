from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json

# ==== 런타임/보안 로직 ====
import subprocess
import tempfile
tempfile.tempdir = "/tmp"   # 임시파일 위치 고정
from os import unlink
import json as _json
import re

# FastAPI 앱: 단 한 번만 생성!
app = FastAPI()

# CORS: 여기서 한 번만 추가 (원하면 특정 도메인으로 제한)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # 예: ["https://code.knue.ac.kr"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FORBIDDEN_REGEXES = [
    r'__import__\s*\(',
    r'\bopen\s*\([^)]*["\'].*["\']',
    r'\bimport\s+os\b',
    r'\bimport\s+subprocess\b',
    r'\bimport\s+socket\b',
    r'\bimport\s+urllib\b',
    r'\bimport\s+requests\b',
    r'\bimport\s+ftplib\b',
    r'\bimport\s+paramiko\b',
    r'\bimport\s+pyodbc\b',
    r'\bsocket\s*\.',
    r'\bsubprocess\b',
    r'\b(Popen|call|run)\s*\('
]

def contains_forbidden_keywords(code):
    lowered = code.lower()
    violations = []
    for pattern in FORBIDDEN_REGEXES:
        if re.search(pattern, lowered):
            violations.append(f"[regex] matched: {pattern}")
    return violations

def run_with_timeout(command, timeout):
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    try:
        _stdout, _stderr = proc.communicate(timeout=timeout)
        return {'stdout': _stdout, 'stderr': _stderr, 'returncode': proc.returncode}
    except subprocess.TimeoutExpired:
        proc.kill()
        _stdout, _stderr = proc.communicate()
        return {'stdout': '', 'stderr': f'Execution time exceeded {timeout} seconds.\n{_stderr}', 'returncode': -1, 'timeout': True}
    except Exception as e:
        proc.kill()
        return {'stdout': '', 'stderr': f'An error occurred: {str(e)}', 'returncode': -1}
    finally:
        if proc.stdout: proc.stdout.close()
        if proc.stderr: proc.stderr.close()

def lambda_handler(event, context):
    try:
        if "body" not in event:
            return {'statusCode': 200, 'body': _json.dumps({'stdout': '', 'stderr': '', 'errorMessage': "Missing 'body' in the request."})}

        body = _json.loads(event["body"])
        code = body.get('code')
        language = body.get('language')

        if not code or not language:
            return {'statusCode': 200, 'body': _json.dumps({'stdout': '', 'stderr': '', 'errorMessage': 'Code and language must be provided.'})}

        violations = contains_forbidden_keywords(code)
        if violations:
            return {'statusCode': 200, 'body': _json.dumps({'stdout': '', 'stderr': f"Forbidden keyword(s) detected: {', '.join(violations)}", 'errorMessage': 'Security policy violation. Please remove these keywords and try again.'})}

        if language == 'python':
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp_py_file:
                tmp_py_file.write(code.encode()); tmp_py_file.flush()
                exec_result = run_with_timeout(["python3", tmp_py_file.name], timeout=5)
            unlink(tmp_py_file.name)
            if exec_result.get('timeout'):
                exec_result['lambda_error'] = 'Task timed out after 5.00 seconds'
            return {'statusCode': 200, 'body': _json.dumps(exec_result)}

        elif language == 'c':
            with tempfile.NamedTemporaryFile(suffix=".c", delete=False) as tmp_c_file:
                tmp_c_file.write(code.encode()); tmp_c_file.flush()
                output_file = tempfile.NamedTemporaryFile(delete=False); output_file.close()
                compile_result = run_with_timeout(["gcc", tmp_c_file.name, "-o", output_file.name], timeout=10)
                unlink(tmp_c_file.name)

                if compile_result['returncode'] == 0:
                    exec_result = run_with_timeout([output_file.name], timeout=5)
                    unlink(output_file.name)
                    if exec_result.get('timeout'):
                        exec_result['lambda_error'] = 'Task timed out after 5.00 seconds'
                    return {'statusCode': 200, 'body': _json.dumps(exec_result)}
                else:
                    unlink(output_file.name)
                    return {'statusCode': 200, 'body': _json.dumps({'stdout': '', 'stderr': compile_result['stderr'], 'returncode': compile_result['returncode']})}

        else:
            return {'statusCode': 200, 'body': _json.dumps({'stdout': '', 'stderr': '', 'errorMessage': 'Unsupported language.'})}

    except Exception as e:
        return {'statusCode': 200, 'body': _json.dumps({'stdout': '', 'stderr': '', 'errorMessage': str(e)})}

# === 라우트 ===
@app.post("/invoke")
async def invoke(request: Request):
    payload = await request.json()
    event = {"body": json.dumps(payload)}
    result = lambda_handler(event, None)
    status = result.get("statusCode", 200)
    body = result.get("body", "{}")
    try:
        body_json = json.loads(body)
    except Exception:
        body_json = {"raw": body}
    return JSONResponse(content=body_json, status_code=status)

@app.get("/healthz")
def health():
    return {"ok": True}
