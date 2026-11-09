"""#368 일회용 localhost MinIO용 합성 파일. 운영 버킷에는 사용할 수 없다."""

import base64
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/scoring-service"))
os.environ["INTERNAL_TOKEN"] = "preflight-local-token"
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from tests.test_preflight import fixture

contents, request = fixture()
client = boto3.client(
    "s3",
    endpoint_url="http://127.0.0.1:58100",
    aws_access_key_id="preflight-local",
    aws_secret_access_key="preflight-local-test-only",
    region_name="ap-northeast-2",
    config=Config(s3={"addressing_style": "path"}),
)
try:
    client.head_bucket(Bucket="models")
except ClientError as error:
    if str(error.response["Error"]["Code"]) != "404":
        raise
else:
    raise SystemExit("Use a fresh disposable MinIO: models bucket already exists")
client.create_bucket(Bucket="models")
for name, body in contents.items():
    for prefix in ["models/m2-klue-narrative/3.0/", "models/missing/3.0/"]:
        if prefix.startswith("models/missing") and name == "model.safetensors":
            continue
        client.put_object(
            Bucket="models",
            Key=prefix + name,
            Body=body,
            ChecksumSHA256=base64.b64encode(hashlib.sha256(body).digest()).decode(),
        )
(ROOT / "output").mkdir(exist_ok=True)
(ROOT / "output/issue368-request.json").write_text(
    request.model_dump_json(by_alias=True), encoding="utf-8"
)
head = client.head_object(
    Bucket="models",
    Key="models/m2-klue-narrative/3.0/model.safetensors",
    ChecksumMode="ENABLED",
)
print(
    {
        "seeded": True,
        "sha256Available": bool(head.get("ChecksumSHA256")),
        "checksumType": head.get("ChecksumType"),
    }
)
