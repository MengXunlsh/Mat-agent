# 通用研究示例

[English](README.md) · 简体中文

[程序首页](../../README.zh-CN.md) · [功能与使用说明](../../docs/usage-guide.zh-CN.md)

本目录是合成软件示例。将需要的输入复制到一个独立研究项目，再在 mat-agent 中打开该项目；分析输出保存到用户项目。以下数据用于熟悉流程和核对数值，不是纳米酶实验测量。

## 单组初始速率拟合

输入：[synthetic-initial-rates.csv](synthetic-initial-rates.csv)。数据由 v = 2.4S/(0.3+S) 生成，无附加噪声。

| 设置 | 值 |
|---|---|
| 底物浓度列 | `substrate_mM`，mM |
| 初始速率列 | `initial_rate_uM_s`，μM/s |
| 预期 Kₘ | 0.3 mM |
| 预期 Vₘₐₓ | 2.4 μM/s |

可向 Agent 发送：“使用 initial-rate-kinetics 拟合这个文件，浓度列 substrate_mM，速率列 initial_rate_uM_s，分别使用 mM 和 μM/s，保存结果。”

在成果中查看拟合曲线、参数、残差、输入及复跑代码。输入是已知初始速率，不需要先从吸光度曲线求速率，也不需要外接计算。

## 多组拟合与重绘

输入：[synthetic-grouped-rates.csv](synthetic-grouped-rates.csv)。设置 `group_columns=["material"]`、`context_columns=["pH"]`，浓度和速率列同上。

| 组别 | pH | 预期 Kₘ / mM | 预期 Vₘₐₓ / (μM/s) |
|---|---:|---:|---:|
| sample-a | 4 | 0.3 | 2.4 |
| sample-b | 5 | 0.6 | 1.8 |

请求叠加或分面绘图。对保存的结果选择“调整曲线”更换标签与布局，数值结果 JSON 保持不变。使用“修订分析”更新同一成果；使用“另建分析”或 `new_analysis=true` 建立独立结果。

## 文献证据保存与比较

一起复制 [synthetic-evidence-draft.json](synthetic-evidence-draft.json) 和 [synthetic-assay-source.md](synthetic-assay-source.md)，保留二者的相对位置。请求 Agent 保存证据草稿，再从保存的 JSON 比较 a1 和 a2。

预期观察：Kₘ 经过等价单位换算后相同，pH 不同，催化剂用量和固定共底物字段缺失。保存结果保留原值、来源和缺失状态，不生成材料活性排名。修改时使用另一个草稿并指定已有 `artifact_id`，报告、JSON 与 CSV 作为同一成果更新。

## 标定与样品反算

输入：[synthetic-calibration.csv](synthetic-calibration.csv) 的关系为 signal = 2 × concentration + 1。使用 signal-analysis，浓度单位 μM，信号单位 a.u.。

再用保存的标定结果反算 [synthetic-sample-signals.csv](synthetic-sample-signals.csv)：sample-a 为 2 μM，sample-b 为 4 μM；最后一个信号超出标定范围，应保留相应状态，不把外推值当成有效范围内定量。

## 给定参数的反应模拟

[synthetic-reaction-network.json](synthetic-reaction-network.json) 描述 A → B，速率常数 k = 0.1 s⁻¹，初始 A 为 0.001 M。使用 reaction-simulation 生成时间曲线，并核对其输入参数、单位和保存的结果。

## 成果版本试用

先保存一项拟合成果，在同项目另一个案例中“引用此版本”，再修订或重绘原分析。案例报告和相关文件应继续读取原引用版本，主动“更新引用”后才切换。版本页可查看修改条目与差异。

“整理讨论为成果”默认最近 1 轮，可调整到最多 15 轮；草稿可编辑、收起和重新打开。该操作使用模型，数值分析工具本身在本机执行。

## 可选计算示例

- [最小 QE 执行检查](qe-smoke/README.zh-CN.md)：一个小 Si 晶胞的准备、提交和结果导入。
- [常用 QE 方法输入](qe-methods/README.zh-CN.md)：收敛、能量组合、电子结构、电荷、热力学与 NEB。

计算示例需要用户已连接、检查并启用的资源，以及明确的计算权限。运行本目录的本机数值示例不需要外接资源。
