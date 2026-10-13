"""Execute the shipped LuaJIT code against bounded native-memory and UI doubles.

The native call implementation is simulated. This proves integration contracts,
not engine behavior, rendering, or multiplayer authority.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import struct
import sys
import tempfile
import unittest
from lupa import luajit21

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build import bundle, murmur64, archive, RESOURCE

SOURCE = bundle()
REFERENCE_TARGETS = {t['type']: t for t in json.loads((ROOT / 'validation/reference.json').read_text())['targets']}
BASE = 0x180000000
PROVIDER_CHECK = None
U = lambda n: struct.pack("<I", n)
Q = lambda n: struct.pack("<Q", n)
F = lambda n: struct.pack("<f", n)


class Memory:
    def __init__(self):
        self.pages = {}
        self.writes = []
        self.denied = False
        self.fail_next = False
        self.partial = False

    def put(self, p, b):
        for i, v in enumerate(b):
            self.pages.setdefault((p + i) >> 12, bytearray(4096))[(p + i) & 4095] = v

    def read(self, p, n):
        try:
            return bytes(self.pages[(p + i) >> 12][(p + i) & 4095] for i in range(n))
        except KeyError:
            return None

    def write(self, p, b):
        self.writes.append((p, bytes(b)))
        if self.fail_next:
            self.fail_next = False
            if self.partial:
                self.put(p, b[:len(b) // 2])
            return False
        self.put(p, b)
        return True

    def query(self, p):
        start = p & ~4095
        return struct.pack("<QQIIQIIII", start, start, 4, 0, 4096, 0x1000, 0x20 if self.denied else 4, 0x20000, 0)


class Game:
    def __init__(self, cfg=None, loader=True, menu=True, bad_build=False, cached=None):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.cfg = self.folder / "StratagemReserve.cfg"
        if cfg:
            self.cfg.write_text(cfg, encoding="utf-8")
        self.mem = Memory()
        self.now = 1_000_000
        self.cooldown = 70.0
        self.pending_call = False
        self.pending_slot = 0
        self.target_slots = {}
        self.failure_call = False
        self.native_error = False
        self.texts = []
        self.shown = []
        self.rendered_counts = []
        self.badge_width = 0
        self.fail_draw = False
        self.calls = 0
        self.manager = 0x60000000
        self.clock = 0x62000000
        self.scene = 0x63000000
        self.player = 0x64000000
        self.hud = 0x65000000
        self.definition = 0x66000000
        self.slot = self.manager + 0x1c0
        self.remote = self.manager + 0x1690 + 0x1c0
        self.row = self.hud + 0x24e340 + 0x146dc0 + 0x1040 + 0x110
        self.card = self.row + 0x7c0
        dos = bytearray(4096)
        dos[:2] = b"MZ"
        struct.pack_into("<I", dos, 60, 0x100)
        dos[0x100:0x104] = b"PE\0\0"
        dos[0x118:0x11a] = b"\x0b\x02"
        struct.pack_into("<I", dos, 0x108, 0 if bad_build else 0x6ab3b43f)
        struct.pack_into("<I", dos, 0x150, 0x4744000)
        self.mem.put(BASE, dos)
        native = (ROOT / "src/native.lua").read_bytes()
        for at, value in re.findall(rb"\{(0x[0-9a-f]+),'([0-9a-f]+)'\}", native):
            self.mem.put(BASE + int(at, 16), bytes.fromhex(value.decode()))
        for rva, p in [(0x347ce50, self.manager), (0x3326348, self.clock), (0x3326340, self.scene),
                       (0x3326468, self.player), (0x346d538, self.hud), (0x33264f8, 0x67000000)]:
            self.mem.put(BASE + rva, Q(p))
        self.mem.put(self.scene + 0xac21c, U(4))
        self.mem.put(self.player + 0x88, U(1))
        self.mem.put(self.player + 0x2c8, b"LOCAL001")
        self.mem.put(self.manager, b"LOCAL001")
        self.mem.put(self.manager + 0x1690, b"REMOTE01")
        self.mem.put(self.manager + 0x2d200, U(2))
        self.mem.put(self.manager + 0x7c0, U(1))
        self.mem.put(self.manager + 0x1690 + 0x7c0, U(1))
        self.mem.put(self.slot, U(147) + U(0xffffffff) + bytes(40))
        self.mem.put(self.remote, U(147) + U(0xffffffff) + bytes(40))
        raw = bytearray(400)
        struct.pack_into("<I", raw, 0, 147)
        struct.pack_into("<I", raw, 0x3c, 2)
        struct.pack_into("<I", raw, 0x50, 0xffffffff)
        struct.pack_into("<f", raw, 0x68, 70)
        struct.pack_into("<Q", raw, 0x98, 0x68000000)
        struct.pack_into("<I", raw, 0xa0, 2)
        self.mem.put(self.definition, raw)
        self.mem.put(0x68000000, bytes.fromhex("ec2bb64283a1c70d15f4dcff8b49f873"))
        self.mem.put(BASE + 0x37cb600 + 147 * 8, Q(self.definition))
        self.mem.put(BASE + 0x21d4aa0 + 147 * 8, Q(0x69000000))
        self.mem.put(0x69000000, b"LATOneshot" + bytes(64))
        self.mem.put(self.hud + 0x24e340 + 0x59, b"\0")
        self.mem.put(self.hud + 0x24e340 + 0x21f5b0, b"\1")
        self.mem.put(self.row + 0x36f0, bytes(112))
        self.mem.put(self.row + 0x36f0, b"\1")
        self.mem.put(self.row + 0x3748, U(0))
        self.mem.put(self.row + 0x374c, U(147))
        self.mem.put(self.row + 0x3758, U(1))
        self.mem.put(self.card + 0x14b8, U(0) + U(1) + bytes(8) + U(147) + U(1))
        self.mem.put(self.row + 0x2028 + 0x110, Q(0))
        self.mem.put(self.row + 0x2028 + 0x11c, b"READY" + bytes(256))
        self.mem.put(self.card + 0xce0 + 0x110, Q(0))
        self.mem.put(self.card + 0xce0 + 0x11c, bytes(256))
        self.target_slots[0] = (147, self.slot, self.row)
        self.lua = luajit21.LuaRuntime(encoding=None)
        g = self.lua.globals()
        g[b"pyread"] = lambda p, n: self.mem.read(int(p), int(n))
        g[b"pywrite"] = lambda p, b: self.mem.write(int(p), bytes(b))
        g[b"pyquery"] = lambda p: self.mem.query(int(p))
        g[b"pycd"] = lambda _upgrades, _owner, type_id, *_args: self.cooldown if int(type_id) == 147 else REFERENCE_TARGETS[int(type_id)]['timings'][-1]
        g[b"pytext"] = self.paint
        g[b"pyshown"] = lambda p, value: self.shown.append((int(p), int(value)))
        g[b"pycountdraw"] = self.draw_count
        g[b"pyreplace"] = lambda a, b: self.replace(a, b)
        g[b"pyframe"] = self.frame
        g[b"cfg_folder"] = str(self.folder).encode()
        g[b"loader_on"] = loader
        self.lua.execute(br'''
          local real=require('ffi'); local proxy={}; for k,v in pairs(real)do proxy[k]=v end
          local kernel={GetCurrentProcess=function()return real.cast('void *',1)end,
              GetModuleHandleA=function()return real.cast('void *',0x180000000)end}
          kernel.ReadProcessMemory=function(_,p,b,n,c)local s=pyread(tonumber(real.cast('uintptr_t',p)),n)
              if not s then c[0]=0;return 0 end;real.copy(b,s,n);c[0]=n;return 1 end
          kernel.WriteProcessMemory=function(_,p,b,n,c)local ok=pywrite(tonumber(real.cast('uintptr_t',p)),real.string(b,n))
              c[0]=ok and n or 0;return ok and 1 or 0 end
          kernel.VirtualQuery=function(p,b,n)real.copy(b,pyquery(tonumber(real.cast('uintptr_t',p))),n);return n end
          kernel.MoveFileExA=function(a,b,flags)assert(flags==9);return pyreplace(a,b)end
          local aliases={};for name,fn in pairs(kernel)do aliases['stratreserve_'..name]=fn end
          proxy.load=function()return aliases end
          proxy.cast=function(kind,p)
              if kind=='float (*)(uintptr_t, uint64_t, uint32_t, uint8_t, uint8_t)'then assert(p==0x1808796a0);return pycd end
              if kind=='uint8_t (*)(uintptr_t, const char *)'then assert(p==0x18143dd60);return pytext end
              if kind=='void (*)(uintptr_t, uint8_t)'then assert(p==0x1814508e0);return pyshown end
              if kind=='void (*)(uintptr_t)'then assert(p==0x18183ae60);return pycountdraw end
              return real.cast(kind,p)
          end
          local original=require;require=function(n)if n=='ffi'then return proxy end;return original(n)end
          print=function()end
          if loader_on then CowboyBingusModLoader={api=1,jit={},log_directory=cfg_folder,
              open_log=function(name)return io.open(cfg_folder..'\\'..name,'wb')end}end
          original_calls=0;shutdown_calls=0
          update=function(dt,marker)original_calls=original_calls+1;pyframe(dt);return dt,marker,nil,42,nil end
          shutdown=function(marker)shutdown_calls=shutdown_calls+1;return marker,99 end
        ''')
        if menu:
            self.lua.execute(b'''
              menu_state={options={},values={},callbacks={},pending={},sets=0,order={}}
              local s=menu_state;ModOptionsMenu={api=1,version=3}
              function ModOptionsMenu.register_option(id,spec)
                  assert(not s.options[id]);assert(type(spec.mod)=='function')
                  assert(#spec.mod()<120)
                  if spec.type=='toggle'then assert(type(spec.default)=='boolean')end
                  if spec.type=='slider'then assert(spec.default>=spec.min and spec.default<=spec.max)end
                  if spec.type=='choice'then assert(spec.default==1 or spec.default==2)end
                  s.options[id]=spec;s.order[#s.order+1]=id;s.values[id]=spec.default;return true
              end
              function ModOptionsMenu.on_change(id,fn)assert(not s.callbacks[id]);s.callbacks[id]=fn;return true end
              function ModOptionsMenu.get(id)return s.values[id]end
              function ModOptionsMenu.set(id,value)s.values[id]=value;s.pending[id]=nil;s.sets=s.sets+1;return true end
              function menu_apply(key,value)local id='stratagem_reserve_'..key;local okay,why=s.callbacks[id](value)
                  if okay then s.values[id]=value end;return okay,why end
            ''')
            if cached:
                globals_ = self.lua.globals()
                globals_[b'cached_values'] = self.lua.table_from({k.encode(): v for k, v in cached.items()})
                self.lua.execute(b'''local register=ModOptionsMenu.register_option
                    ModOptionsMenu.register_option=function(id,spec)
                        local ok=register(id,spec)
                        if cached_values[id]~=nil then menu_state.values[id]=cached_values[id]end
                        return ok
                    end''')
        self.state = self.lua.execute(SOURCE)

    def replace(self, a, b):
        try:
            os.replace(os.fsdecode(a), os.fsdecode(b))
            return 1
        except OSError:
            return 0

    def paint(self, p, text):
        p = int(p)
        self.texts.append((p, bytes(text)))
        self.mem.put(p + 0x110, Q(0))
        self.mem.put(p + 0x11c, bytes(text) + bytes(256 - len(text)))
        return 1

    def draw_count(self, card):
        if self.fail_draw:
            raise RuntimeError('draw failure')
        card = int(card)
        count = struct.unpack('<I', self.mem.read(card + 0x14bc, 4))[0]
        # Model the native renderer's observable contract: integer substitution
        # retains its existing text template and measures the badge after layout.
        self.rendered_counts.append(count)
        self.badge_width = len(str(count)) * 10 + 8
        self.shown.append((card + 0x920, 1))

    def add_target(self, type_id, slot=1):
        """Independent captured identity at an additional local slot and HUD row."""
        entry = REFERENCE_TARGETS[type_id]
        address = self.manager + 0x1c0 + slot * 48
        definition = 0x70000000 + type_id * 0x1000
        raw = bytearray(400)
        struct.pack_into('<I', raw, 0, type_id)
        struct.pack_into('<I', raw, 0x3c, entry['category'])
        struct.pack_into('<I', raw, 0x50, entry['uses'])
        struct.pack_into('<f', raw, 0x68, entry['timings'][-1])
        struct.pack_into('<I', raw, 0x94, entry['cooldown_type'])
        struct.pack_into('<Q', raw, 0x98, definition + 0x300)
        struct.pack_into('<I', raw, 0xa0, len(entry['payload']))
        self.mem.put(definition, raw)
        self.mem.put(definition + 0x300, b''.join(bytes.fromhex(p)[::-1] for p in entry['payload']))
        self.mem.put(definition + 0x200, entry['internal_name'].encode() + bytes(64))
        self.mem.put(BASE + 0x37cb600 + type_id * 8, Q(definition))
        self.mem.put(BASE + 0x21d4aa0 + type_id * 8, Q(definition + 0x200))
        self.mem.put(address, U(type_id) + U(entry['uses']) + bytes(40))
        rows = max(slot + 1, struct.unpack('<I', self.mem.read(self.manager + 0x7c0, 4))[0])
        self.mem.put(self.manager + 0x7c0, U(rows))
        row = self.row + slot * 0x3760
        self.mem.put(row + 0x36f0, bytes(112))
        self.mem.put(row + 0x36f0, b'\1')
        self.mem.put(row + 0x3748, U(slot))
        self.mem.put(row + 0x374c, U(type_id))
        self.mem.put(row + 0x3758, U(1))
        self.mem.put(row + 0x7c0 + 0x14b8, U(slot) + U(1) + bytes(8) + U(type_id) + U(1))
        self.mem.put(row + 0x2028 + 0x110, Q(0))
        self.mem.put(row + 0x2028 + 0x11c, b'READY' + bytes(256))
        self.mem.put(row + 0x7c0 + 0xce0 + 0x110, Q(0))
        self.mem.put(row + 0x7c0 + 0xce0 + 0x11c, bytes(256))
        self.target_slots[slot] = (type_id, address, row)
        return address

    def field(self, offset, fmt="I", slot=0):
        return struct.unpack("<" + fmt, self.mem.read(self.target_slots[slot][1] + offset, struct.calcsize(fmt)))[0]

    def frame(self, dt):
        if self.native_error:
            self.native_error = False
            raise RuntimeError("original callback error")
        self.now += round(float(dt) * 1_000_000)
        self.mem.put(self.clock + 0x18, Q(self.now))
        if self.pending_call:
            self.pending_call = False
            slot = self.pending_slot
            type_id, address, _row = self.target_slots[slot]
            if self.field(4, slot=slot) != 0 and self.now >= self.field(0x18, "Q", slot):
                self.calls += 1
                arrival = self.now + 3_000_000
                self.mem.put(address + 0x10, Q(self.now))
                self.mem.put(address + 0x20, Q(arrival))
                cooldown = self.cooldown if type_id == 147 else REFERENCE_TARGETS[type_id]['timings'][-1]
                self.mem.put(address + 0x18, Q(arrival + round(cooldown * 1_000_000)))
                if not self.failure_call and self.field(4, slot=slot) != 0xffffffff:
                    self.mem.put(address + 4, U(self.field(4, slot=slot) - 1))
                self.failure_call = False
        for slot, (_type_id, _address, row) in self.target_slots.items():
            self.mem.put(row + 0x3758, U(3 if self.now < self.field(0x20, 'Q', slot) else 4 if self.now < self.field(0x18, 'Q', slot) else 1))

    def tick(self, dt=0):
        return self.lua.globals()[b"update"](dt, b"preserved")

    def call(self, dt=0.1, fail=False, slot=0):
        self.pending_call = True
        self.pending_slot = slot
        self.failure_call = fail
        return self.tick(dt)

    def display(self):
        return self.state[b"model"][b"slots"][b"eat17"]

    def apply(self, key, value):
        return self.lua.globals()[b"menu_apply"](key.encode(), value)

    def close(self):
        if self.lua:
            self.lua.globals()[b"shutdown"](b"closed")
        self.lua = None
        self.temp.cleanup()


class RuntimeTests(unittest.TestCase):
    def game(self, **kwargs):
        g = Game(**kwargs)
        self.addCleanup(g.close)
        return g

    def test_initial_ready_is_one_total_use(self):
        g = self.game(); self.assertEqual(g.tick(), (0, b"preserved", None, 42, None))
        self.assertEqual(g.display()[b"count"], 1); self.assertEqual(g.field(4), 1)
        self.assertEqual(g.mem.read(g.remote, 48), U(147) + U(0xffffffff) + bytes(40))

    def test_attach_during_cooldown_has_zero_then_one(self):
        g = self.game(); g.mem.put(g.slot + 0x18, Q(g.now + 30_000_000)); g.tick()
        self.assertEqual(g.display()[b"count"], 0); self.assertEqual(g.field(4), 1)
        g.tick(30); self.assertEqual(g.display()[b"count"], 1)
        self.assertEqual(g.display()[b"progress"], 0)

    def test_accumulate_to_cap_and_stop_overflow(self):
        g = self.game(); g.tick(); g.tick(70); self.assertEqual(g.field(4), 2)
        g.tick(1400); self.assertEqual(g.field(4), 3); self.assertEqual(g.display()[b"progress"], 0)
        g.call(); self.assertEqual(g.display()[b"count"], 2)
        self.assertEqual(g.field(0x18, "Q") - g.field(0x20, "Q"), 5_000_000)

    def test_partial_progress_pauses_through_deployment_and_short_cd(self):
        g = self.game(); g.tick(); g.tick(112)
        self.assertEqual(g.display()[b"count"], 2); self.assertAlmostEqual(g.display()[b"progress"], 42)
        g.call(); progress = g.display()[b"progress"]; g.tick(4)
        self.assertAlmostEqual(g.display()[b"progress"], progress)
        g.tick(4); self.assertAlmostEqual(g.display()[b"progress"], progress)
        g.tick(27.9); self.assertEqual(g.display()[b"count"], 2)

    def test_three_calls_two_short_then_full(self):
        g = self.game(); g.tick(); g.tick(140); g.call(); self.assertEqual(g.display()[b"count"], 2)
        g.call(); self.assertEqual(g.calls, 1)
        g.tick(8); g.call(); self.assertEqual(g.display()[b"count"], 1)
        g.tick(8); g.call(); self.assertEqual(g.display()[b"count"], 0)
        self.assertEqual(g.field(4), 1)  # inaccessible native sentinel
        self.assertEqual(g.field(0x18, "Q") - g.field(0x20, "Q"), 70_000_000)
        self.assertIn(0, g.rendered_counts)
        g.call(); self.assertEqual(g.calls, 3)
        g.tick(73); self.assertEqual(g.display()[b"count"], 1)

    def test_full_cooldown_overshoot_counts_only_ready_time(self):
        g = self.game(); g.tick(); g.call(); g.tick(83)
        self.assertEqual(g.display()[b"count"], 1); self.assertAlmostEqual(g.display()[b"progress"], 10.1)

    def test_runtime_ship_upgrade_cycle(self):
        g = self.game(); g.cooldown = 63; g.tick(); g.tick(63)
        self.assertEqual(g.field(4), 2); self.assertEqual(g.display()[b"cycle"], 63)

    def test_short_setting_applies_to_next_call(self):
        g = self.game(); g.tick(); g.tick(140); self.assertTrue(g.apply("short_cooldown", 2.5)[0])
        g.call(); deadline = g.field(0x18, "Q"); self.assertEqual(deadline - g.field(0x20, "Q"), 2_500_000)
        g.apply("short_cooldown", 10); g.tick(1); self.assertEqual(g.field(0x18, "Q"), deadline)

    def test_capacity_decrease_clamps_and_increase_grants_nothing(self):
        g = self.game(); g.tick(); g.tick(140); g.apply("blue_max_charges", 2); g.tick()
        self.assertEqual(g.field(4), 2); g.apply("blue_max_charges", 8); g.tick(); self.assertEqual(g.field(4), 2)

    def test_cap_one_uses_only_full_cd(self):
        g = self.game(cfg="max_charges=1\n"); g.tick(); g.tick(1000); self.assertEqual(g.field(4), 1)
        g.call(); self.assertEqual(g.field(0x18, "Q") - g.field(0x20, "Q"), 70_000_000)

    def test_failed_native_call_does_not_consume_or_shorten(self):
        g = self.game(); g.tick(); g.tick(90); g.call(fail=True)
        self.assertEqual(g.display()[b"count"], 2)
        self.assertEqual(g.field(0x18, "Q") - g.field(0x20, "Q"), 70_000_000)

    def test_pause_preserves_progress_without_catchup(self):
        g = self.game(); g.tick(); g.tick(20)
        g.mem.put(g.hud + 0x24e340 + 0x59, b"\1"); g.tick(100)
        self.assertEqual(g.display()[b"progress"], 20)
        g.mem.put(g.hud + 0x24e340 + 0x59, b"\0"); g.tick(10)
        self.assertEqual(g.display()[b"progress"], 30)

    def test_mission_exit_restores_owned_uses(self):
        g = self.game(); g.tick(); g.tick(70)
        g.mem.put(g.scene + 0xac21c, U(1)); g.tick(); self.assertEqual(g.field(4), 0xffffffff)
        self.assertIsNone(g.display())

    def test_disable_restores_full_native_deadline_and_uses(self):
        g = self.game(); g.tick(); g.tick(70); g.call()
        full = g.field(0x20, "Q") + 70_000_000
        self.assertTrue(g.apply("enabled", False)[0]); self.assertEqual(g.field(4), 0xffffffff)
        self.assertEqual(g.field(0x18, "Q"), full)
        g.tick(); self.assertEqual(g.state[b"phase"], b"disabled")

    def test_slot_removal_never_writes_retired_identity(self):
        g = self.game(); g.tick(); writes = len(g.mem.writes)
        g.mem.put(g.slot, U(146)); g.tick(); self.assertEqual(len(g.mem.writes), writes)
        self.assertIsNone(g.display())

    def test_bad_build_fails_before_any_write(self):
        g = self.game(bad_build=True); g.tick(); self.assertEqual(g.state[b"phase"], b"stopped")
        self.assertEqual(g.mem.writes, [])

    def test_bad_code_anchor_fails_before_any_write(self):
        g = self.game(); g.mem.put(BASE + 0x135c6f5, b"\x90"); g.tick()
        self.assertEqual(g.state[b"phase"], b"stopped"); self.assertEqual(g.mem.writes, [])

    def test_target_payload_guard(self):
        g = self.game(); g.mem.put(0x68000000, bytes(16)); g.tick()
        self.assertEqual(g.mem.writes, []); self.assertEqual(g.state[b"phase"], b"stopped")

    def test_static_target_modified_fails_closed(self):
        g = self.game(); g.mem.put(g.definition + 0x68, F(5)); g.tick()
        self.assertEqual(g.mem.writes, []); self.assertEqual(g.state[b"phase"], b"stopped")

    def test_existing_finite_uses_conflict(self):
        g = self.game(); g.mem.put(g.slot + 4, U(4)); g.tick()
        self.assertEqual(g.mem.writes, []); self.assertEqual(g.state[b"phase"], b"stopped")

    def test_unexpected_external_count_is_not_overwritten(self):
        g = self.game(); g.tick(); writes = len(g.mem.writes)
        g.mem.put(g.slot + 4, U(8)); g.tick(); self.assertEqual(g.field(4), 8)
        self.assertEqual(len(g.mem.writes), writes); self.assertEqual(g.state[b"phase"], b"stopped")

    def test_count_decrement_without_success_is_rejected(self):
        g = self.game(); g.tick(); g.mem.put(g.slot + 4, U(0)); g.tick()
        self.assertEqual(g.state[b"phase"], b"stopped"); self.assertEqual(g.field(4), 0xffffffff)

    def test_deadline_conflict_is_not_overwritten(self):
        g = self.game(); g.tick(); g.tick(70); g.call()
        g.mem.put(g.slot + 0x18, Q(g.now + 99_000_000)); g.tick()
        self.assertEqual(g.field(0x18, "Q"), g.now + 99_000_000)
        self.assertEqual(g.state[b"phase"], b"stopped")

    def test_failed_write_stops_and_restores(self):
        g = self.game(); g.tick(); g.mem.fail_next = True; g.tick(70)
        self.assertEqual(g.state[b"phase"], b"stopped"); self.assertEqual(g.field(4), 0xffffffff)

    def test_partial_initial_count_write_restores(self):
        g = self.game(); g.mem.fail_next = True; g.mem.partial = True; g.tick()
        self.assertEqual(g.state[b"phase"], b"stopped"); self.assertEqual(g.field(4), 0xffffffff)
        self.assertEqual(g.state[b"model"][b"cleanup_pending"], 0)

    def test_partial_short_deadline_write_restores(self):
        g = self.game(); g.tick(); g.tick(70); g.mem.fail_next = True; g.mem.partial = True; g.call()
        self.assertEqual(g.field(0x18, "Q"), g.field(0x20, "Q") + 70_000_000)
        self.assertEqual(g.field(4), 0xffffffff)
        self.assertEqual(g.state[b"phase"], b"stopped")

    def test_disable_after_two_native_decrements_restores(self):
        g = self.game(); g.tick(); g.tick(140); g.call(); g.tick(8); g.call()
        self.assertEqual(g.field(4), 1); self.assertTrue(g.apply("enabled", False)[0])
        self.assertEqual(g.field(4), 0xffffffff)

    def test_native_mutations_are_local_data_fields_only(self):
        g = self.game(); g.tick(); g.tick(140); g.call(); g.tick(8); g.call(); g.apply("enabled", False)
        self.assertTrue(g.mem.writes)
        self.assertTrue(all((p, len(b)) in [(g.slot + 4, 4), (g.slot + 0x18, 8), (g.card + 0x14bc, 4)] for p, b in g.mem.writes))

    def test_mission_clock_rollback_retires_state(self):
        g = self.game(); g.tick(); g.tick(70); g.now = 1_000_000; g.tick()
        self.assertEqual(g.state[b"phase"], b"stopped"); self.assertEqual(g.field(4), 0xffffffff)

    def test_late_menu_is_registered_without_resetting_progress(self):
        g = self.game(menu=False); g.tick(); g.tick(20)
        g.lua.execute(b'''ModOptionsMenu={api=1,version=2,register_option=function()return true end,
            on_change=function()return true end,get=function()return nil end,set=function()return true end}''')
        for _ in range(121): g.tick()
        self.assertTrue(g.state[b"menu_registered"]); self.assertEqual(g.display()[b"progress"], 20)

    def test_execute_pages_are_never_written(self):
        g = self.game(); g.mem.denied = True; g.tick(); self.assertEqual(g.mem.writes, [])
        self.assertEqual(g.state[b"phase"], b"stopped")

    def test_missing_loader_has_no_update_hook(self):
        g = self.game(loader=False); g.tick(); self.assertEqual(g.mem.writes, [])
        self.assertEqual(g.state[b"phase"], b"stopped")

    def test_no_menu_core_still_runs(self):
        g = self.game(menu=False); g.tick(); g.tick(70); self.assertEqual(g.field(4), 2)

    def test_old_menu_core_still_runs(self):
        g = self.game(); g.lua.globals()[b"ModOptionsMenu"][b"version"] = 1
        g.tick(); self.assertIsNotNone(g.state[b"menu_error"]); self.assertEqual(g.field(4), 1)

    def test_menu_late_registration_single_callbacks(self):
        g = self.game(); g.tick(); g.tick()
        self.assertEqual(len(list(g.lua.globals()[b"menu_state"][b"callbacks"].keys())), 13)
        g.lua.execute(b"menu_state.pending.stratagem_reserve_blue_max_charges=7")
        for _ in range(121): g.tick()
        self.assertEqual(g.lua.globals()[b"menu_state"][b"pending"][b"stratagem_reserve_blue_max_charges"], 7)

    def test_invalid_menu_values_leave_config_unchanged(self):
        g = self.game(); g.tick()
        for key, value in [("blue_max_charges", 0), ("blue_max_charges", 2.5), ("short_cooldown", 0), ("short_cooldown", 5.25), ("enabled", 1), ('green_enabled', 1), ('blue_enabled', 0), ('red_cd_growth', 0.5), ('green_cd_growth', 1.25), ('blue_cd_growth', float('nan')), ('inherit_ratio', 1), ('red_max_charges', 11)]:
            self.assertFalse(g.apply(key, value)[0])
        self.assertEqual(g.state[b"config"][b"blue_max_charges"], 3)

    def test_config_persistence(self):
        g = self.game(); g.tick(); g.apply("blue_max_charges", 6); g.apply("short_cooldown", 4.5)
        text = g.cfg.read_text(encoding="utf8"); self.assertIn("blue_max_charges=6", text)
        self.assertIn("short_cooldown=4.5", text)
        h = self.game(cfg=text); h.tick(); self.assertEqual(h.state[b"config"][b"blue_max_charges"], 6)

    def test_invalid_config_disables_feature(self):
        g = self.game(cfg="short_cooldown=nan\n"); g.tick()
        self.assertEqual(g.state[b"phase"], b"disabled"); self.assertEqual(g.mem.writes, [])

    def test_duplicate_load_does_not_add_hooks(self):
        g = self.game(); g.tick(); second = g.lua.execute(SOURCE); self.assertEqual(second[b"version"], b"0.3.2")
        g.tick(); self.assertEqual(g.lua.globals()[b"original_calls"], 2)

    def test_original_errors_propagate_and_next_frame_restores(self):
        g = self.game(); g.tick(); g.tick(70); g.native_error = True
        with self.assertRaises(RuntimeError): g.tick()
        g.tick(); self.assertEqual(g.field(4), 0xffffffff)
        g.tick(); self.assertEqual(g.field(4), 1)

    def test_shutdown_preserves_arguments_and_returns(self):
        g = self.game(); g.tick(); self.assertEqual(g.lua.globals()[b"shutdown"](b"bye"), (b"bye", 99))
        self.assertEqual(g.field(4), 0xffffffff)

    def test_each_registered_target_consumes_short_then_full_and_restores(self):
        for type_id, entry in REFERENCE_TARGETS.items():
            if type_id == 147:
                continue
            with self.subTest(target=entry['internal_name']):
                g = self.game(); address = g.add_target(type_id)
                g.tick(); cycle = entry['timings'][-1]; g.tick(cycle)
                self.assertEqual(g.field(4, slot=1), 2)
                state = g.state[b'model'][b'slots'][entry['key'].encode()]
                self.assertEqual(state[b'group'], entry['group'].encode())
                self.assertEqual(state[b'cycle'], cycle)
                g.call(slot=1)
                self.assertEqual(g.field(4, slot=1), 1)
                self.assertEqual(g.field(0x18, 'Q', 1) - g.field(0x20, 'Q', 1), 5_000_000)
                g.tick(8); g.call(slot=1)
                self.assertEqual(state[b'count'], 0)
                self.assertEqual(g.field(0x18, 'Q', 1) - g.field(0x20, 'Q', 1), round(cycle * 1_000_000))
                g.tick(cycle + 3)
                self.assertEqual(state[b'count'], 1)
                self.assertTrue(g.apply('enabled', False)[0])
                self.assertEqual(g.mem.read(address + 4, 4), U(entry['uses'] - 2 if entry['uses'] != 0xffffffff else 0xffffffff))

    def test_green_and_blue_have_independent_cycles_and_debits(self):
        g = self.game(); g.add_target(121); g.tick(); g.tick(140)
        green = g.state[b'model'][b'slots'][b'TurretMachinegunGPMG']
        self.assertEqual(g.display()[b'count'], 3); self.assertEqual(green[b'count'], 2)
        green_progress = green[b'progress']
        g.call()
        self.assertEqual(g.display()[b'count'], 2); self.assertEqual(green[b'count'], 2)
        self.assertAlmostEqual(green[b'progress'], green_progress + 0.1)
        blue_progress = g.display()[b'progress']
        g.call(slot=1)
        self.assertEqual(green[b'count'], 1); self.assertEqual(g.display()[b'count'], 2)
        self.assertAlmostEqual(g.display()[b'progress'], blue_progress)

    def test_green_group_disable_restores_only_green_and_preserves_blue_progress(self):
        g = self.game(); g.add_target(121); g.tick(); g.tick(140)
        g.call(); g.call(slot=1)
        blue_deadline = g.field(0x18, 'Q'); blue_progress = g.display()[b'progress']
        full_green = g.field(0x20, 'Q', 1) + 90_000_000
        self.assertTrue(g.apply('green_enabled', False)[0])
        self.assertEqual(g.field(4, slot=1), 0xffffffff)
        self.assertEqual(g.field(0x18, 'Q', 1), full_green)
        self.assertEqual(g.field(4), 2); self.assertEqual(g.field(0x18, 'Q'), blue_deadline)
        g.tick()
        self.assertEqual(g.display()[b'progress'], blue_progress)
        self.assertIsNone(g.state[b'model'][b'slots'][b'TurretMachinegunGPMG'])

    def test_blue_group_disable_restores_only_blue_and_preserves_green_progress(self):
        g = self.game(); g.add_target(121); g.tick(); g.tick(140)
        green = g.state[b'model'][b'slots'][b'TurretMachinegunGPMG']
        progress = green[b'progress']
        self.assertTrue(g.apply('blue_enabled', False)[0])
        self.assertEqual(g.field(4), 0xffffffff); self.assertEqual(g.field(4, slot=1), 2)
        g.tick()
        self.assertEqual(green[b'progress'], progress); self.assertIsNone(g.display())

    def test_group_reenable_during_native_cooldown_does_not_grant_ready_use(self):
        g = self.game(); g.add_target(121); g.tick(); g.tick(140); g.call(slot=1)
        g.apply('green_enabled', False); g.apply('green_enabled', True); g.tick()
        green = g.state[b'model'][b'slots'][b'TurretMachinegunGPMG']
        self.assertEqual(green[b'count'], 0); self.assertEqual(green[b'progress'], 0)
        self.assertEqual(g.field(0x18, 'Q', 1) - g.field(0x20, 'Q', 1), 90_000_000)
        g.tick(93); self.assertEqual(green[b'count'], 1)

    def test_master_disable_restores_every_group_and_blocks_reenable_until_master_on(self):
        g = self.game(); g.add_target(121); g.tick(); g.tick(140); g.call(); g.call(slot=1)
        g.apply('enabled', False)
        for slot in (0, 1): self.assertEqual(g.field(4, slot=slot), 0xffffffff)
        self.assertEqual(g.field(0x18, 'Q') - g.field(0x20, 'Q'), 70_000_000)
        self.assertEqual(g.field(0x18, 'Q', 1) - g.field(0x20, 'Q', 1), 90_000_000)
        g.apply('green_enabled', True); g.tick(20)
        self.assertEqual(len(g.state[b'model'][b'slots']), 0)
        g.apply('enabled', True); g.tick()
        self.assertEqual(g.display()[b'count'], 0)

    def test_disabled_group_does_not_read_or_write_its_invalid_definition(self):
        g = self.game(cfg='green_enabled=0\n'); g.add_target(121)
        g.mem.put(0x70000000 + 121 * 0x1000, bytes(400)); g.tick()
        self.assertEqual(g.state[b'phase'], b'active'); self.assertEqual(g.field(4), 1)
        self.assertEqual(g.field(4, slot=1), 0xffffffff)

    def test_equipped_target_guard_failure_restores_other_group(self):
        g = self.game(); g.add_target(121); g.tick(); g.tick(140)
        g.mem.put(0x70000000 + 121 * 0x1000 + 0x300, bytes(16)); g.tick()
        self.assertEqual(g.state[b'phase'], b'stopped')
        for slot in (0, 1): self.assertEqual(g.field(4, slot=slot), 0xffffffff)

    def test_nonexpendable_support_mission_and_reward_slots_are_untouched(self):
        for type_id in (92, 31, 33, 69, 15, 124, 3, 49, 5):
            with self.subTest(type_id=type_id):
                g = self.game(); address = g.add_target(121)
                g.mem.put(address, U(type_id)); original = g.mem.read(address, 48)
                g.tick(); g.tick(700)
                self.assertEqual(g.mem.read(address, 48), original)
                self.assertEqual(g.state[b'phase'], b'active')

    def test_four_slots_share_short_setting_without_sharing_counts(self):
        g = self.game(); g.add_target(121, 1); g.add_target(6, 2); g.add_target(22, 3)
        g.tick(); g.apply('blue_max_charges', 4); g.apply('green_max_charges', 4); g.apply('short_cooldown', 2.5); g.tick(210)
        self.assertEqual([g.field(4, slot=i) for i in range(4)], [4, 3, 2, 3])
        g.call(slot=2)
        self.assertEqual([g.field(4, slot=i) for i in range(4)], [4, 3, 1, 3])
        self.assertEqual(g.field(0x18, 'Q', 2) - g.field(0x20, 'Q', 2), 2_500_000)

    def test_group_preferences_and_existing_configuration_are_persisted(self):
        g = self.game(cfg='enabled=1\nmax_charges=6\nshort_cooldown=4.5\n'); g.tick()
        self.assertTrue(g.state[b'config'][b'green_enabled']); self.assertTrue(g.state[b'config'][b'blue_enabled'])
        self.assertEqual(g.state[b'config'][b'blue_max_charges'], 6)
        self.assertEqual(g.state[b'config'][b'green_max_charges'], 6)
        self.assertEqual(g.state[b'config'][b'red_max_charges'], 3)
        self.assertEqual(g.state[b'config'][b'short_cooldown'], 4.5)
        g.apply('blue_enabled', False); g.apply('green_enabled', False)
        text = g.cfg.read_text(encoding='utf8')
        h = self.game(cfg=text); h.tick(); self.assertEqual(h.mem.writes, [])
        self.assertFalse(h.state[b'config'][b'green_enabled']); self.assertFalse(h.state[b'config'][b'blue_enabled'])
        self.assertEqual(h.state[b'config'][b'blue_max_charges'], 6)
        self.assertEqual(h.state[b'config'][b'short_cooldown'], 4.5)

    def test_menu_has_global_group_toggles_and_adjustable_shared_short_cooldown(self):
        g = self.game(); g.tick()
        options = g.lua.globals()[b'menu_state'][b'options']
        keys = [b'language', b'enabled', b'inherit_ratio', b'short_cooldown']
        keys += [group + suffix for group in (b'red', b'green', b'blue') for suffix in (b'_enabled', b'_max_charges', b'_cd_growth')]
        self.assertEqual(set(options.keys()), {b'stratagem_reserve_' + k for k in keys})
        slider = options[b'stratagem_reserve_short_cooldown']
        self.assertEqual((slider[b'min'], slider[b'max'], slider[b'step']), (1, 60, 0.5))
        self.assertNotIn(b'EAT-17', options[b'stratagem_reserve_enabled'][b'label']())

    def test_menu_language_first_bilingual_descriptions_and_provider_limits(self):
        g = self.game(); g.tick(); state = g.lua.globals()[b'menu_state']
        self.assertEqual(state[b'order'][1], b'stratagem_reserve_language')
        language = state[b'options'][b'stratagem_reserve_language']
        self.assertEqual(language[b'label'], b'Language')
        self.assertEqual(list(language[b'choices'].values()), ['简体汉字'.encode(), b'English'])
        self.assertEqual(language[b'default'], 1)
        for option in state[b'options'].values():
            title = option[b'mod']().decode()
            label = option[b'label']() if callable(option[b'label']) else option[b'label']
            desc = option[b'description']().decode()
            self.assertLessEqual(len(title), 40); self.assertLessEqual(len(label.decode()), 64)
            self.assertLessEqual(len(desc), 400)
            self.assertIn('中文：', desc); self.assertIn('English:', desc)

    def test_language_switch_preserves_gameplay_and_persists_both_directions(self):
        g = self.game(cfg='blue_max_charges=6\nshort_cooldown=4.5\n'); g.tick(); g.tick(20)
        before = dict(g.state[b'config'].items()); progress = g.display()[b'progress']
        options = g.lua.globals()[b'menu_state'][b'options']
        descriptions = {key: value[b'description']() for key, value in options.items()}
        g.mem.writes.clear()
        self.assertTrue(g.apply('language', 2)[0])
        self.assertEqual(g.mem.writes, []); self.assertEqual(g.display()[b'progress'], progress)
        self.assertEqual(options[b'stratagem_reserve_enabled'][b'mod'](), b'Stratagem Reserve')
        self.assertEqual(options[b'stratagem_reserve_enabled'][b'label'](), b'Enable Stratagem Reserve (master)')
        self.assertEqual(dict(g.state[b'config'].items()), before | {b'language': b'en'})
        self.assertTrue(all(value[b'description']() == descriptions[key] for key, value in options.items()))
        h = self.game(cfg=g.cfg.read_text(encoding='utf8')); h.tick()
        self.assertEqual(h.lua.globals()[b'menu_state'][b'values'][b'stratagem_reserve_language'], 2)
        self.assertEqual(h.state[b'config'][b'blue_max_charges'], 6)
        self.assertTrue(h.apply('language', 1)[0]); self.assertIn('language=zh', h.cfg.read_text())
        self.assertEqual(h.lua.globals()[b'menu_state'][b'options'][b'stratagem_reserve_enabled'][b'mod'](), '战备次数储存'.encode())

    def test_old_and_invalid_language_configs_preserve_existing_settings(self):
        for suffix in ('', 'language=bad\n'):
            g = self.game(cfg='enabled=0\nblue_max_charges=6\nblue_cd_growth=1.5\n' + suffix)
            g.tick(); c = g.state[b'config']
            self.assertEqual(c[b'language'], b'zh'); self.assertFalse(c[b'enabled'])
            self.assertEqual(c[b'blue_max_charges'], 6); self.assertEqual(c[b'blue_cd_growth'], 1.5)
            g.apply('language', 2)
            self.assertIn('blue_max_charges=6', g.cfg.read_text())
            self.assertIn('language=en', g.cfg.read_text())

    def test_language_rejects_invalid_choices_and_failed_saves(self):
        g = self.game(); g.tick()
        for value in (0, 3, 1.5, b'en', True, float('nan')):
            self.assertFalse(g.apply('language', value)[0])
            self.assertEqual(g.state[b'config'][b'language'], b'zh')
        g.lua.globals()[b'pyreplace'] = lambda *_: 0
        self.assertFalse(g.apply('language', 2)[0])
        self.assertEqual(g.state[b'config'][b'language'], b'zh')

    def test_independent_config_overrides_stale_menu_cache(self):
        g = self.game(cfg='language=zh\nblue_max_charges=4\nenabled=0\n', cached={
            'stratagem_reserve_language': 2, 'stratagem_reserve_blue_max_charges': 9,
            'stratagem_reserve_enabled': True})
        g.tick(); values = g.lua.globals()[b'menu_state'][b'values']
        self.assertEqual(values[b'stratagem_reserve_language'], 1)
        self.assertEqual(values[b'stratagem_reserve_blue_max_charges'], 4)
        self.assertFalse(values[b'stratagem_reserve_enabled'])

    def test_menu_v2_language_callbacks_remain_single_and_preserve_unapplied_edits(self):
        g = self.game(); g.lua.globals()[b'ModOptionsMenu'][b'version'] = 2; g.tick()
        state = g.lua.globals()[b'menu_state']
        self.assertIsNone(state[b'options'][b'stratagem_reserve_language'][b'mod_id'])
        state[b'pending'][b'stratagem_reserve_language'] = 2
        state[b'pending'][b'stratagem_reserve_short_cooldown'] = 7.5
        for _ in range(361): g.tick()
        self.assertEqual(state[b'pending'][b'stratagem_reserve_language'], 2)
        self.assertEqual(state[b'pending'][b'stratagem_reserve_short_cooldown'], 7.5)
        self.assertEqual(state[b'sets'], 0); self.assertEqual(len(list(state[b'callbacks'].keys())), 13)

    def test_menu_registration_failure_preserves_core_config_function(self):
        g = self.game()
        g.lua.execute(b'ModOptionsMenu.register_option=function()return false,"refused"end')
        g.tick(); g.tick(70)
        self.assertIn(b'refused', g.state[b'menu_error']); self.assertEqual(g.field(4), 2)

    def test_actual_menu_provider_registration_apply_and_dynamic_refresh(self):
        global PROVIDER_CHECK
        path = os.environ.get('HD2_MOD_OPTIONS_MENU_SOURCE')
        if not path: self.skipTest('external provider source not supplied')
        source = Path(path).read_bytes()
        def module(name):
            marker = b'mom_files.' + name + b' = function(...)'
            start = source.index(marker); end = source.index(b'\nmom_files.', start + len(marker))
            return source[start:end]
        g = self.game(menu=False)
        g.lua.execute(br'''
          local T={upper=string.upper,check=function()return true end,
            length=function(s)local _,n=s:gsub('[^\128-\191]','');return n end}
          mom={state={mods={},options={},option_count=0,values={},callbacks={},revision=0,
            saved={stratagem_reserve_language='2',stratagem_reserve_enabled='false',stratagem_reserve_blue_max_charges='9'},
            pending={},pending_count=0,refused={},refused_count=0,queued={}},
            translation={T=T,tr=function(k)return k end},note=function()end,
            TEXT_TEMPLATE=123,MAX_MODS=112,MAX_ROWS=32,
            descriptor=function()return {},{} end}
          mom_files={}
        ''' + module(b'options') + b'\n' + module(b'api') + b'''
          mom_files.options(mom);mom_files.api(mom);ModOptionsMenu=mom.api
        ''')
        g.tick(); mom = g.lua.globals()[b'mom']; state = mom[b'state']; api = mom[b'api']
        self.assertTrue(g.state[b'menu_registered']); self.assertEqual(api[b'version'], 3)
        self.assertEqual(len(state[b'mods']), 1); self.assertEqual(len(state[b'mods'][1][b'order']), 13)
        self.assertEqual(state[b'mods'][1][b'order'][1][b'id'], b'stratagem_reserve_language')
        self.assertEqual(api[b'get'](b'stratagem_reserve_language'), 1)
        self.assertTrue(api[b'get'](b'stratagem_reserve_enabled'))
        self.assertEqual(api[b'get'](b'stratagem_reserve_blue_max_charges'), 3)
        descriptions = {key: value[b'description'] for key, value in state[b'options'].items()}
        mom[b'set_pending'](b'stratagem_reserve_blue_max_charges', 6)
        for _ in range(121): g.tick()
        self.assertEqual(state[b'pending'][b'stratagem_reserve_blue_max_charges'], 6)
        mom[b'set_pending'](b'stratagem_reserve_language', 2)
        self.assertEqual(mom[b'apply_pending'](), 2)
        mom[b'translation'][b'refresh']()
        self.assertEqual(g.state[b'config'][b'language'], b'en')
        self.assertEqual(g.state[b'config'][b'blue_max_charges'], 6)
        self.assertEqual(state[b'mods'][1][b'title'], b'STRATAGEM RESERVE')
        self.assertEqual(state[b'options'][b'stratagem_reserve_enabled'][b'label'], b'Enable Stratagem Reserve (master)')
        self.assertEqual(state[b'options'][b'stratagem_reserve_language'][b'choices'][2], b'ENGLISH')
        self.assertTrue(all(value[b'description'] == descriptions[key] for key, value in state[b'options'].items()))
        for _ in range(121): g.tick()
        self.assertTrue(all(len(value) == 1 for value in state[b'callbacks'].values()))
        h = self.game(cfg=g.cfg.read_text(encoding='utf8')); h.tick()
        self.assertEqual(h.state[b'config'][b'language'], b'en')
        self.assertEqual(h.state[b'config'][b'blue_max_charges'], 6)
        mom[b'set_pending'](b'stratagem_reserve_language', 1); mom[b'apply_pending']()
        mom[b'translation'][b'refresh']()
        self.assertEqual(state[b'mods'][1][b'title'], '战备次数储存'.encode())
        PROVIDER_CHECK = {'version': 3, 'source_sha256': hashlib.sha256(source).hexdigest(),
            'scope': 'actual API/options modules; text service and native UI descriptor mocked; no native hook or in-game rendering'}

    def test_hud_charging_keeps_native_ready_state(self):
        g = self.game(); g.tick(); g.tick(20)
        self.assertIn((g.row + 0x2028, "储备补充 00:50".encode()), g.texts)
        self.assertEqual(struct.unpack("<I", g.mem.read(g.row + 0x3758, 4))[0], 1)

    def test_three_groups_have_independent_caps(self):
        g = self.game(); g.add_target(121, 1); g.add_target(4, 2); g.tick()
        g.apply('blue_max_charges', 2); g.apply('green_max_charges', 4); g.apply('red_max_charges', 5)
        g.tick(1000)
        self.assertEqual([g.field(4, slot=i) for i in range(3)], [2, 4, 5])
        g.apply('green_max_charges', 1); g.tick()
        self.assertEqual([g.field(4, slot=i) for i in range(3)], [2, 1, 5])

    def test_exponential_refill_stages_and_long_frame_surplus(self):
        g = self.game(cfg='blue_max_charges=5\nblue_cd_growth=2\n'); g.tick()
        g.tick(70); self.assertEqual((g.display()[b'count'], g.display()[b'cycle']), (2, 140))
        g.tick(140 + 30)
        self.assertEqual((g.display()[b'count'], g.display()[b'cycle'], g.display()[b'progress']), (3, 280, 30))
        g.tick(250 + 560)
        self.assertEqual(g.display()[b'count'], 5); self.assertEqual(g.display()[b'progress'], 0)

    def test_three_groups_have_independent_growth_and_default_first_stage(self):
        g = self.game(); g.add_target(121, 1); g.add_target(4, 2); g.tick()
        for group, value in [('red', 1.5), ('green', 2), ('blue', 1)]:
            self.assertTrue(g.apply(group + '_cd_growth', value)[0])
        g.tick(90)
        slots = g.state[b'model'][b'slots']
        self.assertEqual(g.display()[b'cycle'], 70)
        self.assertEqual(slots[b'TurretMachinegunGPMG'][b'cycle'], 180)
        self.assertEqual(slots[b'OrbitalGatlingBarrage'][b'cycle'], 105)
        self.assertEqual([g.field(4, slot=i) for i in range(3)], [2, 2, 2])

    def test_call_inherits_seconds_and_completes_only_after_short_cooldown(self):
        g = self.game(cfg='blue_max_charges=4\nblue_cd_growth=2\n'); g.tick(); g.tick(140)
        self.assertEqual((g.display()[b'progress'], g.display()[b'cycle']), (70, 140))
        g.call(dt=0)
        self.assertEqual((g.display()[b'count'], g.display()[b'progress'], g.display()[b'cycle']), (1, 70, 70))
        self.assertEqual(g.field(0x18, 'Q') - g.field(0x20, 'Q'), 5_000_000)
        g.tick(7.5); self.assertEqual(g.display()[b'count'], 1)
        g.tick(0.5); self.assertEqual((g.display()[b'count'], g.display()[b'progress']), (2, 0))

    def test_call_inherits_ratio_and_pauses_the_converted_progress(self):
        g = self.game(cfg='blue_max_charges=4\nblue_cd_growth=2\ninherit_ratio=1\n'); g.tick(); g.tick(140)
        g.call(dt=0)
        self.assertEqual((g.display()[b'count'], g.display()[b'progress'], g.display()[b'cycle']), (1, 35, 70))
        g.tick(8); self.assertEqual(g.display()[b'progress'], 35)
        g.tick(35); self.assertEqual((g.display()[b'count'], g.display()[b'progress']), (2, 0))

    def test_shared_inheritance_switch_controls_every_group(self):
        for group, type_id in [('blue', 147), ('green', 121), ('red', 4)]:
            for ratio, fraction in [(False, 1), (True, 0.5)]:
                with self.subTest(group=group, ratio=ratio):
                    g = self.game()
                    slot = 0 if type_id == 147 else 1
                    if slot: g.add_target(type_id)
                    g.tick(); g.apply(group + '_cd_growth', 2); g.apply('inherit_ratio', ratio)
                    cycle = REFERENCE_TARGETS[type_id]['timings'][-1]
                    g.tick(cycle * 1.5)
                    key = REFERENCE_TARGETS[type_id]['key'].encode()
                    state = g.state[b'model'][b'slots'][key]
                    before = state[b'progress']; g.call(dt=0, slot=slot)
                    self.assertAlmostEqual(state[b'progress'], before * fraction)
                    self.assertEqual(state[b'cycle'], cycle)

    def test_growth_change_inherits_ratio_or_seconds_without_retroactive_shortening(self):
        for ratio, expected in [(False, 100), (True, 50)]:
            with self.subTest(ratio=ratio):
                g = self.game(cfg='blue_max_charges=4\nblue_cd_growth=2\n'); g.tick(); g.tick(170)
                g.apply('inherit_ratio', ratio); g.apply('blue_cd_growth', 1); g.tick()
                if ratio:
                    self.assertEqual((g.display()[b'count'], g.display()[b'progress']), (2, expected))
                else:
                    self.assertEqual((g.display()[b'count'], g.display()[b'progress']), (3, expected - 70))

    def test_native_upgrade_cycle_changes_use_selected_inheritance(self):
        for ratio, expected in [(False, 20), (True, 10)]:
            with self.subTest(ratio=ratio):
                g = self.game(); g.tick(); g.tick(20); g.apply('inherit_ratio', ratio)
                g.cooldown = 35; g.tick()
                self.assertEqual(g.display()[b'cycle'], 35); self.assertEqual(g.display()[b'progress'], expected)

    def test_multiplier_does_not_extend_full_cooldown_and_pause_keeps_progress(self):
        g = self.game(cfg='blue_cd_growth=3\n'); g.tick(); g.tick(70); g.tick(25)
        g.mem.put(g.hud + 0x24e340 + 0x59, b'\1'); g.tick(500)
        self.assertEqual(g.display()[b'progress'], 25)
        g.mem.put(g.hud + 0x24e340 + 0x59, b'\0'); g.call(dt=0)
        self.assertEqual(g.display()[b'progress'], 25)
        g.tick(8); g.call(dt=0)
        self.assertEqual(g.display()[b'count'], 0)
        self.assertEqual(g.field(0x18, 'Q') - g.field(0x20, 'Q'), 70_000_000)

    def test_orbital_group_disable_leaves_blue_and_green_running(self):
        g = self.game(); g.add_target(121, 1); g.add_target(4, 2); g.tick(); g.tick(140); g.call(slot=2)
        g.apply('red_enabled', False)
        self.assertEqual(g.field(4, slot=2), 0xffffffff)
        self.assertEqual(g.field(0x18, 'Q', 2) - g.field(0x20, 'Q', 2), 70_000_000)
        g.tick(); self.assertEqual([g.field(4, slot=i) for i in (0, 1)], [3, 2])

    def test_laser_retains_three_total_dispatches_and_cannot_recharge_after_exhaustion(self):
        g = self.game(cfg='red_max_charges=10\n'); g.add_target(107); g.tick(); g.tick(600)
        laser = g.state[b'model'][b'slots'][b'OrbitalLaser']
        self.assertEqual((laser[b'count'], laser[b'budget']), (3, 3))
        calls = g.calls
        for _ in range(3): g.call(slot=1); g.tick(8)
        self.assertEqual((laser[b'count'], laser[b'budget'], g.field(4, slot=1)), (0, 0, 0))
        g.tick(100000); g.call(slot=1)
        self.assertEqual(g.calls - calls, 3); self.assertFalse(laser[b'display'][b'charging'])
        g.apply('red_enabled', False); g.apply('red_enabled', True); g.tick(1000); g.call(slot=1)
        self.assertEqual(g.field(4, slot=1), 0); self.assertEqual(g.calls - calls, 3)

    def test_laser_attached_after_prior_calls_respects_remaining_allowance(self):
        g = self.game(); address = g.add_target(107); g.mem.put(address + 4, U(1)); g.tick(); g.tick(2000)
        laser = g.state[b'model'][b'slots'][b'OrbitalLaser']
        self.assertEqual((laser[b'count'], laser[b'budget']), (1, 1))
        g.call(slot=1); g.tick(2000)
        self.assertEqual(g.field(4, slot=1), 0); self.assertEqual(laser[b'count'], 0)

    def test_laser_disable_after_one_call_restores_two_not_three(self):
        g = self.game(); g.add_target(107); g.tick(); g.tick(300); g.call(slot=1)
        g.apply('red_enabled', False)
        self.assertEqual(g.field(4, slot=1), 2)
        g.apply('red_enabled', True); g.tick(); g.tick(1000)
        laser = g.state[b'model'][b'slots'][b'OrbitalLaser']
        self.assertEqual((laser[b'count'], laser[b'budget']), (2, 2))

    def test_laser_shutdown_or_snapshot_failure_preserves_unprocessed_native_dispatch(self):
        for failure in (False, True):
            with self.subTest(snapshot_failure=failure):
                g = self.game(); address = g.add_target(107); g.tick()
                g.pending_call = True; g.pending_slot = 1; g.frame(0.1)
                if failure:
                    g.mem.put(0x70000000 + 107 * 0x1000 + 0x300, bytes(8)); g.tick()
                    self.assertEqual(g.state[b'phase'], b'stopped')
                else: g.apply('red_enabled', False)
                self.assertEqual(g.mem.read(address + 4, 4), U(2))

    def test_laser_short_deadline_write_failure_does_not_refund_dispatch(self):
        g = self.game(cfg='blue_enabled=0\n'); g.add_target(107); g.tick(); g.tick(300)
        g.mem.fail_next = True; g.mem.partial = True; g.call(slot=1)
        self.assertEqual(g.state[b'phase'], b'stopped'); self.assertEqual(g.field(4, slot=1), 2)
        self.assertEqual(g.field(0x18, 'Q', 1) - g.field(0x20, 'Q', 1), 300_000_000)

    def test_config_roundtrip_and_legacy_caps_prefer_explicit_group_values(self):
        g = self.game(cfg='blue_max_charges=2\nmax_charges=6\ngreen_max_charges=4\n')
        g.tick(); config = g.state[b'config']
        self.assertEqual([config[(c + '_max_charges').encode()] for c in ('red','green','blue')], [3,4,2])
        g.apply('red_cd_growth', 1.7); g.apply('green_cd_growth', 1.3); g.apply('blue_cd_growth', 2.1)
        g.apply('inherit_ratio', True)
        text = g.cfg.read_text(encoding='utf8'); self.assertNotIn('\nmax_charges=', text)
        h = self.game(cfg=text); h.tick(); config = h.state[b'config']
        self.assertEqual([config[(c + '_cd_growth').encode()] for c in ('red','green','blue')], [1.7,1.3,2.1])
        self.assertTrue(config[b'inherit_ratio'])

    def test_malformed_new_config_disables_feature(self):
        for cfg in ('red_cd_growth=nan\n', 'green_max_charges=0\n', 'blue_cd_growth=1.25\n', 'inherit_ratio=2\n'):
            with self.subTest(cfg=cfg):
                g = self.game(cfg=cfg); g.tick(); self.assertEqual(g.state[b'phase'], b'disabled')
                self.assertEqual(g.mem.writes, [])

    def test_hud_at_cap_restores_original_status_text(self):
        g = self.game(); g.tick(); g.tick(140)
        self.assertEqual(g.mem.read(g.row + 0x2028 + 0x11c, 6), b"READY\0")

    def test_wrong_hud_target_is_not_painted(self):
        g = self.game(); g.mem.put(g.row + 0x374c, U(146)); g.tick()
        self.assertEqual(g.texts, [])

    def test_counter_uses_native_layout_and_keeps_template(self):
        g = self.game(); g.tick(); g.tick(70)
        self.assertEqual(g.rendered_counts[-1], 2)
        self.assertGreater(g.badge_width, 0)
        self.assertFalse(any(p == g.card + 0xce0 for p, _ in g.texts))

    def test_zero_badge_restores_ui_cache_and_never_changes_gameplay_sentinel(self):
        g = self.game(); g.tick(); g.call()
        self.assertEqual(g.rendered_counts[-1], 0)
        self.assertEqual(struct.unpack('<I', g.mem.read(g.card + 0x14bc, 4))[0], 1)
        self.assertEqual(g.field(4), 1)

    def test_double_digit_counter_runs_native_badge_sizing(self):
        g = self.game(cfg='max_charges=10\n'); g.tick(); g.tick(630)
        self.assertEqual(g.rendered_counts[-1], 10)
        self.assertEqual(g.badge_width, 28)

    def test_native_count_renderer_error_restores_ui_cache(self):
        g = self.game(); g.tick(); g.fail_draw = True; g.call()
        self.assertEqual(g.state[b'phase'], b'stopped')
        self.assertEqual(struct.unpack('<I', g.mem.read(g.card + 0x14bc, 4))[0], 1)

    def test_package_contains_only_one_addon(self):
        b = archive(SOURCE); nt, nf = struct.unpack_from("<II", b, 4)
        self.assertEqual((nt, nf), (1, 1)); self.assertEqual(murmur64(b"mods/stratagem_reserve/core"), murmur64(RESOURCE.encode()))
        row = struct.unpack_from("<7Q6I", b, 72 + nt * 32)
        self.assertEqual(b[row[2] + 8:row[2] + row[7]], SOURCE)
        self.assertTrue(SOURCE.startswith(b"-- HD2-Addon: mods/stratagem_reserve/core\n"))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    report = {"status": "OFFLINE_PASSED", "test_cases": result.testsRun,
              "source_sha256": hashlib.sha256(SOURCE).hexdigest(),
              "engine": "LuaJIT 2.1 via lupa 2.8", "supported_steam_build": 25480438,
              "ingame_tested": False, "multiplayer_tested": False,
              "native_memory": "simulated", "native_dispatch": "simulated", "hud_rendering": "not tested",
              "short_cooldown_anchor": "native arrival endpoint; deployment duration preserved",
              "defaults": {"language": "zh", "enabled": True, "red_enabled": True, "green_enabled": True, "blue_enabled": True,
                           "red_max_charges": 3, "green_max_charges": 3, "blue_max_charges": 3,
                           "red_cd_growth": 1, "green_cd_growth": 1, "blue_cd_growth": 1,
                           "inherit_ratio": False, "short_cooldown": 5},
              "reserve_cycle_formula": "native_effective_cd * group_cd_growth ** max(0, stored_count - 1)",
              "orbital_laser_mission_limit": 3,
              "target_counts": {"red": 13, "green": 18, "blue": 7},
              "menu_descriptions": "Chinese and English in either selected language",
              "real_menu_provider": PROVIDER_CHECK, "skipped_tests": len(result.skipped)}
    (ROOT / "validation/offline.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
