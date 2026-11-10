# 常用 QE 方法的小输入

[English](README.md) · 简体中文

[通用研究示例](../README.zh-CN.md) · [最小执行检查](../qe-smoke/README.zh-CN.md) · [工作流字段](../../../integrations/deepseek-harness/foundation/skills/scientific-computing/inputs.md)

这些小输入用于检查计算和成果导入路径。先复制到用户项目的 `inputs/`，配好自己的资源并下载所需 UPF；同一次试用先运行一种方法。

## 赝势

将对应文件保存到输入 JSON 引用的位置，并保留来源与文件哈希：

- `si.upf`：[Si PBE RRKJ](https://pseudopotentials.quantum-espresso.org/upf_files/Si.pbe-rrkj.UPF)。
- `h.upf`：[H PBE RRKJ](https://pseudopotentials.quantum-espresso.org/upf_files/H.pbe-rrkjus_psl.1.0.0.UPF)。
- `h-paw.upf`：[H PBE PAW](https://pseudopotentials.quantum-espresso.org/upf_files/H.pbe-kjpaw_psl.1.0.0.UPF)。

## 输入与观察点

| 输入 | 检查内容 |
|---|---|
| `convergence.json` | 小 Si₂ 模型的两档截断能，查看各步总能和差值；两点示例不代替正式收敛序列 |
| `adsorption.json` | H₂ 相对两个自旋极化 H 原子的结合能，核对参考态、系数与能量符号；不是表面吸附模型 |
| `electronic-structure.json` | Si₂ 的 DOS、投影及短 Γ–X 路径，核对能量参考和投影分组 |
| `charge-analysis.json` | H₂ 与冻结原子分量的差分电荷、PAW 全电子密度及可选 Bader，核对相同晶胞与网格 |
| `formation-energy.json` | 小 Si 空位模型和指定 Si 参考态的能量组合；不是稀释缺陷模型 |
| `reaction-energy.json` | H₂ → 2H 的电子能和 298.15 K、1 bar 理想气体自由能，检查振动、虚频及校正项 |
| `neb.json` | 三图像的约束共线 H + H₂ 交换，核对端点、原子顺序及路径力收敛 |

使用 scientific-computing 技能，将选定 JSON 交给 `highzyme_qe_workflow_prepare`。检查请求后按原 `job_id` 提交、查询和取回结果。缺少所需程序会在提交前显示；Bader 是用户资源上的可选独立程序。

单项结构优化使用 `highzyme_qe_prepare`，支持 `relax` 和 `vc-relax`。参数字段、路径、零起始原子索引与单位以[工作流字段说明](../../../integrations/deepseek-harness/foundation/skills/scientific-computing/inputs.md)为准。

这些输入检验执行链路。定量研究需优化几何、选择合适自旋与赝势，并对目标性质进行相应收敛检查。
