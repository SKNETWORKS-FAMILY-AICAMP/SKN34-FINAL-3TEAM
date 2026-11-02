"""#40 real core -> learning verification; no learning HTTP double or shared compose.

Test runtime: JDK 21, psycopg[binary], PyYAML, jsonschema. The caller owns fresh
issue40-dashboard-* PostgreSQL/Redis/RabbitMQ sidecars and removes them afterwards.
Only fixed disposable databases are created. OAuth identity and historical learning
records are synthetic SQL fixtures; consent/children/student session/start/draft/
submission and all dashboard reads go through real HTTP APIs. No AI is called.
"""
import argparse
import base64
import datetime as dt
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from zoneinfo import ZoneInfo

import jsonschema
import psycopg
import yaml


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def uid():
    return str(uuid.uuid4())


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def verify(args):
    require(args.db_host.startswith('issue40-dashboard-db-'), 'Dedicated database host required')
    require(args.redis_host.startswith('issue40-dashboard-'), 'Dedicated Redis host required')
    require(args.rabbit_host.startswith('issue40-dashboard-'), 'Dedicated RabbitMQ host required')
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    databases = {'core': 'issue40_core_dashboard', 'learning': 'issue40_learning_dashboard'}
    connections, processes, logs, cases = {}, [], [], []
    credentials = dict(host=args.db_host, port=5432, user='issue40', password='issue40-disposable-password')
    internal = 'issue40-disposable-internal-token'
    secret = base64.b64encode(b'issue40-only-disposable-jwt-secret-32bytes').decode()
    memo = 'PRIVATE_ISSUE40_MEMO_DO_NOT_EXPOSE'
    core_port, learning_port = free_port(), free_port()
    core_url, learning_url = f'http://127.0.0.1:{core_port}', f'http://127.0.0.1:{learning_port}'
    spec = {name: yaml.safe_load((root / f'contracts/openapi/{name}-service.yaml').read_text('utf-8')) for name in databases}

    def sql(service, statement, params=None):
        connection = connections[service]
        require(connection.info.dbname == databases[service], 'Refusing non-verification DB')
        cursor = connection.execute(statement, params)
        return cursor.fetchall() if cursor.description else []

    def schema(service, name, data):
        jsonschema.Draft202012Validator(
            {'$ref': f'#/components/schemas/{name}', 'components': spec[service]['components']},
            format_checker=jsonschema.FormatChecker(),
        ).validate(data)

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(path, token=None, body=None, method=None, expected=200, headers=None, base=core_url):
        supplied = {'Origin': core_url, 'X-Requested-With': 'XMLHttpRequest', **(headers or {})}
        if token:
            supplied['Authorization'] = 'Bearer ' + token
        if body is not None:
            supplied['Content-Type'] = 'application/json'
        data = json.dumps(body).encode() if body is not None else (b'' if method == 'POST' else None)
        req = urllib.request.Request(base + path, data=data, headers=supplied, method=method)
        try:
            response = opener.open(req, timeout=45)
        except urllib.error.HTTPError as error:
            response = error
        payload = json.loads(response.read())
        require(response.status == expected, f'{path}: expected {expected}, got {response.status}, code={payload.get("code")}')
        return payload

    def start_app(name, jar, port):
        log = (output.parent / f'{name}.log').open('w', encoding='utf-8')
        logs.append(log)
        env = {**os.environ, 'DB_URL': f'jdbc:postgresql://{args.db_host}:5432/{databases[name]}',
               'DB_USERNAME': 'issue40', 'DB_PASSWORD': credentials['password'], 'INTERNAL_TOKEN': internal,
               'AUTH_JWT_SECRET': secret, 'AUTH_WEB_ORIGIN': core_url, 'AUTH_COOKIE_SECURE': 'false',
               'RABBITMQ_HOST': args.rabbit_host, 'RABBITMQ_USERNAME': 'issue40', 'RABBITMQ_PASSWORD': 'issue40-test',
               'REDIS_HOST': args.redis_host, 'LEARNING_URL': learning_url, 'AI_URL': 'http://127.0.0.1:1'}
        command = [args.java, '-XX:ActiveProcessorCount=2', '-Xmx512m', '-jar', str(jar.resolve()),
                   f'--server.port={port}', '--server.address=127.0.0.1',
                   '--spring.rabbitmq.listener.simple.auto-startup=false',
                   '--spring.data.redis.connect-timeout=30s', '--spring.data.redis.timeout=30s',
                   '--management.endpoint.health.group.readiness.include=readinessState,db']
        if name == 'learning':
            command += ['--server.tomcat.accesslog.enabled=true', '--server.tomcat.accesslog.buffered=false',
                        f'--server.tomcat.accesslog.directory={output.parent}', '--server.tomcat.accesslog.prefix=learning-access',
                        '--server.tomcat.accesslog.pattern=%r|%{X-Student-Scope}i|%{X-User-Role}i|%{traceparent}i']
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        processes.append(process)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            require(process.poll() is None, f'{name} exited; inspect verification log')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/actuator/health/liveness', timeout=2) as response:
                    if response.status == 200:
                        return process
            except (OSError, urllib.error.URLError):
                time.sleep(.3)
        raise TimeoutError(f'{name} readiness timeout')

    def passed(name):
        cases.append({'case': name, 'passed': True})
        print('PASS', name, flush=True)

    def no_private(payload):
        require(memo not in json.dumps(payload), 'Private memo value leaked')
        if isinstance(payload, dict):
            require(not {'memo', 'draft'} & payload.keys(), 'Private JSON field leaked')
            for value in payload.values():
                no_private(value)
        elif isinstance(payload, list):
            for value in payload:
                no_private(value)

    try:
        with psycopg.connect(dbname='postgres', autocommit=True, **credentials) as admin:
            for database in databases.values():
                require(not admin.execute('SELECT 1 FROM pg_database WHERE datname=%s', (database,)).fetchone(),
                        'Verification requires fresh databases; no existing DB will be replaced')
                admin.execute('CREATE DATABASE ' + database)
        for name, database in databases.items():
            connections[name] = psycopg.connect(dbname=database, autocommit=True, **credentials)
            folder = root / f'backend/{name}-service/src/main/resources/db/migration'
            for file in sorted(folder.glob('V*__*.sql'), key=lambda p: int(re.match(r'V(\d+)__', p.name)[1])):
                with connections[name].transaction():
                    sql(name, file.read_text('utf-8'))
        learning_process = start_app('learning', args.learning_jar, learning_port)
        start_app('core', args.core_jar, core_port)

        user = uid()
        sql('core', "INSERT INTO user_account(id,role,login_id,status,is_demo,created_at,updated_at) VALUES(%s,'PARENT',%s,'ACTIVE',true,now(),now())", (user, user+'@example.invalid'))

        def login():
            session, refresh = uid(), uid()
            hashed = base64.urlsafe_b64encode(hashlib.sha256(refresh.encode()).digest()).decode().rstrip('=')
            sql('core', "INSERT INTO auth_session(id,user_id,role,version,expires_at,created_at) VALUES(%s,%s,'PARENT',1,now()+interval '1 day',now())", (session, user))
            sql('core', "INSERT INTO refresh_token(id,user_id,session_id,token_hash,expires_at,created_at) VALUES(%s,%s,%s,%s,now()+interval '1 day',now())", (uid(), user, session, hashed))
            return request('/api/v1/auth/refresh', body={}, headers={'Cookie': 'sagomungchi_refresh='+refresh})['accessToken']

        for kind in ['TERMS', 'PRIVACY', 'GUARDIAN']:
            doc = uid()
            sql('core', "INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(%s,%s,%s,'Synthetic notice','Disposable verification only',true,(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date,now())", (doc, kind, doc))
        parent = login()
        documents = request('/api/v1/consent-documents')['items']
        choices = lambda guardian: [{'documentId': d['documentId'], 'version': d['version'], 'agreed': True} for d in documents if (d['kind'] == 'GUARDIAN') == guardian]
        request('/api/v1/me/consents', parent, {'consents': choices(False)})
        children = [request('/api/v1/children', parent, {'nickname': f'검증 학생 {i}', 'grade': 3, 'birthYear': 2017, 'consents': choices(True)}, expected=201)['id'] for i in range(2)]
        child, empty_child = children
        student = request('/api/v1/auth/student-sessions', login(), {'childId': child})['accessToken']
        passed('actual_refresh_consent_child_registration_student_session')

        today = dt.datetime.now(ZoneInfo('Asia/Seoul')).date()
        early = dt.datetime.combine(today-dt.timedelta(days=9), dt.time(12), ZoneInfo('Asia/Seoul'))
        late = early+dt.timedelta(days=6)
        old_period = {'from': str(early.date()), 'to': str((early+dt.timedelta(days=2)).date())}
        broad_period = {'from': str(early.date()), 'to': str(today)}
        query = lambda p: '&'.join(f'{k}={v}' for k,v in p.items())
        pbase = f'/api/v1/children/{child}'
        trace = '00-0123456789abcdef0123456789abcdef-0123456789abcdef-01'
        empty = request(f'/api/v1/children/{empty_child}/summary', parent)
        schema('core', 'DashboardSummary', empty)
        require(empty['state'] == 'NO_RECORD' and empty['period'] == {'from': str(today-dt.timedelta(days=6)), 'to': str(today)}, 'Empty/default KST period mismatch')
        passed('empty_records_and_default_KST_period')

        def mission():
            m, version, rubric, hint = uid(), uid(), uid(), uid()
            sql('learning', "INSERT INTO mission(id,code,status,demo_only,sort_order,created_by,created_at,updated_at) VALUES(%s,%s,'PUBLISHED',false,1,%s,now(),now())", (m,'VERIFY40-'+m,user))
            sql('learning', "INSERT INTO mission_version(id,mission_id,version,title,subject,grade_min,grade_max,thinking_type,input_type,question,created_by,created_at) VALUES(%s,%s,1,'합성 미션','과학',3,6,'ANALYZE','NARRATIVE','이유를 말해 볼까?',%s,now())", (version,m,user))
            sql('learning', "INSERT INTO rubric_version(id,mission_id,version,example_answer,created_by,created_at) VALUES(%s,%s,1,'합성 예시',%s,now())", (rubric,m,user))
            sql('learning', "INSERT INTO rubric_element(id,rubric_version_id,code,label,description,points,good_thought,judge_verified,sort_order) VALUES(%s,%s,'reason','까닭','합성 검증 기준',1,false,true,1)", (uid(),rubric))
            sql('learning', 'INSERT INTO hint_question(id,rubric_version_id,seq,content) VALUES(%s,%s,1,\'어떤 까닭일까?\')', (hint,rubric))
            sql('learning', 'UPDATE mission SET current_version_id=%s,current_rubric_version_id=%s,published_version_id=%s,published_rubric_version_id=%s WHERE id=%s', (version,rubric,version,rubric,m))
            return m, version, rubric, hint

        m, version, rubric, hint = mission()
        attempt = request(f'/api/v1/missions/{m}/attempts', student, {}, expected=201)
        attempt_id = attempt['attemptId']
        request(f'/api/v1/attempts/{attempt_id}/draft', student, {'content': {'answer': {'inputType': 'NARRATIVE', 'text': '보존할 초안'}, 'memo': memo}}, method='PUT', headers={'If-Match': '"'+str(attempt['draft']['version'])+'"'})
        home = request('/api/v1/students/me/home', student)
        schema('core', 'DashboardHome', home)
        require(home['state'] == 'NO_RECORD' and home['resume']['draft']['content']['memo'] == memo, 'Draft-only resume lost')
        require(home['resume']['hintUsages'] == [] and 'completedAt' in home['resume'], 'Home record metadata lost')
        passed('real_records_home_plus_private_attempt_draft')
        answer = request(f'/api/v1/attempts/{attempt_id}/answers', student, {'inputType': 'NARRATIVE', 'text': '첫 생각'}, expected=201, headers={'Idempotency-Key': uid()})['answerId']
        request(f'/api/v1/attempts/{attempt_id}/hints', student, {})
        sql('learning', 'UPDATE answer SET submitted_at=%s WHERE id=%s', (early,answer))
        sql('learning', "UPDATE judgment SET process_status='DONE',result='PARTIAL',method='LLM',trial=true,created_at=%s,completed_at=%s WHERE answer_id=%s", (early,early,answer))
        sql('learning', 'UPDATE hint_usage SET opened_at=%s WHERE attempt_id=%s', (early-dt.timedelta(minutes=5),attempt_id))
        second = uid()
        sql('learning', "INSERT INTO answer(id,attempt_id,version,previous_answer_id,input_type,content,plain_text,dictated_by_guardian,idempotency_key,submitted_at) VALUES(%s,%s,2,%s,'NARRATIVE',%s::jsonb,'나중 생각',false,%s,%s)", (second,attempt_id,answer,json.dumps({'inputType':'NARRATIVE','text':'나중 생각'}),uid(),late))
        sql('learning', "INSERT INTO judgment(id,answer_id,process_status,rubric_version_id,retry_count,created_at) VALUES(%s,%s,'PENDING',%s,0,%s)", (uid(),second,rubric,late))
        completed = late+dt.timedelta(minutes=2)
        sql('learning', "UPDATE attempt SET status='COMPLETED',started_at=%s,finished_at=%s,completed_at=%s,updated_at=%s WHERE id=%s", (early-dt.timedelta(hours=1),late+dt.timedelta(minutes=1),completed,completed,attempt_id))
        sql('learning', "INSERT INTO reflection(id,attempt_id,difficulty,changed_text,created_at) VALUES(%s,%s,'NORMAL',null,%s)", (uid(),attempt_id,completed))
        summary = request(pbase+'/summary?'+query(old_period), parent, headers={'traceparent':trace,'X-Student-Scope':empty_child,'X-User-Role':'ADMIN'})
        schema('core','DashboardSummary',summary)
        require(summary['state']=='INSUFFICIENT_SAMPLE' and summary['metrics'][0]['count']==1, 'Small sample mismatch')
        require(summary['metrics'][1]['count']==0 and all(x['value'] is None for x in summary['metrics']), 'Future completion or ratio leaked into old summary')
        record_page = request(pbase+'/attempts?'+query(old_period), parent)
        schema('core','DashboardParentAttempts',record_page)
        row = record_page['items'][0]
        require(len(row['answers'])==1 and row['reflection'] is None and len(row['hintUsages'])==1, 'Historical list boundary mismatch')
        detail = request(pbase+f'/attempts/{attempt_id}?'+query(old_period),parent)
        schema('core','DashboardAttemptDetail',detail)
        require(detail['state']=='OK' and detail['period']==old_period and len(detail['answers'])==2, 'Detail must keep full history')
        require(detail['reflection']['createdAt']==detail['completedAt'] and detail['finishedAt']!=detail['completedAt'], 'Timestamp meanings mismatch')
        no_private(record_page);no_private(detail)
        passed('historical_list_full_detail_and_timestamp_metadata')

        for _ in range(4):
            m,v,r,h = mission(); a,b = uid(),uid()
            sql('learning', "INSERT INTO attempt(id,student_id,mission_id,mission_version_id,rubric_version_id,grade,status,started_at,updated_at) VALUES(%s,%s,%s,%s,%s,3,'IN_PROGRESS',%s,%s)", (a,child,m,v,r,early,early))
            sql('learning', 'INSERT INTO attempt_draft(attempt_id,version,content,saved_at) VALUES(%s,1,%s::jsonb,%s)', (a,json.dumps({'answer':{},'memo':memo}),early))
            sql('learning', "INSERT INTO answer(id,attempt_id,version,input_type,content,plain_text,dictated_by_guardian,idempotency_key,submitted_at) VALUES(%s,%s,1,'NARRATIVE',%s::jsonb,'합성 기록',false,%s,%s)", (b,a,json.dumps({'inputType':'NARRATIVE','text':'합성 기록'}),uid(),early))
            sql('learning', "INSERT INTO judgment(id,answer_id,process_status,rubric_version_id,retry_count,created_at) VALUES(%s,%s,'PENDING',%s,0,%s)", (uid(),b,r,early))
        summary = request(pbase+'/summary?'+query(broad_period),parent)
        require(summary['state']=='OK' and summary['metrics'][0]['count']==5, 'Five-record summary mismatch')
        ids = []
        for page in range(3):
            data=request(pbase+'/attempts?'+query(broad_period)+f'&page={page}&size=2',parent)
            schema('core','DashboardParentAttempts',data);no_private(data)
            require(data['totalElements']==5 and data['page']==page,'Pagination envelope mismatch')
            ids += [a['attemptId'] for a in data['items']]
        require(len(ids)==len(set(ids))==5,'Pagination lost/duplicated records')
        filtered=request(pbase+'/attempts?'+query(broad_period)+'&status=COMPLETED',parent)
        require(filtered['totalElements']==1 and filtered['items'][0]['attemptId']==attempt_id,'Status filter mismatch')
        thinking=request(pbase+'/thinking-types?'+query(broad_period),parent)
        schema('core','DashboardThinkingTypes',thinking)
        require(len(thinking['items'])==5 and sum(x['state']=='NO_RECORD' for x in thinking['items'])==4,'Thinking types missing')
        student_rows=request('/api/v1/students/me/attempts?'+query(broad_period),student)
        schema('core','DashboardStudentAttempts',student_rows);no_private(student_rows)
        activities=request('/api/v1/students/me/thinking-activities?'+query(old_period),student)
        schema('core','DashboardThinkingActivities',activities)
        require(all(x['reflection'] is None for x in activities['items']),'Out-of-period reflection leaked')
        passed('five_records_pagination_status_and_all_seven_public_queries')

        request(pbase+'/summary',expected=401)
        request('/api/v1/students/me/home',parent,expected=403)
        request(f'/api/v1/children/{uid()}/summary',parent,expected=403)
        request(pbase+f'/attempts/{uid()}',parent,expected=404)
        for suffix in ['from=2026-01-01','page=-1','size=101','status=FAILED','from=2026-02-30&to=2026-03-01']:
            request(pbase+'/attempts?'+suffix,parent,expected=400)
        direct={'X-Internal-Token':internal,'X-User-Role':'PARENT','X-User-Id':user,'X-Student-Scope':','.join(children)}
        internal_summary=request(f'/internal/records/students/{child}/summary?'+query(broad_period),headers=direct,base=learning_url)
        require(internal_summary['studentId']==child,'Internal identity mismatch')
        request(f'/internal/records/students/{child}/summary',headers={**direct,'X-Student-Scope':empty_child},base=learning_url,expected=403)
        request(f'/internal/records/students/{child}/summary',headers={**direct,'X-Internal-Token':'invalid'},base=learning_url,expected=401)
        passed('authentication_foreign_child_date_page_and_internal_scope_guards')

        sql('core', "UPDATE student SET status='DELETION_REQUESTED' WHERE id=%s", (child,))
        request(pbase+'/summary',parent,expected=403)
        sql('core', "UPDATE student SET status='ACTIVE' WHERE id=%s", (child,))
        sql('core', "UPDATE guardianship SET status='UNLINKED',unlinked_at=now() WHERE student_id=%s", (child,))
        request(pbase+'/summary',parent,expected=403)
        sql('core', "UPDATE guardianship SET status='LINKED',unlinked_at=null WHERE student_id=%s", (child,))
        history=request('/api/v1/me/consents',parent)['items']
        guardian=next(x['consentId'] for x in history if x.get('studentId')==child and x['status']=='AGREED')
        request('/api/v1/me/consents/'+guardian+'/withdrawal',parent,{})
        request(pbase+'/summary',parent,expected=403)
        request('/api/v1/students/me/home',student,expected=403)
        request('/api/v1/me/consents',parent,{'childId':child,'consents':choices(True)})
        request(pbase+'/summary',parent)
        passed('current_active_link_and_guardian_consent_enforcement')

        access_lines='\n'.join(p.read_text('utf-8') for p in output.parent.glob('learning-access*'))
        traced=[line for line in access_lines.splitlines() if trace in line]
        require(traced and all(f'|{child}|PARENT|{trace}' in line for line in traced),'Narrowed parent context/trace was not forwarded')
        passed('real_learning_access_log_proves_narrowed_parent_scope_and_trace')
        (output.parent/'actual-responses.json').write_text(json.dumps({'home':home,'detail':detail,'summary':summary,'records':record_page,'thinking':thinking,'activities':activities},ensure_ascii=False,indent=2),encoding='utf-8')
        learning_process.terminate();learning_process.wait(timeout=20)
        failure=request(pbase+'/summary',parent,expected=503)
        require(failure.get('code')=='LEARNING_UNAVAILABLE' and failure.get('state')!='NO_RECORD','Outage hidden as no records')
        passed('real_learning_outage_is_error_not_no_record')
        return {'status':'PASS','source':'real core and learning JARs + isolated PostgreSQL databases; synthetic fixtures; no AI/Google call',
                'coreRef':args.core_ref,'learningRef':args.learning_ref,'cases':cases,
                'coreJarSha256':hashlib.sha256(args.core_jar.read_bytes()).hexdigest(),
                'learningJarSha256':hashlib.sha256(args.learning_jar.read_bytes()).hexdigest()}
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait(timeout=5)
        for connection in connections.values():
            connection.close()
        for log in logs:
            log.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core-jar',type=Path,required=True)
    parser.add_argument('--learning-jar',type=Path,required=True)
    parser.add_argument('--db-host',required=True)
    parser.add_argument('--redis-host',required=True)
    parser.add_argument('--rabbit-host',required=True)
    parser.add_argument('--java',default='java')
    parser.add_argument('--core-ref',required=True)
    parser.add_argument('--learning-ref',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=verify(args)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
