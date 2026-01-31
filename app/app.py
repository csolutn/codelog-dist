from flask import Flask, request, jsonify, render_template, session, redirect, g
from flask_babel import Babel, _
from bcrypt import hashpw, gensalt, checkpw
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
import os, re, requests, json
from datetime import datetime


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SESSION_KEY')

# Babel 설정
LANGUAGES = {
    'en': 'English',
    'ko': 'Korean'
}
def get_locale():
    return request.accept_languages.best_match(LANGUAGES.keys())
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'
babel = Babel(app, locale_selector = get_locale)

def format_timestamp(value):
    try:
        return datetime.fromtimestamp(int(value) / 1000).strftime('%Y-%m-%d %H:%M')
    except:
        return "-"
app.jinja_env.filters['format_timestamp'] = format_timestamp


# 기본 DB 클라이언트 (ACTIVE 고정)
DEFAULT_DB_CLIENT = MongoClient(os.getenv('ACTIVE'))
DEFAULT_DB = DEFAULT_DB_CLIENT['Codelog']
DB_CLIENTS = {}  # 전역 dict: {'ACTIVE': MongoClient(...), 'ARCHIVE': MongoClient(...)}

def get_db():
    uri = session.get('db_uri')
    if not uri:
        uri = os.getenv('ACTIVE')  # fallback
    if uri not in DB_CLIENTS:
        DB_CLIENTS[uri] = MongoClient(uri)
    return DB_CLIENTS[uri]['Codelog']

def get_collections():
    db_selected = get_db()  # responses 전용
    return DEFAULT_DB['Problems'], DEFAULT_DB['Sheets'], db_selected['Responses'], DEFAULT_DB['Students']

# # 비밀번호 해시 생성 함수
def hash_password(password):
    return hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')

@app.route('/')
def index():
    studentid = ""
    name = ""
    if 'login' in session:
        studentid  = session["login"]["studentid"]
        name = session["login"]["name"]
    return render_template('index.html', studentid=studentid, name=name)

@app.route('/input')
def input_html():
    return render_template('input.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect('/')

@app.route('/get_problem')
def get_problem():
    alias = request.args.get('alias')
    collection, *_ = get_collections()
    problem = collection.find_one({"alias": alias})

    if problem:
        return jsonify({
            "alias": alias,
            "title": problem.get("title"),
            "desc": problem.get("desc"),
            "ph": problem.get("ph"),
            "example": problem.get("example"),
            "test": problem.get("test"),
            "lang": problem.get("lang"),
        })
    else:
        return jsonify({"error": _("Problem not found")}), 404

def get_data(alias, studentid, name):
    _, sheets_collection, _, _ = get_collections()
    data = []
    sheet = sheets_collection.find_one({'alias': alias})
    problem_list = sheet["problem_list"] if sheet else [alias]

    for problem_alias in problem_list:
        documents = get_problem_data(problem_alias, studentid, name)
        data.extend(documents)
    return data

def get_problem_data(alias, studentid, name):
    responses_collection = DEFAULT_DB["Responses"]
    cursor = responses_collection.find(
        {'problem_alias': alias, 'sid': studentid, 'name': name},
        {'_id': 1, 'timestamp': 1, 'content': 1, 'success': 1}
    ).sort('_id', -1)

    results = []
    for doc in cursor:
        results.append({
            '_id': str(doc['_id']),
            'problem_alias': alias,
            'timestamp': doc.get('timestamp', ""),
            'content': doc.get('content', ""),
            'result': doc.get('success', "")
        })

    if not results:
        results.append({
            '_id': None,
            'problem_alias': alias,
            'timestamp': "",
            'content': "",
            'result': ""
        })
    return results


@app.route('/create')
def create():
    return render_template('create.html')

@app.route('/playback')
def playback():
    return render_template('playback.html')

@app.route('/play')
def play():
    return render_template('play.html')

@app.route('/add_problem', methods=['POST'])
def add_problem():
    collection, sheets_collection, _, _ = get_collections()

    problem_data = request.json
    alias = problem_data.get('alias')

    # alias 중복 여부 확인
    existing_problem = collection.find_one({'alias': alias})
    existing_sheet = sheets_collection.find_one({'alias': alias})
    if existing_problem or existing_sheet:
        return jsonify({"error": "Alias already exists. Please use a unique alias."}), 400

    # 데이터 추가
    collection.insert_one(problem_data)
    return jsonify({"message": "Problem successfully added!"}), 201

def get_test_data(alias):
    collection, *_ = get_collections()
    # alias로 검색하며 필요한 필드만 가져옴
    document = collection.find_one(
        {"alias": alias},
        {"test.input": 1, "test.output": 1, "lang": 1, "_id": 0}  # Projection: 필요한 필드만 가져옴
    )

    # 결과 처리
    if document and "test" in document:
        test_data = {
            "input": document["test"].get("input", ""),
            "output": document["test"].get("output", ""),
            "lang": document.get("lang", "")
        }
        return test_data
    else:
        return None  # alias가 존재하지 않거나 테스트 데이터가 없는 경우

@app.route('/save_response', methods=['POST'])
def save_response():
    *x, responses_collection, x = get_collections()
    try:
        # 클라이언트에서 보낸 데이터 가져오기
        data = request.get_json()
        problemalias = data.get('problem_alias')

        # 채점 가능하면 채점하기
        test_data = get_test_data(problemalias)
        if test_data:
            result = execute_test(data['content'],test_data)
            success = result["success"]
            if 'login' in session and session['login'] in admin_list:
                debug = str(
                    '\n<div class="debug-text">'
                    "----------\ntest debug\n----------"
                    "\n<code>stdout:</code>\n" + result["stdout"] +
                    "\n<code>stderr:</code>\n" + result["stderr"] +
                    "\n<code>test output:</code>\n" + test_data["output"] +
                    "\n<code>test code:</code>\n" + result["code"] +
                    "\n</div>"
                )
            else:
                debug = ""
            output = str (
                "\n<code>stdout:</code>\n" + result["stdout"] +
                "\n<code>stderr:</code>\n" + result["stderr"] +
                "\n<code>test output:</code>\n" + test_data["output"]
                )
        else:
            debug = ""
            success = None
            output = None
            result = {
                "stdout": "",
                "stderr": "",
                "code": ""
            }
            test_data = {
                "output": ""
            }
        success = json.dumps(success)
        # 유효성 검사: _id 필드 확인 (업데이트할 도큐먼트 식별용)
        document_id = data.get('_id')
        # ================================
        # 요청 정보 프린트
        print(f"[save_response] sid: {data.get('sid')}, log_len: {len(data.get('log', []))}, timestamp: {data.get('timestamp')}")
        # ================================

        if document_id:
            # _id 값을 ObjectId로 변환
            document_id = ObjectId(document_id)

            # 기존 도큐먼트 업데이트 (log 필드 업데이트)
            result = responses_collection.update_one(
                {"_id": document_id},
                {
                    "$set": {
                        "sid": data['sid'],
                        "name": data['name'],
                        "content": data['content'],
                        "timestamp": data['timestamp'],
                        "success": success,
                        "output": output,
                        "log": data['log'],
                    }
                }
            )
            # 업데이트 결과 확인
            if result.matched_count > 0:
                return jsonify({"success":success, "debug":debug, "message": _("Answer updated"), "_id": {"$oid": str(document_id)}}), 200
        else:
            # local이면 data에서 _id 항목 삭제
            if '_id' in data:
                del data['_id']
            # 업데이트할 도큐먼트가 없으면 새로운 도큐먼트 생성
            data["success"] = success
            data["output"] = str (
                "\n<code>stdout:</code>\n" + result["stdout"] +
                "\n<code>stderr:</code>\n" + result["stderr"] +
                "\n<code>test output:</code>\n" + test_data["output"]
                )
            result = responses_collection.insert_one(data)
            return jsonify({"success":success, "debug":debug, "message": _("New answer created"), "_id": {"$oid": str(result.inserted_id)}}), 200
    except Exception as e:
        print(f"[save_response][ERROR] sid: {data.get('sid', 'N/A')}, log_len: {len(data.get('log', []))}, timestamp: {data.get('timestamp', 'N/A')}")
        print(_("Error occurred while saving answer: "), e)
        return jsonify({"error": _("Failed to save the answer")}), 500

@app.route('/get_log', methods=['GET'])
def get_log():
    *_, responses_collection, _ = get_collections()
    mongo_id = request.args.get('id')
    if not mongo_id:
        return jsonify({"error": "No MongoDB _id provided"}), 400

    try:
        # Find the document by _id
        from bson.objectid import ObjectId
        document = responses_collection.find_one({"_id": ObjectId(mongo_id)})
        if document is None:
            return jsonify({"error": "No document found with the provided _id"}), 404

        # Return the log data
        return jsonify(document.get("log", []))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/get_sheet', methods=['GET'])
def get_sheet():
    x, sheets_collection, *x = get_collections()

    alias = request.args.get('alias')

    if not alias:
        return jsonify({"error": _("Alias parameter is missing")}), 400

    # alias를 기준으로 Sheets 컬렉션에서 문제 목록을 검색
    sheet = sheets_collection.find_one({"alias": alias})

    if sheet and "problem_list" in sheet:
        return jsonify({"problem_list": sheet["problem_list"]})
    else:
        return jsonify({"problem_list": [alias]})
    
# 페이지 라우트

@app.route('/log', methods=['GET', 'POST'])
def login():
    *x, students_collection = get_collections()
    aliases = []
    sheets_response = []
    number = 0
    studentid=""
    name=""
    password=""
    message=""
    if 'login' in session :
        studentid = session['login']['studentid']
        name = session['login']['name']
        aliases = get_aliases(studentid, name)
        for alias in aliases :
            data = get_data(alias, studentid, name)
            if (data and data != []):
                sheets_response.append(data)
        number = len(aliases)
        return render_template("log.html", 
                            message = message, 
                            sheets = aliases, 
                            sheets_response = sheets_response, 
                            number = number, studentid = studentid, 
                            name = name, 
                            password = password)
    elif request.method == 'POST':
        studentid = request.form.get('studentid')
        name = request.form.get('name')
        password = request.form.get('password')

        if not studentid or not name or not password:
            message  = _("There are missing required fields")
        else: 
            # 학생 정보 확인
            existing_student = students_collection.find_one({"studentid": studentid, "name": name})

            if existing_student:
                # 비밀번호 대조
                if checkpw(password.encode('utf-8'), existing_student['password'].encode('utf-8')):
                    # 로그인 성공 시 alias 리스트 반환
                    aliases = get_aliases(studentid, name)
                    message = _("Login successful!")
                    session["login"] = {"studentid": studentid, "name": name}

                else:
                    message = _("Invalid password.")
                    # 정보 초기화
                    studentid=""
                    name=""
            else:
                # 새로운 학생 등록
                hashed_password = hash_password(password)
                new_student = {
                    "studentid": studentid,
                    "name": name,
                    "password": hashed_password
                }
                students_collection.insert_one(new_student)
                aliases = get_aliases(studentid, name)
                message = _("Account created and logged in successfully!")
                session["login"] = {"studentid": studentid, "name": name}
            for alias in aliases :
                data = get_data(alias, studentid, name)
                sheets_response.append(data)
            number = len(aliases)
    return render_template("log.html", 
                            message = message, 
                            sheets = aliases, 
                            sheets_response = sheets_response, 
                            number = number, studentid = studentid, 
                            name = name, 
                            password = password)

def get_aliases(studentid, name):
    
    *_, responses_collection, _ = get_collections()
    documents = responses_collection.find(
    {"sid": studentid, "name": name},
    {"_id": 0, "alias": 1}  # Projection: alias 필드만 반환
    )

    aliases = set()
    for doc in documents:
        if "alias" in doc:
            aliases.add(doc["alias"])
    aliases = list(aliases)
    aliases.sort()
    return aliases

def check_single(s):
    # 정규식: 영어 소문자, 숫자, 그리고 특수문자로만 이루어진 문자열 검사
    return bool(re.fullmatch(r'(?=.*[a-z])[a-z0-9!@#$%^&*(),.?":{}|<>\-_]+', s))

def c_test_insert(source_code, insert_string):
    # 'int main' 패턴을 찾는 정규식 (다양한 스타일 지원)
    pattern = r"(.*?)(int\s+main\s*\(\s*(?:void)?\s*\)\s*\{)([\s\S]*?)(^\})\s*(.*)"

    match = re.search(pattern, source_code, re.DOTALL | re.MULTILINE)
    
    if match:
        # 그룹화된 부분 추출
        before_main = match.group(1)  # 'int main()' 앞의 모든 코드
        main_signature = match.group(2).strip()  # 'int main(void) {' (공백 제거)
        main_body = match.group(3).strip()  # '{...}' 내부 코드 (공백 제거)
        closing_brace = match.group(4)  # '}' 닫는 중괄호 (줄바꿈 포함)
        after_main = match.group(5)  # '}' 이후의 모든 코드

        # `return` 문 찾기
        return_match = re.search(r"^\s*(return\s+[^;]+;)", main_body, re.MULTILINE)

        if return_match:
            # `return` 문을 찾아 저장 후 삭제
            return_statement = return_match.group(1)
            main_body = re.sub(r"^\s*return\s+[^;]+;", "", main_body, flags=re.MULTILINE).strip()

            # 새로운 코드 삽입 후 return 추가
            updated_main_body = main_body + "printf(\"\\n\"); //test code begins"+"\n" + insert_string + "\n" + return_statement
        else:
            # `return`이 없는 경우 그냥 추가
            updated_main_body = main_body + "\nprintf(\"\\n\"); //test code begins"+"\n" + insert_string

        # 최종 코드 조합
        return f"{before_main}{main_signature}\n{updated_main_body}\n{closing_brace}{after_main}"
    else:
        return source_code  # 패턴이 없으면 원본 반환


LAMBDA_BASE_URL = os.getenv("LAMBDA_BASE_URL")

@app.route("/api/lambda/invoke", methods=["POST"])
def proxy_lambda_invoke():
    if not request.is_json:
        return jsonify({"error": "Invalid JSON"}), 400

    payload = request.get_json()

    try:
        resp = requests.post(
            f"{LAMBDA_BASE_URL}/invoke",
            json=payload,
            timeout=10
        )

        return (
            resp.text,
            resp.status_code,
            {"Content-Type": resp.headers.get("Content-Type", "application/json")}
        )

    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "Lambda service unavailable",
            "detail": str(e)
        }), 503


def execute_test(code, test_data):
    input = test_data["input"]
    output = test_data["output"]
    lang = test_data["lang"]
    if (lang=='c'):
        code = c_test_insert(code, input)
        # print(code)
    else:
        code  = code+"\n"+input
    # Lambda Function URL
    url = f"{LAMBDA_BASE_URL}/invoke"

    # 요청 데이터
    payload = {
        "code": code,
        "language": lang
    }
    try:
        # POST 요청 보내기
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json"  # JSON 데이터 형식 명시
            },
            data=json.dumps(payload)  # JSON 형식으로 데이터 직렬화
        )
        # 응답 상태 확인
        if response.status_code == 200:
            # JSON 응답 파싱
            data = response.json()
            lambda_output = data.get('stdout')  # Lambda에서 반환된 출력
            def normalize(text):
                """불필요한 공백과 줄바꿈을 제거하고, 텍스트를 비교-friendly하게 변환"""
                return re.sub(r'\s+', '', text).strip()  # 연속된 공백을 단일 공백으로 변환
            normal_output = normalize(output)
            normal_lambda_output = normalize(lambda_output)
            # print(normal_output)
            # print(normal_lambda_output)
            data["success"] = normalize(normal_lambda_output).endswith(normal_output)
            data["code"] = code
            # 결과 비교
            return data
        else:
            print(f"HTTP error! Status code: {response.status_code}, Response: {response.text}")
            return None
    except Exception as e:
        print("Error calling Lambda Function:", e)
        return None
    
@app.route('/code_login', methods=['POST'])
def code_login():
    *x, students_collection = get_collections()

    if 'login' in session :
        return jsonify({"message": _("Login successful!"), "status": "success"})
        # JSON 데이터 가져오기
    else :
        data = request.get_json()

    # studentId, studentName, password 값 가져오기
    studentid = data.get('studentId')
    name = data.get('studentName')
    password = data.get('password')

    if not studentid or not name or not password:
        message  = _("There are missing required fields")
        status = "fail"
        return jsonify({"message": message, "status": status}), 400  # 여기에 반환 추가

    else: 
        # 학생 정보 확인
        existing_student = students_collection.find_one({"studentid": studentid, "name": name})

        if existing_student:
            # 비밀번호 대조
            if checkpw(password.encode('utf-8'), existing_student['password'].encode('utf-8')):
                # 로그인 성공 시 alias 리스트 반환
                message = _("Login successful!")
                status = "success"

            else:
                message = _("Invalid password.")
                status = "fail"
        else:
            # 새로운 학생 등록
            hashed_password = hash_password(password)

            new_student = {
                "studentid": studentid,
                "name": name,
                "password": hashed_password
            }
            students_collection.insert_one(new_student)
            message = _("Account created and logged in successfully!")
            status = "success"
        data = {
            "message": message,
            "status": status
        }
        if data["status"] == "success" :
            session["login"] = {"studentid": studentid, "name": name}
        return jsonify(data)
    
#admin
admin_list = json.loads(os.getenv("ADMIN_LIST", "[]"))

@app.route('/admin')
def admin():
    if 'login' in session and session['login'] in admin_list:
        return render_template('admin.html')
    else:
        return redirect('/')

@app.route('/add_sheet', methods=['POST'])
def add_sheet():
    collection, sheets_collection, *_ = get_collections()

    data = request.get_json()
    alias = data.get('alias')
    course = data.get('course')
    problem_list = data.get('problem_list')

    if not alias or not course or not problem_list:
        return jsonify({'error': 'All fields are required.'}), 400

    # Ensure problem_list is a list of strings
    if isinstance(problem_list, str):
        problem_list = [item.strip() for item in problem_list.split(',')]

    sheet_data = {
        "alias": alias,
        "course": course,
        "problem_list": problem_list
    }

    existing_problem = collection.find_one({'alias': alias})
    existing_sheet = sheets_collection.find_one({'alias': alias})

    if existing_problem or existing_sheet:
        return jsonify({"error": "Alias already exists. Please use a unique alias."}), 400

    try:
        sheets_collection.insert_one(sheet_data)  # Insert into MongoDB
        return jsonify({'message': 'Sheet successfully added!'})
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/reset_password', methods=['POST'])
def reset_password():
    *_, students_collection = get_collections()

    data = request.get_json()
    studentid = data.get('sid')
    name = data.get('name')

    if not studentid or not name:
        return jsonify({'error': 'Both fields are required.'}), 400

    try:
        # Query the database to find the student document
        result = students_collection.delete_one({"studentid": studentid, "name": name})

        if result.deleted_count == 0:
            return jsonify({'error': 'No matching student found.'}), 404

        return jsonify({'message': 'Password successfully reset and student record deleted!'})

    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500
    
@app.route('/fetch_all_students', methods=['GET'])
def fetch_all_students():
    *_, students_collection = get_collections()

    try:
        students = list(students_collection.find({}, {"_id": 0, "studentid": 1, "name": 1}))  # Exclude MongoDB _id
        return jsonify({'students': students})
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/search_students', methods=['GET'])
def search_students():
    *_, students_collection = get_collections()

    keyword = request.args.get('keyword', '')

    if not keyword:
        return jsonify({'error': 'Keyword is required.'}), 400

    try:
        students = list(students_collection.find(
            {
                "$or": [
                    {"studentid": {"$regex": keyword, "$options": "i"}},
                    {"name": {"$regex": keyword, "$options": "i"}}
                ]
            },
            {"_id": 0, "studentid": 1, "name": 1}  # Project only 'sid' and 'name'
        ))
        return jsonify({'students': students})
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500
    
# Alias 검색 및 problem_alias 목록 반환
@app.route("/search", methods=["POST"])
def search():
    *_, responses_collection,_ = get_collections()

    alias = request.form.get("alias")
    if not alias:
        return render_template("index.html", problem_aliases=[], message="Alias is required")

    # 문제 목록 필터링
    problem_aliases = responses_collection.distinct("problem_alias", {"alias": alias})
    return render_template("list.html", problem_aliases=problem_aliases)

# 특정 problem_alias에 대한 데이터 반환
@app.route("/get_responses", methods=["GET"])
def get_responses():
    *_, responses_collection,_ = get_collections()

    problem_alias = request.args.get("problem_alias")
    if not problem_alias:
        return jsonify([])

    # 해당 problem_alias의 데이터 검색
    responses = responses_collection.find({"problem_alias": problem_alias}, {"_id": 1, "sid":1, "name": 1, "content": 1, "success": 1, "output":1, "timestamp": 1})
    
    # ObjectId를 문자열로 변환하여 리스트 생성
    response_list = [
        {**doc, "_id": str(doc["_id"])} for doc in responses
    ]

    return jsonify(response_list)

@app.route('/update_problem', methods=['POST'])
def update_problem():
    collection, *_ = get_collections()
    data = request.json

    if not data.get("alias"):
        return jsonify({"error": "Alias is required"}), 400

    problem = {
        "alias": data["alias"],
        "title": data.get("title", ""),
        "desc": data.get("desc", "").replace("\n", "<br>"),
        "ph": data.get("ph", ""),
        "example": data.get("example", {}),
        "lang": data.get("lang", ""),
    }

    if "test" in data:
        problem["test"] = data["test"]

    # Upsert: 기존 문서는 업데이트, 없으면 삽입
    collection.update_one({"alias": data["alias"]}, {"$set": problem}, upsert=True)
    return jsonify({"message": "Problem successfully updated!"})

@app.context_processor
def inject_is_admin():
    """모든 템플릿에서 is_admin 변수를 사용 가능하게 만드는 context processor"""
    if 'login' in session and session['login'] in admin_list:
        return {'is_admin': True}
    else:
        return {'is_admin': False}

@app.route('/get_selected_db')
def get_selected_db():
    return jsonify({"selected": session.get('db_key', '')})

@app.route('/select_db', methods=['POST'])
def select_db():
    if not ('login' in session and session['login'] in admin_list):
        return jsonify({"error": "not admin"}), 403

    data = request.get_json()
    chosen_db = data.get('db')
    if chosen_db not in ['ACTIVE', 'ARCHIVE', 'DS_URI', 'SM2_URI']:
        return jsonify({"error": "invalid choice"}), 400

    db_uri = os.getenv(chosen_db)
    if not db_uri:
        return jsonify({"error": "DB URI not set in .env"}), 500

    session['db_uri'] = db_uri           # 실사용용 Mongo URI
    session['db_key'] = chosen_db        # 드롭다운 선택 상태 유지용

    return jsonify({"status": "ok", "chosen_db": chosen_db})



def get_data_selecteddb(studentid, name, responses_collection, sheets_collection):
    aliases = []
    sheets_response = []

    # alias 목록 추출
    alias_cursor = responses_collection.find(
        {"sid": studentid, "name": name},
        {"_id": 0, "alias": 1}
    )
    alias_set = {doc["alias"] for doc in alias_cursor if "alias" in doc}
    aliases = sorted(alias_set)

    # 각 alias에 대한 응답 데이터 수집
    for alias in aliases:
        # 해당 sheet 정보 확인
        sheet = sheets_collection.find_one({"alias": alias})
        problem_list = sheet["problem_list"] if sheet else [alias]
        print(problem_list)
        for problem_alias in problem_list:
            response_cursor = responses_collection.find(
                {'problem_alias': problem_alias, 'sid': studentid, 'name': name},
                {'_id': 1, 'timestamp': 1, 'content': 1, 'success': 1}
            ).sort('_id', -1)

            results = [{
                '_id': str(doc['_id']),
                'problem_alias': problem_alias,
                'timestamp': doc.get('timestamp', ""),
                'content': doc.get('content', ""),
                'result': doc.get('success', "")
            } for doc in response_cursor]

            if not results:
                results.append({
                    '_id': None,
                    'problem_alias': problem_alias,
                    'timestamp': "",
                    'content': "",
                    'result': ""
                })
            sheets_response.append(results)
    print(sheets_response)
    return aliases, sheets_response, len(aliases)

"""
@app.route('/final', methods=['GET', 'POST'])
def final():
    responses_collection = DEFAULT_DB['Responses']
    students_collection = DEFAULT_DB['Students']
    sheets_collection = DEFAULT_DB['Sheets']

    aliases = []
    sheets_response = []
    number = 0
    studentid = ""
    name = ""
    password = ""
    message = ""
    alias_status = None
    if 'login' in session:
        studentid = session['login']['studentid']
        name = session['login']['name']

    elif request.method == 'POST':
        studentid = request.form.get('studentid')
        name = request.form.get('name')
        password = request.form.get('password')

        if not studentid or not name or not password:
            message  = _("There are missing required fields")
        else: 
            # 학생 정보 확인
            existing_student = students_collection.find_one({"studentid": studentid, "name": name})

            if existing_student:
                # 비밀번호 대조
                if checkpw(password.encode('utf-8'), existing_student['password'].encode('utf-8')):
                    # 로그인 성공 시 alias 리스트 반환
                    message = _("Login successful!")
                    session["login"] = {"studentid": studentid, "name": name}

                else:
                    message = _("Invalid password.")
                    # 정보 초기화
                    studentid=""
                    name=""
            else:
                # 새로운 학생 등록
                hashed_password = hash_password(password)
                new_student = {
                    "studentid": studentid,
                    "name": name,
                    "password": hashed_password
                }
                students_collection.insert_one(new_student)
                message = _("Account created and logged in successfully!")
                session["login"] = {"studentid": studentid, "name": name}
    else:
        return render_template("final.html", 
        message=message,
        sheets=aliases,
        sheets_response=sheets_response,
        number=number,
        studentid=studentid,
        name=name,
        password=password,
        alias_status=alias_status  
        )
    aliases, sheets_response, number, alias_status = get_data_finaldb(
        studentid, name, responses_collection, sheets_collection
    )

    return render_template("final.html", 
        message=message,
        sheets=aliases,
        sheets_response=sheets_response,
        number=number,
        studentid=studentid,
        name=name,
        password=password,
        alias_status=alias_status  
    )


def get_data_finaldb(studentid, name, responses_collection, sheets_collection):
    aliases = []  # 고정된 alias 목록
    sheets_response = []
    alias_status = {}

    for alias in aliases:
        sheet = sheets_collection.find_one({"alias": alias})
        problem_list = sheet["problem_list"] if sheet else []

        sheet_entries = []
        has_missing = False
        has_failure = False

        for problem_alias in problem_list:
            # 최신 응답 하나만 가져오기
            response = responses_collection.find_one(
                {'problem_alias': problem_alias, 'sid': studentid, 'name': name},
                {'_id': 1, 'timestamp': 1, 'content': 1, 'success': 1},
                sort=[('_id', -1)]
            )

            if not response:
                has_missing = True
                sheet_entries.append({
                    '_id': None,
                    'problem_alias': problem_alias,
                    'timestamp': "",
                    'content': "",
                    'result': ""
                })
            else:
                if response.get('success') == "false":
                    has_failure = True
                sheet_entries.append({
                    '_id': str(response['_id']),
                    'problem_alias': problem_alias,
                    'timestamp': response.get('timestamp', ""),
                    'content': response.get('content', ""),
                    'result': response.get('success', "")
                })

        # 버튼 색상 결정
        if has_missing:
            alias_status[alias] = "danger"
        elif has_failure:
            alias_status[alias] = "warning"
        else:
            alias_status[alias] = "success"

        sheets_response.append(sheet_entries)

    return aliases, sheets_response, len(aliases), alias_status


@app.route('/admin/final')
def admin_final():
    sheets_collection = DEFAULT_DB['Sheets']

    # 하드코딩된 SID 리스트
    sids = []

    aliases = [f"sm{i}" for i in range(13)]
    if 'login' in session and session['login'] in admin_list:
        return render_template("admin_final.html", aliases=aliases, sids=sids)
    else:
        return redirect("/")


@app.route('/admin/status')
def admin_status():
    responses_collection = DEFAULT_DB['Responses']
    sheets_collection = DEFAULT_DB['Sheets']

    sid = request.args.get("sid")
    alias = request.args.get("alias")

    sheet = sheets_collection.find_one({"alias": alias})
    problems = sheet.get("problem_list", []) if sheet else []

    has_missing = False
    has_failure = False

    for prob in problems:
        entry = responses_collection.find_one(
            {"sid": sid, "problem_alias": prob},
            {"success": 1},
            sort=[("_id", -1)]
        )
        if not entry:
            has_missing = True
            break
        if entry.get("success") == "false":
            has_failure = True

    if has_missing:
        status = "danger"
    elif has_failure:
        status = "warning"
    else:
        status = "success"

    return jsonify({"sid": sid, "alias": alias, "status": status})


@app.route('/admin/log')
def admin_log():
    sid = request.args.get("sid")
    alias = request.args.get("alias")

    responses_collection = DEFAULT_DB['Responses']
    sheets_collection = DEFAULT_DB['Sheets']

    sheet = sheets_collection.find_one({"alias": alias})
    problem_list = sheet.get("problem_list", []) if sheet else []

    log_data = []
    for prob in problem_list:
        latest = responses_collection.find_one(
            {"sid": sid, "problem_alias": prob},
            {"_id": 0, "timestamp": 1, "content": 1, "success": 1},
            sort=[("_id", -1)]
        )
        if latest:
            log_data.append({
                "problem_alias": prob,
                "timestamp": latest.get("timestamp", ""),
                "content": latest.get("content", ""),
                "result": latest.get("success", "")
            })
        else:
            log_data.append({
                "problem_alias": prob,
                "timestamp": "",
                "content": "",
                "result": ""
            })
    if 'login' in session and session['login'] in admin_list:
        return render_template("admin_log.html", sid=sid, alias=alias, log_data=log_data)
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)