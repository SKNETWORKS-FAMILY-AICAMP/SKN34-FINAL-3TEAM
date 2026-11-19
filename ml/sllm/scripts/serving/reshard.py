"""safetensors 한 파일을 텐서 바이트 그대로 여러 조각(각 MAX 바이트 이하)으로 나눈다. mmap·torch 없이 읽는다."""
import hashlib, json, struct, sys
from pathlib import Path
src, dst, MAX = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
dst.mkdir(parents=True, exist_ok=True)
f = src.open("rb"); n = struct.unpack("<Q", f.read(8))[0]; header = json.loads(f.read(n)); base = 8 + n
meta = header.pop("__metadata__", None)
names = sorted(header, key=lambda k: header[k]["data_offsets"][0])
shards, cur, size = [], [], 0
for k in names:
    b, e = header[k]["data_offsets"]; L = e - b
    if cur and size + L + 200_000_000 > MAX:  # 헤더 여유
        shards.append(cur); cur, size = [], 0
    cur.append(k); size += L
shards.append(cur)
N = len(shards); weight_map = {}; report = []
for i, keys in enumerate(shards, 1):
    name = f"model-{i:05d}-of-{N:05d}.safetensors"; off = 0; h = {}
    for k in keys:
        b, e = header[k]["data_offsets"]; h[k] = {"dtype": header[k]["dtype"], "shape": header[k]["shape"], "data_offsets": [off, off + e - b]}; off += e - b
        weight_map[k] = name
    if meta is not None: h = {"__metadata__": meta, **h}
    hb = json.dumps(h, separators=(",", ":")).encode(); hb += b" " * ((8 - len(hb) % 8) % 8)
    sha = hashlib.sha256()
    with (dst / name).open("wb") as o:
        for chunk in (struct.pack("<Q", len(hb)), hb):
            o.write(chunk); sha.update(chunk)
        for k in keys:
            b, e = header[k]["data_offsets"]; f.seek(base + b); left = e - b
            while left:
                buf = f.read(min(left, 64 << 20)); o.write(buf); sha.update(buf); left -= len(buf)
    total = 8 + len(hb) + off
    assert total <= MAX, (name, total)
    report.append({"file": name, "bytes": total, "sha256": sha.hexdigest(), "tensors": len(keys)})
    print(report[-1], flush=True)
idx = {"metadata": {"total_size": sum(header[k]["data_offsets"][1] - header[k]["data_offsets"][0] for k in names)}, "weight_map": dict(sorted(weight_map.items()))}
(dst / "model.safetensors.index.json").write_text(json.dumps(idx, indent=2) + "\n")
json.dump({"source_tensors": len(names), "shards": report}, open(dst / "reshard-report.json", "w"), indent=1)
