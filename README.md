# 战备次数储存 / Stratagem Reserve

为《HELLDIVERS 2》的轨道战备、防御设施和一次性装备增加可积累的呼叫次数。战备就绪后继续补充储备，有剩余次数时可在短冷却结束后再次呼叫，参数可在游戏内 **MODS** 菜单调整。

[下载 v0.3.3 安装包](https://github.com/abaabaaba234/stratagem-reserve/releases/download/v0.3.3/StratagemReserve_v0.3.3.zip) · [更新日志](https://github.com/abaabaaba234/stratagem-reserve/releases/tag/v0.3.3) · [历史 Releases](https://github.com/abaabaaba234/stratagem-reserve/releases)

v0.3.3 修复单战备异常导致全部功能永久停止、菜单注册失败不重试、初始化过早锁死，以及异常日志和清理逐帧重试。游戏版本号不再作为拒绝条件；原生代码、布局和对象身份仍须通过检查，基础冷却允许在合理范围内变化。三组储备规则、双语菜单和原生额度保持原有行为。

2026-10-17，作者确认两个更新均已测试，自己使用暂未发现问题。由于玩家反馈没有具体报错或同局日志，本次只是针对可能原因进行的尝试性修复，不保证完全解决所有人的舰桥卡顿、不加载或偶发失效。已上传 A 网的同一安装包用于本次 GitHub Release；未重新打包。

## 前置与支持版本

- **Bingus Shared Loader v18 / API 1**。
- **ModOptionsMenu API 1，version 2 或更新版本**，用于游戏内设置。
- 参考布局来自 Steam build **25480438** / EXE **1.8.46015.0**。运行时不限定 Steam build、PE 时间戳或固定映像大小；须通过 PE 格式、映像边界、12 处原生代码锚点、记录结构与目标身份检查。RVA 或布局变化仍会安全暂停，不代表已支持任意未来版本。

前置需另外安装并启用。安装包只包含本模组及验证报告。

## 支持范围

| 分组 | 储存范围 | 数据项数量 |
| --- | --- | ---: |
| 红战备 | 轨道打击和轨道火力网，排除飞鹰与任务战备 | 13 |
| 绿战备 | 哨戒炮、地雷、炮台、防御墙、防护罩中继器、特斯拉塔 | 18 |
| 蓝战备 | 下列一次性装备 | 7 |

蓝战备包括：**EAT-17 消耗性反坦克武器、突击兵、荡平者、消耗性凝固汽油弹、单兵导弹发射井、子弹风暴、便携式地狱火背包**。普通可补弹支援武器与其他背包不在储存范围内。

轨道激光保留**每局最多 3 次**的原生限制。储存只调整剩余额度的就绪节奏，不能增加本局总使用额度；用完后不会继续补充。其他战备的准确身份和分组见 [src/targets.lua](src/targets.lua)。上述数量是当前参考数据中的定义数量，实际可选择的战备以游戏为准。

## 次数与冷却

1. 初始就绪时有 1 次。就绪后再完成一个补充周期，增加 1 次，直到该组上限。
2. 右下角显示的是总可用次数；真正进入部署或冷却阶段时，仍需等待该阶段结束才能呼叫。
3. 成功呼叫消耗 1 次。仍有次数时，保留原生部署阶段，再进入设定的短冷却；次数用尽时进入完整原生冷却。
4. 部署和冷却期间暂停补充，保留已有补充进度。补充期间保留原生就绪图标，并显示“储备补充”倒计时；实际冷却期间使用原生不可用状态。
5. 各战备独立计数。同组仅共享设置，不共享储备。

补充周期使用游戏原生的有效冷却值，包含舰船升级与任务修正。可为三组分别设置储备增长倍率：

```text
补充周期 = 原生有效冷却 * 增长倍率^(当前储备次数 - 1)
```

例如倍率为 1.5：有 1、2、3 次储备时，下一次补充分别需要原冷却的 1、1.5、2.25 倍。默认 1.0 不增长。增长倍率只影响储备补充，不改变短冷却或次数用尽后的完整冷却。

呼叫减少储备后，补充周期随之缩短。共用的继承开关决定如何保留进度：

- **关闭：按时间继承，默认。** 保留已完成的秒数。
- **开启：按比例继承。** 保留已完成的百分比。

例如已完成 70/140 秒，周期降至 70 秒后：按时间保留 70 秒，按比例保留 35 秒。短冷却期间仍暂停补充；即使继承的时间已足够，也需等到短冷却结束才补充次数。达到上限后不积累隐藏的额外进度。

## MODS 设置

| 设置 | 范围 / 默认值 |
| --- | --- |
| Language（首行） | 简体汉字 / English，默认中文 |
| 模组总开关 | 默认开启 |
| 红、绿、蓝战备分组开关 | 各自独立，默认开启 |
| 各组储存次数上限 | 1–10 次，默认各 3 次 |
| 各组补充冷却增长倍率 | 1.0–3.0，步长 0.1，默认各 1.0 |
| 短冷却时间 | 1–60 秒，步长 0.5，默认 5 秒，三组通用 |
| 按比例继承补充进度 | 默认关闭，三组通用 |

降低上限会裁掉多余次数，提高上限不会直接赠送次数。短冷却设置从下一次成功呼叫生效。关闭某组会恢复该组仍由模组持有的原生字段；再次开启后重新开始储存。轨道激光已使用的额度不会被返还。

从旧版升级时，旧通用上限会迁移至蓝、绿两组；红组默认上限为 3。设置会自动保存。

切换语言后点击应用，关闭并重新打开 Esc 菜单刷新标题和标签。语言只作用于本模组；旧配置缺少语言字段时使用中文，并保留已有设置。两种语言模式下，所有选项介绍都显示中英双语。

## 安装与升级

1. 关闭游戏，使用本地 `dist/StratagemReserve_v0.3.3.zip`。
2. 将 ZIP 导入 Arsenal 或 HD2MM，安装并启用上述前置和本模组。升级时替换旧模组条目。
3. 按前置说明调整加载顺序。Arsenal 默认优先级下，Bingus Shared Loader 应位于列表底部；启用首项优先时则放在顶部。
4. 执行 **Purge → Deploy**，重新启动游戏。不要同时使用两个管理器部署。
5. 打开 Esc 菜单的 **MODS** 页面，找到“战备次数储存 / Stratagem Reserve”。

配置与日志位于：

```text
%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\StratagemReserve.cfg
%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\StratagemReserve.log
```

如果没有生效，先查看日志里的 `enabled`、`paused`、`SUSPENDED` 和 `cleanup_pending`：

- `waiting` 表示等待 Loader／有效任务上下文；`disabled` 表示配置总开关关闭；`partial` 表示部分战备暂停；`suspended` 表示公共原生访问暂不可用。
- 单个战备身份、次数或写入异常只隔离该战备；恢复前核对所有权，不覆盖其他写入者。瞬时异常按 1–30 秒退避重试，定义失败至少间隔 5 秒复查。旧记录未恢复前，不重新接管同一战备。离场后重新发现对象。
- 同类型重复槽位全部跳过，其他战备继续；不选择任意一个，也不共享储备。重复消失后自动重新验证。
- 菜单失败按退避重试，保留已完成的控件与回调注册，避免重复绑定；正常每 120 帧同步一次。
- 配置只修复不合法字段的内存值，合法设置和明确的 `enabled=0` 保留。读取时保留原文件，下一次成功应用设置时保存；日志记录修复字段。
- 待清理字段退避重试，最长间隔 30 秒；记录保留至恢复成功或身份退休。重复日志 30 秒内去重，去重表最多 64 项，文件正常每 5 秒刷新并在退出时关闭。

加载器 API 尚未就绪时，通过现有 update 低频等待；update 不存在时不设置成功标记，允许之后重新执行 addon。保留原 update 的全部参数、尾部 nil 返回值及异常。如果后加载的其他 MOD 直接覆盖 update 并丢弃原调用链，本 MOD 无法自行获得执行机会；需调整该 MOD 或部署顺序。这一外部问题仍需玩家同局日志和实机排查。

## 验证范围

v0.3.3 的 **106 项离线测试通过，无跳过**，覆盖原有玩法、身份／版本元数据边界、单战备隔离与恢复、重复槽位、菜单分步重试、配置字段修复、连续异常日志和清理退避。实际菜单提供者的 API/options 模块已隔离执行，文本服务与原生 UI 仍为模拟。详见 [离线报告](validation/offline.json)。参考记录含 38 个目标定义和 12 处原生代码特征。

EAT-17 的次数积累、消耗、短冷却与完整冷却已有实机日志；次数显示和 v0.3.1 菜单文字已收到用户正常显示的反馈。尚未完成全部战备、增长倍率与联机场景的全面实机验证。

[离线报告](validation/offline.json) 使用模拟的原生内存和调用过程，`ingame_tested` / `multiplayer_tested` 为 `false`，不能用它证明所有游戏内或联机效果。模组仅处理本机玩家的战备记录。

## 开发与打包

需要 Python 3.10 或更新版本及 [requirements-dev.txt](requirements-dev.txt) 中的依赖。在仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools\verify_reference.py --code <历史代码捕获> --stratagems <参考JSON>
# 可选：设置 HD2_MOD_OPTIONS_MENU_SOURCE 为实际菜单 Lua，启用真实提供者隔离检查
.\.venv\Scripts\python.exe tests\test_runtime.py
.\.venv\Scripts\python.exe tools\build.py
```

输出为 `dist/StratagemReserve_v0.3.3.zip`。构建会运行测试并检查当前源码与验证记录；Release ZIP 包含补丁、管理器清单和两份验证报告。

新增目标需修改 `src/targets.lua` 并核对原生身份与次数语义。更新原生适配器或目标定义后，使用 `tools/verify_reference.py --code <代码捕获路径> --stratagems <参考JSON路径>` 重新生成参考验证记录。仓库中的数据身份与代码特征来自保留的 build 25480438 历史只读捕获；重新验证需要自行提供对应参考文件。

## English

Adds stored calls to supported orbital, defensive and expendable-equipment stratagems in HELLDIVERS 2. A ready stratagem continues accumulating charges; when charges remain after a call, it becomes usable again after a configurable short cooldown. This changes gameplay and the pace of stratagem use.

[Download the v0.3.3 installation ZIP](https://github.com/abaabaaba234/stratagem-reserve/releases/download/v0.3.3/StratagemReserve_v0.3.3.zip) · [Release notes](https://github.com/abaabaaba234/stratagem-reserve/releases/tag/v0.3.3). GitHub's automatic source archives require a local build and are not installation packages.

On 2026-10-17 the author confirmed testing both updates without observing problems in their own environment. Reports lacked specific errors or same-session logs, so these are tentative fixes based on possible causes and are NOT guaranteed to fully resolve every user's ship stutter, loading failure or intermittent behavior. This Release uses the exact ZIP uploaded to AyakaMods, without rebuilding it.

### Changes in v0.3.3

Adds per-target fault isolation and automatic retries, resumable menu registration, deferred initialization, bounded logging and cleanup backoff. Game-version metadata no longer rejects a compatible layout, and reasonable base-cooldown changes are accepted. Charge rules, bilingual menus and native mission-use limits retain their previous behavior.

### Requirements

- Bingus Shared Loader v18 / API 1.
- The in-game MODS menu additionally requires ModOptionsMenu API 1 / version 2 or newer.
- Reference layout: Steam build **25480438** / EXE **1.8.46015.0**. Runtime acceptance uses PE format, image bounds, 12 code anchors, record structure and target identity, without a Steam-build, timestamp or exact-image-size allowlist. Changed RVAs/layouts still suspend safely; arbitrary future versions are not verified.

Install the loader and menu separately. This ZIP contains this mod and its validation reports.

### Supported stratagems

| Group | Scope | Reference definitions |
| --- | --- | ---: |
| Red | Orbital strikes and barrages; excludes Eagles and mission stratagems | 13 |
| Green | Sentries, mines, emplacements, barriers, shield relay and Tesla tower | 18 |
| Blue | Seven expendable equipment types listed below | 7 |

Blue equipment includes EAT-17, Commando, Leveller, Expendable Napalm, Solo Silo, Bullet Storm and the Portable Hellbomb backpack. Ordinary reloadable support weapons and other backpacks are excluded. Exact internal identities are recorded in the target source. The counts describe reference definitions; actual availability depends on the game.

Orbital Laser retains its native **three-use limit per mission**. Storage changes when the remaining uses become ready; it never adds to the mission's total allowance. Exact target identities are recorded in [src/targets.lua](src/targets.lua).

### Charges and cooldowns

1. A stratagem initially becomes ready with one charge. Each additional refill cycle adds one until the group's cap.
2. The bottom-right HUD count represents total available calls. Deployment and cooldown stages must still finish before another call.
3. A successful call spends one charge. If any remain, native deployment is followed by the configured short cooldown. An empty reserve uses the full native cooldown.
4. Refill pauses during deployment and cooldown while preserving progress. Refill uses the ready icon and a reserve countdown; actual cooldown uses the native unavailable state.
5. Each stratagem has its own count. Group settings do not create a shared reserve.

Refill uses the native effective cooldown, including ship upgrades and mission modifiers:

```text
refill duration = native effective cooldown * growth^(stored charges - 1)
```

At growth 1.5, storing 1/2/3 charges makes the next refill take 1/1.5/2.25 times the native cooldown. Default growth 1.0 keeps refill duration constant. Growth affects refill only; short cooldown and the full cooldown after exhausting charges retain their separate behavior.

Progress inheritance defaults to elapsed time. Turning on percentage inheritance preserves the completed fraction when the refill duration changes. For example, 70/140 seconds becomes 70 seconds under time inheritance, or 35 seconds under percentage inheritance, when the cycle falls to 70 seconds. Refill still waits until short cooldown ends. A full reserve does not accumulate hidden extra progress.

### MODS settings

| Setting | Range / default |
| --- | --- |
| Language, first row | Chinese / English; Chinese default |
| Master switch | On |
| Red, green and blue switches | Independently on |
| Each group's charge cap | 1–10; default 3 |
| Each group's refill growth | 1.0–3.0 in steps of 0.1; default 1.0 |
| Shared short cooldown | 1–60 seconds in steps of 0.5; default 5 |
| Shared percentage inheritance | Off, preserving elapsed time |

Apply changes in MODS. Close and reopen Esc after changing language to refresh titles and labels. All descriptions remain bilingual; game-wide language and other mods are unaffected. Old configurations without a language field default to Chinese while retaining their existing values.

Lowering a cap trims excess charges; increasing it grants no free charges. A changed short cooldown applies to the next successful call. Disabling a group restores native fields still owned by this mod; re-enabling restarts storage. Used Orbital Laser allowance is never refunded. A legacy shared cap migrates to green and blue; red defaults to three.

### Installation and troubleshooting

1. Close the game and import `StratagemReserve_v0.3.3.zip` into Arsenal or HD2MM, replacing the old entry. Use one manager.
2. Install and enable the loader, menu and this mod.
3. Follow loader priority guidance: put Bingus Shared Loader at the bottom with Arsenal's default priority, or at the top with first-mod priority enabled.
4. Run **Purge → Deploy**, restart the game, then open **Esc → MODS → Stratagem Reserve**.
5. To uninstall, close the game, remove or disable the mod in the manager, and Purge → Deploy again.

Settings and logs:

```text
%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\StratagemReserve.cfg
%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\StratagemReserve.log
```

Check `enabled`, `paused`, `SUSPENDED` and `cleanup_pending` in the log. Status is `waiting` for dependencies/mission context, `disabled` for an explicit master-off setting, `partial` for isolated target faults, or `suspended` for a shared native-access failure.

A target failure pauses only that target, restores owned changes and retries with 1–30 second backoff; invalid definitions are rechecked no faster than every 5 seconds. All duplicate slots of a type are skipped until unambiguous. Pending restoration prevents reattachment to the same target; other targets continue. External values are never blindly restored over.

Menu retries retain completed registrations and callbacks; normal synchronization runs every 120 frames. Invalid configuration fields use defaults individually while valid settings, including `enabled=0`, remain intact. Loading preserves the original file; the next successful settings apply saves it. Repeated logs are deduplicated for 30 seconds with at most 64 entries, normal file flushes occur every 5 seconds, and unresolved cleanup retries at intervals up to 30 seconds without discarding ownership records.

Late Loader availability is retried through the existing update. Missing update leaves no success marker, allowing a later addon retry. Original callback arguments, trailing nil results and errors are preserved. Another MOD that overwrites global update without chaining it still prevents this mod from running; fix that MOD or deployment order and collect same-session logs for diagnosis.

### Validation limits

All **106 offline checks pass with no skips** for v0.3.3, covering existing gameplay, compatibility metadata, isolation/recovery, duplicates, partial menu registration, configuration repair, persistent callback errors and cleanup backoff. Actual API/options modules from the deployed menu provider were executed with mocked text/native UI services. See [validation/offline.json](validation/offline.json). Reference evidence covers 38 definitions and 12 code signatures.

Earlier EAT-17 charge accumulation, consumption and cooldown behavior had gameplay logs; users also confirmed v0.3.1 HUD/menu text. The author reports successful local gameplay testing of v0.3.3 on 2026-10-17. Ship-frame performance was not measured. Full target coverage, growth settings, multiplayer and anti-cheat compatibility remain unverified. Offline checks use simulated memory/calls; their recorded flags describe that offline run, separately from the later user report. The mod processes the local player's stratagem records.

Build with Python 3.10+ and [requirements-dev.txt](requirements-dev.txt): run `python tests/test_runtime.py`, then `python tools/build.py`. The build validates source/report hashes and produces `dist/StratagemReserve_v0.3.3.zip` with a loader-discoverable Lua patch, manager manifest and two validation reports. Native-reference regeneration requires supplying the corresponding historical build-25480438 capture and stratagem JSON to `tools/verify_reference.py`.
