# WPT Pad Designer 项目状态审计

> 审计日期：2026-11-26  
> 代码基线：`02962ff` + 本轮 Icepak 修复、页面文案与状态审计（已提交为 `7fb92fa`）  
> 判定口径：只有在本机 AEDT 2025 R2 端到端跑过，且有产物、日志或回归结果的项，才算“已验证”；静态检查、单次运行和“代码已写”都不算签核。

## 0. 一句话结论

核心设计流程、2D/3D Maxwell、PDF 报告、仿真锁/中止/清理、候选搜索和开源发布已经完成并有实测证据。**尚未完成**的是：完整热签核（Icepak 目前只跑通单侧半模型筛查）、DDQ/BP/多线圈 3D、页面内 3D 参数扫描、拼块磁板 3D 拼缝、样机实测和 4K 目视复核。

当前项目应定位为：**设计初选 + 2D/3D 电磁校核 + 单侧热筛查的开源工具**，不是“全工况签核 / 量产批准”工具。

## 1. 完成并验证（有端到端证据）

| 模块 | 状态 | 证据 |
|---|---|---|
| 主页面与视图 | ✅ | 立体/正视/侧视/顶视、缩放/旋转/平移/复位、专注模式、层序标注、控制台 0 error |
| 功率范围 | ✅ | 滑块与数字框 10–10000 W、步进 10 W；10/100/500/1k/3k/10k 六点采样无 NaN |
| 3 kW 失败原因 | ✅ | 判为母线/电池电压边界不可实现，不是 Litz 选型失败；PDF 与页面均给出明确原因 |
| 1250×0.1 mm Litz | ✅ | 3 kW 工况可选并完成窗口/电流密度校核 |
| TX/RX 四种模式 | ✅ | TX only / RX only / combined / compare；单侧隐藏 Z 间隙、总高、TX→RX 箭头、间隙/偏心箭头和 RX 板 |
| 连续平面螺旋 3D | ✅ | 圆形/方形/矩形均为连续螺旋多段线，不是同心圆；引线、端帽、锥度无断口 |
| 安装复选框 | ✅ | 4/6/7/8/9 节标题左侧“安装”；取消后层隐藏、`ins=0`/`tim=0`、标注消失 |
| 磁板形态 7.1/7.2/7.3 | ✅ | 材料 / 整装-拼装 / 圆形-方形 / 厚度 / 外形自动-手动；整装隐藏 7.3；磁板形状独立于线圈；headless Edge 交互验证通过 |
| 磁板形状 3D | ✅ | 圆线圈 Ø250 + 300×300 方板：单侧 TX 237 s / L 51.59 µH；组合 443 s / L 73.63、M 54.56、k 0.741；矩形 400×300 + Ø560 圆板：单侧 TX 271 s / L 105.62 µH |
| 小线圈实测反推 | ✅ | 线圈1/2 DCR 反推约 130×0.1 / 160×0.1 mm；页面解析 L 分别高估 21.8% / 25.7%；详见 `COIL_MEASURED_ANALYSIS.md` |
| 方形磁板 R 角 | ✅ | 7.2 支持 0–宽度/2，自动同步铝板/绝缘/导热/外壳/2D/3D；AEDT 竖边倒圆，R20 3D 求解通过 |
| 小线圈 3D 自感 | ✅ | 线圈1 无磁板 30.94 µH（−1.4%）；线圈2 含约 180 mm×2 引线 ≈32.5 µH（−2.3%）；详见分析文档 |
| 3D 视图自动适配 | ✅ | 按当前视角投影 AABB 填满画布，排除边界框；旋转/缩放/改窗口自动重算 |
| 右侧 8.2 自建样品 | ✅ | 线圈1/2 实测 Ls、DCR、Q、3D 偏差表已加入右侧 08 |
| 右侧 09 多视角图 | ✅ | 3D 自动导出等轴测/正视/侧视/顶视 B 云图；温度 PNG 支持导入 |
| 闪电电流特效 | ✅ | TX/RX 间多股环形闪电，随 3D 模型旋转；旧三条波浪线已隐藏 |
| 标题层级与左栏分组 | ✅ | 一级绿色徽标、二级 `7.1` 纯文本；左栏“系统设置(1–3)/项目执行顺序(4–10)” |
| 默认折叠与备注 | ✅ | 所有节/备注/ANSYS 子任务默认折叠；备注 18×18 切换按钮 |
| 候选搜索漏斗 | ✅ | 功率带+范围 → 粗筛约 10–20 → 精修约 5；实测 320 组/14 显示 → 18 组/17 通过/5 显示 |
| 方案搜索锁定 | ✅ | `1.3 方案搜索` 启用后锁定 76 个控件，关闭恢复；控制台 0 error |
| 2D Maxwell | ✅ | 严格网格审计 `AGV-3kW-A_20261123_091206`：L 44.48 µH / M 30.37 µH / k 0.6829；Cu 14.239 W、Al 4.914 W、Bmax 106.57 mT；144.4 s |
| 2D worker 子进程 | ✅ | `AGV-3kW-A_20261123_093810` 数值与旧路径一致；196.2 s；56 文件 + 63.9 MB ZIP；4 张图 0 损坏；无残留进程 |
| 3D 组合 TX+RX | ✅ | `j3d_090020_1` / `3d_circ_090026`：380.9 s；L 42.92 µH / M 31.00 µH / k 0.7221；4 张场图；自动适配全模型 |
| 3D 单侧 TX | ✅ | `j3d_100733_4` / `3d_circ_100734`：173.6 s；L 32.92 µH；M/k 为 null |
| 3D 单侧 RX | ✅ | `j3d_101624_5` / `3d_circ_101625`：175.4 s；L 33.13 µH；M/k 为 null；图像为居中 RX 板 |
| 3D 回归 | ✅ | `wpt_3d_regression.py --check` 圆形/DD/方形/矩形 4 组全部通过 |
| 2D 回归 | ✅ | `wpt_regression.py` 16 项对比全部通过（解析 vs FEM 存档包络） |
| 仿真锁定 | ✅ | 2D/3D 均验证：`simLockOn=true`、124 控件 disabled、`.side[inert]`、仅“停止仿真”可用；解锁恢复 11 个常禁控件 |
| 2D 中止 | ✅ | `/solve/cancel` 0.19 s 返回 `killed=true`；worker+AEDT 消失；`/health` 约 0.2 s 恢复；UI 显示“已中止” |
| 3D 中止/关页/看门狗 | ✅ | `j3d_100326_1`（中止）、`j3d_100425_2`（beacon 关页）、`j3d_100613_3`（看门狗）均清理干净 |
| 关页自动清理 | ✅ | 2D 求解中关标签页，worker+AEDT 约 1 s 消失；`curl --max-time 10` 断开时 2–3 s 自动终止 |
| 无假阳性 | ✅ | 完整 2D 求解 42.4 s 正常返回 L 75.63 / M 54.12 / k 0.7157，未误判为断开 |
| PDF 双 2D+3D | ✅ | 240 KB；封面/摘要/参数/2D 表/3D 表/附A 4 图/附B 4 图；8 个产物 URL 均 200；A4 14 页、3 个分页、无空白页 |
| PDF 仅 2D | ✅ | 231 KB；附A 正常；附B 明确“未执行 Maxwell 3D，无 3D 原始图”；无 3D 表 |
| PDF 打开方式 | ✅ | `window.open(blobURL,'_blank')` 新窗口/标签页；`#reportWrap` 保持隐藏 |
| WebGL 降级 | ✅ | headless Edge `--disable-webgl` 运行验证，显示降级提示，不再白屏 |
| Icepak 求解器 | ✅ | OpenSSL DLL 修复后，最小探针与完整热模型均可求解（本轮新增，详见第 2 节） |
| 开源发布 | ✅ | GitHub `yzs00700/wpt-pad-designer`、Gitee `hello-yong/wpt-pad-designer`，public，MIT |
| 双远端同步 | ✅ | `sync.ps1` 实测 pull → commit → push GitHub + Gitee，exit 0 |

### 1.1 关键数值基线

| 项目 | 数值 |
|---|---|
| 2D 严格网格（3 kW / 85 kHz / 30 mm / Ø250） | L 44.48 µH、M 30.37 µH、k 0.6829 |
| 3D 组合 TX+RX | L 42.92 µH、M 31.00 µH、k 0.7221 |
| 3D 单侧 TX / RX | L 32.92 / 33.13 µH；M/k 为空 |
| 2D vs 3D | L +3.6%、M −2.0%、k −5.4%（轴对称近似已知偏差方向） |
| Icepak 单侧低/高损耗 | 33.5 / 35.7 °C（半模型损耗，非签核） |

## 2. 本轮新增：Icepak 热筛查修复（2026-11-26）

### 2.1 根因

1. **求解器启动失败**：早期 `Failed to run solver` 不是许可证拒绝，而是 Fluent/Icepak 引擎缺 OpenSSL DLL。把 `libssl-3-x64.dll` / `libcrypto-3-x64.dll` 从 `...\fluent\ntbin\win64` 复制到 `...\fluent\fluent25.2.0\cortex\win64` 后，最小探针和完整模型都能求解。
2. **温度 1548 °C 的错误**：第一版把 HTC 挂在铝板固体表面。Icepak 将其解释为“固体 ↔ 机柜内空气”的换热；封闭机柜没有热沉，热量出不去，温度一路爬到 1548 °C。最小 1 W 铝块试验同样得到 1701–4727 °C，确认是边界类型问题。
3. **正确边界**：HTC 必须挂在**机柜（Region）外表面**，代表铝板/散热筋向环境散热；铝板与机柜底面之间保留 2 mm 薄空气隙，避免完全重合被当成绝热接触。最小模型 1 W / 10 W/m²K / 40×40 mm 底面得到 **87.7 °C**，与解析 87.5 °C 一致。

### 2.2 全模型结果

模型：TX 单侧；线圈损耗 1.8871 W；铝板取双面总损耗的一半 2.03125 W；磁板取双面总损耗的一半；HTC 28.3 W/m²K（基板 10 × 面积增益 2.83）；环境 25 °C；稳态 TemperatureOnly。

| 工况 | 总损耗 | 线圈最高 | 磁板最高 | 铝板最高 | 合理性 |
|---|---:|---:|---:|---:|---|
| core_low | 5.46 W | 33.51 °C | 33.45 °C | 33.38 °C | ✅ |
| core_high | 6.86 W | 35.66 °C | 35.60 °C | 35.52 °C | ✅ |

产物：`validation_icepak_thermal_low.json`、`validation_icepak_thermal_high.json`；脚本：`wpt_icepak_thermal.py`。

### 2.3 仍不能签核的原因

- 只有 TX 单侧，未含 RX 线圈及其损耗。
- 铝板/磁板取“半模型损耗”，不是完整 TX+RX 工作点。
- 未建外壳、散热筋实体、辐射、温度相关材料（PC95 B-P、铜/铝电阻率随温度变化）。
- 未做网格无关性、收敛敏感性、瞬态和样机温升标定。
- 页面温度主值仍是解析筛查；Icepak 只是独立脚本，尚未接入页面/PDF 的自动取数。

## 3. 已实现但未充分测试 / 有限验证

| 项目 | 现状 | 缺口 |
|---|---|---|
| 4K / 高 DPI 标注 | 布局按 DPR 独立，理论不重叠 | 未在 4K 实机目视复核；只做了常规 DPI |
| PDF 浏览器兼容 | Edge/Chromium headless 打印通过 | Firefox/Safari 未测；打印对话框设置未覆盖所有浏览器 |
| 3D 回归 `--run` | `--check` 4 组通过 | 本轮未重跑 `--run`（单次 1–6 分钟）；数值来自此前端到端运行 |
| 2D 回归 `--rerun` | 默认 `--check` 16 项通过 | 本轮未用 AEDT 重跑 4 组基线 |
| Icepak 重复性 | 低/高各跑 1 次，结果合理 | 未做重复运行、网格无关性、HTC 敏感性扫描 |
| Icepak 取温 | 已改用 `get_temperature_extremum` | 只取体最大值；未导出全场云图/切片，未核对热点位置物理合理性 |
| 单侧 3D 图像 | TX/RX 各 1 次，图像已核对 | 未覆盖所有形状/偏心/倾斜组合 |
| 候选搜索 | 圆形/方形/矩形已跑 | DD/DDQ/BP 的候选与 3D 未闭环 |
| 关页清理 | 2D/3D 均验证 | 极端断网、系统休眠、AEDT 自身崩溃未覆盖 |
| Gitee 同步 | 已实测 | Token 有有效期；过期后 Gitee push 会失败，GitHub 不受影响 |

## 4. 未开发 / 明确缺口

| 优先级 | 项目 | 说明 |
|---|---|---|
| P0 | 完整热签核 | Icepak 扩展到 TX+RX 全模型、外壳/散热筋、辐射、温度相关材料；网格无关性 + 样机标定 |
| P0 | Maxwell → Icepak 损耗映射 | 当前 `wpt_icepak_thermal.py` 使用硬编码损耗，未从 2D/3D 结果自动传递 |
| P1 | DDQ / BP Q 线圈与多线圈 3D | 页面按钮禁用并明确提示；不能用 2D 结果冒充 |
| P1 | 3D 参数扫描 UI | 目前只有单点复核；批量用 `wpt_3d_sweep.py` |
| P1 | 拼块磁板 3D 拼缝 | 3D 磁板按整块建模，L/k 相对实际拼块偏高 |
| P2 | 样机与实测 | 无物理样机、温升、Rac/Q、EMC/ICNIRP 实测 |
| P2 | 4K/高 DPI 目视验收 | 布局理论独立，但未实机确认 |
| P2 | CI/自动化 | 回归是手动脚本；无 GitHub Actions/自动 PDF 回归 |
| P3 | 安装包/一键环境 | 桥接必须用 AEDT CPython 启动；无打包安装器 |
| P3 | 多语言/主题 | 非本轮目标 |

## 5. 发布与同步状态

| 项目 | 状态 |
|---|---|
| GitHub | https://github.com/yzs00700/wpt-pad-designer（public） |
| Gitee | https://gitee.com/hello-yong/wpt-pad-designer（public，默认 `main`） |
| 许可证 | MIT |
| 基线提交 | `02962ff`（35 文件、8 commits，提交前工作区干净） |
| 同步脚本 | `sync.ps1` / `sync.bat`：pull → add/commit → push origin + gitee |
| 认证 | GitHub 用 `gh` keyring；Gitee 用 Windows Credential Manager 中的 `hello-yong` token |
| 风险 | Gitee token 有有效期（约 7 天）；过期后需续期，否则 Gitee push 失败 |

> 本次审计改动（Icepak 修复、页面文案、README、改进方案、状态文档）已提交为 `7fb92fa`，并已同步到 GitHub 与 Gitee；两端 `main` 均为 `7fb92fa`。

## 6. 复现 / 验收命令

```powershell
# 1) 启动桥接（必须用 AEDT CPython）
& 'D:\ANSYS2025R2\ANSYS Inc\v252\AnsysEM\commonfiles\CPython\3_10\winx64\Release\python\python.exe' wpt_bridge.py

# 2) 静态编译检查
& $py -m py_compile wpt_bridge.py wpt_bridge_3d.py wpt_2d_worker.py wpt_3d_worker.py `
  wpt_regression.py wpt_3d_regression.py wpt_icepak_thermal.py

# 3) 2D 回归（默认不启动 AEDT）
& $py wpt_regression.py

# 4) 3D 回归（只读基线）
& $py wpt_3d_regression.py --check

# 5) 3D 真跑（单次 1–6 分钟）
& $py wpt_3d_regression.py --run circular

# 6) Icepak 单侧热筛查（单次约 2 分钟）
& $py wpt_icepak_thermal.py low
& $py wpt_icepak_thermal.py high
```

## 7. 建议下一步

1. **先提交并同步本次审计**：`git add` → commit → `sync.ps1`，确认 GitHub/Gitee 都到新提交。
2. **补 PDF 文案复核**：本次改了 Icepak 文案，重新导出一次双 2D+3D PDF，确认页数、附A/B 和文字。
3. **把 Icepak 接入损耗映射**：从 2D/3D 结果读取 TX/RX 铜损、铝损、磁损，不再硬编码。
4. **扩展 Icepak 到 TX+RX 全模型**：加 RX、外壳、散热筋、辐射；做网格无关性和 HTC 敏感性。
5. **再做 DDQ/BP 多线圈 3D 与 3D 扫描 UI**。
6. **样机阶段**：实测铝板/散热筋/线圈热点、Rac/Q、EMC/ICNIRP，回填模型偏差包络。

---

## 8. 审计勾选表

- [x] 主页面、视图、层序、安装复选框、TX/RX 四模式
- [x] 功率 10 W–10 kW、3 kW 边界原因、1250×0.1 Litz
- [x] 连续平面螺旋 3D、引线/端帽/锥度
- [x] 第 7 节 7.1/7.2/7.3 磁板形态（整装/拼装、圆形/方形、自动/手动外形）
- [x] 方形磁板 R 角 0–宽度/2，页面与 3D 建模同步
- [x] 两组小线圈 Maxwell 3D 自感复核（线圈1 −1.4%，线圈2 含引线 −2.3%）
- [x] 3D 视图自动适配、右侧 8.2 自建样品表、09 多视角图/温度图导入
- [x] TX/RX 3D 闪电电流特效（随模型旋转）
- [x] 圆形线圈+方形磁板、矩形线圈+圆形磁板的 3D 单侧/组合求解
- [x] 两组小线圈 DCR 反推利兹线候选（130×0.1 / 160×0.1）与设计器偏差记录
- [x] 2D 轴对称对方形磁板明确拒绝并提示改用 3D
- [x] 候选搜索漏斗与方案锁定
- [x] 2D Maxwell 端到端 + worker 取消/关页清理
- [x] 3D 组合/单侧 TX/单侧 RX + 自动适配 + 回归
- [x] 仿真锁定、中止、看门狗、无假阳性
- [x] PDF 双 2D+3D / 仅 2D、附A/附B、新窗口
- [x] WebGL 降级
- [x] Icepak 求解器修复 + 单侧半模型 33.5/35.7 °C
- [x] GitHub/Gitee 发布与 `sync.ps1` 双推
- [ ] 完整 Icepak TX+RX/外壳/散热筋/辐射热签核
- [ ] Maxwell → Icepak 损耗自动映射
- [ ] DDQ/BP Q 线圈与多线圈 3D
- [ ] 3D 参数扫描 UI
- [ ] 拼块磁板 3D 拼缝
- [ ] 样机温升 / Rac/Q / EMC 实测
- [ ] 4K 实机目视复核
- [ ] PDF 在 Firefox/Safari 的兼容性
- [ ] CI 自动回归
