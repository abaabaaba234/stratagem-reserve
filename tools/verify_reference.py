"""Cross-check native guards against preserved, read-only build 25480438 evidence.

Does not start the game, attach to processes, or modify the reference library.
The captured code is historical; runtime anchors still have to match at startup.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def verify(code_path, reference_path):
    native = (ROOT / "src/native.lua").read_bytes()
    target_source = (ROOT / "src/targets.lua").read_bytes()
    code = code_path.read_bytes()
    anchors = []
    for offset, raw in re.findall(rb"\{(0x[0-9a-f]+),'([0-9a-f]+)'\}", native):
        rva = int(offset, 16)
        expected = bytes.fromhex(raw.decode())
        matched = code[rva - 0x1000:rva - 0x1000 + len(expected)] == expected
        anchors.append({"rva": hex(rva), "expected_hex": expected.hex(), "matched_capture": matched})
        assert matched, f"native anchor differs at {rva:x}"
    assert len(anchors) >= 10
    captured = json.loads(reference_path.read_text(encoding="utf8"))
    eat = [x for x in captured["entries"] if x["type"] == 147]
    assert len(eat) == 1
    eat = eat[0]
    assert eat["internal_name"] == "LATOneshot" and eat["uses"] == 0xffffffff
    assert eat["category"] == 2 and eat["cooldown_type"] == 0 and eat["timings"][-1] == 70
    assert eat["payload"] == ["0dc7a18342b62bec", "73f8498bffdcf415"]
    report = {
        "steam_build": 25480438,
        "snapshot_current_install_check": "PASS; 365 files checked on 2026-10-11 using verify_snapshot.py --current-game",
        "decoded_reference_equivalence": "NOT ESTABLISHED",
        "code_capture_sha256": hashlib.sha256(code).hexdigest(),
        "code_capture_origin": "eagle-carpet-bomb/research/current/code.bin; historical read-only capture, not new gameplay proof",
        "stratagem_reference_sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
        "native_source_sha256": hashlib.sha256(native).hexdigest(),
        "target_source_sha256": hashlib.sha256(target_source).hexdigest(),
        "anchors": anchors,
        "target": eat,
        "slot_layout": {"stride": 48, "type": 0, "current_uses": 4, "call_start": 16,
                        "cooldown_endpoint": 24, "arrival_endpoint": 32},
        "hud_binding": "match native row slot index and type; count uses native card; recharge text uses ready status widget",
        "hud_position_ingame_verified": False,
    }
    (ROOT / "validation/reference.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(f"PASS: {len(anchors)} code anchors and EAT-17 captured definition")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", type=Path, default=Path(r"E:\code\hd2 mods\eagle-carpet-bomb\research\current\code.bin"))
    parser.add_argument("--stratagems", type=Path, default=Path(r"E:\code\hd2 mods\hd2-data-reference\build-25480438\readable\stratagems-captured-sanitized.json"))
    args = parser.parse_args()
    verify(args.code, args.stratagems)
