# WPT Pad Designer 功能测试报告

> 测试日期：2026-11-27  
> 环境：Windows / Edge headless + AEDT 2025 R2 / Icepak 2025.2  
> 代码：`ac8d97f` + 本次 `side` 修复  
> 口径：只有实际跑通并拿到结果的项才标“通过”；“未复跑”不等于失败。

## 1. 静态检查

| 项目 | 结果 | 证据 |
|---|---|---|
| Python 编译 | ✅ 通过 | `wpt_bridge.py`、`wpt_bridge_3d.py`、2D/3D/thermal worker、回归/扫描脚本全部 `py_compile` |
| 2D 回归（不启动 AEDT） | ✅ 通过 | `wpt_regression.py` 16 项解析 vs 存档 FEM 包络全部通过 |
| 3D 回归（只读基线） | ✅ 通过 | `wpt_3d_regression.py --check` 圆形/DD/方形/矩形 4 组全部通过 |
| 页面 JS 语法/运行 | ✅ 通过 | headless Edge `--dump-dom`，无 `Uncaught/SyntaxError/ReferenceError/TypeError` |

## 2. 页面功能

| 功能 | 结果 | 证据 |
|---|---|---|
| 默认加载 / 主题 / 左栏层级 | ✅ | 页面渲染、`credTag` 动态生成、8.2 表存在 |
| TX / RX 单侧 / 组合 / 对比 | ✅（修复后） | RX 徽标从错误的“TX 单侧”修正为“RX 单侧”；3D 请求 `side=rx/both` 正确 |
| 安装复选框 4/6/7/8/9 | ✅ | 取消 `insOn/timOn/aluOn/shellOn` 后 notes 显示 0.00 mm/未安装；恢复后还原 |
| 7.2 方形 R 角 / 整装-拼装 / 手动外形 | ✅ | R20、100×100、整装；notes 显示“方形 R20.0 mm、整装单块” |
| 5.6 引出线长度 / 出线方式 | ✅ | 130 mm、顶侧出线写入 notes/params |
| 线圈高度 | ✅ | 不再固定 4 mm；默认 3000×0.1 为 7.54 mm；用户 130×0.1 约 1.7 mm |
| 8.2 自建样品标准 | ✅ | 表头 + 2 行实测线圈；推定 130×0.10 mm |
| 候选搜索 | ✅ | 320 组，32 组通过，显示前 15；modal 打开 |
| 保存 / 读取工程 | ✅ | 保存 `TEST-SAVE`、改 OD 后读取恢复 OD 300 |
| PDF 报告内容 | ✅ | `window.open` 拦截后读取 Blob：269,977 字符，含标题/打印按钮；附A/附B 仅在对应数据存在时出现 |
| 3D 视图自动适配 | ✅ | 投影 AABB 填满画布；默认模型明显放大 |
| 闪电电流特效 | ✅ | `WPTView.setFlow(true/false)` 调用无异常；截图可见多股环形闪电 |
| 温度勾选 / 09 温度表 | ✅ | 复选框、`thermalStat/thermalTbl` 存在；后端 `/thermal` 已跑通 |

## 3. 2D / 3D / 温度实测

| 测试 | 结果 | 数值 |
|---|---|---|
| 2D 错误窗口拒绝 | ✅ | 3000×0.1、12 匝、65 mm 窗口：正确拒绝，提示 90.83 > 65.00 mm |
| 2D 快速求解 | ✅ | 1250×0.1：46.2 s，L 73.07 µH / M 51.63 µH / k 0.7066 |
| 3D 单侧 TX | ✅ | 252.7 s，L 50.6 µH（L_raw 51.75），7 张图（model + 6 张 B 云图） |
| 3D 多视角图 | ✅ | 等轴测、正视、侧视、顶视、磁板 0°/90° 全部导出，`errors=[]` |
| 2D 中止 | ✅ | cancel 返回 `killed=true`；worker/AEDT 消失；health 立即空闲 |
| 3D 中止 | ✅ | 3.2 s 进入 cancelled；health 立即空闲 |
| Icepak 最小探针 | ✅ | `RESULT ok=True`，60.1 s |
| Icepak 参数化 worker | ✅ | 线圈2 参数：39 s，最高 77.6 °C，`plausible=true` |
| `/thermal` HTTP 链路 | ✅ | 74.4 s 完成，最高 77.5 °C，health 空闲 |

> 温度模型：单侧半模型；方形磁板在 Icepak 中按等面积圆等效（面积一致，R 角不建）；不是热签核。

## 4. 本轮发现并修复

1. **`side` 丢失**：`compute()` 未返回 `side`，导致 RX 单侧徽标显示 TX、3D 请求永远 `both`。已加入 `side:inp.side`，RX/3D payload 复测通过。
2. **线圈高度固定 4 mm**：已改为 `束径 × 层数 + 0.15 mm`，并加内径反算提示。
3. **方形 Icepak 卡死**：方形叠层在求解器启动阶段卡住；热模型改为等面积圆等效，3D 电磁仍保留真实方板和 R 角。
4. **温度链路阻塞**：重启 Ansys PLE Licensing 服务后恢复；最小探针、worker、`/thermal` 均通过。

## 5. 未在本轮复跑 / 仍需补测

- 3D **组合 TX+RX** 本轮未重跑（此前 `j3d_090020` / `3d_circ_090026` 已通过：L 42.92 / M 31.00 / k 0.7221）；单侧路径本轮已复跑。
- 2D **严格网格审计 + ZIP** 本轮未重跑（此前 `AGV-3kW-A_20261123_093810` 已通过）；本轮跑的是快速 2D。
- 页面“勾选温度 → 3D 完成 → 自动 `/thermal` → 09 表”尚未做完整 UI 端到端；后端 `/thermal` 和页面代码均已跑通。
- PDF 本轮验证的是内容生成；A4 打印页数与附A/B 图片需在改版后再打印确认。
- 4K/高 DPI 目视、Firefox/Safari PDF、DDQ/BP 多线圈 3D、3D 扫描 UI、拼块磁板 3D 拼缝仍未完成。
