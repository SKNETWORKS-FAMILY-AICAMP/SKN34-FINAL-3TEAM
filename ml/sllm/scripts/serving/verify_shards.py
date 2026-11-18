"""원본과 조각의 텐서마다 dtype·shape·바이트 sha256이 같은지 대조한다."""
import hashlib, json, struct, sys
from pathlib import Path
def tensors(path):
    f = open(path, "rb"); n = struct.unpack("<Q", f.read(8))[0]; h = json.loads(f.read(n)); m = h.pop("__metadata__", None)
    for k, v in h.items():
        b, e = v["data_offsets"]; f.seek(8 + n + b); s = hashlib.sha256(); left = e - b
        while left:
            buf = f.read(min(left, 64 << 20)); s.update(buf); left -= len(buf)
        yield k, (v["dtype"], tuple(v["shape"]), s.hexdigest()), m
src, d = sys.argv[1], Path(sys.argv[2])
a = {}; ma = None
for k, v, m in tensors(src): a[k] = v; ma = m
b = {}; mb = set()
for p in sorted(d.glob("model-*.safetensors")):
    for k, v, m in tensors(p): b[k] = v; mb.add(json.dumps(m, sort_keys=True))
idx = json.load(open(d / "model.safetensors.index.json"))
ok = a == b and set(idx["weight_map"]) == set(a) and mb == {json.dumps(ma, sort_keys=True)}
print(json.dumps({"tensors_source": len(a), "tensors_shards": len(b), "identical": ok, "metadata_kept": mb == {json.dumps(ma, sort_keys=True)}}))
