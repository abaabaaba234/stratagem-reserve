"""Build one Bingus v18 discoverable Lua resource; no game assets or loader bundled."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.1"
RESOURCE = "mods/stratagem_reserve/core"


def bundle():
    parts = [f"-- HD2-Addon: {RESOURCE}\n", "if rawget(_G,'StratagemReserve') then return rawget(_G,'StratagemReserve') end\n"]
    for name, symbol in [("targets", "Targets"), ("model", "Model"), ("native", "Native")]:
        source = (ROOT / "src" / f"{name}.lua").read_text(encoding="utf-8")
        parts.append(f"local {symbol}=(function()\n{source}\nend)()\n")
    parts.append("if type(jit)=='table' and type(jit.off)=='function' then jit.off(Native.new,true);jit.off(Model.new,true) end\n")
    parts.append((ROOT / "src/bootstrap.lua").read_text(encoding="utf-8"))
    return "".join(parts).encode("utf-8")


def murmur64(data):
    mask, m = (1 << 64) - 1, 0xc6a4a7935bd1e995
    h = len(data) * m & mask
    for i in range(0, len(data) // 8 * 8, 8):
        k = int.from_bytes(data[i:i + 8], "little") * m & mask
        k ^= k >> 47
        h = (h ^ (k * m & mask)) * m & mask
    tail = data[len(data) // 8 * 8:]
    if tail:
        h = (h ^ int.from_bytes(tail, "little")) * m & mask
    h ^= h >> 47
    h = h * m & mask
    return h ^ (h >> 47)


def archive(source):
    kind = 0xa14e8dfa2cd117e2
    body = struct.pack("<II", len(source), 2) + source
    offset = (72 + 32 + 80 + 15) & ~15
    size = max(4096, (offset + len(body) + 15) & ~15)
    header = struct.pack("<4I", 0xf0000011, 1, 1, 0) + bytes(16) + struct.pack("<Q", size) + bytes(32)
    types = struct.pack("<IIQQII", 0, 0, kind, 1, 16, 16)
    entry = struct.pack("<7Q6I", murmur64(RESOURCE.encode()), kind, offset, 0, 0, 0, 0, len(body), 0, 0, 16, 16, 0)
    return header + types + entry + bytes(offset - 184) + body + bytes(size - offset - len(body))


def manifest():
    return {
        "Version": 1,
        "Guid": "e9bc7209-4ac6-4c86-a211-1cf1e44e45c4",
        "Name": "战备次数储存 / Stratagem Reserve v" + VERSION,
        "Description": "EAT-17 实验版。就绪后继续补充储备次数；次数未用完时采用短冷却。MODS 可调总次数上限和短冷却。需 Bingus Shared Loader v18 与 ModOptionsMenu API 1 / version 2+。仅支持 build 25480438，本版次数显示与联机效果待验证。",
        "Options": [{"Name": "EAT-17 次数储存", "Description": "默认上限 3 次，短冷却 5 秒。只影响本机玩家；原生部署时间保留。", "Include": ["Core"]}],
    }


def build():
    subprocess.run([sys.executable, str(ROOT / "tests/test_runtime.py")], cwd=ROOT, check=True)
    source = bundle()
    report = json.loads((ROOT / "validation/offline.json").read_text())
    assert report["status"] == "OFFLINE_PASSED"
    assert report["source_sha256"] == hashlib.sha256(source).hexdigest()
    reference = json.loads((ROOT / "validation/reference.json").read_text())
    assert reference["native_source_sha256"] == hashlib.sha256((ROOT / "src/native.lua").read_bytes()).hexdigest(), "re-run verify_reference.py"
    assert reference["target_source_sha256"] == hashlib.sha256((ROOT / "src/targets.lua").read_bytes()).hexdigest(), "re-run verify_reference.py"
    assert all(a["matched_capture"] for a in reference["anchors"])
    name = "Core/9ba626afa44a3aa3.patch_0"
    files = {
        name: archive(source), name + ".stream": b"", name + ".gpu_resources": b"",
        "manifest.json": json.dumps(manifest(), ensure_ascii=True, indent=2).encode("ascii"),
        "VALIDATION.json": json.dumps(report, indent=2).encode(),
        "REFERENCE.json": json.dumps(reference, indent=2).encode(),
    }
    out = ROOT / "dist" / f"StratagemReserve_v{VERSION}.zip"
    out.parent.mkdir(exist_ok=True)
    temp = out.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as z:
        for key, value in sorted(files.items()):
            info = zipfile.ZipInfo(key, (2026, 10, 11, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, value)
    with zipfile.ZipFile(temp) as z:
        assert z.testzip() is None
        assert all(z.read(k) == v for k, v in files.items())
        b = z.read(name)
        nt, nf = struct.unpack_from("<II", b, 4)
        assert (nt, nf) == (1, 1)
        row = struct.unpack_from("<7Q6I", b, 72 + nt * 32)
        assert row[:2] == (murmur64(RESOURCE.encode()), 0xa14e8dfa2cd117e2)
        assert b[row[2] + 8:row[2] + row[7]] == source
    assert source == bundle(), "source changed during packaging"
    temp.replace(out)
    (ROOT / "manifest.json").write_bytes(files["manifest.json"])
    print(out)
    print("SHA256", hashlib.sha256(out.read_bytes()).hexdigest())
    return out


if __name__ == "__main__":
    build()
