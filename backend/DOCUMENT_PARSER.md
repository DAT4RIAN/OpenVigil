# 独立 PDF/OCR 文档解析

本增量在现有知识原件、段落、pgvector、权限、读审计与工程审核上增加 Docling 路径。默认仍使用原生解析；客户端明确提交 `parser: "docling"` 时，API 仅验证原件并事务性排队，不在 HTTP 中加载 OCR 或执行布局推理。这里的运行方法与本地验收不构成正式发布或现场精度资格。

## 运行边界

- `document-parse` 使用独立 Dramatiq actor，单进程、单线程；布局/OCR 在第二个独立 Python 中计算，API 与通用 worker 不安装这些数值依赖。
- 文档与解析事件保存原件 SHA-256、文档版本、模型清单 SHA-256、七个执行模块 SHA-256 和十二个核心包版本。执行时再次观察身份，任何漂移不能发布正文。
- 预取模型的文件大小与 SHA 全量核对，解析时关闭远程服务、外部插件和隐式下载。临时 HOME/模型缓存与凭据隔离，解析进程不继承数据库、对象存储和模型供应商凭据。
- 当前上限：50 MiB、200 页、页面宽高各 2000 PDF points、400 万字符、512 段，每段 8000 字符。子进程最多 180 秒、stdout 24 MiB、stderr 64 KiB；取消、超时或超限回收本任务子进程。加密 PDF、无文本结果和无法精确归属页面的跨页元素明确失败。
- 租约与发布事务防止过期 worker 写入。最多三次实际尝试；终态失败不生成正文、段落或向量。非终态失败与到期租约由现有 relay 恢复，原始失败事件保留。

## 准备隔离依赖与模型

Python 3.12。选择项目内独立环境，保持 API 环境原依赖。固定锁包含 CPU PyTorch 和平台条件；不要将整份解析锁安装进 API 环境。

```powershell
uv venv .artifacts/document-parser/runtime --python 3.12
uv pip sync --python .artifacts/document-parser/runtime/Scripts/python.exe backend/requirements.document-parser.txt --require-hashes --torch-backend cpu
.artifacts/document-parser/runtime/Scripts/python.exe scripts/prepare-document-models.py --output .artifacts/document-parser/models
Get-FileHash .artifacts/document-parser/models/openvigil-model-manifest.json -Algorithm SHA256
```

模型准备脚本执行受限公共下载并验证固定来源/权重。布局模型来自固定 Heron commit，TableFormer 来自固定 Docling models commit，中文检测/识别/方向模型来自冻结 RapidOCR registry SHA。清单记录许可证及原始链接。已有清单的模型目录会核验，不覆盖已有权重。模型准备完成后可移除网络下载权限；运行时不需要网络推理。

## API、通用 worker 与专用 worker 的配置

使用现有配置加载方式，给 API、relay 和专用 worker 提供相同模型清单与当前源码身份。以下值是配置示例；设置前先计算实际清单 SHA，不修改现有 `.env` 的凭据。

```text
WINDOPS_DOCUMENT_PARSER_ENABLED=true
WINDOPS_DOCUMENT_PARSER_PYTHON=<isolated Python absolute path>
WINDOPS_DOCUMENT_PARSER_MODELS_PATH=<model directory absolute path>
WINDOPS_DOCUMENT_PARSER_MODEL_MANIFEST_SHA256=<actual lowercase SHA-256>
WINDOPS_DOCUMENT_PARSER_RUNTIME_DIRECTORY=<writable task scratch directory>
```

启动专用队列：

```powershell
backend/.venv/Scripts/python.exe -m dramatiq windops_backend.document_parse_tasks --queues document-parse --processes 1 --threads 1
```

保留现有通用 worker、Outbox relay 与读审计 worker。`GET /api/v1/knowledge/parser-capabilities` 仅声明配置状态，`worker_health_verified` 始终为 false；不得把它当作 worker 探活或 OCR 精度验收。

专用 Linux 镜像使用 `backend/Dockerfile.document-parser`，必须传入不可变 API 基础镜像。构建会核对 API 的基础依赖锁，安装独立 `/opt/document-parser` 环境与实际需要的 OpenCV 动态库，并重新安装本次源码的业务包。子进程使用 Python `-I` 隔离模式和显式包路径加载，不把 API 的整个 `site-packages` 加入独立解析环境。模型另以只读目录挂载到 `/models`，实际清单 SHA 由运行配置提供；UID/GID 10001，`/tmp` 使用可写、有容量限额的临时挂载。镜像不包含模型或生产凭据。新 worker 尚不能由既有双镜像发布报告自动获得资格；正式发布需要单独纳入签名、SBOM/CVE、部署网络/资源政策及同版本联合验收。

## 页面来源与人工复核

状态依次为 `pending_parse → parsing → pending → indexed`；失败重试回到 `pending_parse`，耗尽为 `parse_failed`。重放同一原件/版本/范围/解析器不会生成第二个解析事件；换解析器必须使用新的不可变文档 ID。未知提交响应保留文件、文档 ID 和幂等键，阻止换输入，并核验同一提交。

原生路径保留旧v1请求哈希格式，旧客户端省略parser及新客户端显式native可重放同一旧键；Docling是不同输入，不能用原生旧键切换。每次重放仍先核对当前范围权限，撤权后不会返回旧收据或增加重放次数。

每段保留正文偏移、文本 SHA、实际页码与 top-left PDF points 矩形，空白页不重新编号。表格单元格保留实际行列，但页面矩形的精度是整个表格区域 `table_region`；页面区域示意不是原 PDF 的像素预览，也不宣称精确单元格框。原件链接由后端重新校验 SHA 与权限后短时签发。

所有 OCR 段落标记 `requires_numeric_review=true`。索引成功与原件字节一致，只证明来源和数据流；数字、正负号、小数点、单位及表格读序仍需对照原件人工核对。不能由 OCR 自动授予作业许可、填补缺失工程阈值或声明绝对索力。领域精度、真实校准/规程、责任人和现场影子运行待实际资料验证。

## 隔离验收

先准备明确的扫描测试 PDF，再运行受控业务验收；以下参数需指向本仓库 `.artifacts` 中的实际文件。该 harness 创建随机名称、仅 loopback 暴露的四个依赖与任务进程，结束后清理自己创建的服务和测试卷，并保存报告、原始失败、浏览器 trace、数据库/对象/图谱收据。身份、扫描资料、嵌入模型和 release 是声明测试资料，不是生产数据。

```powershell
backend/.venv/Scripts/python.exe backend/scripts/run_business_e2e.py --scenario document --document-python .artifacts/document-parser/runtime/Scripts/python.exe --document-models .artifacts/document-parser/models --document-fixture .artifacts/document-parser/synthetic-scan.pdf
```

Linux 本地构建与无网络/只读/非 root 的真实 OCR 探针：

```powershell
backend/.venv/Scripts/python.exe backend/scripts/verify_document_image.py --api-base <actual local API runtime> --models .artifacts/document-parser/models --fixture .artifacts/document-parser/synthetic-scan.pdf
```

此 Linux 探针专用于本次两页中文测试资料（空白第一页、十五段及九个表格单元格），不是任意文档精度评价。验收结论以不可变报告的 `passed`、`cleanup_passed` 与当前源码身份为准，不能仅凭命令启动或界面出现判断完成。
