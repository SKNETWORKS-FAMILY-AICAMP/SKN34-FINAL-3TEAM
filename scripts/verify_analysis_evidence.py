"""Actual core -> learning evidence contract check, only against named disposable #41 DBs.
Synthetic records only. Does not require AI, payment, Google, or a production token.
"""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid

import psycopg
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]

def main():
    core = psycopg.connect(os.environ["CORE_VERIFY_DSN"], autocommit=True)
    learning = psycopg.connect(os.environ["LEARNING_VERIFY_DSN"], autocommit=True)
    if core.execute("SELECT current_database()").fetchone()[0] != "issue41_core" or learning.execute("SELECT current_database()").fetchone()[0] != "issue41_learning":
        raise RuntimeError("Refusing databases outside the disposable issue41 namespace")
    base = os.environ["CORE_VERIFY_URL"].rstrip("/")
    internal_url = os.environ["LEARNING_VERIFY_URL"].rstrip("/")
    key = base64.b64decode(os.environ["AUTH_VERIFY_SECRET"])
    user, student, session, conversation, message, evidence = [uuid.uuid4() for _ in range(6)]
    mission, version, rubric, attempt, answer = [uuid.uuid4() for _ in range(5)]
    quote = "Synthetic evidence record for issue 41"
    def require(value, title):
        if not value: raise AssertionError(title)
    def jwt(owner, sid):
        def b64(data): return base64.urlsafe_b64encode(data).decode().rstrip("=")
        now = int(time.time())
        head = b64(json.dumps({"alg":"HS256","typ":"JWT"}).encode())
        payload = b64(json.dumps({"iss":"sagomungchi-core","aud":["access"],"sub":str(owner),"sid":str(sid),"role":"PARENT","ver":1,"iat":now,"exp":now+300}).encode())
        text = head+"."+payload
        return text+"."+b64(hmac.new(key,text.encode(),hashlib.sha256).digest())
    token = jwt(user,session)
    def request(path, expected=200, auth=None, url=base, headers=None):
        values = dict(headers or {})
        if url == base:
            values["Authorization"] = "Bearer " + (auth or token)
            values["X-User-Id"] = "forged"
            values["X-Student-Scope"] = str(uuid.uuid4())
        try: response = urllib.request.urlopen(urllib.request.Request(url+path, headers=values), timeout=15)
        except urllib.error.HTTPError as ex: response = ex
        body = json.loads(response.read())
        require(response.status == expected, f"{path}: HTTP {response.status}, expected {expected}, code={body.get('code')}")
        return body
    def account(owner, sid):
        core.execute("INSERT INTO user_account(id,role,login_id,status,is_demo,created_at,updated_at) VALUES(%s,'PARENT',%s,'ACTIVE',true,now(),now())", (owner,str(owner)+"@example.invalid"))
        core.execute("INSERT INTO auth_session(id,user_id,role,version,expires_at,created_at) VALUES(%s,%s,'PARENT',1,now()+interval '1 hour',now())", (sid,owner))
        for kind in ["TERMS","PRIVACY"]:
            doc = core.execute("SELECT id FROM consent_document WHERE kind=%s ORDER BY effective_from DESC,created_at DESC,id DESC LIMIT 1", (kind,)).fetchone()
            if doc:
                core.execute("INSERT INTO consent(id,document_id,subject_user_id,agreed,status,agreed_at) VALUES(%s,%s,%s,true,'AGREED',now())", (uuid.uuid4(),doc[0],owner))
    account(user,session)
    core.execute("INSERT INTO student(id,nickname,grade,birth_year,is_demo,status,pin_failed_count,created_at,updated_at) VALUES(%s,'Synthetic',3,2017,true,'ACTIVE',0,now(),now())", (student,))
    core.execute("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(%s,%s,%s,'REGISTER','LINKED',now())", (uuid.uuid4(),user,student))
    for kind in ["TERMS","PRIVACY","GUARDIAN"]:
        doc = uuid.uuid4()
        core.execute("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(%s,%s,%s,'Synthetic','Synthetic',true,CURRENT_DATE,now())", (doc,kind,str(doc)))
        core.execute("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(%s,%s,%s,%s,true,'AGREED',now())", (uuid.uuid4(),doc,user,student if kind=='GUARDIAN' else None))
    core.execute("INSERT INTO conversation(id,parent_user_id,student_id,period_from,period_to,created_at,updated_at) VALUES(%s,%s,%s,CURRENT_DATE-6,CURRENT_DATE,now(),now())", (conversation,user,student))
    core.execute("""INSERT INTO conversation_message(id,conversation_id,seq,question,answer,scope_student_id,scope_from,scope_to,scope_changed,status,source,verification,retry_count,created_at,completed_at) VALUES(%s,%s,1,'Synthetic question','Synthetic answer',%s,CURRENT_DATE-6,CURRENT_DATE,false,'COMPLETED','LLM',%s::jsonb,0,now(),now())""", (message,conversation,student,json.dumps({"numbersMatched":True,"quotesMatched":True})))
    core.execute("INSERT INTO message_evidence(id,message_id,attempt_id,answer_id,answer_version) VALUES(%s,%s,%s,%s,1)", (evidence,message,attempt,answer))
    actor = uuid.uuid4()
    learning.execute("INSERT INTO mission(id,code,status,demo_only,sort_order,created_by,created_at,updated_at) VALUES(%s,%s,'DRAFT',true,1,%s,now(),now())", (mission,str(mission),actor))
    learning.execute("INSERT INTO mission_version(id,mission_id,version,title,subject,grade_min,grade_max,thinking_type,input_type,question,created_by,created_at) VALUES(%s,%s,1,'Synthetic mission','language',3,6,'ANALYZE','NARRATIVE','Synthetic question',%s,now())", (version,mission,actor))
    learning.execute("INSERT INTO rubric_version(id,mission_id,version,created_by,created_at) VALUES(%s,%s,1,%s,now())", (rubric,mission,actor))
    learning.execute("INSERT INTO attempt(id,student_id,mission_id,mission_version_id,rubric_version_id,grade,status,started_at,updated_at) VALUES(%s,%s,%s,%s,%s,3,'IN_PROGRESS',now(),now())", (attempt,student,mission,version,rubric))
    learning.execute("INSERT INTO answer(id,attempt_id,version,input_type,content,plain_text,dictated_by_guardian,idempotency_key,submitted_at) VALUES(%s,%s,1,'NARRATIVE','{}',%s,false,%s,now())", (answer,attempt,quote,uuid.uuid4()))
    path = f"/api/v1/conversations/{conversation}/messages/{message}/evidence"
    before = request(path)
    require(before["items"][0]["quote"] == quote, "Actual learning quote must pass through unchanged")
    require(before["items"][0]["evidenceId"] == str(evidence), "core owns evidence UUID")
    other, other_session = uuid.uuid4(), uuid.uuid4()
    account(other,other_session)
    request(path,404,auth=jwt(other,other_session))
    request(f"/api/v1/conversations/{conversation}/messages/{uuid.uuid4()}/evidence",404)
    internal_headers = {"X-Internal-Token":os.environ["INTERNAL_VERIFY_TOKEN"],"X-User-Role":"PARENT","X-User-Id":str(user),"X-Student-Scope":str(uuid.uuid4())}
    request(f"/internal/records/evidence?answerIds={answer}",403,url=internal_url,headers=internal_headers)
    learning.execute("DELETE FROM answer WHERE id=%s", (answer,))
    after = request(path)
    require(after["items"][0]["available"] is False and "quote" not in after["items"][0], "Deleted record must be unavailable without replacement quote")
    spec = yaml.safe_load((ROOT/"contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
    schema = {"$ref":"#/components/schemas/AnalysisEvidenceResponse","components":spec["components"]}
    for value in [before,after]: Draft202012Validator(schema).validate(value)
    print(json.dumps({"actualCoreLearningPostgres":True,"availableEvidence":True,"foreignParent":404,"forgedMessage":404,"learningScopeForgery":403,"deletedEvidence":False,"openapiPayloadValidation":True}))
    core.close(); learning.close()

if __name__ == "__main__": main()
