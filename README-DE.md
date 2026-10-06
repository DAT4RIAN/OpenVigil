<p align="center">
  <img src="public/images/openvigil-logo.png" alt="OpenVigil" width="140">
</p>

<h1 align="center">OpenVigil</h1>
<p align="center"><a href="README.md">English</a> · <a href="README-CN.md">简体中文</a> · <b>Deutsch</b> · <a href="README-ES.md">Español</a> · <a href="README-FR.md">Français</a> · <a href="README-JA.md">日本語</a> · <a href="README-KO.md">한국어</a> · <a href="README-IT.md">Italiano</a></p>
<p align="center"><b>Multi-Agenten-Plattform für intelligente Betriebsführung und Instandhaltung von Windenergieanlagen</b><br>Überwachung, Diagnose, menschliche Entscheidungen und Arbeiten vor Ort in einem auditierbaren Ablauf verbinden.</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="Apache-Lizenz 2.0">
  <img src="https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=111827" alt="React 19.2">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/status-production%20candidate-f59e0b" alt="Kandidat für den Produktivbetrieb">
</p>

<p align="center">
  <a href="#installation">Installation</a> ·
  <a href="#schnellstart">Schnellstart</a> ·
  <a href="#funktionen">Funktionen</a> ·
  <a href="#architektur">Architektur</a> ·
  <a href="#modellkonfiguration">Modellkonfiguration</a> ·
  <a href="#entwicklung">Entwicklung</a> ·
  <a href="#lizenz">Lizenz</a>
</p>

---

<p align="center">
  <img src="public/openvigil-command-center.png" alt="OpenVigil Betriebszentrale" width="960">
</p>

> _Informationen zur Betriebsführung von Windenergieanlagen sind häufig über Anlagen, SCADA, Alarme, Modelle, menschliche Freigaben, Arbeitsaufträge und Nachweise vor Ort verteilt. Die Herausforderung besteht darin, jede Einschätzung auf eine Quelle zurückzuführen, jede Entscheidung einer verantwortlichen Person zuzuordnen und das Ergebnis jeder Maßnahme überprüfen zu können._
>
> _OpenVigil verbindet „Überwachung → Alarme → Mission → Diagnose → menschliche Entscheidungen → Arbeitsaufträge → Nachweise vor Ort → erneute Zustandsbewertung → Wissensaktualisierung“ zu einem nachvollziehbaren, wiederherstellbaren und durch Berechtigungen geregelten Ablauf. KI ordnet Nachweise und schlägt Alternativen vor; Menschen genehmigen Maßnahmen mit hohem Risiko._

## Projektstatus

> [!IMPORTANT]
> OpenVigil ist derzeit eine **Implementierung als Kandidat für den Produktivbetrieb**, kein bereits produktiv eingesetztes System. Der Standardmodus `demo` bietet deterministische Produktvorführungen. Der Modus `production` verbindet ein unabhängig bereitgestelltes Python-Backend, das den maßgeblichen Zustand verwaltet und Anfragen verweigert, wenn Identität, Konfiguration, Abhängigkeiten oder APIs die Anforderungen nicht erfüllen. Reale Windparks, Systeme vor Ort, Modellanbieter und Release-Umgebungen erfordern weiterhin gemeinsame Abnahmetests.

Das Produkt ist als intelligente Plattform für die Betriebsführung und Instandhaltung von Windenergieanlagen positioniert. Die Bilder auf der Anmeldeseite und der Demo-Windpark veranschaulichen ein Szenario; sie definieren weder den Produktumfang noch belegen sie eine Anbindung vor Ort oder eine Produktionsabnahme.

## Installation

### Voraussetzungen

- Node.js `>= 22.13.0`
- pnpm `11.21.0`, vorzugsweise über Corepack verwaltet
- Python `3.12.x`, nur für `backend/` erforderlich
- Docker Compose, optional zum Starten der lokalen Abhängigkeiten des Python-Backends

### Quellcode herunterladen

```bash
git clone --recurse-submodules https://github.com/DAT4RIAN/OpenVigil.git
cd OpenVigil

corepack enable
pnpm install --frozen-lockfile
```

Das Repository verwendet `pnpm-lock.yaml`. Erzeugen oder committen Sie keine `package-lock.json`, und mischen Sie npm- und pnpm-Lockdateien nicht innerhalb einer Änderung.

## Schnellstart

### Produktdemo

```bash
pnpm dev
```

Öffnen Sie `http://localhost:3000`. Die Standard-Demo umfasst 64 deterministische Windenergieanlagen, das Szenario einer Hauptlageranomalie an WT-023, den Workflow-Zustand in D1, endliche SSE-Streams, simulierte WebSockets und eine Agenten-Laufzeit mit 17 Werkzeugen. Sie unterstützt Produktvorführungen, Screenshots und Regressionstests.

### Build für den Produktivbetrieb

```bash
pnpm build
pnpm start
```

`pnpm start` stellt dasselbe Build-Artefakt bereit, das für Releases verwendet wird. Der Standardmodus bleibt Demo. Der Produktivmodus erfordert einen konfigurierten Sites Worker, die Adresse des Python-Backends, eine delegierte Identität, eine genehmigte Release-ID und einen Image-Digest. Noch nicht migrierte Routen greifen nicht auf Fixtures zurück.

### Vertikaler Funktionsumfang des Python-Backends

Führen Sie die folgenden Befehle in Windows PowerShell aus. Die `.env` im Repository-Stamm ist die einzige lokale Konfigurationsdatei; erstellen Sie sie nur dann aus `.env.example`, wenn sie noch nicht vorhanden ist.

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

Der derzeit einzige Migrations-Head lautet `0032_structural_workflow`. Führen Sie in `backend/` den Befehl `python scripts/verify_migration_head.py` aus, um den Migrationsgraphen und die dokumentierten Angaben zu prüfen.

Der Referenzimport fragt nach dem Schlüssel für `operations_manager`. Starten Sie anschließend das Outbox-Relay, den Dramatiq-Worker, den Read-Audit-Worker und die API in vier separaten Terminals:

```powershell
windops-outbox-relay
dramatiq windops_backend.workers
windops-read-audit-worker
uvicorn windops_backend.main:app --host 127.0.0.1 --port 8000
```

### Wiederholbarer lokaler Start unter Windows

Führen Sie nach der Installation der Frontend-Abhängigkeiten und dem Anlegen von `backend/.venv` diese Befehle im Repository-Stamm aus:

```powershell
./scripts/Start-Local.ps1
./scripts/Status-Local.ps1
./scripts/Stop-Local.ps1
```

Beim ersten Start werden standardmäßig Port `3000` für das Frontend und Port `8000` für die API verwendet. Mit `-FrontendPort 3180 -ApiPort 8180` können Sie freie Ports auswählen. Weitere Starts verwenden die gespeicherten Ports und prüfen vorhandene Dienste, bevor sie Prozesse erstellen. Ein Portkonflikt oder eine abweichende Prozessidentität bricht den Vorgang ab; die Skripte beenden den Prozess, der den Port belegt, nicht.

Dies ist eine isolierte Entwicklungsumgebung. Das Frontend bleibt im Demo-Modus; das unabhängige Python-Backend verwendet `development / deterministic / static_tokens`. Damit sind weder die Anbindung an das Produktionsgateway noch die Abnahme realer Modelle nachgewiesen. Die Skripte leiten aus dem Repository-Pfad ein separates Compose-Projekt ab und verwenden PostgreSQL `25432`, Redis `26379`, MinIO `29000/29001` und Neo4j `27474/27687`; alle Ports sind an Loopback-Adressen gebunden.

Generierte lokale Zugangsdaten, Compose-Konfiguration, Prozessidentitäten und Protokolle werden im ignorierten Verzeichnis `.artifacts/local-stack/` gespeichert. Diese Konfiguration gehört zum isolierten Startablauf: Sie liest oder überschreibt die `.env` des Benutzers im Repository-Stamm nicht und importiert Referenzdaten nicht automatisch. Beim gewöhnlichen manuellen Start wird weiterhin die `.env` im Repository-Stamm verwendet. Teilen oder committen Sie dieses Artefaktverzeichnis nicht.

Der Start wartet auf die Abhängigkeiten, wendet Alembic-Migrationen an, baut das Frontend und startet API, Dramatiq, Outbox-Relay, Read-Audit-Worker und Frontend. Die Statusprüfung kontrolliert den Migrations-Head, Redis, fünf MinIO-Buckets, Neo4j, API-Authentifizierung, die Speicherung des Read-Audits für die aktuelle Anfrage und die Anmeldeseite. Bei Fehlern bleiben Abhängigkeiten, Daten und Prozessprotokolle für die Diagnose erhalten. `Stop-Local.ps1` prüft PID, Erstellungszeit, Befehl und Repository-Zugehörigkeit, bevor es die zugehörigen Prozesse und das Compose-Projekt stoppt; Container, Zugangsdaten und Datenvolumes bleiben erhalten.

Führen Sie nach Änderungen an Stylesheet-Einstiegspunkten oder Datenbankmigrationen `pnpm check:architecture --write` aus und prüfen Sie das aktualisierte Architekturverzeichnis. `pnpm check:architecture` und CI weisen ein veraltetes Verzeichnis zurück.

## Funktionen

### Betriebszentrale

Die Startseite kombiniert Flotten-KPIs, eine Zustandsmatrix, Leistungstrends, Alarme mit hoher Priorität, aktive Missions und Agent Activity. Sie zeigt, was im Windpark geschieht und woran die KI arbeitet.

### Betriebs- und Instandhaltungsablauf

```text
SCADA / CMS / Wetter / manuelle Alarme
              │
              ▼
       Alarm → Mission
              │
              ▼
  Nachweise und Diagnose durch mehrere Agenten
              │
              ▼
  Alternativen und menschliche Freigabe
              │
              ▼
  Arbeitsauftrag → geordnete Aufgaben vor Ort
              │
              ▼
  Zustandsneubewertung → Wissensaktualisierung
```

Das Demo-Szenario WT-023 bildet den gesamten Weg ab: auffällige Hauptlagervibration und -temperatur, Mission-Erstellung, Diagnose, Alternativenvergleich, Freigabe, Arbeitsauftrag, fünf Aufgaben vor Ort, Zustandsverbesserung und Wissenssicherung. Alle Schreibvorgänge enthalten Idempotenzschlüssel, Korrelations-IDs, erwartete Revisionen und ausschließlich angehängte Audit-Ereignisse.

Ausführbare Empfehlungen im Python-Backend müssen über `execution_plan_id` an die geregelte Arbeitsvorlage der aktuellen Mission gebunden sein; die Maßnahmen müssen zu dieser Vorlage passen. Vorlagen stammen aus `analysis_profile.work_order_plan` oder der Standard-Inspektionsvorlage des Servers. Ihr Inhalt und Anlagenumfang bestimmen die Bindungskennung. Fehlende, unbekannte, veraltete oder nicht passende Bindungen führen bei der Freigabe zu 409. Ältere Entscheidungen ohne Bindung müssen überarbeitet werden. Ungebundene Empfehlungen wie ein Austausch können zur Diskussion stehen, werden aber nicht stillschweigend in Inspektionsaufträge umgewandelt. Aufgaben, Messschwellen, Sicherheitsanforderungen, Dauer und Abschlussregeln stammen immer aus der geregelten Vorlage.

Die fünf KI-Prüfarten verwenden ein explizites `review_target`, das die geprüfte Alternative und Arbeitsvorlage festhält. Die Prüfungen bewerten die Durchführung dieses Instandhaltungsplans. Voraussetzungen werden in `conditions`, Betriebsbeschränkungen der Windenergieanlage in `operating_constraints` gespeichert. Eine Prüfung erteilt keine Betriebserlaubnis; die Ausführung erfordert weiterhin menschliche Freigabe. Gültige negative Prüfungen bleiben erhalten. Historische Prüfungen ohne explizites Ziel werden nicht automatisch als verifizierte neue Prüfungen eingestuft.

Das Ausführungsregister für reale Modelle speichert in `evaluation_result.request` den Anfrage-Digest, die Nachrichtengröße in UTF-8-Bytes und die Konfiguration der Ausgabe-Token, jedoch nicht den Anfrageinhalt. Antworten enthalten außerdem den Abschlussgrund und die Größe der öffentlichen Antwort. Vom Anbieter als abgeschnitten gekennzeichnete Antworten werden auch dann abgelehnt, wenn sie als JSON lesbar sind. Wenn ein späterer Knoten fehlschlägt oder die Geschäftstransaktion zurückgerollt wird, bewahrt `completed_node_usage` im Fehlerdatensatz Verbrauch, Modellidentität und Latenz zuvor erfolgreicher Modellknoten dieses Versuchs; zurückgerollte Entscheidungsausgaben bleiben nicht erhalten. Unbekannter Verbrauch eines fehlgeschlagenen Knotens verhindert, dass die Versuchskosten als vollständig erfasst oder kostenlos gelten. Fehlende historische Datensätze werden nicht erfunden.

### Fachliche Arbeitsbereiche

| Arbeitsbereich                           | Route                                | Hauptfunktionen                                                                                 |
| ---------------------------------------- | ------------------------------------ | ----------------------------------------------------------------------------------------------- |
| Betriebszentrale                         | `/`                                  | Flottenzustand, Risikoobjekte, Missions und Agentenaktivität                                    |
| Windpark / Windenergieanlage             | `/wind-farms`, `/turbines/:id`       | Anlagentopologie, Zustand, SCADA, Alarme und Instandhaltungskontext                             |
| SCADA / Alarme                           | `/scada`, `/alarms`                  | Zeitreihenüberwachung, Schwellen, Qualitätscodes, Anomalien und Bearbeitungsstatus              |
| Agenten / Missions                       | `/agents`, `/missions`               | Agentenorganisation, Aufgabenwarteschlangen, Nachweise, Kollaborationsverlauf und Freigabereife |
| Entscheidungen / Arbeitsaufträge         | `/decisions`, `/work-orders`         | Alternativenvergleich, menschliche Freigabe, Aufgabenkontrollen und Nachweise vor Ort           |
| Zustand / Vorausschauende Instandhaltung | `/health`, `/predictive-maintenance` | Zustandsmatrizen, Risikorangfolge, RUL-Anzeige und Wartungsfenster                              |
| Ressourcen / Instandhaltung              | `/resources`, `/maintenance`         | Teams, Ersatzteile, Werkzeuge, Wetterfenster, Kalender und Konfliktprüfung                      |
| Wissen / Berichte                        | `/knowledge`, `/reports`             | Nachweissuche, Wissensfälle, Berichtsvorschau und PDF/DOCX-Export                               |
| Daten / Modelle / Diagnose               | `/data`, `/models`, `/diagnosis`     | Daten-Governance, CARE-Bewertung, Modellprüfungen und Diagnoseherkunft                          |
| Digitaler Zwilling / Einstellungen       | `/digital-twin`, `/settings`         | 2D-Betriebsansichten, Laufzeitstatus, Identität und Datenrichtlinien                            |

Die Seite für den digitalen Zwilling bietet betrieblichen Kontext. Sie beansprucht weder physikalische Simulation noch Echtzeitsteuerung oder ein ingenieurtechnisches 3D-Modell.

### Zusammenarbeit mehrerer Agenten

Die 22 Agenten der Demo sind in drei Ebenen organisiert:

| Ebene        | Beispielrollen                                                                              | Aufgaben                                                                           |
| ------------ | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Entscheidung | SCADA-Analyse, Vibrationsdiagnose, vorausschauende Instandhaltung, Instandhaltungsstrategie | Anomalien erkennen, Nachweise ordnen und Diagnosen sowie Alternativen vorschlagen  |
| Prüfung      | Sicherheits-, technische, wirtschaftliche, Compliance- und Ressourcenprüfung                | Sicherheits-, Technik-, Wirtschafts-, Compliance- und Ressourcenbedingungen prüfen |
| Ausführung   | Arbeitsauftrag, Team, Ersatzteile, Instandhaltung, Bericht, Wissen                          | Genehmigte Entscheidungen in geregelte Ausführung und Rückmeldung überführen       |

Das Python-Backend verwendet einen unabhängigen LangGraph-Workflow und einen SQL-Katalog mit 11 Werkzeugen. UI und APIs zeigen ausschließlich öffentliche, strukturierte, auditierbare Nachweise und Schlussfolgerungen. Sie zeigen oder erfinden keine verborgene Chain-of-Thought eines Modells.

### CARE v6 Benchmark

CARE v6 bietet einen separaten Offline-Pfad für Anomalieerkennung und geregelte Bewertung. Rohdaten sind nicht im Repository enthalten; Betreiber müssen ausdrücklich eine autorisierte, schreibgeschützte Quelle bereitstellen.

| Bereich             | Aktuelle Implementierung                                                                                                                                                       |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Datenvertrag        | 95 Ereignisse, 36 Anlagen innerhalb ihrer Windparks, 5,242,948 Zeilen; feste Importreihenfolge A → C → B                                                                       |
| Qualitätsbehandlung | Rohwerte bleiben unverändert; Qualitätsprobleme werden in einer separaten Maske erfasst; Ground Truth ist für die Bewertung erst nach dem Einfrieren der Vorhersagen verfügbar |
| Speicherung         | Alle Signale liegen in partitionierten Parquet-Breittabellen; nur ausgewählte, begrenzte Replay-Zeitfenster gelangen in den Online-Zeitreihenspeicher                          |
| Bewertung           | Leave-one-asset-out-Bewertung innerhalb jedes Windparks mit 36 Folds, 95 Ereignissen und 281,249 Vorhersagepunkten                                                             |
| Governance          | Datensätze, Artefakte, Modelle, Bewertungen, Replays und Exporte sind an unveränderliche Identitäten, Digests und Berechtigungen gebunden                                      |
| Grenzen             | Die aktuellen Ergebnisse belegen weder Generalisierung über Windparks hinweg noch reale RUL, 30-Tage-Ausfallwahrscheinlichkeit oder Sicherheit vor Ort                         |

Der CARE-Datensatz und abgeleitete Distributionsartefakte, die seiner Lizenz unterliegen, folgen CC BY-SA 4.0. Die Apache-Lizenz 2.0 für OpenVigils eigenen Quellcode gilt nicht für diese Datenbestände.

### APIs und Echtzeitdaten

| Endpunkt                                      | Zweck                                                                                                   |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `/api/runtime`                                | Aktueller Laufzeitmodus, Backend-Bereitschaft und bereinigte Release-Identität                          |
| `/api/workflow/:assetId`                      | Demo-Workflow-Snapshots, Freigaben, Arbeitsaufträge und Audit-Zustand                                   |
| `/api/backend/:path+`                         | Über eine Positivliste beschränktes FastAPI-Gateway im Produktivmodus                                   |
| `/api/v1/events/stream`                       | Produktions-SSE mit Cursor-Fortsetzung und begrenztem Wiederverbinden                                   |
| `/ws/scada`, `/ws/alarms`, `/ws/agent-events` | Simulierte Demo-Echtzeitkanäle; im Produktivmodus werden nicht erfüllte Anforderungen sicher abgewiesen |

Bei Produktionsanfragen stellt der Sites Worker für jeden Benutzer kurzlebige delegierte Token aus, die Methode, Ziel, Body-Digest und eine eindeutige `jti` binden. Browser greifen nicht direkt auf PostgreSQL, Redis, MinIO oder Neo4j zu.

## Architektur

```text
Browser
   │
   ▼
vinext / React 19 Anwendung
   │
   ├── Demo
   │     └── Cloudflare Worker + D1
   │           ├── deterministische Fixtures
   │           ├── Workflow- / Audit-Zustand
   │           └── endliches SSE + simuliertes WebSocket
   │
   └── Produktion
         └── Sites Identitätsgateway
               │  delegiertes JWT / Positivliste / Release-Prüfung
               ▼
             FastAPI
               ├── PostgreSQL / TimescaleDB / pgvector
               ├── Redis / Dramatiq / dauerhafte Outbox
               ├── MinIO geregelte Artefakte
               ├── Neo4j abgeleiteter Wissensgraph
               ├── LiteLLM Reasoning und Embeddings
               └── SCADA / MQTT / HTTPS / EAM Konnektoren
```

Demo-D1 und Produktions-PostgreSQL bilden getrennte Grenzen. Zwischen ihnen gibt es keine implizite Datenreplikation. Fehlgeschlagene Produktionsabfragen dürfen keine Demo-Daten als Ersatz anzeigen.

### Technologie-Stack

| Ebene     | Technologien                                                  |
| --------- | ------------------------------------------------------------- |
| Web       | React 19, TypeScript, vinext, Vite, Tailwind CSS              |
| Daten-UI  | TanStack Query, TanStack Table, Zustand, ECharts, Three.js    |
| Edge      | Cloudflare Worker, D1, SSE, WebSocket                         |
| Backend   | Python 3.12, FastAPI, Pydantic, async SQLAlchemy, LangGraph   |
| Asynchron | PostgreSQL transactional outbox, Redis, Dramatiq              |
| Daten     | PostgreSQL, TimescaleDB, pgvector, MinIO, Neo4j               |
| KI        | LiteLLM, OpenAI-kompatible Anbieter, separater Embedding-Pfad |
| Qualität  | Node test runner, Playwright, Pytest, Ruff, mypy, Bandit      |

Stabile Kompatibilitätskennungen wie `windops_backend`, `WINDOPS_*`, `x-windops-*` sowie die vorhandenen Datenbank-, Objektspeicher- und Telemetrie-Namensräume bleiben erhalten.

## Modellkonfiguration

Die gesamte lokale Modellkonfiguration gehört in die `.env` im Repository-Stamm. Die dortige `.env.example` ist die einzige Feldvorlage. Legen Sie keine weitere Umgebungskonfiguration in `backend/` oder an anderer Stelle an.

Setzen Sie vor dem Aktivieren realen Reasonings:

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
```

Unterstützte Chat-Anbieter:

| `WINDOPS_LLM_PROVIDER` | Variable für die Basis-URL           | Variable für den API-Schlüssel    | Modellvariable              |
| ---------------------- | ------------------------------------ | --------------------------------- | --------------------------- |
| `siliconflow`          | `WINDOPS_SILICONFLOW_BASE_URL`       | `WINDOPS_SILICONFLOW_API_KEY`     | `WINDOPS_SILICONFLOW_MODEL` |
| `bailian`              | `WINDOPS_BAILIAN_BASE_URL`           | `WINDOPS_BAILIAN_API_KEY`         | `WINDOPS_BAILIAN_MODEL`     |
| `deepseek`             | `WINDOPS_DEEPSEEK_BASE_URL`          | `WINDOPS_DEEPSEEK_API_KEY`        | `WINDOPS_DEEPSEEK_MODEL`    |
| `default`              | Bestehende LiteLLM-/Anbieterumgebung | Vom jeweiligen Anbieter verwaltet | `WINDOPS_LITELLM_MODEL`     |

Beispiel:

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
WINDOPS_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
WINDOPS_SILICONFLOW_API_KEY=
WINDOPS_SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

Alibaba Cloud Bailian verwendet standardmäßig `https://dashscope.aliyuncs.com/compatible-mode/v1`, DeepSeek `https://api.deepseek.com`. Die `base_url` muss HTTPS verwenden und darf keine Zugangsdaten enthalten. Speichern Sie API-Schlüssel nur in der ignorierten `.env` im Repository-Stamm oder in einer produktiven Geheimnisverwaltung.

OpenCode Go ist für Anfragen von Coding-Agenten vorgesehen. Das aktuelle Backend liest `OPENCODE_GO_*` nicht; `.env.example` enthält nur seine Referenzadresse und Variablennamen, um eine Auswahl als Anbieter für Windanlagendiagnosen zu vermeiden. Chat und Embeddings verwenden separate Verbindungskonfigurationen. Die Anwendung übernimmt Chat-Endpunkt oder -Schlüssel nicht automatisch für Embeddings. Ist ein Anbieterkonto für beide Modelltypen autorisiert, kann sein Schlüssel an beiden Konfigurationseinstiegen separat hinterlegt werden.

Der vorhandene Vektorspeicher erfordert 1536 Dimensionen. Konfigurieren Sie separat einen OpenAI-kompatiblen Embedding-Dienst, beispielsweise ein SiliconFlow-Qwen-Modell, das diese Dimensionszahl unterstützt:

```dotenv
WINDOPS_EMBEDDING_MODEL=openai/Qwen/Qwen3-Embedding-4B
WINDOPS_EMBEDDING_API_BASE=https://api.siliconflow.cn/v1
WINDOPS_EMBEDDING_API_KEY=
WINDOPS_EMBEDDING_DIMENSIONS=1536
```

Schlüssel gehören ausschließlich in private lokale Konfigurationen oder die Geheimnisverwaltung der Bereitstellung. Ohne die obigen expliziten Einstellungen für Endpunkt, Schlüssel und Dimensionen behält LiteLLM sein Standardverbindungsverhalten bei. Explizite Endpunkte müssen HTTPS ohne eingebettete Zugangsdaten verwenden. Anfrageparameter werden an den realen Anbieter gesendet; Antworten müssen vollständige, eindeutige Indizes, Vektoren mit 1536 Dimensionen und endliche numerische Werte enthalten. Vektoren werden weder aufgefüllt noch gekürzt. Angaben zu unterstützten Dimensionen finden Sie in der [SiliconFlow Embedding-API](https://docs.siliconflow.cn/docs/api/embeddings-post).

Die Suche vergleicht nur Vektoren des aktuellen Embedding-Anbieters und -Modells. Erzeugen Sie nach einem Modellwechsel alte Vektoren über den vorhandenen begrenzten automatischen Indexierungspfad oder `POST /api/v1/knowledge-graph/reindex` des globalen Wissensadministrators neu. Noch nicht neu indexierte alte Vektoren werden von der Rangfolge ausgeschlossen. Die gemeinsame Produktionsabnahme verwendet dieselbe Verbindungskonfiguration wie Indexierung und Abfragen.

### Regressionsevaluation mit realen Modellen

Führen Sie den Befehl in `backend/` mit aktivierter `.venv` aus. Er liest die vorhandene LiteLLM-Konfiguration aus der `.env` im Repository-Stamm, ruft reale Anbieter auf und verursacht Kosten. Deterministische Ersatzimplementierungen werden nicht akzeptiert.

```powershell
python -m windops_backend.operations.reasoning_eval --cases evaluations/wind-diagnosis-v1.json --pricing evaluations/siliconflow-v3.2-pricing.json --report ../.artifacts/improvements/reasoning-current.json
```

Die sechs integrierten synthetischen Ingenieurfälle behandeln Hauptlager, Getriebe, Temperatursensor, fehlende Daten, Identitätskonflikte und Prompt-Injection in Nachweistexten. Die Bewertung prüft Fehlerklasse, Komponente, Konfidenz, Präzision unterstützender Quellenverweise, Vollständigkeit erforderlicher Quellenverweise und expliziten Verzicht auf eine Aussage. Zeitüberschreitungen und Fehler zählen nicht als solcher Verzicht. Falllabels, `required_evidence` und `supporting_evidence` werden nicht in den Modellkontext aufgenommen. Das optionale `supporting_evidence` bezeichnet zusätzliche gültige Quellenverweise; fehlt es, gelten nur erforderliche Nachweise als unterstützend. Diese kleine Stichprobe dient der technischen Regression von Prompts und Modellen. Sie kann weder die Diagnosegenauigkeit in realen Windparks schätzen noch beweisen, dass Freitextschlussfolgerungen frei von allen semantischen Fehlern sind. Die Evaluation verwendet einen separaten Prompt und eine öffentliche Diagnoseausgabe anstelle einer Abnahme des Produktionsworkflows; die produktive Konfidenzprüfung bleibt unverändert.

Berichte bewahren jeden erfolgreichen und fehlgeschlagenen Fall, die End-to-End-P95 einschließlich des ersten Ladens der Anbieterbibliothek, Verbrauch und Kosten jedes Versuchs, die Anzahl unbekannter Kosten, Zwischensummen bekannter Kosten, Fall-/Prompt-/Code-Digests, Git-Zustand sowie angeforderte und zurückgegebene Modellidentitäten. Fehlende Verbrauchsangaben, abweichende Modellidentität oder Anfrage-Timeout kennzeichnen die Gesamtkosten als `UNVERIFIED`, statt den Versuch als kostenlosen Erfolg zu behandeln. Kosten sind Schätzungen anhand einer datierten Preistabelle mit Quellenangabe ohne Cache-Rabatte, keine Abrechnungsnachweise. Geben Sie beim Modellwechsel eine passende Preisdatei an.

Anfragen setzen `max_tokens=1024` und werden nicht wiederholt; eine Evaluation führt höchstens 50 Fälle aus dem Fallsatz aus. In der [SiliconFlow API](https://docs.siliconflow.cn/docs/api/chat-completions-post) begrenzt dieser Parameter die finale Antwort, ohne den internen Denkverbrauch des Modells. `maximum_total_cost` ist eine Stoppschwelle, die nach dem Eingang einer Antwort geprüft wird. Die letzte Anfrage kann sie überschreiten; nicht vom Anbieter gemeldete Kosten können nicht berücksichtigt werden. Nutzen Sie anbieterseitige Grenzen, wenn ein striktes Kontobudget erforderlich ist. Der integrierte Satz mit sechs Fällen verwendet eine Schwelle von 1 CNY. Jeder Fehler an einem absoluten Prüfkriterium speichert den Bericht und beendet den Prozess mit einem Fehlercode. Fehlgeschlagene Fälle werden weder gelöscht noch automatisch bis zum Erfolg wiederholt.

Bewahren Sie einen geprüften Bericht auf, der die absoluten Kriterien erfüllt, und ergänzen Sie anschließend `--baseline <report-path>` für den Regressionsvergleich. Bei passenden Fall-Digests, Berichtsversionen und Preiswährungen dürfen Klassifikation, Aussageverzicht und Quellenmetriken nicht schlechter werden; P95 und geschätzte Kosten dürfen höchstens um 20% steigen. Eine inkompatible oder fehlgeschlagene Baseline kann kein bestandenes Regressionsergebnis liefern. Reale Windparkfälle erfordern einen separaten, von Fachleuten geprüften Fallsatz mit der Kennzeichnung `expert-reviewed-field-cases`.

## Entwicklung

`docs/` ist ein rein lokales Dokumentationsverzeichnis und wird weder in Git committet noch über GitHub verteilt. Als „nur lokales Dokument“ gekennzeichnete Stammverzeichnis-Dokumente verweisen auf Materialien, die Maintainern mit lokalen Kopien zur Verfügung stehen; ein sauberer Clone enthält sie nicht. Die von CI benötigte Artefaktrichtlinie liegt in `scripts/repository-artifact-policy.json` und verbietet das Tracking von Dateien unter `docs/`. Formatprüfungen des Repositorys hängen nicht vom lokalen Dokumentationsverzeichnis ab.

### Web

```bash
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
pnpm test
```

Weitere nützliche Befehle:

```bash
pnpm test:coverage
pnpm test:e2e
pnpm test:start-smoke
pnpm run check:repository-artifacts
```

`pnpm test` führt vor den Node-Vertragstests einen Produktionsbuild und Prüfungen des Bundle-Budgets aus. `pnpm test:e2e` verwendet echtes Chromium, um wichtige Seiten, Identität, Berechtigungen und Fehlerbehebung zu prüfen.

### Tests des Geschäftsablaufs mit realen Abhängigkeiten

Stellen Sie Docker Engine/Compose, Node/pnpm und Python 3.12 bereit. Führen Sie in `backend/` den Befehl `uv sync --frozen --extra test --extra structural` aus und kehren Sie dann in den Repository-Stamm zurück:

```bash
pnpm exec playwright install chromium
pnpm test:e2e:business
```

Der Befehl baut das aktuelle Frontend und erstellt anschließend ein separates Compose-Projekt mit zufälligem Namen und Loopback-Ports. Es laufen echtes PostgreSQL, Redis, MinIO, Neo4j, FastAPI, Dramatiq, Outbox-Relay und Read-Audit-Worker. Chromium-Anfragen laufen durch den Worker und prüfen Freigaben, verweigerte Berechtigungen, Wiederholungen nach Netzwerkfehlern, idempotente Wiederausführung und fünf Uploads von Nachweisen vor Ort. Abschließend prüfen die Tests Datenbankeinträge und Objekt-Hashes direkt. Bei Erfolg wie bei Fehler entfernt der Runner seine eigenen Prozesse und synthetischen Datenvolumes; er greift nicht in die gespeicherte lokale Entwicklungsumgebung ein.

Beobachtungen und Referenzmaterial sind synthetisch. Diagnose und Embeddings verwenden deterministische Testimplementierungen; Identitätsanbieter-, Release- und Image-Identitäten sind Testkonfigurationen. HTTP-Prozesse prüfen die tatsächlichen produktiven Authentifizierungs- und Speicherprotokollzweige, während Worker im Testmodellmodus bleiben. Diese Prüfungen belegen den technischen Ablauf, keine Modellgenauigkeit, keinen realen Identitätsanbieter und keine Produktionsrelease-Abnahme. Berichte und private Protokolle liegen in `.artifacts/business-e2e/<run-id>/`; Konfiguration, private Schlüssel und Traces können temporäre Zugangsdaten enthalten. CI lädt nur `report.json` hoch. Die Standard-Browsersuite und der bestehende Smoke-Test für Konfigurationsrotation bleiben separat.

Konfigurieren Sie für direkte Browser-Uploads im Worker `WINDOPS_ARTIFACT_UPLOAD_ORIGINS` mit den exakten, durch Kommas getrennten HTTPS-Origins der vom Backend ausgegebenen Upload-URLs. Erlauben Sie im Objektspeicher PUT/CORS vom Anwendungs-Origin. Die Standard-CSP erlaubt nur Verbindungen zum selben Origin. Die Einstellung weist Wildcards, Pfade, Zugangsdaten und CSP-Direktiven zurück; ungültige Werte liefern vor der Ausführung von Geschäftsanfragen 503. Lokales HTTP ist für die obigen isolierten Tests nur erlaubt, wenn Seite und Speicher beide `http://127.0.0.1` verwenden.

### Lokale Messung der Nutzerperformance

Starten Sie zuerst die isolierte Umgebung gemäß „Wiederholbarer lokaler Start unter Windows“ und führen Sie dann im Repository-Stamm aus:

```powershell
./scripts/Start-Local.ps1
pnpm exec playwright install chromium
pnpm measure:performance --report .artifacts/improvements/performance.json
./scripts/Stop-Local.ps1
```

Das Messskript verbindet sich ausschließlich mit Loopback-Ports, die in `.artifacts/local-stack/configuration.json` dieses Repositorys gespeichert sind. Es liest die Authentifizierung aus der isolierten Laufzeitkonfiguration, ohne Zugangsdaten auszugeben. Es startet oder stoppt keine Dienste und ändert keine Geschäftsdaten; reale API-Leseaudits werden weiterhin gespeichert. Mit `--samples 10 --api-samples 40 --list-size 5000` ändern Sie Stichprobenzahlen und synthetische Lastdatengröße. Mindestens fünf Browser- und 20 API-Stichproben sind erforderlich. Die Durchläufe sind sequenziell und bewahren jede fehlgeschlagene Stichprobe.

Berichte unterscheiden drei Nachweisarten:

- Chromium-Messungen bei 1440px und 390px für Startseite, Diagnosezentrum und vorausschauende Instandhaltung: FCP; Zeit bis der bezeichnete Inhalt sichtbar ist und zwei Frames verstrichen sind; LCP, Layoutverschiebungen und lange Aufgaben bis zu diesem Zeitpunkt; sowie Latenz vom Eingabeereignis der globalen Suche bis sichtbare Ergebnisse vorliegen und zwei Frames verstrichen sind. Jede Stichprobe nutzt einen neuen Browserkontext, während Server- und Betriebssystem-Caches bereits warm sein können. Der 390px-Viewport ist eine schmale Desktop-Browseransicht, kein physisches Telefon.
- Lange Alarmlisten: 2,000 synthetische Datensätze nach der tatsächlichen Demo-Alarmstruktur werden nur während dieses Browserdurchlaufs in eine Leseantwort eingefügt. Die reale Seite und DataTable führen Aktualisierung, Paginierung und Filterung aus. Demo-Abfragen haben einen Cache von 30 Sekunden; jede Stichprobe wartet 31 Sekunden realer Zeit, bevor die Wiederverbindung ausgelöst wird. Diese Vorbereitung ist von der Latenz zwischen Aktualisierung und Darstellung ausgeschlossen; die Browseruhr wird nicht verändert. Berichte bewahren Datensatzanzahl, Antwortbytes, Daten-Digest und tatsächliche DOM-Zeilenanzahl.
- Eine unabhängige reale FastAPI-Instanz: authentifizierte Anfragen an `/catalog`, `/turbines` und `/data-catalog` mit einem Aufwärmdurchlauf und anschließender Messung der vollständigen Antwort- und JSON-Parsingzeit, P50/P95, zurückgegebenen Anzahlen und Antwortbytes. Eine leere Datenbank wird ausdrücklich als null zurückgegebene Zeilen erfasst. Das belegt weder Durchsatz bei produktivem Datenumfang noch eine Abnahme des produktiven Frontend-Backend-Pfads.

Feste lokale Budgets sind FCP 2,500ms, Inhaltsbereitschaft und Listenaktualisierung 4,000ms, Interaktion 300ms, Filterung großer Listen 1,000ms und API-P95 500ms. Fehlende Stichproben, Anfragefehler, Browserfehler oder überschrittene Budgets speichern den Bericht und beenden den Prozess mit einem Fehlercode. P95 verwendet Nearest-Rank und entspricht bei fünf Stichproben dem Maximum. Berichte enthalten außerdem CPU-/System-/Browserdetails, Viewport, Datenmenge, Git-Zustand und Build-/Skript-Digests. Inhaltsbereitschaft, LCP-Stichtag und Interaktion über zwei Frames sind lokale experimentelle Metriken; sie ersetzen weder vollständiges LCP oder INP realer Nutzer noch eine formale SLO-Abnahme.

### Python

Führen Sie in `backend/` mit aktivierter `backend/.venv` aus:

```powershell
python -m pytest tests -q
python -m ruff format --check src tests alembic scripts
python -m ruff check src tests alembic scripts
python -m mypy --no-incremental src
alembic upgrade head --sql
```

Prüfen der optionalen CARE-Abhängigkeiten:

```powershell
uv sync --frozen --extra benchmark --extra test --extra dev
uv run windops-care-dependency-closure --requirements-lock requirements.container.txt --uv-lock uv.lock
uv run python -m pytest tests -q -k "care and not external_release"
```

SQLite-Tests verwenden deterministische Embeddings sowie Artefaktprüfer und Graphersatz im Arbeitsspeicher. Sie ersetzen keine Abnahme mit PostgreSQL, TimescaleDB, MinIO, Neo4j oder realen Modellanbietern.

Die Testanzahl ergibt sich aus der automatischen Ermittlung durch Befehle und CI. Bei gewöhnlichen lokalen Durchläufen ohne externe Ressourcen können `external_release`-Tests übersprungen werden; diese übersprungenen Tests gelten nicht als bestandene Release-Prüfungen. Vorgesehene externe Abnahmeumgebungen müssen `WINDOPS_FAIL_ON_SKIPPED=1` setzen, wodurch jedes Überspringen als Fehler gilt, und echte Nachweise gemäß der Release-Abnahmecheckliste aufbewahren (nur lokales Dokument: `docs/runbooks/release-acceptance.md`).

## Grenzen der Produktionsabnahme

Der Produktionskandidat umfasst delegierte Identität, RBAC, Datenbereiche, Idempotenz, Revisionen, Outbox, Auditing, Sicherung/Wiederherstellung, Release-Identitäten und sichere Ablehnung bei nicht erfüllten Anforderungen. Folgendes muss in genehmigten Umgebungen noch abgeschlossen werden:

- Formale Cluster-Bereitstellung von Python-API und Workern, Image-Scanning, SBOM, Signaturen und Zulassungsprüfungen.
- Gemeinsame Abnahme von PostgreSQL, TimescaleDB, Redis, MinIO, Neo4j, LiteLLM und Embedding-Diensten.
- Reale SCADA-, CMS-, Wetter- und EAM-Datenverträge sowie Integration der Berechtigungen vor Ort.
- Notfallwiederherstellung, Lasttests, SLOs, Alarmweiterleitung, DAST, manuelle Penetrationstests und Prüfungen nach dem Release.
- Browser-WCAG, visuelle Regression und Abnahme unterstützter Geräte.
- Prüfung der CARE-Lizenz, Replays aus produktivem Objektspeicher und manuelle Prüfung windparkübergreifender Ontologiezuordnungen.

Cloudflare Sites hostet nur die Webanwendung und das Identitätsgateway, nicht das Python-Backend. Ein erfolgreicher Sites-Release ersetzt keine Abnahme von Backend, Abhängigkeiten oder Systemen vor Ort. Der detaillierte Nachweisstatus steht in [EXECUTION_PROGRESS.md](./EXECUTION_PROGRESS.md), [AUDIT_REPORT.md](./AUDIT_REPORT.md) und [UI_AUDIT_REPORT.md](./UI_AUDIT_REPORT.md).

## Mitwirken

Informationen zu Entwicklungssetup, Validierung und PR-Prozess finden Sie im [Leitfaden für Beiträge (Chinesisch)](./CONTRIBUTING.md), Hinweise zu Schwachstellenmeldungen und Schutz von Zugangsdaten in der [Sicherheitsrichtlinie (Chinesisch)](./SECURITY.md).

Issues und Pull Requests sind willkommen für:

- Reale Probleme bei Workflow-Abschluss, Berechtigungen, Idempotenz oder Wiederherstellung.
- Barrierefreiheit, responsive Layouts, Datenvisualisierung und Darstellung des Laufzeitstatus.
- Funktionen mit realen Datenquellen, Berechtigungsmodell und Abnahmekriterien.
- Tests, die Probleme reproduzieren und tatsächliches Verhalten prüfen.

Erzeugen Sie keine scheinbar bestandenen Ergebnisse durch Löschen fehlgeschlagener Tests, Abschwächen von Assertions, hartcodierte Rückgabewerte, stilles Verschlucken von Fehlern oder Rückgriff auf Fixtures.

## Lizenz

OpenVigils eigener Quellcode steht unter der [Apache-Lizenz 2.0](./LICENSE).

Der CARE-v6-Datensatz und abgeleitete Distributionsartefakte, die seiner Lizenz unterliegen, sind nicht von Apache-Lizenz 2.0 erfasst und werden nicht mit diesem Repository verteilt. Diese Bestände folgen [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) und erfordern Quellenangabe, Lizenzlink, Beschreibung von Änderungen und Weitergabe unter gleichen Bedingungen.

## Danksagungen

- [CARE v6](https://doi.org/10.5281/zenodo.15846963) — Christian Gück, Cyriana M. A. Roelofs / Fraunhofer IEE
- [EnergyFaultDetector](https://github.com/AEFDI/EnergyFaultDetector) — festgelegte offizielle Referenz zur Prüfung des CARE-Scores
- PyScada, NetBird Dashboard, OpenClaw Mission Control, next-shadcn-dashboard-starter und Grafana — Referenzen für Informationsarchitektur, Interaktion und visuelle Recherche

Vollständige Drittquellen, festgelegte Commits, Lizenzen und Grenzen der unabhängigen Neuimplementierung finden Sie in [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
