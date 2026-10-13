# 战备次数储存 / Stratagem Reserve

为《HELLDIVERS 2》的轨道战备、防御设施和一次性装备增加可积累的呼叫次数。战备就绪后继续补充储备，有剩余次数时可在短冷却结束后再次呼叫，参数可在游戏内 **MODS** 菜单调整。

[下载 v0.3.2 安装包](https://github.com/abaabaaba234/stratagem-reserve/releases/tag/v0.3.2) · [全部 Releases](https://github.com/abaabaaba234/stratagem-reserve/releases)

v0.3.2 新增默认中文的 `Language` 选择，可切换本模组的标题与标签；所有菜单介绍在两种语言下始终同时显示中文和英文。储备、伤害、升级、冷却和原生额度规则沿用 v0.3.1。

## 前置与支持版本

- **Bingus Shared Loader v18 / API 1**。
- **ModOptionsMenu API 1，version 2 或更新版本**，用于游戏内设置。
- Steam build **25480438** / 游戏 EXE **1.8.46015.0**。游戏更新后需要重新核对数据与代码特征。

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

1. 关闭游戏，从 Release 下载 `StratagemReserve_v0.3.2.zip`。
2. 将 ZIP 导入 Arsenal 或 HD2MM，安装并启用上述前置和本模组。升级时替换旧模组条目。
3. 按前置说明调整加载顺序。Arsenal 默认优先级下，Bingus Shared Loader 应位于列表底部；启用首项优先时则放在顶部。
4. 执行 **Purge → Deploy**，重新启动游戏。不要同时使用两个管理器部署。
5. 打开 Esc 菜单的 **MODS** 页面，找到“战备次数储存 / Stratagem Reserve”。

配置与日志位于：

```text
%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\StratagemReserve.cfg
%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\StratagemReserve.log
```

如果没有生效，先检查日志中的版本、目标附加记录与停止原因。版本、战备定义或代码特征不匹配时，模组会停止处理；其他模组修改同一冷却或次数字段也可能触发保护。

## 验证范围

v0.3.2 的 **86 项离线测试通过**，在原有 78 项测试的基础上增加菜单语言、双语介绍、旧配置迁移与真实菜单 API 注册/应用/刷新检查。具体范围见 [离线报告](validation/offline.json)。原生适配与目标定义保留，参考记录含 38 个目标定义和 12 处原生代码特征。

EAT-17 的次数积累、消耗、短冷却与完整冷却已有实机日志；次数显示和 v0.3.1 菜单文字已收到用户正常显示的反馈。尚未完成全部战备、增长倍率与联机场景的全面实机验证。

[离线报告](validation/offline.json) 使用模拟的原生内存和调用过程，`ingame_tested` / `multiplayer_tested` 为 `false`，不能用它证明所有游戏内或联机效果。模组仅处理本机玩家的战备记录。

## 开发与打包

需要 Python 3.10 或更新版本及 [requirements-dev.txt](requirements-dev.txt) 中的依赖。在仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tests\test_runtime.py
.\.venv\Scripts\python.exe tools\build.py
```

输出为 `dist/StratagemReserve_v0.3.2.zip`。构建会运行测试并检查当前源码与验证记录；Release ZIP 包含补丁、管理器清单和两份验证报告。

新增目标需修改 `src/targets.lua` 并核对原生身份与次数语义。更新原生适配器或目标定义后，使用 `tools/verify_reference.py --code <代码捕获路径> --stratagems <参考JSON路径>` 重新生成参考验证记录。仓库中的数据身份与代码特征来自保留的 build 25480438 历史只读捕获；重新验证需要自行提供对应参考文件。

## English

Adds stored calls to supported orbital, defensive and expendable-equipment stratagems in HELLDIVERS 2. A ready stratagem continues accumulating charges; when charges remain after a call, it becomes usable again after a configurable short cooldown. This changes gameplay and the pace of stratagem use.

[Download the v0.3.2 installation ZIP](https://github.com/abaabaaba234/stratagem-reserve/releases/tag/v0.3.2). GitHub's automatic source archives require a local build and are not installation packages.

### Changes in v0.3.2

Adds a persistent `Language` choice in the first MODS row, defaulting to Chinese. It changes this mod's title and labels. Every option description shows Chinese and English together in either language. Existing setting IDs, gameplay parameters, damage, upgrades and native-use limits are preserved.

### Requirements

- Bingus Shared Loader v18 / API 1.
- The in-game MODS menu additionally requires ModOptionsMenu API 1 / version 2 or newer.
- Steam build **25480438** / game EXE **1.8.46015.0**. Other builds have not been verified; game updates require checking the native data and code signatures again.

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

1. Close the game and import `StratagemReserve_v0.3.2.zip` into Arsenal or HD2MM, replacing the old entry. Use one manager.
2. Install and enable the loader, menu and this mod.
3. Follow loader priority guidance: put Bingus Shared Loader at the bottom with Arsenal's default priority, or at the top with first-mod priority enabled.
4. Run **Purge → Deploy**, restart the game, then open **Esc → MODS → Stratagem Reserve**.
5. To uninstall, close the game, remove or disable the mod in the manager, and Purge → Deploy again.

Settings and logs:

```text
%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\StratagemReserve.cfg
%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\StratagemReserve.log
```

Unsupported versions, mismatched stratagem definitions or unexpected code signatures stop processing and log the reason. Mods that alter the same charge or cooldown fields may also trigger ownership protections.

### Validation limits

All **86 offline checks pass** for v0.3.2, retaining the original 78 checks and adding language, bilingual-description, configuration-migration and actual menu-API checks. See [validation/offline.json](validation/offline.json) for coverage. Native adapter and target sources are unchanged; reference evidence covers 38 definitions and 12 code signatures.

Earlier EAT-17 charge accumulation, consumption and cooldown behavior had gameplay logs; users also confirmed v0.3.1 HUD/menu text. This release's new native UI rendering and gameplay have not been tested in-game. Full target coverage, growth settings, multiplayer and anti-cheat compatibility remain unverified. Offline checks use simulated memory/calls and do not establish those behaviors. The mod processes the local player's stratagem records.

Build with Python 3.10+ and [requirements-dev.txt](requirements-dev.txt): run `python tests/test_runtime.py`, then `python tools/build.py`. The build validates source/report hashes and produces `dist/StratagemReserve_v0.3.2.zip` with a loader-discoverable Lua patch, manager manifest and two validation reports. Native-reference regeneration requires supplying the corresponding historical build-25480438 capture and stratagem JSON to `tools/verify_reference.py`.
