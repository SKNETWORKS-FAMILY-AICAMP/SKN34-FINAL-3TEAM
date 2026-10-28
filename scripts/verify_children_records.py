"""Verify real core -> learning -> PostgreSQL record existence using disposable DBs.

Run with report-service's existing Python environment (psycopg). Never uses shared
core_db/learning_db: the database names below are required before any writes.
All records are synthetic schema-valid fixtures, not production student records.
"""
import argparse
import base64
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
import uuid

import psycopg


def verify():
    core = psycopg.connect(os.environ["CORE_VERIFY_DSN"], autocommit=True)
    learning = psycopg.connect(os.environ["LEARNING_VERIFY_DSN"], autocommit=True)
    if core.execute("SELECT current_database()").fetchone()[0] != "issue37_core_records":
        raise RuntimeError("Refusing non-disposable core database")
    if learning.execute("SELECT current_database()").fetchone()[0] != "issue37_learning_records":
        raise RuntimeError("Refusing non-disposable learning database")
    core_url = os.environ["CORE_VERIFY_URL"].rstrip("/")
    learning_url = os.environ["LEARNING_VERIFY_URL"].rstrip("/")
    internal = os.environ["INTERNAL_VERIFY_TOKEN"]
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    access = None
    results = []
    user, session = uuid.uuid4(), uuid.uuid4()
    documents, students, attempts, answers, missions = [], [], [], [], []
    deleted = []

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    def request(base, path, *, body=None, headers=None, expected=200):
        h = dict(headers or {})
        if base == core_url:
            h.update({"Origin": core_url, "X-Requested-With": "XMLHttpRequest"})
            if access:
                h["Authorization"] = "Bearer " + access
        if body is not None:
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=h)
        try:
            response = opener.open(req, timeout=40)
        except urllib.error.HTTPError as error:
            response = error
        data = json.loads(response.read())
        require(response.status == expected, f"{path}: expected HTTP {expected}, got {response.status}; code={data.get('code')}")
        return data

    def children_case(name, expected):
        page = request(core_url, "/api/v1/children")
        require(page["totalElements"] == 3, "Only the parent's three registered children may be returned")
        by_id = {row["id"]: row for row in page["items"]}
        observed = []
        for child, wanted in zip(students[:3], expected):
            item = by_id[str(child)]
            require(item["hasRecords"] is wanted, f"{name}: incorrect hasRecords")
            require(item["recordState"] == "AVAILABLE", f"{name}: actual provider must be AVAILABLE")
            observed.append(item["hasRecords"])
        results.append({"case": name, "http": 200, "hasRecords": observed, "recordState": "AVAILABLE"})

    def make_attempt(student):
        mission, version, rubric = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        missions.append((mission, version, rubric))
        actor = uuid.uuid4()
        learning.execute("INSERT INTO mission(id,code,status,demo_only,sort_order,created_by,created_at,updated_at) VALUES(%s,%s,'DRAFT',true,1,%s,now(),now())", (mission,str(mission),actor))
        learning.execute("INSERT INTO mission_version(id,mission_id,version,title,subject,grade_min,grade_max,thinking_type,input_type,question,created_by,created_at) VALUES(%s,%s,1,'Synthetic mission','language',3,6,'ANALYZE','NARRATIVE','Synthetic question',%s,now())", (version,mission,actor))
        learning.execute("INSERT INTO rubric_version(id,mission_id,version,created_by,created_at) VALUES(%s,%s,1,%s,now())", (rubric,mission,actor))
        attempt = uuid.uuid4()
        attempts.append(attempt)
        learning.execute("INSERT INTO attempt(id,student_id,mission_id,mission_version_id,rubric_version_id,grade,status,started_at,updated_at) VALUES(%s,%s,%s,%s,%s,3,'IN_PROGRESS',now(),now())", (attempt,student,mission,version,rubric))
        return attempt, rubric

    def submit(attempt, rubric, state):
        answer = uuid.uuid4()
        previous = learning.execute("SELECT id,version FROM answer WHERE attempt_id=%s ORDER BY version DESC LIMIT 1", (attempt,)).fetchone()
        answers.append(answer)
        learning.execute("INSERT INTO answer(id,attempt_id,version,previous_answer_id,input_type,content,plain_text,dictated_by_guardian,idempotency_key,submitted_at) VALUES(%s,%s,%s,%s,'NARRATIVE','{}'::jsonb,'Synthetic submitted record',false,%s,now())", (answer,attempt,1 if previous is None else previous[1]+1,None if previous is None else previous[0],uuid.uuid4()))
        learning.execute("INSERT INTO judgment(id,answer_id,process_status,result,rubric_version_id,retry_count,created_at) VALUES(%s,%s,%s,%s,%s,0,now())", (uuid.uuid4(),answer,state,'CORRECT' if state == 'DONE' else None,rubric))

    try:
        raw = str(uuid.uuid4())
        hashed = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()).decode().rstrip("=")
        core.execute("INSERT INTO user_account(id,role,login_id,password_hash,display_name,status,is_demo,created_at,updated_at) VALUES(%s,'PARENT',%s,NULL,'Synthetic verification parent','ACTIVE',true,now(),now())", (user,str(user)+'@example.invalid'))
        core.execute("INSERT INTO auth_session(id,user_id,role,version,expires_at,created_at) VALUES(%s,%s,'PARENT',1,now()+interval '1 day',now())", (session,user))
        core.execute("INSERT INTO refresh_token(id,user_id,session_id,token_hash,expires_at,created_at) VALUES(%s,%s,%s,%s,now()+interval '1 day',now())", (uuid.uuid4(),user,session,hashed))
        for kind in ("TERMS", "PRIVACY", "GUARDIAN"):
            document = uuid.uuid4()
            documents.append(document)
            core.execute("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(%s,%s,%s,'Synthetic non-binding notice','Disposable verification document',true,(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date,now())", (document,kind,str(document)))
        token = request(core_url, "/api/v1/auth/refresh", body={}, headers={"Cookie": "sagomungchi_refresh="+raw})
        access = token["accessToken"]
        docs = request(core_url, "/api/v1/consent-documents")["items"]
        choices = [{"documentId": d["documentId"], "version": d["version"], "agreed": True} for d in docs]
        account_choices = [c for c in choices if next(d for d in docs if d['documentId']==c['documentId'])['kind'] != 'GUARDIAN']
        guardian_choices = [c for c in choices if c not in account_choices]
        request(core_url, "/api/v1/me/consents", body={"consents": account_choices})
        empty = request(core_url, "/api/v1/children")
        require(empty["items"] == [] and empty["totalElements"] == 0, "Empty child list")
        require(request(core_url,"/api/v1/me")["nextAction"]=="CHILD_REGISTRATION_REQUIRED", "Empty child registration guidance")
        results.append({"case":"empty_children_registration_guidance","http":200})
        for n in range(3):
            child = request(core_url, "/api/v1/children", body={"nickname":f"Verification {n+1}","grade":3,"birthYear":2017,"consents":guardian_choices},expected=201)
            students.append(uuid.UUID(child["id"]))
        children_case("zero_records", [False,False,False])
        a, ra = make_attempt(students[0])
        learning.execute("INSERT INTO attempt_draft(attempt_id,version,content,saved_at) VALUES(%s,1,'{\"memo\":\"Synthetic private memo\"}'::jsonb,now())", (a,))
        children_case("draft_only", [False,False,False])
        other = uuid.uuid4(); students.append(other)
        foreign_attempt, foreign_rubric = make_attempt(other);submit(foreign_attempt,foreign_rubric,"DONE")
        children_case("other_student_record_ignored",[False,False,False])
        submit(a,ra,"PENDING")
        children_case("one_submitted_record",[True,False,False])
        b,rb=make_attempt(students[1]);submit(b,rb,"FAILED")
        children_case("failed_only_excluded",[True,False,False])
        submit(b,rb,"DONE")
        children_case("valid_resubmission_included",[True,True,False])
        c,rc=make_attempt(students[2]);submit(c,rc,"DONE");submit(c,rc,"PENDING")
        children_case("multiple_submitted_records",[True,True,True])
        learning.execute("INSERT INTO deleted_student(student_id,scope,event_id,deleted_at) VALUES(%s,'RECORDS',%s,now())",(students[1],uuid.uuid4()));deleted.append(students[1])
        children_case("deleted_record_excluded",[True,False,True])
        direct = {"X-Internal-Token":internal,"X-User-Role":"PARENT","X-Student-Scope":str(students[0])}
        require(request(learning_url,f"/internal/records/students/{students[0]}/exists",headers=direct)["hasRecords"] is True,"Direct real producer record")
        request(learning_url,f"/internal/records/students/{students[1]}/exists",headers=direct,expected=403)
        request(learning_url,f"/internal/records/students/{students[0]}/exists",headers=direct|{"X-Internal-Token":"invalid"},expected=401)
        request(learning_url,f"/internal/records/students/{students[0]}/exists",headers=direct|{"X-User-Role":"ADMIN"},expected=403)
        results.append({"case":"internal_token_role_scope_guards","statuses":[200,403,401,403]})
        history=request(core_url,"/api/v1/me/consents")["items"]
        guardian=next(row for row in history if row["studentId"]==str(students[0]) and row["status"]=="AGREED")
        request(core_url,f"/api/v1/me/consents/{guardian['consentId']}/withdrawal",body={})
        blocked=next(row for row in request(core_url,"/api/v1/children")["items"] if row["id"]==str(students[0]))
        require(blocked['hasRecords'] is None and blocked['recordState']=='CONSENT_REQUIRED',"Guardian withdrawal blocks real records")
        results.append({"case":"guardian_withdrawal","hasRecords":None,"recordState":"CONSENT_REQUIRED"})
        return {"status":"PASS","cases":results,"source":"actual core and learning JARs with independent PostgreSQL databases; synthetic stored fixtures"}
    finally:
        # Only the IDs created by this invocation, in required FK order.
        core.execute("DELETE FROM refresh_token WHERE user_id=%s",(user,))
        core.execute("DELETE FROM auth_session WHERE user_id=%s",(user,))
        core.execute("DELETE FROM consent WHERE subject_user_id=%s",(user,))
        core.execute("DELETE FROM guardianship WHERE parent_user_id=%s",(user,))
        if students: core.execute("DELETE FROM student WHERE id=ANY(%s)",(students[:3],))
        core.execute("DELETE FROM user_account WHERE id=%s",(user,))
        if documents: core.execute("DELETE FROM consent_document WHERE id=ANY(%s)",(documents,))
        if answers:
            learning.execute("DELETE FROM judgment WHERE answer_id=ANY(%s)",(answers,))
            learning.execute("DELETE FROM answer WHERE id=ANY(%s)",(answers,))
        if attempts:
            learning.execute("DELETE FROM attempt_draft WHERE attempt_id=ANY(%s)",(attempts,))
            learning.execute("DELETE FROM attempt WHERE id=ANY(%s)",(attempts,))
        if deleted: learning.execute("DELETE FROM deleted_student WHERE student_id=ANY(%s)",(deleted,))
        for mission,version,rubric in missions:
            learning.execute("DELETE FROM rubric_version WHERE id=%s",(rubric,))
            learning.execute("DELETE FROM mission_version WHERE id=%s",(version,))
            learning.execute("DELETE FROM mission WHERE id=%s",(mission,))
        core.close(); learning.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=verify()
    serialized=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output: args.output.write_text(serialized+'\n',encoding='utf-8')
    print(serialized)
