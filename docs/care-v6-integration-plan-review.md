# CARE v6 数据集接入开发计划评审意见

## 1. 文档信息

- 评审日期：2026-08-26
- 被评审方案：[CARE v6 数据集接入与验证开发计划](./care-v6-integration-development-plan.md)
- 本地数据集：`C:\coding\reference\CARE_To_Compare`
- 本地压缩包：`C:\coding\reference\CARE_To_Compare.zip`
- 评审范围：本地数据真实性、CARE 官方资料、现有 WindOps 架构、SCADA 接入、模型运行时、告警链路、数据治理、测试与许可证要求
- 评审方式：只读核验；未修改项目代码或原始数据集

## 2. 总体结论

结论为：**有条件通过**。

方案的总体方向合理，以下核心决策应当保留：

- 不新建独立的通用数据平台；
- CARE 首先作为离线算法基准库使用；
- 原始数据只读保存，标准层使用 Parquet；
- PostgreSQL 保存数据集、事件、质量和评估元数据；
- TimescaleDB 只保存精选回放窗口和必要信号，不接收全量宽表展开结果；
- 前端只读取聚合、分页和降采样后的受治理数据；
- 将异常检测、提前预警和 RUL 明确区分；
- 正常事件必须参与误报评估；
- 标签和故障描述与模型输入隔离。

但是，当前方案尚不具备直接进入导入器、模型运行时或平台回放开发的条件。必须先解决本报告第 5 节列出的 P0 问题，并将修订后的契约纳入阶段 0 验收。

## 3. 本地数据核验结果

### 3.1 文件、规模和校验和

本地核验结果如下：

| 项目              |                                                           核验结果 |
| ----------------- | -----------------------------------------------------------------: |
| 事件数据文件      |                                                              95 个 |
| 风场级元数据文件  |                                                               6 个 |
| CSV 合计          |                                                             101 个 |
| 解压 CSV 总大小   |                                  19,987,475,455 字节，约 18.61 GiB |
| ZIP 大小          |                                                 5,503,439,673 字节 |
| ZIP MD5           |                                 `2547b58c21ac8c242d13232860cf500c` |
| ZIP SHA-256       | `ca61379e98956d891041ad45c885109bd8a14199fde0688d0184a11c2d4194f1` |
| 时间点总数        |                                                          5,242,948 |
| train 时间点      |                                                          4,961,699 |
| prediction 时间点 |                                                            281,249 |
| 未分类时间点      |                                                                  0 |

本地 ZIP 的 MD5 与 [Zenodo 记录 15846963](https://zenodo.org/records/15846963) 公布值一致。

### 3.2 事件、资产和信号统计

| 风场 | 事件 | 异常 | 正常 | 风机 | 总列数 | 信号列 | 基础传感器 |
| ---- | ---: | ---: | ---: | ---: | -----: | -----: | ---------: |
| A    |   22 |   12 |   10 |    5 |     86 |     81 |         54 |
| B    |   15 |    6 |    9 |    9 |    257 |    252 |         63 |
| C    |   58 |   27 |   31 |   22 |    957 |    952 |        238 |
| 合计 |   95 |   45 |   50 |   36 |      — |      — |          — |

事件 ID 完整覆盖 `0..94`，未发现缺失或重复。所有事件的 `event_start_id` 和 `event_end_id` 均位于对应文件的有效 ID 范围内。

根目录 README 仍记录旧版本的 `44 anomaly / 51 normal`，但本地 v6 元数据和当前 Zenodo 记录均为 `45 anomaly / 50 normal`。原方案以事件元数据为准是正确的。

### 3.3 全量展开规模

只计算每个基础传感器的 Avg 信号，全量数据已经约有 877,283,801 个标量测量值：

- A 场：64,624,338；
- B 场：54,121,095；
- C 场：758,538,368。

因此，将全量数据展开为 TimescaleDB 长表不可取。标准层应明确保持适合列裁剪的宽表 Parquet；在线层只能导入精选事件、精选窗口和精选信号。

## 4. 已确认合理的方案内容

### 4.1 数据分层

原始 ZIP/CSV、标准 Parquet、PostgreSQL 元数据、TimescaleDB 在线回放和前端聚合展示之间的边界清晰，符合当前项目架构，也能避免 API 或浏览器直接处理约 20 GiB CSV。

### 4.2 数据真值隔离

将 `event_label`、事件区间和 `event_description` 放入独立真值域，并禁止其进入模型特征，是防止标签泄漏的正确做法。评估前隐藏、评估后揭示也适合诊断演示。

### 4.3 Avg 优先策略

当前 Zenodo v6 说明确认 Min、Max 和 Std 在各风场存在不同程度的物理不合理值，B 场尤其严重，而 Avg 总体更可信。首版默认只启用 Avg 是合理的保守策略。

### 4.4 RUL 边界

CARE 没有逐时间点的标准剩余寿命标签，只适合验证异常检测、事件识别、误报控制和提前预警。方案禁止把提前告警时间包装成经 CARE 验证的 RUL 精度，这一边界必须保留。

## 5. P0：实施前必须修订的问题

### P0-1：导入字段契约与真实文件不完全一致

本地 `feature_description.csv` 的实际列名是 `statistics_type`，而不是 README 所写的 `statistic_type`。该字段的值是逗号分隔的统计类型集合，例如：

```text
maximum,minimum,average,std_dev
```

此外，A 场存在八个没有统计后缀的实际信号列：

```text
sensor_44
sensor_45
sensor_46
sensor_47
sensor_48
sensor_49
sensor_50
sensor_51
```

这些列在元数据中仍声明为 `average`。如果导入器只按 `<sensor>_<stat>` 后缀拆分，将漏掉或错误分类这八个信号。

另一个需要显式说明的事实是：`event_id` 不存在于事件数据行中，只存在于文件名和 `event_info.csv` 中。

要求修改：

- 读取真实的 `statistics_type` 字段；
- 将逗号分隔集合规范化为稳定集合，不依赖原始顺序；
- 使用元数据驱动的“原始列名 → 基础传感器 → statistic”映射；
- 为 A 场八个裸列建立有版本的显式别名；
- 从文件名取得事件 ID，并与 `event_info.csv` 双向校验；
- 未知列、缺失列和重复映射必须失败关闭，不能静默忽略。

阶段 0/1 验收必须证明 A/B/C 分别有 81/252/952 个信号列全部一一映射，且无未解释的多余列。

### P0-2：遗漏零值缺失、状态不一致和缩放语义

[官方论文](https://doi.org/10.3390/data9120138) 与当前 Zenodo 说明明确指出：

- B/C 场使用 `0` 替代缺失值；
- 大段连续零值需要谨慎处理；
- B/C 场状态码可能因短暂通信错误而不一致；
- 各事件时间戳被独立平移，跨事件的匿名时间顺序已经失真；
- 功率和无功功率信号经过额定功率缩放。

当前方案只强调空单元格抽查和 Min/Max/Std 问题，不能覆盖这些风险。

要求修改：

- 增加每特征零值比例、最长连续零段、零值与运行状态/功率的关联报告；
- 禁止全局将 `0` 直接替换为 null；
- 只有经过特征级规则确认，才允许将特定零段标记为疑似缺失；
- 为数据质量保留独立缺失/不确定掩码，不覆盖原始值；
- 建立分风场的状态码可信规则；
- 明确功率信号的缩放语义，禁止把其值解释为未经匿名化的绝对设备额定功率；
- 禁止使用匿名时间戳推导不同事件的真实先后顺序。

### P0-3：CARE Score 的 v6 评分协议未被冻结

CARE Score 并不是简单的事件召回率。论文定义中至少包含：

- 点级 `Fβ`，通常使用 `β = 0.5`；
- 正常事件的 Accuracy；
- 基于 criticality 的事件级 `Fβ`；
- criticality 阈值 72；
- Earliness 加权分数；
- 正常 Accuracy 低于 0.5 以及未检测到异常等特殊分支；
- 二值预测阈值，而不是只保存连续 anomaly score。

v6 还特别说明，A 场异常事件的 prediction 时段不应机械使用旧版本状态标签过滤，因为 A 场状态来源主要用于训练过滤。

要求修改：

- 定义不可变的 `care-score-v6` 评估器版本；
- 固化各风场、各事件类型的状态过滤规则；
- 固化 criticality 的比较边界、重置规则、异常状态处理和所有权重；
- 同时保存原始 anomaly score、阈值版本和最终二值预测；
- 阈值和超参数只能使用 train/validation 数据确定；
- 禁止根据同一 prediction 真值选择最优阈值；
- 明确区分模型开发结果、调参结果和最终保留测试结果。

至少应增加以下黄金测试：

- all-normal；
- all-anomaly；
- 无告警；
- criticality 恰好 71、72、73；
- 正常事件持续误报；
- A 场 v6 状态例外；
- B/C 异常状态过滤；
- Earliness 前半段、后半段和事件终点；
- `Acc < 0.5` 特殊分支。

原方案中的“每风机年误报数”目前没有可靠分母。由于事件包覆盖区间重叠且跨事件年份顺序失真，首版建议报告：

- 正常事件误报率；
- 每 1000 个有效正常运行小时误报数；
- 每 prediction event-day 误报数。

只有在去重暴露时间得到明确证明后，才报告每风机年指标。

### P0-4：当前回放 ID、顺序号和时间策略与现有接入水位冲突

现有 SCADA 接入实现按以下范围维护水位：

```text
source_id + turbine_id + variable
```

相关实现位于：

- [`services/ingest.py`](../backend/src/windops_backend/services/ingest.py)
- [`models.py`](../backend/src/windops_backend/models.py)
- [`config.py`](../backend/src/windops_backend/config.py)

CARE 的 `id` 在每个事件中从 0 重新开始。本地核验还显示，同一资产只要包含多个事件，其事件文件覆盖区间就相互重叠。若按原方案使用共享的 `care-v6-replay`、`CARE-<farm>-<asset>` 和原始 `id`：

- 后续事件会使用低于已有最高水位的 sequence；
- 重复 sequence 边界可能被隔离；
- 时间回退超过允许迟到窗口时会被隔离；
- 多个事件包会混入同一风机/变量时序；
- 最新特征查询可能从不同事件包拼装模型输入；
- 模型预测的 turbine/timestamp 唯一约束可能发生冲突。

只给匿名时间戳附加 UTC 也不能解决问题。原始时间主要位于 2022—2024 年，不会自然进入现有 LIVE、24H 或 30D 展示窗口。

要求修改：

- 新增正式的 `benchmark_replay_run_id`；
- 将逻辑 CARE 资产与在线回放实例分开；
- 首版优先使用事件级或运行级虚拟风机，避免污染同一逻辑资产时序；
- 或者扩展服务端 stream key、查询、模型输入和访问控制，使其显式包含 replay run；
- 使用确定性的合成回放时间轴，并保留 `source_time_stamp`、`anonymous_observed_at` 和时间偏移规则；
- `source_event_id` 应包含 dataset version、replay run、event、row 和 variable；
- 将幂等性定义为“同一 replay run 重试不重复”；新 replay run 是明确的新业务运行；
- `source_sequence` 应在最终 stream scope 内稳定单调，不能简单复用会跨事件重置的原始 `id`。

### P0-5：CARE 异常模型与当前模型运行时、告警数据模型不兼容

当前模型运行时存在以下硬约束：

- 只有 `predictive` 类型模型可部署；
- predictive 输出必须包含 `failure_probability_30d`；
- predictive 输出必须包含 `remaining_useful_life_days`；
- 所有推理结果都会执行 RUL、概率和 anomaly score 校验。

相关实现位于：

- [`schemas.py`](../backend/src/windops_backend/schemas.py)
- [`services/models.py`](../backend/src/windops_backend/services/models.py)

这会迫使 CARE 异常模型输出没有数据依据的 RUL 字段，与方案定义的 RUL 边界直接冲突。

告警链路也存在结构限制：

- `Alarm.source_event_id` 强制关联 ingest receipt；
- 当前自动触发器只识别 `main_bearing_vibration_rms`；
- 触发条件是单样本固定阈值；
- 现有 `evaluation_gate` 只被保存，没有服务器端质量门槛执行逻辑。

要求修改：

- 增加正式的 anomaly 模型运行契约，不要求虚构 RUL 或 30 天故障概率；
- anomaly 输出至少包含 anomaly score、component、model/deployment version、feature window 和证据引用；
- 告警应能够直接关联受治理的模型预测，而不是只能依赖伪装成 SCADA 属性的 anomaly score；
- 增加模型预测到告警的明确外键或通用告警来源模型；
- 增加连续 N 窗口、冷却期、恢复阈值、告警去重和策略版本状态；
- 将 CARE 质量门槛落实为服务器端可验证的激活条件；
- 未通过门槛的模型不得仅凭前端状态或任意 JSON 被激活。

## 6. P1：进入规模化前应补强的问题

### P1-1：跨风场泛化需要独立协议

A/B/C 的信号空间分别为 81/252/952 列，匿名传感器编号不具有跨场一致语义。本地按 description 精确比较时，三个风场没有完全相同的共同描述字段。

因此，“跨风场泛化”不能由现有 `source_variable` 映射自然获得。建议划分为三个明确协议：

1. 单事件 train → prediction 的 CARE 兼容基准；
2. 场内跨风机或 leave-one-turbine-out 泛化；
3. 基于人工审核语义本体或共同特征集的跨风场迁移。

首版应先完成前两项。第三项必须有版本化的 canonical feature ontology、映射置信度和人工审核记录。

### P1-2：Parquet 物理布局和执行进程需要明确

当前后端基础依赖中没有 PyArrow、Polars、DuckDB、Pandas 或 scikit-learn。约 20 GiB 导入和模型评估也不应在 FastAPI 请求事务中执行。

建议：

- 建立独立的 benchmark 可选依赖组并锁定版本；
- 使用 CLI 或独立 Worker 执行导入、质量审计和评估；
- 明确资源上限、取消、恢复、重试和任务心跳；
- Parquet 保持宽表，按 `dataset_version/farm/event` 分区；
- 根据查询方式决定是否再按 split 分文件或 row group；
- 使用支持列裁剪的读取方式和稳定压缩算法；
- 禁止一次把 C 场完整宽表装入内存；
- 生产环境为原始 ZIP、标准 Parquet和评估制品配置专用 MinIO bucket/prefix 与生命周期规则。

### P1-3：模型实体应复用现有注册表

方案提出的“模型版本”逻辑实体不应与现有 `RegisteredModel` 重复建设。建议：

- 现有 `RegisteredModel` 保存模型包、输入输出契约和内容哈希；
- 新增 BenchmarkEvaluationRun 关联现有 model ID/version；
- 事件级结果保留在独立 BenchmarkEventResult；
- 汇总指标既不能只写入任意 `metrics` JSON，也不能复制完整模型实体；
- 发布门槛引用不可变的 evaluation run 和指标快照。

### P1-4：许可证要求需落实到制品级

CARE v6 使用 CC BY-SA 4.0。[Creative Commons 官方说明](https://creativecommons.org/licenses/by-sa/4.0/)要求署名、许可证链接、修改说明，并对对外分发的改编材料落实 ShareAlike。

方案目前只写了 DOI、作者和许可证展示，还应增加：

- 数据集归属和推荐引用文本；
- 原始记录 URL 与 DOI；
- `changes_made` 和转换规则版本；
- 适用于标准 Parquet、派生数据导出和报告附件的许可证声明；
- 数据制品许可证与项目 MIT 源代码许可证分离；
- 对外分发前进行制品类型和 ShareAlike 适用性复核。

这部分是工程合规建议，不替代正式法律意见。

## 7. 建议的修订后实施顺序

### 阶段 0A：真实数据契约

- 固化 ZIP MD5 和 SHA-256；
- 固化 101 个 CSV 的大小、SHA-256、行数和 schema hash；
- 建立真实 `statistics_type` 解析；
- 建立 A 场裸列覆盖；
- 固化零值缺失、状态、单位、缩放和时间语义；
- 用 A/B/C 各一个小型固定样例验证映射。

### 阶段 0B：评分协议

- 冻结 `care-score-v6`；
- 明确 A/B/C 状态过滤差异；
- 固化阈值校准边界；
- 建立黄金向量和基准输出；
- 定义场内泛化与跨场泛化的独立协议。

### 阶段 0C：平台兼容设计

- 确定 replay run、逻辑资产和在线实例模型；
- 确定合成时间轴、sequence 和 source event ID；
- 确定 anomaly 运行时和预测记录；
- 确定通用告警来源、策略状态和模型预测外键；
- 确定数据集、事件、质量和评估表的迁移方案；
- 确定专用对象存储和 Worker/CLI 边界。

### 阶段 1：最小导入验证

先导入 A 场一项异常事件和一项正常事件，完成：

- 原始清单；
- 宽表 Parquet；
- 质量报告；
- 标签隔离；
- 重复导入确定性；
- 小范围性能和内存验证。

通过后再扩展到 A 场全部 22 个事件。

### 阶段 2：离线基准

- 完成简单基线和目标模型；
- 使用统一评估器；
- 保存 score、binary prediction、阈值和事件级结果；
- 不使用 prediction 真值调参；
- 正常事件和失败事件全部进入汇总。

### 阶段 3：平台垂直切片

只有 anomaly 运行时、模型预测溯源、通用告警策略和 replay run 隔离完成后，才接入精选事件的 SCADA 回放及 Mission/诊断/决策闭环。

### 阶段 4/5：界面与规模化

按原方案扩展数据中心、模型管理、诊断中心、全量 95 事件和发布门槛，同时保持分页、降采样、访问控制和许可证展示。

## 8. 修订版阶段 0 通过门槛

进入正式开发前，至少满足：

- [ ] A/B/C 的 81/252/952 个信号全部映射，无未知或静默丢弃列；
- [ ] `statistics_type`、A 场裸列和 event ID 来源已固化并有测试；
- [ ] B/C 零值缺失和状态不一致进入质量规则；
- [ ] 缩放功率和匿名跨事件时间语义得到显式标记；
- [ ] `care-score-v6` 公式、参数、状态规则和黄金向量冻结；
- [ ] 模型阈值不能读取 prediction 真值；
- [ ] replay run、虚拟资产、合成时间、sequence 和幂等键无冲突；
- [ ] anomaly 模型无需输出 RUL；
- [ ] 告警能够引用模型预测且具备连续窗口、冷却和恢复状态；
- [ ] Parquet 明确采用宽表并由独立 CLI/Worker 处理；
- [ ] SHA-256、来源、转换记录和 CC BY-SA 制品要求进入不可变清单；
- [ ] 现有 RegisteredModel、访问控制和数据目录扩展关系已经评审。

## 9. 最终建议

批准继续完成阶段 0 的方案修订和小型固定样例验证；在 P0-1 至 P0-5 全部关闭前，不批准直接开始全量导入、模型上线或平台回放。

完成上述修订后，原方案以 A 场打通端到端垂直切片、再扩展到 C 场和全量 95 个事件的总体顺序是合理的。

## 10. 参考资料

- [CARE v6 Zenodo 记录](https://zenodo.org/records/15846963)
- [CARE to Compare 官方论文](https://doi.org/10.3390/data9120138)
- [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- [原 CARE v6 接入开发计划](./care-v6-integration-development-plan.md)
- [`backend/src/windops_backend/services/ingest.py`](../backend/src/windops_backend/services/ingest.py)
- [`backend/src/windops_backend/services/models.py`](../backend/src/windops_backend/services/models.py)
- [`backend/src/windops_backend/models.py`](../backend/src/windops_backend/models.py)
- [`backend/src/windops_backend/schemas.py`](../backend/src/windops_backend/schemas.py)
- [`backend/src/windops_backend/config.py`](../backend/src/windops_backend/config.py)
