<p align="center">
  <img src="public/images/openvigil-logo.png" alt="OpenVigil" width="140">
</p>

<h1 align="center">OpenVigil</h1>
<p align="center"><a href="README.md">English</a> · <a href="README-CN.md">简体中文</a> · <a href="README-DE.md">Deutsch</a> · <a href="README-ES.md">Español</a> · <a href="README-FR.md">Français</a> · <b>日本語</b> · <a href="README-KO.md">한국어</a> · <a href="README-IT.md">Italiano</a></p>
<p align="center"><b>風力発電の運用・保守を支えるマルチエージェントプラットフォーム</b><br>監視、診断、人による意思決定、現場作業を、監査可能なワークフローでつなぎます。</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="Apache License 2.0">
  <img src="https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=111827" alt="React 19.2">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/status-production%20candidate-f59e0b" alt="本番導入候補">
</p>

<p align="center">
  <a href="#インストール">インストール</a> ·
  <a href="#クイックスタート">クイックスタート</a> ·
  <a href="#機能">機能</a> ·
  <a href="#アーキテクチャ">アーキテクチャ</a> ·
  <a href="#モデル設定">モデル設定</a> ·
  <a href="#開発">開発</a> ·
  <a href="#ライセンス">ライセンス</a>
</p>

---

<p align="center">
  <img src="public/openvigil-command-center.png" alt="OpenVigil 運用コマンドセンター" width="960">
</p>

> _風力発電の運用情報は、設備、SCADA、アラーム、モデル、人による承認、作業指示書、現場の証拠に分散しがちです。課題は、すべての判断に根拠を持たせ、すべての意思決定に責任者を割り当て、すべての作業結果を検証できるようにすることです。_
>
> _OpenVigil は「監視 → アラーム → Mission → 診断 → 人による意思決定 → 作業指示書 → 現場の証拠 → 健全性の再評価 → ナレッジ更新」を、追跡・復旧が可能で権限管理されたワークフローにつなぎます。AI は証拠を整理して代替案を提案し、高リスクの作業は人が承認します。_

## プロジェクトの状況

> [!IMPORTANT]
> OpenVigil は現在、**本番導入候補の実装**であり、すでに本番運用されているシステムではありません。既定の `demo` モードは決定論的な製品デモを提供します。`production` モードは、正式な状態を管理する独立配備の Python バックエンドに接続し、ID、設定、依存サービス、API が要件を満たさない場合は処理を拒否します。実際の風力発電所、現場システム、モデルプロバイダー、リリース環境については、引き続き合同の受け入れ試験が必要です。

本製品は風力発電のインテリジェントな運用・保守プラットフォームとして位置付けられています。ログイン画面の画像と Demo の発電所はシナリオの例であり、製品の対象範囲を定義するものでも、現場との接続や本番受け入れを証明するものでもありません。

この文書は **2026-10-08** に現在のリポジトリと照合しました。既存の風車保守フローに加え、現段階では**陸上ハイブリッドタワー**を優先します。構造監視、管理された再測定フロー、独立 PDF/OCR 知識取り込みを実装済みです。2026-10-07 の最新パーサー検証は `COMPLETE_LOCAL_SOFTWARE_VERIFIED` で、ローカルソフトウェアと隔離 Linux 実行を対象とします。現場精度、実際の校正・手順、シャドー運用、正式リリース資格は `UNVERIFIED` です。[実行進捗](EXECUTION_PROGRESS.md) で現在の結論と過去の記録を区別しています。

## インストール

### 必要条件

- Node.js `>= 22.13.0`
- pnpm `11.21.0`。Corepack による管理を推奨
- Python `3.12.x`。`backend/` を使用する場合のみ必要
- Docker Compose。Python バックエンドのローカル依存サービス起動に使用する場合のみ必要

### コードの取得

```bash
git clone --recurse-submodules https://github.com/DAT4RIAN/OpenVigil.git
cd OpenVigil

corepack enable
pnpm install --frozen-lockfile
```

このリポジトリは `pnpm-lock.yaml` を使用します。`package-lock.json` を生成・コミットしたり、同じ変更で npm と pnpm のロックファイルを混在させたりしないでください。

## クイックスタート

### 製品デモ

```bash
pnpm dev
```

`http://localhost:3000` を開きます。既定の Demo には、決定論的な 64 基の風車設備、WT-023 の主軸受異常シナリオ、D1 のワークフロー状態、有限の SSE ストリーム、模擬 WebSocket、16 個のツールを備えたエージェント実行環境が含まれます。製品デモ、スクリーンショット、回帰確認に使用できます。

### 本番向けビルド

```bash
pnpm build
pnpm start
```

`pnpm start` はリリースに使用するものと同じビルド成果物を配信します。既定では引き続き Demo で動作します。本番モードには、設定済みの Sites Worker、Python バックエンドのアドレス、委任された ID、承認済みリリース ID、イメージのダイジェストが必要です。未移行のルートはフィクスチャにフォールバックしません。

### Python バックエンドの垂直スライス

以下のコマンドを Windows PowerShell で実行します。リポジトリルートの `.env` が唯一のローカル設定ファイルです。まだ存在しない場合に限り、`.env.example` から作成してください。

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test,dev,structural]"

docker compose up -d
alembic upgrade head
windops-reference-import --reference-pack wt023
```

現在の唯一のマイグレーション head は `0032_structural_workflow` です。`backend/` から `python scripts/verify_migration_head.py` を実行すると、マイグレーショングラフと文書内の宣言を確認できます。

参照データのインポートでは `operations_manager` のキーが要求されます。その後、outbox リレー、Dramatiq ワーカー、読み取り監査ワーカー、API をそれぞれ別の 4 つのターミナルで起動します。

```powershell
windops-outbox-relay
dramatiq windops_backend.workers
windops-read-audit-worker
uvicorn windops_backend.main:app --host 127.0.0.1 --port 8000
```

### 任意の分析ワーカー

構造分析を手動起動する場合、上記 4 サービスを維持し、別のターミナルで `backend/` から同じ設定と有効化済み環境を使って専用キューを起動します。`structural` extra が pyOMA2 を提供し、長時間の計算は HTTP 処理外で実行します。

```powershell
python -m dramatiq windops_backend.structural_tasks --queues structural-analysis --processes 1 --threads 1
```

PDF/OCR は既定で無効です。独立 Python 環境、事前取得モデル、実際のモデルマニフェスト SHA-256、専用 `document-parse` ワーカーが必要です。ハッシュ固定インストール、`WINDOPS_DOCUMENT_PARSER_*`、ワーカーコマンド、Linux イメージ、隔離検証は [DOCUMENT_PARSER.md](backend/DOCUMENT_PARSER.md) を参照してください。OCR 依存関係は API 環境に入れません。

### Windows での再現可能なローカル起動

フロントエンドの依存関係をインストールし、`backend/.venv` を作成した後、リポジトリルートで次のコマンドを実行します。

```powershell
./scripts/Start-Local.ps1
./scripts/Status-Local.ps1
./scripts/Stop-Local.ps1
```

初回起動の既定ポートはフロントエンドが `3000`、API が `8000` です。空いているポートを指定するには `-FrontendPort 3180 -ApiPort 8180` を使用します。以後の起動では保存済みポートを再利用し、プロセスを作る前に既存サービスを確認します。ポート競合やプロセス ID の不一致があれば処理を停止します。スクリプトはポートを占有するプロセスを終了しません。

これは分離された開発用スタックです。フロントエンドは Demo のままで、独立した Python バックエンドは `development / deterministic / static_tokens` を使用します。本番ゲートウェイとの接続や実モデルの受け入れを証明するものではありません。スクリプトはリポジトリのパスから別の Compose プロジェクトを生成し、PostgreSQL `25432`、Redis `26379`、MinIO `29000/29001`、Neo4j `27474/27687` を使用します。すべてのポートはループバックアドレスにバインドされます。

生成されたローカル認証情報、Compose 設定、プロセス識別情報、ログは、Git の対象外である `.artifacts/local-stack/` に保存されます。この設定は分離起動専用で、ユーザーのルート `.env` を読み取ったり上書きしたりせず、参照データも自動インポートしません。通常の手動起動では引き続きルート `.env` を使用します。この成果物ディレクトリを共有・コミットしないでください。

起動処理は依存サービスを待ち、Alembic マイグレーションを適用してフロントエンドをビルドし、API、Dramatiq、outbox リレー、読み取り監査ワーカー、フロントエンドを起動します。状態確認ではマイグレーション head、Redis、5 つの MinIO バケット、Neo4j、API 認証、現在のリクエストに対する読み取り監査の永続化、ログイン画面を検証します。失敗時には調査のために依存サービス、データ、プロセスログを保持します。`Stop-Local.ps1` は PID、作成時刻、コマンド、リポジトリへの所属を確認してから対応するプロセスと Compose プロジェクトを停止します。コンテナ、認証情報、データボリュームは保持されます。

管理起動は専用 `structural-analysis` ワーカーも起動します。OCR モデルの準備や `document-parse` の起動は行いません。必要な場合は上記の独立パーサー設定を使用します。

スタイルシートのエントリーポイントやデータベースマイグレーションを変更したら、`pnpm check:architecture --write` を実行し、更新されたアーキテクチャ一覧を確認してください。`pnpm check:architecture` と CI は古い一覧を拒否します。

## 機能

### 運用コマンドセンター

ホーム画面は、設備群の KPI、健全性マトリクス、出力トレンド、優先度の高いアラーム、進行中の Mission、Agent Activity をまとめ、発電所で起きていることと AI の作業状況を表示します。

### 運用・保守ワークフロー

```text
SCADA / CMS / 気象 / 手動アラーム
              │
              ▼
       アラーム → Mission
              │
              ▼
  マルチエージェントによる証拠整理と診断
              │
              ▼
  代替案と人による承認
              │
              ▼
  作業指示書 → 順序付けされた現場作業
              │
              ▼
  健全性の再評価 → ナレッジ更新
```

WT-023 の Demo は、主軸受の振動・温度異常から、Mission 作成、診断、代替案比較、承認、作業指示書、5 つの現場作業、健全性の回復、ナレッジの記録までを一貫して扱います。すべての書き込みに冪等性キー、相関 ID、期待リビジョン、追記専用の監査イベントが付与されます。

Python バックエンドの実行可能な推奨事項は、`execution_plan_id` によって現在の Mission の管理対象作業テンプレートに結び付ける必要があり、実施内容もそのテンプレートと一致しなければなりません。テンプレートは `analysis_profile.work_order_plan` またはサーバー既定の点検テンプレートから取得します。その内容と設備範囲から結び付け識別子が決まります。結び付けが欠落、不明、古い、または不一致の場合、承認時に 409 を返します。結び付けのない古い意思決定は改訂が必要です。交換などの未結び付けの提案は検討用に残せますが、黙って点検作業指示書に変換されることはありません。作業、測定閾値、安全要件、所要時間、完了条件は常に管理対象テンプレートから取得します。

5 種類の AI レビューは、評価対象の候補案と作業テンプレートを記録する明示的な `review_target` を共有します。レビューはその保守計画の実行を評価します。前提条件は `conditions`、風車の運転制約は `operating_constraints` に保存します。レビューは運転許可を与えるものではなく、実行には引き続き人による承認が必要です。有効な不合格レビューは保持されます。明示的な対象がない過去のレビューを、検証済みの新しいレビューに自動昇格させることはありません。

実モデルの実行台帳は、`evaluation_result.request` にリクエストのダイジェスト、UTF-8 バイト単位のメッセージサイズ、出力トークン設定を記録し、リクエスト本文は保存しません。レスポンスには終了理由と公開レスポンスのサイズも記録します。プロバイダーが途中切断と示したレスポンスは、JSON として解析できても拒否します。後続ノードの失敗や業務トランザクションのロールバック時には、失敗記録内の `completed_node_usage` が同じ試行内で先に成功したモデルノードの使用量、モデル ID、遅延を保持します。ロールバックされた意思決定の出力は保持しません。失敗ノードの使用量が不明なら、その試行の費用を完全に確定したものや無料とは扱えません。存在しない過去の記録を作り上げることはありません。

### 業務ワークスペース

| ワークスペース         | ルート                               | 主な機能                                                           |
| ---------------------- | ------------------------------------ | ------------------------------------------------------------------ |
| 運用コマンドセンター   | `/`                                  | 設備群の状態、リスク対象、Mission、エージェント活動                |
| 発電所 / 風車          | `/wind-farms`, `/turbines/:id`       | 設備構成、健全性、SCADA、アラーム、保守コンテキスト                |
| SCADA / アラーム       | `/scada`, `/alarms`                  | 時系列監視、閾値、品質コード、異常、対応状況                       |
| エージェント / Mission | `/agents`, `/missions`               | エージェント構成、タスクキュー、証拠、協働履歴、承認準備状況       |
| 意思決定 / 作業指示書  | `/decisions`, `/work-orders`         | 代替案比較、人による承認、作業ゲート、現場の証拠                   |
| 健全性 / 予知保全      | `/health`, `/predictive-maintenance` | 健全性マトリクス、リスク順位、RUL 表示、保守期間                   |
| リソース / 保守        | `/resources`, `/maintenance`         | 作業班、部品、工具、気象条件に基づく作業期間、カレンダー、競合確認 |
| 構造                   | `/structural`                        | 部材、緊張材、校正、波形、モード分析、再測定、健全性レビュー       |
| ナレッジ / レポート    | `/knowledge`, `/reports`             | 証拠検索、ナレッジ事例、レポートプレビュー、PDF/DOCX 出力          |
| データ / モデル / 診断 | `/data`, `/models`, `/diagnosis`     | データガバナンス、CARE 評価、モデルゲート、診断の出所              |
| デジタルツイン / 設定  | `/digital-twin`, `/settings`         | 2D 運用ビュー、実行状態、ID、データポリシー                        |

デジタルツイン画面は運用コンテキストを提供します。物理シミュレーション、リアルタイム制御、工学用途の 3D モデルを実現しているとは主張しません。

### マルチエージェントの協働

Demo の 22 エージェントは 3 層で構成されます。

| 層       | 代表的な役割                                           | 責務                                                         |
| -------- | ------------------------------------------------------ | ------------------------------------------------------------ |
| 意思決定 | SCADA 分析、振動診断、予知保全、保守戦略               | 異常検出、証拠整理、診断と代替案の提案                       |
| レビュー | 安全、工学、経済、コンプライアンス、リソースのレビュー | 安全・工学・経済・コンプライアンス・リソース条件の確認       |
| 実行     | 作業指示書、作業班、部品、保守、レポート、ナレッジ     | 承認済みの意思決定を管理された実行とフィードバックにつなげる |

Python バックエンドは独立した LangGraph ワークフローと 18 ツールの SQL カタログを使用します。UI と API が公開するのは、公開可能で構造化された監査可能な証拠と結論だけです。モデルの非公開 Chain-of-Thought を表示したり作り上げたりしません。

### 陸上ハイブリッドタワーの運用

本番ワークスペース `/structural` はタワー部材、緊張材、校正済み測定チャンネル、原波形、直接張力測定、専用分析キュー、健全性基準を接続します。原本を SHA-256 で検証します。pyOMA2 FDD は品質除外、モード、未定量の不確かさを保持します。タワーモードから未校正の絶対張力は推定できません。

モード変動と直接プレストレスのシナリオは Mission、独立した工学レビュー、承認、再測定作業指示、健全性レビュー、審査待ち知識事例を再利用します。手順の段落は原文位置を保持します。グラフ結論の読み取りでは範囲、承認済み改訂、原本を再検証し、データ不足、撤回、期限切れ、出典変更時は利用を阻止します。

分析はアルゴリズム、実行コード、設定、校正の識別情報を固定します。ハイブリッド配置では API と構造イメージの digest、リリース bundle も固定します。結果ハッシュは PostgreSQL JSONB 再読み取り後も検証可能です。イメージ項目は配置宣言であり、未設定時は `unbound` です。観測された実行イメージの識別には配置と署名の証拠が必要です。

ローカル検証は合成信号、テスト ID、決定論的推論を使用します。実 SHM、タワーパラメーター、校正、許可済み手順、現場責任者は未提供です。SSI/減衰資格、校正済み絶対張力推定、OpenFAST/Kratos 研究には別途入力と検証が必要です。現場・正式リリース資格は `UNVERIFIED` のままです。

### 追跡可能な知識と PDF/OCR 解析

TXT、Markdown、PDF、DOCX のネイティブ解析が既定です。明示的な `parser: "docling"` は隔離 Docling による PDF レイアウト、表、中国語 OCR を選択します。API が原本を検証し、トランザクション内でキュー登録します。専用ワーカーは別の隔離 Python プロセスで計算します。原本 SHA-256、文書版、モデルマニフェスト、コードハッシュ、パッケージ ID を固定して再検証します。

- 知識画面は `pending_parse → parsing → pending → indexed`、再試行、終端 `parse_failed` を表示します。リースは古いワーカーの公開を阻止し、実際の試行は最大 3 回です。失敗・未完了の解析は検索可能な本文段落やベクトルを生成しません。
- 段落はテキストハッシュ、オフセット、実ページ番号、ページ領域、表の行列を保持し、空白ページを再番号付けしません。表の矩形は `table_region` であり、正確なセル枠や PDF ピクセルプレビューではありません。全 OCR 段落に `requires_numeric_review=true` を付け、工学用途の前に数値、符号、単位、読順を原本と照合します。
- ネイティブ v1 ハッシュと省略/明示 `native` のリプレイ互換性を維持します。パーサー変更には新しい不変文書 ID が必要です。送信応答が不明な場合はファイル、文書 ID、冪等キーを保持して確認し、各リプレイは現在の権限を検証してから受領記録を返します。
- 上限は 50 MiB、200 ページ、解析子プロセス 180 秒です。暗号化、空、破損、超過、ID 不一致の入力は明示的に失敗します。モデルを事前取得・検証し、実行時は暗黙のダウンロード、リモートサービス、外部プラグインを無効にします。

解析成功後に段落を公開し、既存 pgvector 索引と範囲管理された Neo4j 投影を要求します。原本リンクはハッシュと権限の再検証後に発行します。`GET /api/v1/knowledge/parser-capabilities` は設定の宣言だけで、`worker_health_verified=false` はワーカーの稼働証明ではありません。索引と出典は OCR 精度や現場作業許可を保証しません。[DOCUMENT_PARSER.md](backend/DOCUMENT_PARSER.md) を参照してください。

### CARE v6 ベンチマーク

CARE v6 は、独立したオフライン異常検出と管理された評価の経路を提供します。生データはリポジトリに含まれません。利用者が明示的に、利用許可のある読み取り専用ソースを用意する必要があります。

| 項目       | 現在の実装                                                                                                                              |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| データ契約 | 95 イベント、各発電所内の 36 設備、5,242,948 行。インポート順序は A → C → B に固定                                                      |
| 品質処理   | 生の値を保持し、品質問題は別のマスクに記録。正解データは予測を凍結した後にのみ評価器へ公開                                              |
| 保存       | 全信号をパーティション化したワイドテーブル形式の Parquet に保存。選択された範囲限定のリプレイ期間だけをオンライン時系列ストアに取り込む |
| 評価       | 各発電所内で leave-one-asset-out 評価を実施。36 分割、95 イベント、281,249 予測点                                                       |
| ガバナンス | データセット、成果物、モデル、評価、リプレイ、出力を不変の ID、ダイジェスト、権限に結び付ける                                           |
| 限界       | 現在の結果から、発電所間の汎化、実際の RUL、30 日以内の故障確率、現場の安全性は主張できない                                             |

CARE データセットと、そのライセンスの対象となる派生配布成果物は CC BY-SA 4.0 に従います。OpenVigil 自身のソースコードに適用される Apache License 2.0 は、これらのデータ資産を対象としません。

### API とリアルタイムデータ

| エンドポイント                                | 用途                                                                  |
| --------------------------------------------- | --------------------------------------------------------------------- |
| `/api/runtime`                                | 現在の実行モード、バックエンドの準備状態、機密情報を除いたリリース ID |
| `/api/workflow/:assetId`                      | Demo ワークフローのスナップショット、承認、作業指示書、監査状態       |
| `/api/backend/:path+`                         | 本番モードの許可リスト付き FastAPI ゲートウェイ                       |
| `/api/v1/knowledge/parser-capabilities`       | バックエンドの解析設定と上限。ワーカーの死活監視ではありません        |
| `/api/v1/events/stream`                       | カーソルによる再開と制限付き再接続を備えた本番 SSE                    |
| `/ws/scada`, `/ws/alarms`, `/ws/agent-events` | Demo の模擬リアルタイムチャネル。本番では要件未達時に処理を拒否       |

本番リクエストでは、Sites Worker がユーザーごとに短期間の委任トークンを発行し、メソッド、対象、本文のダイジェスト、一意の `jti` を結び付けます。ブラウザーは PostgreSQL、Redis、MinIO、Neo4j に直接アクセスしません。

## アーキテクチャ

```text
ブラウザー
   │
   ▼
vinext / React 19 アプリケーション
   │
   ├── Demo
   │     └── Cloudflare Worker + D1
   │           ├── 決定論的フィクスチャ
   │           ├── ワークフロー / 監査状態
   │           └── 有限 SSE + 模擬 WebSocket
   │
   └── 本番
         └── Sites ID ゲートウェイ
               │  委任 JWT / 許可リスト / リリース検証
               ▼
             FastAPI
               ├── PostgreSQL / TimescaleDB / pgvector
               ├── Redis / Dramatiq / 永続 outbox
               ├── MinIO 管理対象成果物
               ├── Neo4j 派生ナレッジグラフ
               ├── LiteLLM 推論と埋め込み
               ├── 隔離構造ワーカー / pyOMA2 FDD
               ├── 隔離文書ワーカー / Docling + OCR
               └── SCADA / MQTT / HTTPS / EAM コネクター
```

Demo の D1 と本番の PostgreSQL は別の境界です。両者の間に暗黙のデータ複製はなく、失敗した本番クエリの代わりに Demo データを表示することはできません。

### 技術スタック

| 層           | 技術                                                        |
| ------------ | ----------------------------------------------------------- |
| Web          | React 19, TypeScript, vinext, Vite, Tailwind CSS            |
| データ UI    | TanStack Query, TanStack Table, Zustand, ECharts, Three.js  |
| エッジ       | Cloudflare Worker, D1, SSE, WebSocket                       |
| バックエンド | Python 3.12, FastAPI, Pydantic, async SQLAlchemy, LangGraph |
| 非同期処理   | PostgreSQL transactional outbox, Redis, Dramatiq            |
| データ       | PostgreSQL, TimescaleDB, pgvector, MinIO, Neo4j             |
| AI           | LiteLLM、OpenAI 互換プロバイダー、独立した埋め込み経路      |
| 構造         | pyOMA2 FDD、専用キュー、隔離計算子プロセス                  |
| 文書         | Docling、表抽出、中国語 OCR、独立 CPU ハッシュ固定環境      |
| 品質         | Node test runner, Playwright, Pytest, Ruff, mypy, Bandit    |

互換性を保つため、`windops_backend`、`WINDOPS_*`、`x-windops-*`、既存のデータベース・オブジェクトストレージ・テレメトリーの名前空間を維持します。

## モデル設定

ローカルのモデル設定はすべてリポジトリルートの `.env` に置きます。ルートの `.env.example` が唯一の設定項目テンプレートです。`backend/` や他の場所に別の環境設定を作らないでください。

実モデルによる推論を有効にする前に、次を設定します。

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
```

対応するチャットプロバイダー：

| `WINDOPS_LLM_PROVIDER` | ベース URL の変数                 | API キーの変数                | モデルの変数                |
| ---------------------- | --------------------------------- | ----------------------------- | --------------------------- |
| `siliconflow`          | `WINDOPS_SILICONFLOW_BASE_URL`    | `WINDOPS_SILICONFLOW_API_KEY` | `WINDOPS_SILICONFLOW_MODEL` |
| `bailian`              | `WINDOPS_BAILIAN_BASE_URL`        | `WINDOPS_BAILIAN_API_KEY`     | `WINDOPS_BAILIAN_MODEL`     |
| `deepseek`             | `WINDOPS_DEEPSEEK_BASE_URL`       | `WINDOPS_DEEPSEEK_API_KEY`    | `WINDOPS_DEEPSEEK_MODEL`    |
| `default`              | 既存の LiteLLM / プロバイダー環境 | 各プロバイダーで管理          | `WINDOPS_LITELLM_MODEL`     |

設定例：

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
WINDOPS_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
WINDOPS_SILICONFLOW_API_KEY=
WINDOPS_SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

Alibaba Cloud Bailian の既定 URL は `https://dashscope.aliyuncs.com/compatible-mode/v1`、DeepSeek は `https://api.deepseek.com` です。`base_url` は認証情報を埋め込まない HTTPS URL にしてください。API キーは Git の対象外であるルート `.env`、または本番のシークレット管理サービスにのみ保存します。

OpenCode Go はコーディングエージェントの通信向けです。現在のバックエンドは `OPENCODE_GO_*` を読み取りません。`.env.example` には参照 URL と変数名のみを残し、風車診断のプロバイダーとして選択されることを防いでいます。チャットと埋め込みは別の接続設定を使用します。チャットのエンドポイントやキーを埋め込み用に自動再利用しません。同じプロバイダーアカウントが両方のモデル種別で許可されている場合は、それぞれの設定箇所にキーを個別に設定できます。

既存のベクトルストアは 1536 次元を必要とします。この次元数に対応する SiliconFlow の Qwen モデルなど、OpenAI 互換の埋め込みサービスを別途設定してください。

```dotenv
WINDOPS_EMBEDDING_MODEL=openai/Qwen/Qwen3-Embedding-4B
WINDOPS_EMBEDDING_API_BASE=https://api.siliconflow.cn/v1
WINDOPS_EMBEDDING_API_KEY=
WINDOPS_EMBEDDING_DIMENSIONS=1536
```

キーは非公開のローカル設定または配備先のシークレット管理にのみ保存してください。上記のエンドポイント、キー、次元数を明示しなければ、LiteLLM は既定の接続動作を維持します。明示するエンドポイントは認証情報のない HTTPS URL が必要です。リクエストパラメーターは実プロバイダーに送信され、レスポンスには欠落・重複のないインデックス、1536 次元のベクトル、有限の数値が必要です。ベクトルの埋め合わせや切り詰めは行いません。対応する次元数は [SiliconFlow 埋め込み API](https://docs.siliconflow.cn/docs/api/embeddings-post) を参照してください。

検索では現在の埋め込みプロバイダー・モデルのベクトルだけを比較します。モデル変更後は、既存の範囲限定の自動インデックス作成経路、またはグローバルナレッジ管理者の `POST /api/v1/knowledge-graph/reindex` で古いベクトルを再生成してください。未再生成の古いベクトルはランキングから除外します。本番の合同受け入れでは、インデックス作成・検索と同じ接続設定を使用します。

### 実モデルの回帰評価

`.venv` を有効にした状態で `backend/` から実行します。コマンドはルート `.env` の既存 LiteLLM 設定を読み取り、実プロバイダーを呼び出すため料金が発生します。決定論的な代替実装は認められません。

```powershell
python -m windops_backend.operations.reasoning_eval --cases evaluations/wind-diagnosis-v1.json --pricing evaluations/siliconflow-v3.2-pricing.json --report ../.artifacts/improvements/reasoning-current.json
```

組み込みの 6 つの合成工学ケースは、主軸受、増速機、温度センサー、データ欠落、ID の競合、証拠テキスト内のプロンプトインジェクションを対象とします。採点では故障分類、部品、信頼度、根拠引用の適合率、必須引用の再現率、明示的な回答保留を確認します。タイムアウトやエラーは回答保留と見なしません。ケースのラベル、`required_evidence`、`supporting_evidence` はモデルのコンテキストから除外します。任意の `supporting_evidence` は追加の有効な引用を示します。未指定の場合、必須の証拠のみを根拠として扱います。この小規模サンプルはプロンプトとモデルの工学的な回帰確認を目的とします。実発電所の診断精度を推定したり、自由記述の結論にあらゆる意味上の誤りがないと証明したりすることはできません。評価は本番ワークフローの受け入れではなく、独立したプロンプトと公開診断出力を使用します。本番の信頼度ゲートは変更しません。

レポートには成功・失敗した全ケース、プロバイダーライブラリの初回読み込みを含むエンドツーエンド P95、各試行の使用量と費用、不明費用の件数、既知費用の小計、ケース・プロンプト・コードのダイジェスト、Git 状態、要求・応答のモデル ID を保持します。使用量の欠落、モデル ID の不一致、リクエストのタイムアウトがある場合、総費用を `UNVERIFIED` とし、無料の成功とは扱いません。費用は日付と出典のある料金表からの推定値で、キャッシュ割引を含まず、請求記録ではありません。モデル変更時には対応する料金ファイルを指定してください。

リクエストは `max_tokens=1024` を設定し、再試行しません。1 回の評価で実行するのはケース集合内の最大 50 ケースです。[SiliconFlow API](https://docs.siliconflow.cn/docs/api/chat-completions-post) では、この値は最終レスポンスを制限し、モデル内部の思考に使う量は含みません。`maximum_total_cost` はレスポンス受信後に確認する停止閾値です。最後のリクエストは閾値を超えることがあり、プロバイダーが報告しない料金も把握できません。厳密なアカウント予算が必要なら、プロバイダー側の制限を使用してください。組み込みの 6 ケース集合の閾値は 1 CNY です。絶対基準のゲートに不合格があればレポートを保存し、非ゼロで終了します。失敗ケースを削除したり、合格するまで自動再実行したりしません。

絶対基準を満たして内容確認済みのレポートを保持し、回帰比較には `--baseline <report-path>` を追加します。ケースのダイジェスト、レポートバージョン、料金通貨が一致する場合、分類・回答保留・引用の指標は低下を認めず、P95 と推定費用の増加は最大 20% です。非互換または不合格のベースラインから回帰合格を出すことはできません。実発電所のケースには、専門家がレビューし `expert-reviewed-field-cases` とラベル付けした別のケース集合が必要です。

## 開発

`docs/` はローカル専用の文書ディレクトリであり、Git コミットや GitHub での配布から除外されています。ルート文書内で「ローカル専用文書」と記された資料は、ローカルコピーを持つメンテナー向けで、クリーンなクローンには含まれません。CI が必要とする成果物ポリシーは `scripts/repository-artifact-policy.json` にあり、`docs/` 配下のファイル追跡を禁止しています。リポジトリの書式チェックはローカル文書ディレクトリに依存しません。

### Web

```bash
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
pnpm test
```

その他の便利なコマンド：

```bash
pnpm test:coverage
pnpm test:e2e
pnpm test:start-smoke
pnpm run check:repository-artifacts
```

`pnpm test` は本番ビルドと Bundle サイズ予算の確認後に Node の契約テストを実行します。`pnpm test:e2e` は実際の Chromium を使用し、主要画面、ID、権限、エラー復旧を検証します。

### 実依存サービスを使った業務ワークフロー試験

Docker Engine/Compose、Node/pnpm、Python 3.12 を用意します。`backend/` で `uv sync --frozen --extra test --extra structural` を実行し、リポジトリルートに戻ります。

```bash
pnpm exec playwright install chromium
pnpm test:e2e:business
```

コマンドは現在のフロントエンドをビルドし、ランダムな名前とループバックポートを持つ独立した Compose プロジェクトを作成します。実際の PostgreSQL、Redis、MinIO、Neo4j、FastAPI、Dramatiq、outbox リレー、読み取り監査ワーカーを起動します。Chromium のリクエストは Worker を経由し、承認、権限拒否、ネットワーク障害後の再試行、冪等な再実行、5 回の現場証拠アップロードを検証します。最後にデータベース記録とオブジェクトのハッシュを直接確認します。成功・失敗のいずれでも、自分で作ったプロセスと合成データのボリュームを削除します。保存済みのローカル開発スタックには操作を加えません。

観測値と参照資料は合成データです。診断と埋め込みには決定論的なテスト実装を使用し、ID プロバイダー・リリース・イメージの ID はテスト設定です。HTTP プロセスは実際の本番認証・ストレージプロトコルの分岐を実行し、ワーカーはテスト用モデルモードを維持します。これらの試験で確認できるのは工学的なワークフローであり、モデル精度、実 ID プロバイダー、本番リリースの受け入れではありません。レポートと非公開ログは `.artifacts/business-e2e/<run-id>/` に保存します。設定、秘密鍵、トレースに一時認証情報が含まれる場合があります。CI がアップロードするのは `report.json` のみです。既定のブラウザースイートと既存の設定ローテーション smoke test は別に維持します。

ブラウザーからの直接アップロードでは、バックエンドが発行するアップロード URL の正確な HTTPS オリジンをコンマ区切りで Worker の `WINDOPS_ARTIFACT_UPLOAD_ORIGINS` に設定し、オブジェクトストレージ側でアプリケーションのオリジンからの PUT/CORS を許可してください。既定の CSP は同一オリジン接続のみを許可します。この設定はワイルドカード、パス、認証情報、CSP ディレクティブを拒否し、不正な値では業務リクエストの実行前に 503 を返します。上記の分離試験でのみ、ページとストレージが両方とも `http://127.0.0.1` を使用する場合にローカル HTTP を許可します。

### ローカルのユーザーパフォーマンス測定

先に「Windows での再現可能なローカル起動」で分離スタックを起動し、リポジトリルートから実行します。

```powershell
./scripts/Start-Local.ps1
pnpm exec playwright install chromium
pnpm measure:performance --report .artifacts/improvements/performance.json
./scripts/Stop-Local.ps1
```

測定スクリプトはこのリポジトリの `.artifacts/local-stack/configuration.json` に記録されたループバックポートにのみ接続します。分離実行設定から認証情報を読みますが出力しません。サービスの起動・停止や業務データの変更は行いませんが、実 API の読み取り監査は永続化されます。`--samples 10 --api-samples 40 --list-size 5000` でサンプル数と合成負荷データ量を調整できます。ブラウザーは最低 5 サンプル、API は最低 20 サンプルが必要です。順次実行し、失敗サンプルもすべて保持します。

レポートは 3 種類の証拠を区別します。

- ホーム、診断センター、予知保全の Chromium による 1440px・390px 測定：FCP、指定コンテンツが表示されて 2 フレーム経過するまでの時間、その時点までの LCP・レイアウトシフト・長いタスク、グローバル検索の入力イベントから結果表示と 2 フレーム経過までの遅延。各サンプルは新しいブラウザーコンテキストを使いますが、サーバーや OS のキャッシュはすでに温まっている可能性があります。390px はデスクトップブラウザーの狭い表示領域で、実物のスマートフォンではありません。
- 長いアラーム一覧：実際の Demo アラーム構造に従う 2,000 件の合成レコードを、そのブラウザー実行内の読み取りレスポンスだけに注入します。実ページと DataTable が更新、ページング、フィルタリングを行います。Demo クエリのキャッシュは 30 秒で、各サンプルは実時間で 31 秒待ってから再接続を起動します。この準備時間は更新から描画までの遅延に含めず、ブラウザー時計も変更しません。レコード数、レスポンスのバイト数、データダイジェスト、実 DOM 行数を保持します。
- 独立した実 FastAPI インスタンス：認証付きの `/catalog`、`/turbines`、`/data-catalog` リクエストで 1 回のウォームアップ後、完全なレスポンスと JSON 解析時間、P50/P95、返却件数、レスポンスのバイト数を測定します。空のデータベースは 0 行返却と明記します。本番データ規模のスループットや、本番のフロントエンドからバックエンドまでの経路の受け入れを証明するものではありません。

固定のローカル予算は FCP 2,500ms、コンテンツ準備と一覧更新 4,000ms、操作 300ms、大規模一覧の絞り込み 1,000ms、API P95 500ms です。サンプル不足、リクエスト失敗、ブラウザーエラー、予算超過があればレポートを保存して非ゼロで終了します。P95 は nearest-rank 方式で、5 サンプルでは最大値です。CPU・システム・ブラウザー情報、表示領域、データ量、Git 状態、ビルド・スクリプトのダイジェストも記録します。コンテンツ準備、LCP の計測打ち切り、2 フレームで測る操作はローカルの実験指標です。実ユーザーの完全な LCP、INP、正式な SLO 受け入れの代わりにはなりません。

### Python

`backend/.venv` を有効にして `backend/` から実行します。

```powershell
python -m pytest tests -q
python -m ruff format --check src tests alembic scripts
python -m ruff check src tests alembic scripts
python -m mypy --no-incremental src
alembic upgrade head --sql
```

任意の CARE 依存関係の確認：

```powershell
uv sync --frozen --extra benchmark --extra test --extra dev
uv run windops-care-dependency-closure --requirements-lock requirements.container.txt --uv-lock uv.lock
uv run python -m pytest tests -q -k "care and not external_release"
```

SQLite テストでは決定論的な埋め込み、メモリ内の成果物検証器、メモリ内のグラフ代替を使用します。PostgreSQL、TimescaleDB、MinIO、Neo4j、実モデルプロバイダーの受け入れを置き換えるものではありません。

テスト件数はコマンドと CI の自動検出結果に基づきます。外部リソースがない通常のローカル実行では `external_release` テストをスキップできる場合がありますが、これらのスキップはリリース合格として扱いません。指定された外部受け入れ環境では `WINDOPS_FAIL_ON_SKIPPED=1` を設定し、スキップが 1 件でもあれば失敗とし、リリース受け入れチェックリストに従って実証拠を保持してください（ローカル専用文書：`docs/runbooks/release-acceptance.md`）。

## 本番受け入れの範囲と限界

本番導入候補には、委任 ID、RBAC、データスコープ、冪等性、リビジョン、outbox、監査、バックアップ・復元、リリース ID、要件未達時の安全な拒否が含まれます。以下は承認された環境で引き続き実施が必要です。

- Python API とワーカーの正式なクラスター配備、イメージスキャン、SBOM、署名、アドミッションチェック。
- PostgreSQL、TimescaleDB、Redis、MinIO、Neo4j、LiteLLM、埋め込みサービスの合同受け入れ。
- 実 SCADA、CMS、気象、EAM のデータ契約と現場権限の連携。
- 災害復旧、負荷試験、SLO、アラート配信、DAST、手動侵入試験、リリース後の確認。
- ブラウザーでの WCAG、視覚回帰、対応端末の受け入れ。
- CARE ライセンスの確認、本番オブジェクトストレージからのリプレイ、発電所間のオントロジーマッピングの手動レビュー。
- ハイブリッドタワーの現場校正・領域精度、OCR 数値の人手確認・精度評価、同一版 API・構造ワーカー・新文書イメージのリリース資格。文書ワーカーには独自の署名、SBOM/CVE 証拠、ネットワーク/資源ポリシーが必要で、既存の 2 イメージ報告では資格を取得できません。

Cloudflare Sites がホストするのは Web アプリケーションと ID ゲートウェイのみで、Python バックエンドはホストしません。Sites のリリース成功はバックエンド、依存スタック、現場システムの受け入れを置き換えません。証拠の詳細な状態は [EXECUTION_PROGRESS.md](./EXECUTION_PROGRESS.md)、[AUDIT_REPORT.md](./AUDIT_REPORT.md)、[UI_AUDIT_REPORT.md](./UI_AUDIT_REPORT.md) に記録されています。

## コントリビューション

開発環境、検証要件、PR の手順は[コントリビューションガイド（中国語）](./CONTRIBUTING.md)、脆弱性報告と認証情報の保護は[セキュリティポリシー（中国語）](./SECURITY.md)を参照してください。

次のような Issue と Pull Request を歓迎します。

- ワークフロー完了、権限、冪等性、復旧に関する実際の問題。
- アクセシビリティ、レスポンシブレイアウト、データ可視化、実行状態の表示。
- 実データソース、権限モデル、受け入れ基準を伴う機能。
- 問題を再現し、実際の動作を検証するテスト。

失敗テストの削除、アサーションの弱体化、ハードコードした値の返却、エラーの黙殺、フィクスチャへのフォールバックによって、見かけの合格を作らないでください。

## ライセンス

OpenVigil 自身のソースコードは [Apache License 2.0](./LICENSE) で提供されます。

CARE v6 データセットと、そのライセンスの対象となる派生配布成果物は Apache License 2.0 の対象外であり、このリポジトリでは配布しません。これらは [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) に従い、出典表示、ライセンスリンク、変更内容の説明、同一条件での継承が必要です。

## 謝辞

- [CARE v6](https://doi.org/10.5281/zenodo.15846963) — Christian Gück, Cyriana M. A. Roelofs / Fraunhofer IEE
- [EnergyFaultDetector](https://github.com/AEFDI/EnergyFaultDetector) — CARE スコア検証用に固定した公式参照実装
- PyScada、NetBird Dashboard、OpenClaw Mission Control、next-shadcn-dashboard-starter、Grafana — 情報設計、操作、視覚研究の参考

第三者ソース、固定コミット、ライセンス、クリーンルーム実装の境界については [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) を参照してください。
