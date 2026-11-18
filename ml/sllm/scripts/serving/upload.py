"""파일마다 단일 PutObject + ChecksumSHA256(FULL_OBJECT)로 올리고 HEAD로 확인한다. 덮어쓰지 않는다(If-None-Match)."""
import base64, hashlib, json, os, sys
import boto3
bucket, prefix, d = sys.argv[1], sys.argv[2].rstrip("/") + "/", sys.argv[3]
files = sys.argv[4:]
s3 = boto3.client("s3", region_name="ap-northeast-2"); out = []
for f in files:
    p = os.path.join(d, f); h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(64 << 20), b""): h.update(b)
    b64 = base64.b64encode(h.digest()).decode(); size = os.path.getsize(p)
    assert size <= 5_000_000_000, f
    with open(p, "rb") as fh:
        r = s3.put_object(Bucket=bucket, Key=prefix + f, Body=fh, ContentLength=size, ChecksumSHA256=b64, IfNoneMatch="*")
    hd = s3.head_object(Bucket=bucket, Key=prefix + f, ChecksumMode="ENABLED")
    ok = hd.get("ChecksumSHA256") == b64 and hd.get("ChecksumType") == "FULL_OBJECT" and hd["ContentLength"] == size
    out.append({"key": prefix + f, "bytes": size, "sha256": h.hexdigest(), "checksumType": hd.get("ChecksumType"), "verified": ok})
    print(json.dumps(out[-1]), flush=True)
json.dump(out, open(os.path.join("/data", "upload-" + prefix.strip("/").replace("/", "_") + ".json"), "w"), indent=1)
