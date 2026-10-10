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
BASE = 0x180000000
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
    def __init__(self, cfg=None, loader=True, menu=True, bad_build=False):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.cfg = self.folder / "StratagemReserve.cfg"
        if cfg:
            self.cfg.write_text(cfg, encoding="utf-8")
        self.mem = Memory()
        self.now = 1_000_000
        self.cooldown = 70.0
        self.pending_call = False
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
        self.lua = luajit21.LuaRuntime(encoding=None)
        g = self.lua.globals()
        g[b"pyread"] = lambda p, n: self.mem.read(int(p), int(n))
        g[b"pywrite"] = lambda p, b: self.mem.write(int(p), bytes(b))
        g[b"pyquery"] = lambda p: self.mem.query(int(p))
        g[b"pycd"] = lambda *args: self.cooldown
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
              menu_state={options={},values={},callbacks={},pending={},sets=0}
              local s=menu_state;ModOptionsMenu={api=1,version=3}
              function ModOptionsMenu.register_option(id,spec)
                  assert(not s.options[id]);assert(type(spec.mod)=='string' and #spec.mod<120)
                  if spec.type=='toggle'then assert(type(spec.default)=='boolean')end
                  if spec.type=='slider'then assert(spec.default>=spec.min and spec.default<=spec.max)end
                  s.options[id]=spec;s.values[id]=spec.default;return true
              end
              function ModOptionsMenu.on_change(id,fn)assert(not s.callbacks[id]);s.callbacks[id]=fn;return true end
              function ModOptionsMenu.get(id)return s.values[id]end
              function ModOptionsMenu.set(id,value)s.values[id]=value;s.pending[id]=nil;s.sets=s.sets+1;return true end
              function menu_apply(key,value)local id='stratagem_reserve_'..key;local okay,why=s.callbacks[id](value)
                  if okay then s.values[id]=value end;return okay,why end
            ''')
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

    def field(self, offset, fmt="I"):
        return struct.unpack("<" + fmt, self.mem.read(self.slot + offset, struct.calcsize(fmt)))[0]

    def frame(self, dt):
        if self.native_error:
            self.native_error = False
            raise RuntimeError("original callback error")
        self.now += round(float(dt) * 1_000_000)
        self.mem.put(self.clock + 0x18, Q(self.now))
        if self.pending_call:
            self.pending_call = False
            if self.field(4) != 0 and self.now >= self.field(0x18, "Q"):
                self.calls += 1
                arrival = self.now + 3_000_000
                self.mem.put(self.slot + 0x10, Q(self.now))
                self.mem.put(self.slot + 0x20, Q(arrival))
                self.mem.put(self.slot + 0x18, Q(arrival + round(self.cooldown * 1_000_000)))
                if not self.failure_call and self.field(4) != 0xffffffff:
                    self.mem.put(self.slot + 4, U(self.field(4) - 1))
                self.failure_call = False
        self.mem.put(self.row + 0x3758, U(3 if self.now < self.field(0x20, "Q") else 4 if self.now < self.field(0x18, "Q") else 1))

    def tick(self, dt=0):
        return self.lua.globals()[b"update"](dt, b"preserved")

    def call(self, dt=0.1, fail=False):
        self.pending_call = True
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
        g = self.game(); g.tick(); g.tick(140); g.apply("max_charges", 2); g.tick()
        self.assertEqual(g.field(4), 2); g.apply("max_charges", 8); g.tick(); self.assertEqual(g.field(4), 2)

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
        self.assertEqual(len(list(g.lua.globals()[b"menu_state"][b"callbacks"].keys())), 3)
        g.lua.execute(b"menu_state.pending.stratagem_reserve_max_charges=7")
        for _ in range(121): g.tick()
        self.assertEqual(g.lua.globals()[b"menu_state"][b"pending"][b"stratagem_reserve_max_charges"], 7)

    def test_invalid_menu_values_leave_config_unchanged(self):
        g = self.game(); g.tick()
        for key, value in [("max_charges", 0), ("max_charges", 2.5), ("short_cooldown", 0), ("short_cooldown", 5.25), ("enabled", 1)]:
            self.assertFalse(g.apply(key, value)[0])
        self.assertEqual(g.state[b"config"][b"max_charges"], 3)

    def test_config_persistence(self):
        g = self.game(); g.tick(); g.apply("max_charges", 6); g.apply("short_cooldown", 4.5)
        text = g.cfg.read_text(encoding="utf8"); self.assertIn("max_charges=6", text)
        self.assertIn("short_cooldown=4.5", text)
        h = self.game(cfg=text); h.tick(); self.assertEqual(h.state[b"config"][b"max_charges"], 6)

    def test_invalid_config_disables_feature(self):
        g = self.game(cfg="short_cooldown=nan\n"); g.tick()
        self.assertEqual(g.state[b"phase"], b"disabled"); self.assertEqual(g.mem.writes, [])

    def test_duplicate_load_does_not_add_hooks(self):
        g = self.game(); g.tick(); second = g.lua.execute(SOURCE); self.assertEqual(second[b"version"], b"0.1.1")
        g.tick(); self.assertEqual(g.lua.globals()[b"original_calls"], 2)

    def test_original_errors_propagate_and_next_frame_restores(self):
        g = self.game(); g.tick(); g.tick(70); g.native_error = True
        with self.assertRaises(RuntimeError): g.tick()
        g.tick(); self.assertEqual(g.field(4), 0xffffffff)
        g.tick(); self.assertEqual(g.field(4), 1)

    def test_shutdown_preserves_arguments_and_returns(self):
        g = self.game(); g.tick(); self.assertEqual(g.lua.globals()[b"shutdown"](b"bye"), (b"bye", 99))
        self.assertEqual(g.field(4), 0xffffffff)

    def test_hud_charging_keeps_native_ready_state(self):
        g = self.game(); g.tick(); g.tick(20)
        self.assertIn((g.row + 0x2028, "储备补充 00:50".encode()), g.texts)
        self.assertEqual(struct.unpack("<I", g.mem.read(g.row + 0x3758, 4))[0], 1)

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
              "defaults": {"max_charges": 3, "short_cooldown": 5, "target": "LATOneshot/147"}}
    (ROOT / "validation/offline.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
