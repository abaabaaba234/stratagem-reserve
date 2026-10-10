"""Cross-check native guards against preserved, read-only build 25480438 evidence.

Does not start the game, attach to processes, or modify the reference library.
The captured code is historical; runtime anchors still have to match at startup.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
from lupa import luajit21

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
    identities = {x["type"]: x for x in captured["entries"]}
    lua = luajit21.LuaRuntime()
    registry = lua.execute(target_source.decode('utf8'))
    selected, keys, ids = [], set(), set()
    groups = {"green": set(), "blue": set()}
    for _, target in registry.items():
        type_id = target['type_id']
        entry = identities[type_id]
        assert type_id not in ids and target['key'] not in keys, 'duplicate target identity'
        ids.add(type_id); keys.add(target['key'])
        assert target['group'] in groups
        groups[target['group']].add(type_id)
        assert entry['internal_name'] == target['internal_name'], f'name differs: {type_id}'
        assert entry['category'] == target['category'] == 2
        assert entry['uses'] == 0xffffffff and entry['cooldown_type'] == 0
        assert entry['timings'][-1] == target['baseline_cooldown']
        payload = [bytes.fromhex(target['payloads'][i])[::-1].hex() for i in range(1, len(target['payloads']) + 1)]
        assert entry['payload'] == payload, f'payload differs: {type_id}'
        selected.append(dict(entry, group=target['group'], key=target['key'], label=target['label']))
    green = {x['type'] for x in captured['entries'] if x['title'].upper().startswith(('SENTR', 'EMPLACEMENTS.'))
             and x['category'] == 2 and x['uses'] == 0xffffffff and x['cooldown_type'] == 0}
    assert groups['green'] == green, 'green defence coverage differs'
    assert groups['blue'] == {6, 16, 39, 89, 99, 120, 147}, 'blue expendable allowlist differs'
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
        "targets": sorted(selected, key=lambda t: t['type']),
        "group_counts": {group: len(members) for group, members in groups.items()},
        "slot_layout": {"stride": 48, "type": 0, "current_uses": 4, "call_start": 16,
                        "cooldown_endpoint": 24, "arrival_endpoint": 32},
        "hud_binding": "match native row slot index and type; native count renderer formats and lays out badge; recharge text uses ready status widget",
        "hud_position_ingame_verified": False,
    }
    (ROOT / "validation/reference.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(f"PASS: {len(anchors)} code anchors and {len(selected)} captured definitions; green={len(green)}, blue=7")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", type=Path, default=Path(r"E:\code\hd2 mods\eagle-carpet-bomb\research\current\code.bin"))
    parser.add_argument("--stratagems", type=Path, default=Path(r"E:\code\hd2 mods\hd2-data-reference\build-25480438\readable\stratagems-captured-sanitized.json"))
    args = parser.parse_args()
    verify(args.code, args.stratagems)
