# CARE v6 数据集接入与验证开发计划

## 1. 文档信息

- 数据集名称：Wind Turbine SCADA Data For Early Fault Detection（CARE to Compare）
- 数据集版本：CARE v6
- 官方记录：[Zenodo 15846963](https://zenodo.org/records/15846963)
- 官方论文：[CARE to Compare](https://doi.org/10.3390/data9120138)
- DOI：[10.5281/zenodo.15846963](https://doi.org/10.5281/zenodo.15846963)
- 数据许可证：[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- 本地原始目录：`C:\coding\reference\CARE_To_Compare`
- 本地压缩包：`C:\coding\reference\CARE_To_Compare.zip`
- 评审依据：[CARE v6 数据集接入开发计划评审意见](./care-v6-integration-plan-review.md)
- 修订状态：已将评审中的 P0/P1 要求纳入阶段门槛；P0 契约未冻结前不得开始全量导入、模型上线或平台回放
- 文档目的：定义 CARE v6 在 WindOps 中的数据治理、离线评估、异常模型运行时、平台回放和界面展示方案。

## 2. 总体结论与强制决策

### 2.1 不新建独立数据平台

CARE v6 首先作为离线算法基准库使用。需要演示、验收和追溯时，在现有数据中心中增加“基准数据集”能力，并将模型评估结果关联到现有模型管理和诊断中心。

不建设通用数据平台的原因：

- 当前项目已有数据中心、SCADA 归档、模型注册、诊断和 Mission 工作流；
- CARE 解压后约 18.61 GiB，单事件最多 957 列，不适合浏览器直接处理；
- 仅展开 Avg 信号就约有 8.77 亿个标量值，全量写入 TimescaleDB 长表不可接受；
- 算法验证的核心是可复现的数据契约、质量报告、评分协议和模型追溯，而不是原始文件浏览器。

### 2.2 数据分层

```text
CARE v6 ZIP/CSV（只读原始层）
                 |
                 v
       独立 CLI/Worker 导入与审计
          |                    |
          v                    v
宽表分区 Parquet          PostgreSQL 基准元数据
          |                    |
          v                    v
离线训练/评分 <------ RegisteredModel 与评估运行
          |
          v
精选事件 + 精选 Avg 信号 + anomaly prediction
          |
          v
隔离的 BenchmarkReplayRun
          |
          v
SCADA/模型预测 -> 通用告警策略 -> Mission -> 诊断/决策
```

### 2.3 存储边界

- 原始层：原始 ZIP/CSV 只读保存，不进入 Git，不允许就地修复。
- 标准层：按 `dataset_version/farm/event` 分区保存宽表 Parquet，支持列裁剪。
- 质量层：保存质量摘要和独立质量掩码，不覆盖原始数值。
- 元数据层：PostgreSQL 保存数据集版本、文件、事件、映射、质量、评估和回放运行。
- 模型层：复用现有 `RegisteredModel`，不重复创建第二套模型注册表。
- 在线层：TimescaleDB 仅保存指定回放运行中的精选窗口、精选信号和必要证据。
- 制品层：MinIO 使用 CARE 专用 bucket/prefix 保存原始包、标准 Parquet、质量报告、预测和评估报告。
- 展示层：前端只读取分页、聚合和降采样后的受治理 API。

### 2.4 阶段门禁

实施分为阶段 0A、0B、0C 三个前置设计门禁。三项均通过后才能进行阶段 1：

- 0A：真实数据契约；
- 0B：`care-score-v6` 评分协议；
- 0C：平台兼容设计。

任何 P0 项目不得用占位字段、伪造 RUL、前端状态或人工跳过检查的方式绕过。

## 3. 本地数据核验基线

### 3.1 文件、规模和校验和

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

本地 ZIP 的 MD5 与 Zenodo 官方值一致。数据集不可变清单必须同时记录 MD5 和 SHA-256；文件级清单使用 SHA-256。

### 3.2 事件、资产和信号统计

| 风场 | 事件 | 异常 | 正常 | 风机 | 总列数 | 元数据列 | 信号列 | 基础传感器 |
| ---- | ---: | ---: | ---: | ---: | -----: | -------: | -----: | ---------: |
| A    |   22 |   12 |   10 |    5 |     86 |        5 |     81 |         54 |
| B    |   15 |    6 |    9 |    9 |    257 |        5 |    252 |         63 |
| C    |   58 |   27 |   31 |   22 |    957 |        5 |    952 |        238 |
| 合计 |   95 |   45 |   50 |   36 |      — |        — |      — |          — |

事件 ID 完整覆盖 `0..94`，未发现缺失或重复。所有事件的 `event_start_id` 和 `event_end_id` 均位于对应文件有效 ID 范围内。

根目录 README 仍记录旧统计 `44 anomaly / 51 normal`；实现必须以本地 v6 事件元数据为准，期望值为 `45 anomaly / 50 normal`。

### 3.3 全量展开规模

仅计算基础传感器的 Avg 信号，全量数据约包含 877,283,801 个标量测量值：

- A 场：64,624,338；
- B 场：54,121,095；
- C 场：758,538,368。

因此：

- 标准层必须保持宽表 Parquet；
- 禁止将全量信号展开到 TimescaleDB；
- 禁止一次把 C 场完整宽表装入内存；
- 在线层只能导入精选事件、窗口和信号。

### 3.4 真实文件契约

事件数据文件位于：

```text
Wind Farm <A|B|C>/datasets/<event_id>.csv
```

CSV 使用分号 `;` 分隔，前五列固定为：

```text
time_stamp;asset_id;id;train_test;status_type_id
```

`event_id` 不存在于事件数据行中。导入器必须从文件名取得事件 ID，并与对应 `event_info.csv` 双向校验。

`feature_description.csv` 的真实字段名是 `statistics_type`，不是 README 中的 `statistic_type`。其值是逗号分隔的统计类型集合，例如：

```text
maximum,minimum,average,std_dev
```

导入器必须将其规范化为去重、稳定排序的集合，不能依赖原始顺序。

大多数信号列使用以下后缀：

```text
sensor_0_avg
sensor_0_min
sensor_0_max
sensor_0_std
wind_speed_3_avg
power_62_avg
```

A 场还存在八个没有统计后缀、但元数据声明为 average 的信号列：

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

这八列必须通过版本化显式别名映射为 average，不能仅靠列名后缀推断。

### 3.5 已确认的数据质量问题

1. A 场 `event_info.csv` 使用 `asset`，B/C 使用 `asset_id`。
2. A/B 的 `°C`、`°` 已损坏为 `�C`、`�`。
3. 官方确认各场 `Min/Max/Std` 有物理不合理值，B 场最严重；Avg 总体更可信。
4. B/C 使用 `0` 表示部分缺失数据，大段连续零值需要特征级判断。
5. `0` 也可能是合法物理值，禁止全局替换为 null。
6. B/C 状态码可能受短时通信错误影响，状态值不能无条件视为真值。
7. 各事件时间戳被独立平移，跨事件的匿名时间先后关系失真。
8. 功率和无功功率信号经过额定功率缩放，不得解释为未经匿名化的绝对设备功率。
9. A 场 prediction 异常时段不应机械使用旧状态标签过滤；A 场状态主要用于训练过滤。
10. 空单元格抽查良好不代表零值、状态或物理质量可靠。

### 3.6 数据使用优先级

| 优先级 | 风场 | 用途                       | 主要原因                               |
| -----: | ---- | -------------------------- | -------------------------------------- |
|      1 | C    | 大规模评估与场内泛化       | 事件、资产和信号覆盖最广               |
|      2 | A    | 首个端到端导入试点         | 数据量适中、语义较清晰、异常事件多于 B |
|      3 | B    | 轴承、振动和变压器专项验证 | 有专项价值，但统计量和零值问题较突出   |

实施顺序不是简单按优先级全量导入：先用 A 场一项异常和一项正常事件验证契约，再扩展到 A 场全部 22 个事件，之后扩展 C，最后按故障类型选择 B。

## 4. 验证目标与边界

### 4.1 可以验证

- 单事件 train 到 prediction 的 CARE 兼容异常检测；
- 场内跨风机或 leave-one-turbine-out 泛化；
- 正常事件误报控制；
- 故障事件提前预警；
- 数据质量过滤对模型结果的影响；
- 模型异常分数到告警、Mission、诊断证据和决策的业务闭环；
- 数据、模型、阈值、评分器和评估结果的可追溯性。

### 4.2 跨风场验证的限制

A/B/C 分别有 81/252/952 个信号列，匿名传感器编号不具备跨场统一语义，三个风场也没有可直接依赖的完全一致 description 集合。必须将验证协议分开：

1. 单事件 `train -> prediction` 的 CARE 兼容基准；
2. 场内跨风机或 leave-one-turbine-out；
3. 基于人工审核语义本体或共同特征集的跨风场迁移。

首版只承诺前两项。第三项必须先建立版本化 canonical feature ontology、映射置信度和人工审核记录，不允许按匿名传感器编号自动对齐。

### 4.3 不可以证明

- 不能证明 RUL 回归精度，因为 CARE 没有逐时间点的标准剩余寿命标签；
- 不能验证气象窗口、海况或维修资源调度；
- 不能代表在线高频振动频谱，CARE 主要是 10 分钟汇总信号；
- 不能使用匿名时间戳推导不同事件的真实先后、真实季节或真实场站时间；
- 不能把事件描述作为模型根因诊断能力的输入证据；
- 不能把经过缩放的功率解释为真实绝对额定功率。

## 5. 阶段 0A：真实数据契约

### 5.1 不可变数据清单

每个数据集版本建立不可变清单，至少包含：

- `dataset_id = care` 和 `dataset_version = v6`；
- Zenodo URL、DOI、推荐引用、作者归属和许可证；
- 原始 ZIP 文件名、字节数、MD5 和 SHA-256；
- 101 个 CSV 的相对路径、字节数、SHA-256、行数和 schema hash；
- 95 个事件的风场、文件名、事件 ID、资产、split 行数和事件区间；
- 导入工具版本、Git commit、依赖锁摘要和运行时间；
- 字段映射、单位映射、质量规则和转换规则版本；
- `changes_made` 和生成制品的许可证声明。

原始 CSV 不得复制后修改。所有修复写入标准层，并记录规则、原值语义、修复值语义和适用范围。

### 5.2 元数据驱动的字段映射

不得仅按 `<sensor>_<stat>` 拆分列名。映射生成过程为：

1. 读取真实 `statistics_type`；
2. 解析并规范化逗号分隔统计类型集合；
3. 读取事件文件真实表头；
4. 使用 feature metadata、统计类型集合、标准后缀和版本化别名建立映射；
5. 对 A 场八个裸列应用显式 average 别名；
6. 校验映射为一对一；
7. 对未知列、缺失列、重复映射和歧义映射失败关闭；
8. 输出可审计的 column mapping artifact。

映射验收必须证明：

- A 场 81 个信号列全部映射；
- B 场 252 个信号列全部映射；
- C 场 952 个信号列全部映射；
- 没有静默丢弃、未知或多对一冲突。

### 5.3 规范字段映射

| CARE 来源                | 标准字段                    | 规则                                                |
| ------------------------ | --------------------------- | --------------------------------------------------- |
| 风场目录 A/B/C           | `source_farm`               | 保留来源维度，不映射为真实风场                      |
| `asset` / `asset_id`     | `source_asset_id`           | 兼容元数据中的两个名称                              |
| `<event_id>.csv` 文件名  | `benchmark_event_id`        | 与 `event_info.csv` 双向校验                        |
| `id`                     | `source_row_id`             | 保留事件文件内原始序号，不直接假定为跨事件 sequence |
| `time_stamp`             | `anonymous_observed_at`     | 保留匿名无时区时间                                  |
| `train_test`             | `benchmark_split`           | 仅允许 `train`、`prediction`                        |
| `status_type_id`         | `operating_status_id`       | 运行状态，不等于数据质量                            |
| 真实信号列               | `source_column`             | 原样保存列名                                        |
| feature metadata + alias | `base_sensor` / `statistic` | 元数据驱动映射                                      |
| `event_label`            | 独立真值域                  | 禁止进入特征和阈值校准输入                          |
| `event_start_id/end_id`  | 独立评分真值域              | 仅评估器访问                                        |
| `event_description`      | 独立解释真值域              | 评估后按权限揭示                                    |

### 5.4 时间语义

标准层同时保留：

- `source_time_stamp`：原始文本；
- `anonymous_observed_at`：解析后的无时区时间；
- `source_row_id`：原始 `id`；
- `timestamp_semantics = independently-shifted-anonymized`；
- 数据文件内的相对间隔和间隔异常。

约束：

- 不给标准层时间戳伪造真实场站时区；
- 不按匿名时间戳对不同事件排序、拼接或去重暴露时间；
- 不从匿名年份推导季节或年度指标；
- 在线回放必须使用单独的确定性合成时间轴，详见阶段 0C。

### 5.5 单位和缩放语义

建立版本化单位映射：

| 原始单位  | 规范单位         | 处理                     |
| --------- | ---------------- | ------------------------ |
| `�C`      | `°C`             | A/B 温度单位损坏修复     |
| `�`       | `°`              | A/B 角度单位损坏修复     |
| `Celsius` | `°C`             | 温度单位统一             |
| `deg`     | `°`              | 角度单位统一             |
| 空字符串  | `1` 或 `unknown` | 只有确认无量纲时使用 `1` |

单位映射结合 `description`、`is_angle` 和人工审核，不能只做字符串替换。功率和无功功率另加：

```text
value_semantics = anonymized-rated-power-scaled
absolute_power_interpretation_allowed = false
```

### 5.6 零值、缺失和质量掩码

导入器必须为每个特征生成或汇总：

- 零值比例；
- 最长连续零段；
- 零段数量和时间范围；
- 零值与运行状态、功率和相邻信号的关系；
- null、NaN、Infinity 和解析失败数量；
- 常量段、突变和物理范围异常；
- Min/Avg/Max/Std 约束违反情况。

处理原则：

- 不全局把 `0` 替换为 null；
- 只有特征级、风场级规则确认后，才将特定零段标记为疑似缺失；
- 原值始终保留；
- 缺失/不确定信息写入独立 sparse mask、质量表或伴随制品；
- 质量掩码必须包含规则 ID、规则版本、置信度和原因；
- 模型训练明确声明如何使用或忽略质量掩码。

### 5.7 状态可信规则

状态过滤按风场和评分协议版本管理：

- A 场：状态主要用于训练数据过滤；异常 prediction 窗口遵循 CARE v6 特例；
- B/C 场：状态可用于过滤，但必须考虑短时通信错误和连续性；
- `operating_status_id` 不直接映射为平台的 `quality=bad`；
- 状态修正规则不得覆盖原始状态；
- 状态规则版本必须进入评估运行身份。

### 5.8 信号启用策略

- 首版默认只启用元数据确认的 average，包括 A 场八个裸 average 列；
- 默认禁用 Min/Max/Std；
- 统计量经特征级质量验证后才能逐项启用；
- 角度使用环形处理，不按普通线性变量处理；
- 计数器检测重置、回绕和非单调变化；
- 缩放功率只能作为相对信号使用；
- 每个特征集合必须版本化并保存完整列清单。

### 5.9 标签隔离和数据切分

- 模型训练只读取 `train` 数据；
- validation 只能从 train 内按时间或资产划分；
- prediction 真值不得用于阈值、超参数、早停或特征选择；
- 模型在 prediction 上只输出分数和二值预测；
- 真值域只由最终评估器访问；
- 记录模型实际读取的列和 split 摘要；
- 禁止跨事件随机行拆分；
- 必须调查同资产不同事件中重复或重叠训练历史导致的泄漏。

## 6. 阶段 0B：冻结 `care-score-v6` 评分协议

### 6.1 不可变评估器

建立不可变评估器版本 `care-score-v6`。实现前必须从官方论文或权威参考实现固化：

- 点级 `Fβ`，默认 `β = 0.5`；
- 正常事件 Accuracy；
- 基于 criticality 的事件级 `Fβ`；
- criticality 阈值 72；
- Earliness 加权分数；
- 正常 Accuracy 低于 0.5 的特殊分支；
- 未检测到异常、没有有效点和无法评分的分支；
- A/B/C 状态过滤差异；
- criticality 比较边界、重置规则和异常状态处理；
- 所有分项权重、舍入和聚合顺序。

比较符号和边界不能凭经验推断。阶段 0B 必须将公式、常量、状态规则、来源引用和黄金输出写入版本化规范；规范未评审通过时不得把实现标记为 `care-score-v6`。

### 6.2 预测制品

每次事件级评分同时保存：

- 原始 `anomaly_score` 序列；
- threshold 数值和 threshold policy version；
- 最终 binary prediction 序列；
- 有效点和过滤点 mask；
- criticality/earliness 中间量；
- 分项得分、总分和特殊分支；
- 模型、部署、特征集合、质量规则和评估器版本。

### 6.3 阈值校准边界

- 阈值和超参数只能用 train 或 train 内 validation 确定；
- 禁止使用同一 prediction 真值选择最佳阈值；
- 开发结果、调参结果和最终保留测试结果使用不同状态；
- 最终测试运行不可被原地覆盖；
- 重新调参后必须生成新的模型版本或评估运行。

### 6.4 首版指标

首版至少报告：

- CARE Score 及全部组成项；
- 正常事件误报率；
- 每 1000 个有效正常运行小时误报数；
- 每 prediction event-day 误报数；
- 事件检测率；
- 告警提前量的中位数和分位数；
- Precision、Recall、F0.5 和 PR-AUC；
- 分风场、分资产和分故障类型结果；
- 无法评分、数据失败和模型失败事件数。

首版不报告“每风机年误报数”。只有证明事件包暴露时间已正确去重，且没有使用跨事件失真的匿名年份后，才允许增加该指标。

### 6.5 黄金测试

至少固化以下输入和期望输出：

- all-normal；
- all-anomaly；
- 无告警；
- criticality 恰好 71、72、73；
- 正常事件持续误报；
- A 场 v6 状态例外；
- B/C 异常状态过滤；
- Earliness 前半段、后半段和事件终点；
- `Accuracy < 0.5` 特殊分支；
- 没有有效点评分；
- threshold 边界相等情况。

### 6.6 泛化协议

评估运行明确声明以下协议之一：

- `care-event-train-prediction-v6`；
- `within-farm-leave-one-turbine-out-v1`；
- `cross-farm-ontology-v1`。

第三种协议在 canonical feature ontology 未完成前保持禁用。

## 7. 独立执行进程与 Parquet 设计

### 7.1 依赖和运行边界

当前后端基础依赖没有 PyArrow、Polars、DuckDB、Pandas 或 scikit-learn。实现时新增独立 `benchmark` 可选依赖组并锁定版本，不把大数据依赖强制加入在线 API 最小运行环境。

阶段 0A 通过小样例 ADR 选择列式引擎。最低要求：

- 支持流式或分批读取分号 CSV；
- 支持 Parquet 列裁剪和 row group；
- 能对 C 场文件实施有界内存处理；
- 依赖版本进入 lockfile 和评估运行清单。

### 7.2 执行方式

- 导入、质量审计、训练和评估由 CLI 或独立 Worker 执行；
- FastAPI 请求只创建任务、查询状态或取消任务；
- 禁止在 HTTP 数据库事务中解析大型 CSV 或训练模型；
- 任务记录心跳、进度、当前文件、资源统计、失败原因和检查点；
- 支持受控取消、恢复和有限重试；
- 重试不得重复写入不可变制品或最终指标；
- 临时文件位于项目配置的受控临时目录，不使用全局用户目录。

### 7.3 Parquet 物理布局

推荐基础布局：

```text
care/v6/standard/farm=<A|B|C>/event=<event_id>/data.parquet
care/v6/quality/farm=<A|B|C>/event=<event_id>/quality.parquet
care/v6/predictions/model=<model-version>/run=<evaluation-run>/...
```

要求：

- 标准数据保持宽表；
- 以 `dataset_version/farm/event` 为稳定分区键；
- 是否按 split 分文件由小样例查询基准决定；
- row group 大小和压缩算法固定并记录版本；
- 不为每个传感器创建大量小文件；
- 每个制品保存 schema hash、row count、content hash 和生成规则版本。

### 7.4 对象存储

生产环境为以下内容配置专用 MinIO bucket 或 prefix：

- `raw`：官方 ZIP 和原始清单；
- `standard`：Parquet 标准层；
- `quality`：质量报告和掩码；
- `predictions`：预测序列；
- `reports`：评分与导出制品。

分别设置访问策略、保留期、版本控制、生命周期规则和备份范围。

## 8. 模型注册、异常运行时与发布门槛

### 8.1 复用现有模型注册表

- `RegisteredModel` 继续保存模型包、模型类型、输入/输出契约、版本和内容哈希；
- 新增 `BenchmarkEvaluationRun`，关联现有 model ID/version；
- 新增 `BenchmarkEventResult` 保存事件级结果；
- 新增结构化 `BenchmarkMetricSnapshot` 保存发布门槛所需的固定指标；
- 扩展指标可以保存在 JSON，但关键发布指标不能只存在任意 JSON 中；
- 不创建重复的模型实体或第二套模型版本体系。

### 8.2 正式 anomaly 模型契约

现有 predictive 契约要求 `failure_probability_30d` 和 `remaining_useful_life_days`，不适用于 CARE。必须新增正式 `anomaly` 模型类型，并按类型执行条件校验。

anomaly 输出至少包含：

- `anomaly_score`；
- `binary_prediction`；
- `component` 或受控的 unknown；
- model ID/version 和 deployment version；
- threshold policy version；
- feature window 起止时间/序号；
- feature set version；
- evidence artifact reference；
- benchmark replay run ID（在线回放时）。

约束：

- anomaly 模型不要求 RUL 或 30 天故障概率；
- predictive 模型现有 RUL/概率契约保持不变；
- 不允许给 anomaly 模型填充无依据的占位 RUL；
- 输入窗口必须限定在同一 dataset/event/replay run，禁止从不同事件包拼接最新特征。

### 8.3 服务器端评估门槛

模型激活条件由服务器端执行，至少验证：

- 模型类型和输入/输出 schema；
- 模型包哈希和部署版本；
- 不可变 `BenchmarkEvaluationRun` 已完成且未失效；
- 指标快照由指定 `care-score-v6` 产生；
- 正常事件误报指标和异常事件检测指标达到策略门槛；
- 评估覆盖要求的风场/协议；
- 数据、特征、质量规则和 threshold 版本匹配；
- 没有失败事件被排除；
- 审批和审计事件完整。

前端状态、任意 metrics JSON 或手工填写结果不能绕过该门槛。

## 9. 阶段 0C：平台兼容与回放设计

### 9.1 逻辑资产与回放实例分离

建立两层资产语义：

- 逻辑 CARE 资产：`CARE-<farm>-<source_asset>`，用于离线统计和数据目录；
- 在线回放实例：绑定 `benchmark_replay_run_id + event_id` 的隔离虚拟风机，用于 SCADA 水位、查询、模型输入和告警。

首版使用事件级/运行级虚拟风机，避免修改现有 `source_id + turbine_id + variable` 水位范围。在线 ID 必须满足当前长度约束，例如：

```text
CR6-<run8>-<farm><asset>-E<event>
```

禁止把多个重叠事件包直接回放到同一个 `CARE-<farm>-<asset>` 在线时序中。

如果未来需要在一个在线资产中合并多个 replay run，必须先扩展服务端 stream key、查询、访问控制和模型窗口，使它们显式包含 replay run；不能只修改前端过滤。

### 9.2 BenchmarkReplayRun

新增正式回放运行实体，至少包含：

- `benchmark_replay_run_id`；
- dataset/version、farm、event 和逻辑资产；
- 隔离虚拟风机 ID；
- replay mode、速度和状态；
- 合成时间 anchor 和时间规则版本；
- sequence 规则版本；
- source event ID 规则版本；
- 选择的变量和窗口；
- 模型/deployment/threshold policy；
- 创建者、取消者、开始/结束时间和错误；
- 上次确认的 row/sequence 检查点。

幂等性定义为：同一 replay run 的同一步骤重试不重复；新 replay run 是新的、可审计的业务运行。

### 9.3 合成回放时间轴

原始时间仅保存在属性和证据中。在线 `observed_at` 使用确定性合成规则，例如：

```text
observed_at = replay_anchor_at + source_row_id * 10 minutes
```

具体规则在阶段 0C 冻结，并满足：

- `replay_anchor_at` 在 run 创建后不可变；
- 同一 run 重试生成相同时间；
- 时间位于平台可查询的 LIVE/24H/30D 范围或明确的历史回放范围；
- 不声称合成时间是场站真实时间；
- 原始 `source_time_stamp`、`anonymous_observed_at`、原始间隔和时间规则版本均保留；
- 如需保留原始间隔而非固定 10 分钟，必须定义另一独立、版本化模式，不能混用。

### 9.4 Sequence 和事件幂等键

当前水位按 `source_id + turbine_id + variable` 维护。首版事件级回放实例下：

- 每个 variable 的 `source_sequence` 可使用连续 `source_row_id`；
- 一个回放实例只绑定一个事件包，避免跨事件从 0 重置；
- 窗口裁剪仍保留原始 row ID，不重新从 0 编号；
- 运行恢复从持久化检查点继续；
- 不得跨 replay run 复用在线虚拟风机 ID。

`source_event_id` 包含 dataset version、replay run、event、row 和 variable identity。考虑现有 128 字符限制，variable 使用稳定短 ID 或内容哈希，并通过映射表还原：

```text
care6:<run-id>:<farm>:<event>:<row>:<variable-hash>
```

### 9.5 SCADA 接入边界

- 使用现有 `/api/v1/scada/ingest`，每批最多 1000 条；
- `source_id` 使用受治理的 `care-v6-replay`；
- 生产环境预先配置接入源、权限、允许变量和单位契约；
- 只接入精选 Avg 信号和指定窗口；
- `status_type_id` 放入 attributes，不伪装成数据质量；
- 原始质量问题通过 quality code/attributes 引用质量规则；
- 模型异常结果写入受治理模型预测记录，不只塞进 SCADA attributes。

### 9.6 模型预测到告警的来源模型

当前告警依赖 ingest receipt，且自动触发器只识别单样本 `main_bearing_vibration_rms`。需要迁移为通用告警来源：

- `Alarm.source_event_id` 兼容既有 SCADA 告警，但允许模型预测作为主来源；
- 新增 `model_prediction_id` 外键或等价的通用告警来源关联；
- 数据库约束保证告警至少有一个有效来源；
- 模型告警可同时引用预测、原始样本窗口和评估/回放运行；
- 现有 SCADA 告警保持兼容；
- 不创建假的 ingest receipt，也不把任意 CARE 信号改名为主轴承振动。

### 9.7 通用告警策略状态

策略按模型版本、部件、资产范围和 deployment version 管理，至少包含：

- 触发阈值；
- 连续 N 窗口；
- 恢复阈值；
- 冷却期；
- 告警去重键；
- 策略版本和启停状态；
- 当前连续计数、恢复计数和上次告警状态；
- 对乱序、缺失窗口和质量不确定样本的处理规则。

告警状态由服务端持久化，不能依赖单个请求内存或前端状态。

## 10. 前端展示方案

### 10.1 数据中心

扩展现有数据目录类型，增加 `benchmark` 或等价类别，显示：

- CARE v6 版本、DOI、许可证、ZIP 大小和双校验和；
- 风场、资产、事件、split 和字段覆盖；
- 原始层、标准层、质量层和导入状态；
- 字段/单位/质量规则版本；
- 零值、连续零段、状态可信度、缩放功率和统计量风险；
- 启用、禁用、未知和失败映射列数；
- 事件目录、访问受控的真值信息；
- 降采样关键曲线；
- 最近导入、评估和回放运行状态。

### 10.2 模型管理

显示：

- 现有 RegisteredModel ID/version；
- 模型类型 `anomaly`；
- 特征集合、threshold policy 和评估协议；
- CARE Score 及组成项；
- 正常误报和异常检测指标；
- 分风场/资产结果；
- 评估覆盖、失败事件和不可评分事件；
- 服务器端门槛结论；
- 不可变报告和预测制品。

### 10.3 诊断中心

对回放事件展示：

- 明确标记的合成回放时间轴；
- 原始匿名时间只作为来源证据；
- 降采样关键信号、质量 mask 和运行状态；
- anomaly score、binary prediction 和 threshold；
- 模型最早告警点和提前量；
- 模型预测、告警、Mission 和决策链路；
- 评估前隐藏、评估后按权限揭示的真值区间和故障描述。

### 10.4 明确不做

首版不开发：

- 浏览器加载完整事件 CSV；
- 同时绘制 957 个信号；
- 任意 SQL/Notebook 在线环境；
- 通用机器学习训练 IDE；
- 原始数据在线编辑；
- 将 CARE 数据复制到前端静态资源；
- 用 UI 配置绕过服务器端模型激活门槛。

## 11. 数据库实体与迁移边界

建议新增或扩展以下实体，最终以迁移设计评审为准：

| 实体                      | 用途                     | 关系/约束                                      |
| ------------------------- | ------------------------ | ---------------------------------------------- |
| `BenchmarkDatasetVersion` | 数据集版本和许可证       | 唯一 dataset/version/content hash              |
| `BenchmarkFile`           | 文件清单                 | 关联 dataset version，保存 SHA-256/schema hash |
| `BenchmarkEvent`          | 事件索引                 | 唯一 dataset version + event ID                |
| `BenchmarkFeatureMap`     | 原始列映射               | 映射版本内 source column 唯一                  |
| `BenchmarkQualityReport`  | 质量摘要和制品引用       | 关联 event/feature/rule version                |
| `BenchmarkEvaluationRun`  | 不可变评估运行           | 关联现有 RegisteredModel/version               |
| `BenchmarkEventResult`    | 事件级分数和制品         | 唯一 evaluation run + event                    |
| `BenchmarkMetricSnapshot` | 结构化发布指标           | 指标名、协议、版本和数值唯一                   |
| `BenchmarkReplayRun`      | 回放隔离、时间和检查点   | 唯一 run ID 和在线虚拟资产                     |
| anomaly 模型类型/契约     | 无 RUL 的异常模型        | 扩展现有模型注册和预测表                       |
| 告警来源关联              | 预测/SCADA 到告警溯源    | 至少一个有效来源，兼容既有数据                 |
| 告警策略状态              | N 窗口、冷却、恢复、去重 | 按策略/部署/资产或部件唯一                     |

数据库变更必须通过 Alembic migration，考虑既有数据回填、约束上线顺序、索引、事务和回滚风险。禁止只修改 ORM。

## 12. 分阶段实施计划

### 阶段 0A：真实数据契约

任务：

- 固化 ZIP MD5/SHA-256 和 101 个 CSV 清单；
- 固化真实 `statistics_type` 解析；
- 建立 A 场八个裸 average 列映射；
- 双向校验文件名事件 ID 和 `event_info.csv`；
- 固化单位、缩放、零值、状态和匿名时间语义；
- 建立质量 mask 规范；
- 用 A/B/C 各一个小型固定样例验证映射和有界内存读取；
- 形成列式引擎与 Parquet 布局 ADR。

完成标准：见第 16 节 P0 通过门槛。

### 阶段 0B：评分协议

任务：

- 冻结 `care-score-v6` 公式、常量和状态规则；
- 冻结 A/B/C 状态过滤差异；
- 冻结 threshold 校准边界；
- 建立黄金向量和权威期望输出；
- 定义开发、调参和最终测试运行状态；
- 定义单事件和场内泛化协议；
- 暂停跨场协议，直到 ontology 评审完成。

完成标准：见第 16 节 P0 通过门槛。

### 阶段 0C：平台兼容设计

任务：

- 冻结 replay run、逻辑资产和在线实例模型；
- 冻结合成时间、sequence、幂等键和检查点；
- 设计 anomaly 模型运行契约；
- 设计模型预测到告警的来源和外键；
- 设计连续窗口、冷却、恢复和去重状态；
- 设计现有 RegisteredModel 的复用关系；
- 设计数据库 migration、对象存储和 CLI/Worker 边界；
- 设计服务器端评估激活门槛。

完成标准：见第 16 节 P0 通过门槛。

### 阶段 1：最小导入验证

先导入 A 场一项异常和一项正常事件，不直接导入全部 A 场。

任务：

- 生成原始清单和文件 hash；
- 输出宽表 Parquet 和独立质量制品；
- 验证 81 个 A 场信号全部映射；
- 验证标签隔离和 train/validation/prediction 边界；
- 验证重复导入的确定性；
- 测量峰值内存、吞吐、取消、恢复和失败清理；
- 核验制品级许可证元数据。

通过后扩展到 A 场全部 22 个事件。

### 阶段 2：离线基准

任务：

- 建立简单基线和目标 anomaly 模型；
- 使用冻结的 `care-score-v6`；
- 保存 score、binary prediction、threshold、mask 和事件级结果；
- 确保 prediction 真值不参与调参；
- 将正常事件、失败事件和不可评分事件全部纳入汇总；
- 关联现有 RegisteredModel；
- 生成不可变指标快照和报告。

完成标准：

- 相同清单、规则、模型、种子和评估器可复现；
- 黄金测试全部通过；
- 每项指标可追溯到事件预测制品；
- 没有通过排除失败事件改善指标。

### 阶段 3：平台垂直切片

只有 anomaly 运行时、预测溯源、告警来源、通用策略和 replay run 隔离完成后才开始。

任务：

- 为 A 场一项异常和一项正常事件分别创建回放实例；
- 配置受治理的 `care-v6-replay` 来源和变量契约；
- 回放少量关键 Avg 信号；
- 持久化 anomaly prediction；
- 由通用策略创建或抑制告警；
- 验证 Mission、诊断、决策和审计链路；
- 验证同一 run 重试幂等、新 run 隔离。

完成标准：

- 水位、sequence、时间、预测唯一约束均无冲突；
- 最新窗口查询不会跨事件或跨 run 拼接；
- 告警直接引用模型预测；
- 正常事件验证误报抑制；
- 真值未参与在线触发。

### 阶段 4：界面

任务：

- 扩展后端数据目录和前端 `benchmark` 类别；
- 展示清单、质量、映射和导入状态；
- 在模型管理展示评估运行和服务器端门槛；
- 在诊断中心展示合成时间、预测和业务闭环；
- 增加受控 CSV/JSON 报告导出；
- 加入许可证、归属和修改说明。

完成标准：

- 页面不读取原始 CSV；
- 大列表分页或有界查询；
- 曲线服务端降采样；
- UI 状态与权威后端一致；
- 真值揭示符合访问控制。

### 阶段 5：规模化与发布

任务：

- 扩展到 C 场，再按专项需求扩展 B 场；
- 最终覆盖全部 95 个事件；
- 完成场内泛化；
- 建设跨场 ontology 后再启用跨场迁移协议；
- 建立模型候选发布门槛和评估回归；
- 完成性能、权限、备份恢复和故障注入验证；
- 编写运行手册、许可证说明和发布说明。

完成标准：

- 全量运行有稳定资源上限；
- 任务失败、数据损坏和存储不可用均有明确状态；
- 发布门槛由服务器强制执行；
- 来源、转换、许可证和制品可审计。

## 13. 测试计划

### 13.1 导入与契约测试

- 分号、UTF-8 BOM 和字符损坏；
- 真实 `statistics_type` 和集合规范化；
- `asset` / `asset_id`；
- A 场八个裸 average 列；
- 文件名事件 ID 与元数据双向校验；
- A/B/C 的 81/252/952 列全映射；
- 未知、缺失、重复和歧义映射失败关闭；
- 时间戳、row ID、split、状态和单位；
- 标签字段不进入特征矩阵；
- schema hash、row count 和 content hash 可重复。

### 13.2 数据质量测试

- 零值比例和最长连续零段；
- 合法零值不被全局改写；
- 原值与质量 mask 分离；
- B/C 状态短暂不一致；
- A 场 prediction 状态例外；
- 功率缩放语义；
- Min/Avg/Max/Std 物理约束；
- 常量、null、NaN、Infinity、异常跳变和采样间隔；
- 事件区间在 ID 范围内；
- 单事件单资产约束。

### 13.3 评分黄金测试

- all-normal、all-anomaly、无告警；
- criticality 71/72/73；
- 正常事件持续误报；
- A 场状态例外和 B/C 状态过滤；
- Earliness 前半段、后半段和终点；
- `Accuracy < 0.5`；
- 无有效点和 threshold 相等边界；
- score、binary prediction 和 threshold 均保存；
- prediction 真值无法被训练或校准组件读取。

### 13.4 模型运行时和发布测试

- anomaly 模型无需 RUL/30 天概率即可注册和推理；
- predictive 模型原有契约保持兼容；
- anomaly 输出缺少必要字段时失败；
- 输入窗口不能跨 event/replay run；
- 评估运行和指标快照不可变；
- 未达门槛、失败事件缺失或版本不匹配时不能激活；
- 前端或任意 JSON 无法绕过服务器门槛。

### 13.5 回放与告警集成测试

- 每批 1000 条限制和接入源权限；
- 同 run 重试幂等、新 run 独立；
- 虚拟在线资产不复用；
- sequence 单调和水位恢复；
- 合成时间确定且位于预期查询窗口；
- 乱序、迟到、隔离和检查点恢复；
- model prediction 外键和告警来源约束；
- 连续 N 窗口、冷却、恢复和去重；
- 正常事件不产生无依据告警；
- Mission/诊断/决策链路完整。

### 13.6 性能和韧性测试

- 单事件和 C 场大文件峰值内存；
- 全量导入和评估耗时；
- Parquet 列裁剪、row group 和压缩效果；
- Worker 心跳、取消、恢复和重试；
- MinIO/数据库短暂不可用；
- 回放限速和数据库写入速率；
- 前端分页和曲线降采样响应时间。

## 14. 安全、权限与许可证

### 14.1 安全和隔离

- CARE 与生产数据使用独立来源、命名空间、对象存储前缀和权限范围；
- 原始数据、标准层和预测制品不得进入 Git 或前端构建物；
- 真值和故障描述按评估角色控制访问；
- 导入、转换、评估、回放、导出和删除均写审计日志；
- 不记录密钥、令牌或对象存储凭据；
- 清理任务只能操作解析后确认属于指定 dataset version/run 的派生分区；
- replay run 不能读取或污染真实生产资产。

### 14.2 制品级许可证要求

每个标准 Parquet、派生数据导出和报告附件至少携带：

- 数据集名称和作者归属；
- 推荐引用文本；
- Zenodo 原始记录 URL 和 DOI；
- CC BY-SA 4.0 名称和链接；
- `changes_made`；
- 转换、字段映射和质量规则版本；
- 原始数据集版本和内容哈希；
- 制品许可证声明。

CARE 数据制品许可证与 WindOps MIT 源代码许可证分离。对外分发前复核制品类型和 ShareAlike 适用性；本节为工程合规要求，不替代法律意见。

## 15. 风险与缓解

| 风险                       | 影响               | 缓解措施                                |
| -------------------------- | ------------------ | --------------------------------------- |
| 仅按后缀映射信号           | A 场裸列丢失       | 元数据驱动映射、显式别名、全列闭合验收  |
| 把零值全局转为缺失         | 删除合法物理值     | 特征级规则和独立质量 mask               |
| Min/Max/Std 不合理         | 模型学习错误模式   | 默认禁用，逐特征审计后启用              |
| prediction 真值参与调参    | 指标虚高           | train 内 validation、最终测试不可变     |
| CARE Score 实现偏差        | 模型排名不可比     | 冻结 `care-score-v6` 和黄金向量         |
| 重复训练历史泄漏           | 泛化结果虚高       | 禁止随机行拆分，按事件/资产审查重复数据 |
| 跨风场匿名编号误对齐       | 伪泛化             | 首版禁用，先建人工审核 ontology         |
| 全量展开 TimescaleDB       | 存储和查询失控     | 宽表 Parquet，在线只保存精选信号        |
| 大文件在 API 事务中处理    | 超时和资源耗尽     | 独立 CLI/Worker、有界内存和检查点       |
| 跨事件复用 sequence/时间   | 水位隔离、时序污染 | replay run + 事件级在线资产 + 合成时间  |
| 运行时强制 RUL             | 伪造模型输出       | 新增正式 anomaly 契约                   |
| 告警只能依赖 SCADA receipt | 无法追溯模型预测   | 增加 prediction 告警来源和外键          |
| 前端门槛可绕过             | 未验证模型上线     | 服务器端不可变评估门槛                  |
| 功率缩放被误解             | 错误设备结论       | 显式缩放语义，禁止绝对功率解释          |
| 许可证声明缺失             | 合规风险           | 制品级归属、修改说明和 ShareAlike 复核  |

## 16. 阶段 0 强制通过门槛

进入阶段 1 前必须全部满足：

- [ ] ZIP MD5/SHA-256 和 101 个 CSV 的大小、SHA-256、行数、schema hash 已固化；
- [ ] A/B/C 的 81/252/952 个信号全部一一映射，无未知或静默丢弃列；
- [ ] `statistics_type`、A 场八个裸列和 event ID 来源已固化并有测试；
- [ ] B/C 零值缺失、连续零段和状态不一致进入质量规则；
- [ ] 缩放功率和跨事件匿名时间语义得到显式标记；
- [ ] 原始数值与独立质量 mask 均可追溯；
- [ ] `care-score-v6` 公式、常量、状态规则、边界和黄金向量冻结；
- [ ] threshold/超参数无法读取 prediction 真值；
- [ ] 每风机年误报指标保持禁用，除非暴露时间去重得到证明；
- [ ] replay run、逻辑资产、在线实例、合成时间、sequence 和幂等键无冲突；
- [ ] anomaly 模型无需输出 RUL 或 30 天故障概率；
- [ ] 告警能够引用模型预测并具备连续窗口、冷却、恢复和去重状态；
- [ ] 模型发布门槛由服务器端执行并关联不可变评估运行；
- [ ] Parquet 明确保持宽表并由独立 CLI/Worker 有界处理；
- [ ] 专用 MinIO prefix、生命周期、访问控制和备份范围明确；
- [ ] 现有 RegisteredModel、访问控制、数据目录和 migration 关系通过评审；
- [ ] SHA-256、来源、修改记录和 CC BY-SA 制品要求进入不可变清单。

任一项未满足时，阶段 0 状态保持未完成，不允许先标记通过再补实现。

## 17. 首个可交付版本

首个可交付版本控制为一个有真实门禁的垂直切片：

1. 完成阶段 0A/0B/0C 设计和黄金样例；
2. 导入 A 场一项异常和一项正常事件；
3. 生成不可变清单、宽表 Parquet、质量报告和 mask；
4. 运行一个简单基线和一个目标 anomaly 模型；
5. 使用冻结的 `care-score-v6` 保存 score、binary prediction 和 threshold；
6. 使用现有 RegisteredModel 和新的 anomaly 契约登记模型；
7. 分别创建两个隔离的 replay run 和在线虚拟资产；
8. 回放少量关键 Avg 信号并持久化模型预测；
9. 通过通用告警策略对异常事件触发、对正常事件抑制；
10. 验证告警、Mission、诊断、决策和审计证据链；
11. 在数据中心、模型管理和诊断中心展示受治理结果；
12. 验证许可证、归属和修改说明随导出制品传播。

该垂直切片验收后，先扩展到 A 场全部 22 个事件，再扩展 C 场和全量 95 个事件。

## 18. 总体验收标准

- 官方 ZIP 双校验和与文件级不可变清单验证通过；
- 95 个事件、36 台风机、45 个异常和 50 个正常事件统计一致；
- 全部 81/252/952 信号列有唯一、可审计映射；
- 零值、状态、统计量、单位、缩放功率和匿名时间均有显式规则；
- 原始数据只读，所有派生制品可追溯且带许可证元数据；
- 模型特征不包含真值，prediction 真值不参与阈值或超参数选择；
- `care-score-v6` 和配套指标由黄金测试验证且可复现；
- 正常、失败和不可评分事件均进入结果汇总；
- 完整数据保存在宽表 Parquet，TimescaleDB 未接收全量展开数据；
- anomaly 运行时不要求伪造 RUL，predictive 现有契约保持兼容；
- 每个 replay run 的资产、时间、sequence、查询和模型窗口相互隔离；
- 告警能够直接追溯到模型预测和原始证据；
- 连续窗口、恢复、冷却、去重和发布门槛由服务器端执行；
- 数据中心、模型管理和诊断中心展示一致的权威结果；
- 对外制品包含归属、DOI、许可证链接、修改说明和适用的 ShareAlike 声明。

## 19. 参考资料

- [CARE v6 Zenodo 记录](https://zenodo.org/records/15846963)
- [CARE to Compare 官方论文](https://doi.org/10.3390/data9120138)
- [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- [计划评审意见](./care-v6-integration-plan-review.md)
- [`backend/src/windops_backend/services/ingest.py`](../backend/src/windops_backend/services/ingest.py)
- [`backend/src/windops_backend/services/models.py`](../backend/src/windops_backend/services/models.py)
- [`backend/src/windops_backend/models.py`](../backend/src/windops_backend/models.py)
- [`backend/src/windops_backend/schemas.py`](../backend/src/windops_backend/schemas.py)
- [`backend/src/windops_backend/config.py`](../backend/src/windops_backend/config.py)
