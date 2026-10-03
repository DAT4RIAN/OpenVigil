<p align="center">
  <img src="public/images/openvigil-logo.png" alt="OpenVigil" width="140">
</p>

<h1 align="center">OpenVigil</h1>
<p align="center"><a href="README.md">English</a> · <a href="README-CN.md">简体中文</a> · <a href="README-DE.md">Deutsch</a> · <a href="README-ES.md">Español</a> · <a href="README-FR.md">Français</a> · <a href="README-JA.md">日本語</a> · <a href="README-KO.md">한국어</a> · <b>Italiano</b></p>
<p align="center"><b>Piattaforma multiagente per la gestione e la manutenzione intelligenti degli impianti eolici</b><br>Collega monitoraggio, diagnosi, decisioni umane e interventi sul campo in un flusso verificabile tramite audit.</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="Licenza Apache 2.0">
  <img src="https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=111827" alt="React 19.2">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/status-production%20candidate-f59e0b" alt="Candidato alla produzione">
</p>

<p align="center">
  <a href="#installazione">Installazione</a> ·
  <a href="#avvio-rapido">Avvio rapido</a> ·
  <a href="#funzionalità">Funzionalità</a> ·
  <a href="#architettura">Architettura</a> ·
  <a href="#configurazione-dei-modelli">Configurazione dei modelli</a> ·
  <a href="#sviluppo">Sviluppo</a> ·
  <a href="#licenza">Licenza</a>
</p>

---

<p align="center">
  <img src="public/openvigil-command-center.png" alt="Centro operativo OpenVigil" width="960">
</p>

> _Le informazioni sulla gestione eolica sono spesso distribuite tra impianti, SCADA, allarmi, modelli, approvazioni umane, ordini di lavoro ed evidenze sul campo. La sfida consiste nell’associare una fonte a ogni valutazione, un responsabile a ogni decisione e un risultato verificabile a ogni azione._
>
> _OpenVigil collega «monitoraggio → allarmi → Mission → diagnosi → decisioni umane → ordini di lavoro → evidenze sul campo → rivalutazione dello stato → aggiornamento delle conoscenze» in un flusso tracciabile, recuperabile e regolato da autorizzazioni. L’IA organizza le evidenze e propone alternative; le persone autorizzano le azioni ad alto rischio._

## Stato del progetto

> [!IMPORTANT]
> OpenVigil è attualmente un’**implementazione candidata alla produzione**, non un sistema già operativo in produzione. La modalità predefinita `demo` offre dimostrazioni deterministiche del prodotto. La modalità `production` si collega a un backend Python distribuito in modo indipendente che mantiene lo stato autorevole e rifiuta le operazioni quando identità, configurazione, dipendenze o API non soddisfano i requisiti. Parchi eolici reali, sistemi sul campo, fornitori di modelli e ambienti di rilascio richiedono ancora un collaudo congiunto.

Il prodotto è concepito come piattaforma intelligente per la gestione e la manutenzione eoliche. Le immagini di accesso e il parco Demo illustrano uno scenario; non definiscono l’ambito del prodotto né dimostrano integrazione sul campo o accettazione in produzione.

## Installazione

### Requisiti

- Node.js `>= 22.13.0`
- pnpm `11.21.0`, preferibilmente gestito tramite Corepack
- Python `3.12.x`, necessario solo per `backend/`
- Docker Compose, facoltativo per avviare le dipendenze locali del backend Python

### Ottenere il codice

```bash
git clone --recurse-submodules https://github.com/DAT4RIAN/OpenVigil.git
cd OpenVigil

corepack enable
pnpm install --frozen-lockfile
```

Il repository usa `pnpm-lock.yaml`. Non generare né includere nei commit `package-lock.json` e non mescolare file di lock npm e pnpm nella stessa modifica.

## Avvio rapido

### Demo del prodotto

```bash
pnpm dev
```

Aprire `http://localhost:3000`. La Demo predefinita include 64 turbine deterministiche, lo scenario di anomalia del cuscinetto principale WT-023, lo stato del flusso in D1, stream SSE finiti, WebSocket simulati e un ambiente di esecuzione degli agenti con 17 strumenti. Supporta dimostrazioni del prodotto, screenshot e verifiche di regressione.

### Build per la produzione

```bash
pnpm build
pnpm start
```

`pnpm start` serve lo stesso artefatto di build utilizzato per il rilascio. La modalità predefinita resta Demo. La modalità produzione richiede un Sites Worker configurato, l’indirizzo del backend Python, un’identità delegata, un ID di rilascio approvato e un digest dell’immagine. Le route non ancora migrate non ripiegano su fixture.

### Porzione funzionale verticale del backend Python

Eseguire i seguenti comandi in Windows PowerShell. Il `.env` nella radice è l’unico file di configurazione locale; crearlo da `.env.example` solo se non esiste già.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test,dev]"

docker compose up -d
alembic upgrade head
windops-reference-import --reference-pack wt023
```

L’unica revisione finale di migrazione attuale è `0028_read_audit_pipeline`. Da `backend/`, eseguire `python scripts/verify_migration_head.py` per verificare il grafo delle migrazioni e le dichiarazioni documentate.

L’importazione di riferimento richiede la chiave `operations_manager`. Avviare poi il relay outbox, il worker Dramatiq, il worker di audit delle letture e l’API in quattro terminali distinti:

```powershell
windops-outbox-relay
dramatiq windops_backend.workers
windops-read-audit-worker
uvicorn windops_backend.main:app --host 127.0.0.1 --port 8000
```

### Avvio locale riproducibile su Windows

Dopo aver installato le dipendenze frontend e creato `backend/.venv`, eseguire questi comandi dalla radice del repository:

```powershell
./scripts/Start-Local.ps1
./scripts/Status-Local.ps1
./scripts/Stop-Local.ps1
```

Il primo avvio usa per impostazione predefinita la porta frontend `3000` e la porta API `8000`. Usare `-FrontendPort 3180 -ApiPort 8180` per scegliere porte disponibili. Gli avvii successivi riutilizzano le porte salvate e verificano i servizi esistenti prima di creare processi. Un conflitto di porta o un’identità di processo non corrispondente interrompe l’operazione; gli script non terminano il processo che occupa la porta.

Si tratta di uno stack di sviluppo isolato. Il frontend resta in Demo e il backend Python indipendente usa `development / deterministic / static_tokens`. Questo non dimostra la connessione al gateway di produzione né l’accettazione di modelli reali. Gli script ricavano un progetto Compose separato dal percorso del repository e usano PostgreSQL `25432`, Redis `26379`, MinIO `29000/29001` e Neo4j `27474/27687`, con tutte le porte associate a indirizzi di loopback.

Credenziali locali generate, configurazione Compose, identità dei processi e log sono salvati nella directory ignorata `.artifacts/local-stack/`. Questa configurazione appartiene all’avvio isolato: non legge né sovrascrive il `.env` dell’utente nella radice e non importa automaticamente dati di riferimento. L’avvio manuale ordinario continua a usare il `.env` nella radice. Non condividere né includere nei commit questa directory di artefatti.

L’avvio attende le dipendenze, applica le migrazioni Alembic, compila il frontend e avvia API, Dramatiq, relay outbox, worker di audit delle letture e frontend. I controlli di stato verificano la revisione finale di migrazione, Redis, cinque bucket MinIO, Neo4j, autenticazione API, persistenza dell’audit di lettura della richiesta corrente e pagina di accesso. In caso di errore, dipendenze, dati e log sono conservati per la diagnosi. `Stop-Local.ps1` verifica PID, ora di creazione, comando e appartenenza al repository prima di fermare i processi e il progetto Compose corrispondenti; conserva container, credenziali e volumi dati.

Dopo aver modificato i punti di ingresso dei fogli di stile o le migrazioni del database, eseguire `pnpm check:architecture --write` e controllare l’inventario aggiornato dell’architettura. `pnpm check:architecture` e CI rifiutano un inventario obsoleto.

## Funzionalità

### Centro operativo

La pagina iniziale riunisce KPI della flotta, matrice di stato, tendenze di potenza, allarmi prioritari, Mission attive e Agent Activity per mostrare ciò che accade nel parco e il lavoro dell’IA.

### Flusso di gestione e manutenzione

```text
SCADA / CMS / meteo / allarmi manuali
              │
              ▼
       Allarme → Mission
              │
              ▼
  Evidenze e diagnosi multiagente
              │
              ▼
  Alternative e approvazione umana
              │
              ▼
  Ordine di lavoro → attività sul campo ordinate
              │
              ▼
  Rivalutazione dello stato → aggiornamento delle conoscenze
```

Lo scenario Demo WT-023 segue l’intero percorso: vibrazione e temperatura anomale del cuscinetto principale, creazione di Mission, diagnosi, confronto delle alternative, approvazione, ordine di lavoro, cinque attività sul campo, recupero dello stato e acquisizione delle conoscenze. Tutte le scritture includono chiavi di idempotenza, ID di correlazione, revisioni attese ed eventi di audit solo in aggiunta.

Le raccomandazioni eseguibili nel backend Python devono essere associate tramite `execution_plan_id` al modello di lavoro governato della Mission corrente; le azioni devono corrispondere al modello. I modelli provengono da `analysis_profile.work_order_plan` o dal modello di ispezione predefinito del server. Contenuto e ambito degli asset determinano l’identificatore dell’associazione. Associazioni mancanti, sconosciute, obsolete o incompatibili restituiscono 409 durante l’approvazione. Le vecchie decisioni prive di associazione richiedono revisione. Raccomandazioni non associate, come una sostituzione, possono restare disponibili per discussione ma non diventano silenziosamente ordini di ispezione. Attività, soglie di misura, requisiti di sicurezza, durata e regole di chiusura provengono sempre dal modello governato.

I cinque tipi di revisione IA condividono un `review_target` esplicito che registra l’alternativa candidata e il modello di lavoro esaminati. Le revisioni valutano l’esecuzione di quel piano di manutenzione. Le precondizioni sono salvate in `conditions` e le restrizioni operative della turbina in `operating_constraints`; una revisione non concede autorizzazione all’esercizio e l’esecuzione richiede ancora approvazione umana. Le revisioni valide con esito negativo sono conservate; le revisioni storiche prive di obiettivo esplicito non diventano automaticamente nuove revisioni verificate.

Il registro di esecuzione dei modelli reali salva in `evaluation_result.request` il digest della richiesta, la dimensione del messaggio in byte UTF-8 e la configurazione dei token di output, senza memorizzare il corpo della richiesta. Le risposte registrano anche motivo di conclusione e dimensione della risposta pubblica. Le risposte segnalate come troncate dal fornitore sono rifiutate anche se interpretabili come JSON. Se un nodo successivo fallisce o la transazione aziendale viene annullata, `completed_node_usage` nel record di errore conserva utilizzo, identità del modello e latenza dei nodi precedenti riusciti nello stesso tentativo; le decisioni annullate non sono conservate. Un utilizzo sconosciuto di un nodo fallito impedisce di considerare il costo del tentativo completo o gratuito. I record storici mancanti non vengono inventati.

### Aree di lavoro

| Area                            | Route                                | Capacità principali                                                                                       |
| ------------------------------- | ------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| Centro operativo                | `/`                                  | Stato della flotta, oggetti di rischio, Mission e attività degli agenti                                   |
| Parco eolico / Turbina          | `/wind-farms`, `/turbines/:id`       | Topologia degli asset, stato, SCADA, allarmi e contesto di manutenzione                                   |
| SCADA / Allarmi                 | `/scada`, `/alarms`                  | Monitoraggio temporale, soglie, codici di qualità, anomalie e stato di gestione                           |
| Agenti / Mission                | `/agents`, `/missions`               | Organizzazione degli agenti, code, evidenze, cronologia di collaborazione e preparazione all’approvazione |
| Decisioni / Ordini di lavoro    | `/decisions`, `/work-orders`         | Confronto delle alternative, approvazione umana, controlli delle attività ed evidenze sul campo           |
| Stato / Manutenzione predittiva | `/health`, `/predictive-maintenance` | Matrici di stato, graduatoria dei rischi, visualizzazione RUL e finestre di manutenzione                  |
| Risorse / Manutenzione          | `/resources`, `/maintenance`         | Squadre, ricambi, strumenti, finestre meteo, calendari e controllo dei conflitti                          |
| Conoscenze / Report             | `/knowledge`, `/reports`             | Ricerca di evidenze, casi di conoscenza, anteprime ed esportazione PDF/DOCX                               |
| Dati / Modelli / Diagnosi       | `/data`, `/models`, `/diagnosis`     | Governance dei dati, valutazione CARE, controlli dei modelli e provenienza delle diagnosi                 |
| Gemello digitale / Impostazioni | `/digital-twin`, `/settings`         | Viste operative 2D, stato di esecuzione, identità e politiche dei dati                                    |

La pagina del gemello digitale fornisce contesto operativo. Non dichiara simulazione fisica, controllo in tempo reale o un modello 3D di livello ingegneristico.

### Collaborazione multiagente

I 22 agenti della Demo sono organizzati in tre livelli:

| Livello    | Ruoli rappresentativi                                                                        | Responsabilità                                                                |
| ---------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Decisione  | Analisi SCADA, diagnosi delle vibrazioni, manutenzione predittiva, strategia di manutenzione | Rilevare anomalie, organizzare evidenze e proporre diagnosi e alternative     |
| Revisione  | Sicurezza, ingegneria, economia, conformità, risorse                                         | Esaminare condizioni di sicurezza, ingegneria, economia, conformità e risorse |
| Esecuzione | Ordini di lavoro, squadre, ricambi, manutenzione, report, conoscenze                         | Trasformare decisioni approvate in esecuzione governata e feedback            |

Il backend Python usa un flusso LangGraph indipendente e un catalogo SQL con 11 strumenti. UI e API espongono solo evidenze e conclusioni pubbliche, strutturate e verificabili tramite audit. Non mostrano né inventano la Chain-of-Thought nascosta di un modello.

### Benchmark CARE v6

CARE v6 offre un percorso separato per rilevamento offline delle anomalie e valutazione governata. I dati grezzi non sono inclusi nel repository; gli operatori devono fornire esplicitamente una fonte autorizzata in sola lettura.

| Area               | Implementazione attuale                                                                                                                                  |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Contratto dei dati | 95 eventi, 36 asset all’interno dei rispettivi parchi, 5,242,948 righe; ordine di importazione fisso A → C → B                                           |
| Qualità            | Valori grezzi invariati; problemi registrati in una maschera separata; ground truth disponibile al valutatore solo dopo il congelamento delle previsioni |
| Archiviazione      | Tutti i segnali in tabelle larghe Parquet partizionate; solo finestre di replay selezionate e limitate entrano nell’archivio temporale online            |
| Valutazione        | Valutazione leave-one-asset-out in ciascun parco: 36 fold, 95 eventi e 281,249 punti di previsione                                                       |
| Governance         | Dataset, artefatti, modelli, valutazioni, replay ed esportazioni associati a identità immutabili, digest e autorizzazioni                                |
| Limiti             | I risultati attuali non dimostrano generalizzazione tra parchi, RUL reale, probabilità di guasto a 30 giorni o sicurezza sul campo                       |

Il dataset CARE e gli artefatti derivati di distribuzione soggetti alla sua licenza seguono CC BY-SA 4.0. La Licenza Apache 2.0 del codice proprio di OpenVigil non copre questi asset di dati.

### API e dati in tempo reale

| Endpoint                                      | Scopo                                                                                          |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `/api/runtime`                                | Modalità corrente, disponibilità del backend e identità di rilascio con dati sensibili rimossi |
| `/api/workflow/:assetId`                      | Snapshot Demo, approvazioni, ordini di lavoro e stato di audit                                 |
| `/api/backend/:path+`                         | Gateway FastAPI su lista di consentiti in produzione                                           |
| `/api/v1/events/stream`                       | SSE di produzione con ripresa tramite cursore e riconnessione limitata                         |
| `/ws/scada`, `/ws/alarms`, `/ws/agent-events` | Canali Demo simulati; rifiuto sicuro in produzione se i requisiti non sono soddisfatti         |

Per le richieste di produzione, il Sites Worker emette token delegati di breve durata per ciascun utente, associando metodo, destinazione, digest del corpo e `jti` univoco. I browser non accedono direttamente a PostgreSQL, Redis, MinIO o Neo4j.

## Architettura

```text
Browser
   │
   ▼
Applicazione vinext / React 19
   │
   ├── Demo
   │     └── Cloudflare Worker + D1
   │           ├── fixture deterministiche
   │           ├── stato del flusso / audit
   │           └── SSE finiti + WebSocket simulati
   │
   └── Produzione
         └── Gateway di identità Sites
               │  JWT delegato / lista di consentiti / verifica del rilascio
               ▼
             FastAPI
               ├── PostgreSQL / TimescaleDB / pgvector
               ├── Redis / Dramatiq / outbox persistente
               ├── artefatti governati MinIO
               ├── grafo di conoscenza derivato Neo4j
               ├── ragionamento ed embedding LiteLLM
               └── connettori SCADA / MQTT / HTTPS / EAM
```

D1 della Demo e PostgreSQL di produzione sono confini separati. Non esiste replicazione implicita tra loro e le query di produzione fallite non possono mostrare dati Demo come ripiego.

### Stack tecnologico

| Livello     | Tecnologie                                                            |
| ----------- | --------------------------------------------------------------------- |
| Web         | React 19, TypeScript, vinext, Vite, Tailwind CSS                      |
| UI dei dati | TanStack Query, TanStack Table, Zustand, ECharts, Three.js            |
| Edge        | Cloudflare Worker, D1, SSE, WebSocket                                 |
| Backend     | Python 3.12, FastAPI, Pydantic, async SQLAlchemy, LangGraph           |
| Asincrono   | PostgreSQL transactional outbox, Redis, Dramatiq                      |
| Dati        | PostgreSQL, TimescaleDB, pgvector, MinIO, Neo4j                       |
| IA          | LiteLLM, fornitori compatibili OpenAI, percorso di embedding separato |
| Qualità     | Node test runner, Playwright, Pytest, Ruff, mypy, Bandit              |

Sono mantenuti gli identificatori stabili di compatibilità `windops_backend`, `WINDOPS_*`, `x-windops-*` e i namespace esistenti di database, archiviazione a oggetti e telemetria.

## Configurazione dei modelli

Tutta la configurazione locale dei modelli appartiene al `.env` nella radice del repository. Il `.env.example` nella radice è l’unico modello dei campi. Non creare un’altra configurazione d’ambiente in `backend/` o altrove.

Prima di attivare il ragionamento reale, impostare:

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
```

Fornitori di chat supportati:

| `WINDOPS_LLM_PROVIDER` | Variabile URL di base                | Variabile chiave API                 | Variabile modello           |
| ---------------------- | ------------------------------------ | ------------------------------------ | --------------------------- |
| `siliconflow`          | `WINDOPS_SILICONFLOW_BASE_URL`       | `WINDOPS_SILICONFLOW_API_KEY`        | `WINDOPS_SILICONFLOW_MODEL` |
| `bailian`              | `WINDOPS_BAILIAN_BASE_URL`           | `WINDOPS_BAILIAN_API_KEY`            | `WINDOPS_BAILIAN_MODEL`     |
| `deepseek`             | `WINDOPS_DEEPSEEK_BASE_URL`          | `WINDOPS_DEEPSEEK_API_KEY`           | `WINDOPS_DEEPSEEK_MODEL`    |
| `default`              | Ambiente LiteLLM/fornitore esistente | Gestita dal fornitore corrispondente | `WINDOPS_LITELLM_MODEL`     |

Esempio:

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
WINDOPS_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
WINDOPS_SILICONFLOW_API_KEY=
WINDOPS_SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

Alibaba Cloud Bailian usa per impostazione predefinita `https://dashscope.aliyuncs.com/compatible-mode/v1`; DeepSeek usa `https://api.deepseek.com`. La `base_url` deve usare HTTPS senza credenziali incorporate. Salvare le chiavi API solo nel `.env` ignorato nella radice o in un gestore di segreti di produzione.

OpenCode Go è destinato al traffico degli agenti di programmazione. Il backend attuale non legge `OPENCODE_GO_*`; `.env.example` conserva solo indirizzo di riferimento e nomi delle variabili per evitarne la selezione come fornitore di diagnosi eolica. Chat ed embedding usano configurazioni di connessione separate. L’applicazione non riutilizza automaticamente endpoint o chiave della chat per gli embedding. Se un account è autorizzato per entrambi i tipi di modello, la sua chiave può essere configurata separatamente nei due punti di ingresso.

L’archivio vettoriale esistente richiede 1536 dimensioni. Configurare separatamente un servizio di embedding compatibile OpenAI, ad esempio un modello Qwen di SiliconFlow che supporti questo numero di dimensioni:

```dotenv
WINDOPS_EMBEDDING_MODEL=openai/Qwen/Qwen3-Embedding-4B
WINDOPS_EMBEDDING_API_BASE=https://api.siliconflow.cn/v1
WINDOPS_EMBEDDING_API_KEY=
WINDOPS_EMBEDDING_DIMENSIONS=1536
```

Inserire le chiavi solo in configurazioni locali private o nella gestione dei segreti del deployment. Senza le impostazioni esplicite di endpoint, chiave e dimensioni riportate sopra, LiteLLM mantiene la connessione predefinita. Gli endpoint espliciti devono usare HTTPS senza credenziali incorporate. I parametri vengono inviati al fornitore reale e le risposte devono contenere indici completi e univoci, vettori a 1536 dimensioni e valori numerici finiti. I vettori non vengono completati né troncati. Consultare l’[API di embedding SiliconFlow](https://docs.siliconflow.cn/docs/api/embeddings-post) per le dimensioni supportate.

La ricerca confronta solo vettori del fornitore e modello di embedding correnti. Dopo un cambio di modello, rigenerare i vecchi vettori tramite il percorso esistente di indicizzazione automatica limitata o il `POST /api/v1/knowledge-graph/reindex` dell’amministratore globale delle conoscenze. I vecchi vettori non reindicizzati sono esclusi dalla graduatoria. Il collaudo congiunto in produzione usa la stessa configurazione di connessione dell’indicizzazione e delle query.

### Valutazione di regressione con modelli reali

Eseguire da `backend/` con `.venv` attivato. Il comando legge la configurazione LiteLLM esistente dal `.env` nella radice, effettua chiamate reali al fornitore e comporta costi. I sostituti deterministici non sono accettati.

```powershell
python -m windops_backend.operations.reasoning_eval --cases evaluations/wind-diagnosis-v1.json --pricing evaluations/siliconflow-v3.2-pricing.json --report ../.artifacts/improvements/reasoning-current.json
```

I sei casi ingegneristici sintetici integrati coprono cuscinetto principale, moltiplicatore, sensore di temperatura, dati mancanti, conflitti d’identità e prompt injection nel testo delle evidenze. Il punteggio verifica classificazione del guasto, componente, confidenza, precisione delle citazioni di supporto, richiamo delle citazioni richieste e astensione esplicita; timeout ed errori non contano come astensione. Etichette, `required_evidence` e `supporting_evidence` sono esclusi dal contesto del modello. Il `supporting_evidence` facoltativo identifica ulteriori citazioni valide; se assente, solo le evidenze richieste sono considerate di supporto. Questo piccolo campione consente regressioni ingegneristiche di prompt e modelli. Non stima l’accuratezza diagnostica di parchi reali né prova che le conclusioni in testo libero siano prive di tutti gli errori semantici. La valutazione usa un prompt separato e un output pubblico di diagnosi, anziché un collaudo del flusso di produzione; il controllo di confidenza di produzione resta invariato.

I report conservano tutti i casi riusciti e falliti, P95 end-to-end inclusivo del primo caricamento della libreria del fornitore, utilizzo e costo per tentativo, conteggi dei costi sconosciuti, subtotali noti, digest di casi/prompt/codice, stato Git e identità dei modelli richieste/restituite. Utilizzo mancante, identità del modello non corrispondente o timeout rendono il costo totale `UNVERIFIED`, anziché trattare il tentativo come successo gratuito. I costi sono stime da una tabella datata e con fonti, senza sconti di cache; non sono registrazioni di fatturazione. Fornire un file prezzi corrispondente quando si cambia modello.

Le richieste impostano `max_tokens=1024` e non vengono ritentate; una valutazione esegue al massimo 50 casi dell’insieme. Nell’[API SiliconFlow](https://docs.siliconflow.cn/docs/api/chat-completions-post), questo parametro limita la risposta finale escludendo il consumo del ragionamento interno del modello. `maximum_total_cost` è una soglia di arresto controllata dopo la ricezione della risposta. L’ultima richiesta può superarla e non è possibile contabilizzare costi non dichiarati dal fornitore. Usare limiti lato fornitore se serve un budget rigoroso dell’account. L’insieme integrato di sei casi usa una soglia di 1 CNY. Qualsiasi fallimento di un controllo assoluto salva il report e termina con codice diverso da zero; i casi falliti non sono cancellati né rieseguiti automaticamente fino al successo.

Conservare un report verificato che superi i controlli assoluti, poi aggiungere `--baseline <report-path>` per il confronto di regressione. Con digest dei casi, versioni dei report e valute compatibili, le metriche di classificazione, astensione e citazione non devono diminuire; P95 e costo stimato possono aumentare al massimo del 20%. Una baseline incompatibile o fallita non può produrre una regressione superata. I casi di parchi reali richiedono un insieme distinto esaminato da esperti e contrassegnato `expert-reviewed-field-cases`.

## Sviluppo

`docs/` è una directory di documentazione esclusivamente locale, esclusa dai commit Git e dalla distribuzione GitHub. I documenti nella radice contrassegnati «documento solo locale» rimandano a materiali disponibili ai manutentori con copie locali; un clone pulito non li include. La politica degli artefatti richiesta da CI è in `scripts/repository-artifact-policy.json` e vieta il tracciamento dei file sotto `docs/`. I controlli di formattazione del repository non dipendono dalla documentazione locale.

### Web

```bash
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
pnpm test
```

Altri comandi utili:

```bash
pnpm test:coverage
pnpm test:e2e
pnpm test:start-smoke
pnpm run check:repository-artifacts
```

`pnpm test` esegue una build di produzione e controlli del budget del bundle prima dei test di contratto Node. `pnpm test:e2e` usa Chromium reale per verificare pagine principali, identità, autorizzazioni e recupero dagli errori.

### Test del flusso operativo con dipendenze reali

Preparare Docker Engine/Compose, Node/pnpm e Python 3.12. Eseguire `uv sync --frozen --extra test` in `backend/`, quindi tornare alla radice:

```bash
pnpm exec playwright install chromium
pnpm test:e2e:business
```

Il comando compila il frontend corrente, poi crea un progetto Compose separato dal nome casuale con porte di loopback. Esegue PostgreSQL, Redis, MinIO, Neo4j, FastAPI, Dramatiq, relay outbox e worker di audit delle letture reali. Le richieste Chromium passano attraverso il Worker per verificare approvazioni, rifiuto dei permessi, nuovi tentativi dopo errori di rete, replay idempotente e cinque caricamenti di evidenze sul campo. Infine i test controllano direttamente record del database e hash degli oggetti. Sia in caso di successo sia di errore, l’esecutore rimuove i propri processi e volumi di dati sintetici; non agisce sullo stack locale salvato.

Osservazioni e materiali di riferimento sono sintetici. Diagnosi ed embedding usano implementazioni di test deterministiche; identità del fornitore d’identità, del rilascio e dell’immagine sono configurazioni di test. I processi HTTP esercitano i rami effettivi dei protocolli di autenticazione e archiviazione di produzione, mentre i worker mantengono la modalità modello di test. Questi controlli dimostrano il flusso ingegneristico, non l’accuratezza dei modelli, un fornitore d’identità reale o il collaudo del rilascio in produzione. Report e log privati sono in `.artifacts/business-e2e/<run-id>/`; configurazione, chiavi private e tracce possono contenere credenziali temporanee. CI carica solo `report.json`. La suite browser predefinita e lo smoke test esistente della rotazione di configurazione restano separati.

Per caricamenti diretti dal browser, configurare `WINDOPS_ARTIFACT_UPLOAD_ORIGINS` del Worker con le origini HTTPS esatte delle URL di caricamento emesse dal backend, separate da virgole, e consentire PUT/CORS dall’origine dell’applicazione nell’archivio a oggetti. La CSP predefinita consente solo connessioni alla stessa origine. L’impostazione rifiuta caratteri jolly, percorsi, credenziali e direttive CSP; valori non validi restituiscono 503 prima di eseguire richieste operative. HTTP locale è consentito solo se pagina e archivio usano entrambi `http://127.0.0.1`, per i test isolati sopra descritti.

### Misurazione locale delle prestazioni utente

Avviare prima lo stack isolato seguendo «Avvio locale riproducibile su Windows», quindi eseguire dalla radice:

```powershell
./scripts/Start-Local.ps1
pnpm exec playwright install chromium
pnpm measure:performance --report .artifacts/improvements/performance.json
./scripts/Stop-Local.ps1
```

Lo script di misurazione si collega solo alle porte di loopback registrate in `.artifacts/local-stack/configuration.json` di questo repository. Legge l’autenticazione dalla configurazione isolata senza stampare credenziali. Non avvia né ferma servizi e non modifica dati operativi; gli audit reali di lettura API vengono comunque salvati. Usare `--samples 10 --api-samples 40 --list-size 5000` per regolare campioni e dimensione dei dati sintetici di carico. Servono almeno cinque campioni browser e 20 API. Le esecuzioni sono sequenziali e conservano ogni campione fallito.

I report distinguono tre tipi di evidenze:

- Misure Chromium a 1440px e 390px per pagina iniziale, centro diagnosi e manutenzione predittiva: FCP; tempo fino alla visibilità del contenuto designato e al trascorrere di due frame; LCP, spostamenti di layout e attività lunghe fino a quel punto; latenza dall’evento di input della ricerca globale fino ai risultati visibili e a due frame trascorsi. Ogni campione usa un nuovo contesto browser, mentre le cache del server e del sistema operativo possono essere già calde. Il viewport di 390px è una finestra stretta di browser desktop, non un telefono fisico.
- Liste lunghe di allarmi: 2,000 record sintetici secondo la struttura effettiva della Demo vengono inseriti in una risposta di lettura solo durante quell’esecuzione browser. La pagina reale e DataTable effettuano aggiornamento, paginazione e filtraggio. Le query Demo hanno una cache di 30 secondi; ogni campione attende 31 secondi reali prima di attivare la riconnessione. Questa preparazione è esclusa dalla latenza tra aggiornamento e visualizzazione, e l’orologio del browser non viene modificato. I report conservano numero dei record, byte della risposta, digest dei dati e numero effettivo di righe DOM.
- Un’istanza FastAPI reale indipendente: richieste autenticate a `/catalog`, `/turbines` e `/data-catalog`, con un riscaldamento seguito da misure di risposta completa e parsing JSON, P50/P95, conteggi restituiti e byte. Un database vuoto è registrato esplicitamente con zero righe restituite. Non dimostra throughput alla scala dei dati di produzione né collaudo del percorso frontend-backend di produzione.

I budget locali fissi sono FCP 2,500ms, contenuto pronto e aggiornamento liste 4,000ms, interazione 300ms, filtraggio di grandi liste 1,000ms e P95 API 500ms. Campioni mancanti, richieste fallite, errori browser o budget superati salvano il report e terminano con codice diverso da zero. P95 usa nearest-rank e coincide con il massimo con cinque campioni. I report registrano anche CPU/sistema/browser, viewport, volume dei dati, stato Git e digest di build/script. Contenuto pronto, termine della misura LCP e interazione su due frame sono metriche sperimentali locali; non sostituiscono LCP completo, INP degli utenti reali o collaudo formale degli SLO.

### Python

Da `backend/` con `backend/.venv` attivato:

```powershell
python -m pytest tests -q
python -m ruff format --check src tests alembic scripts
python -m ruff check src tests alembic scripts
python -m mypy --no-incremental src
alembic upgrade head --sql
```

Per verificare le dipendenze CARE facoltative:

```powershell
uv sync --frozen --extra benchmark --extra test --extra dev
uv run windops-care-dependency-closure --requirements-lock requirements.container.txt --uv-lock uv.lock
uv run python -m pytest tests -q -k "care and not external_release"
```

I test SQLite usano embedding deterministici, un verificatore di artefatti in memoria e un sostituto del grafo in memoria. Non sostituiscono il collaudo con PostgreSQL, TimescaleDB, MinIO, Neo4j o fornitori di modelli reali.

Il numero di test deriva dal rilevamento automatico dei comandi e di CI. Nelle esecuzioni locali ordinarie prive di risorse esterne, i test `external_release` possono essere saltati; questi test saltati non contano come collaudi di rilascio superati. Gli ambienti esterni di collaudo designati devono impostare `WINDOPS_FAIL_ON_SKIPPED=1`, rendendo ogni test saltato un errore, e conservare evidenze reali secondo la checklist di accettazione del rilascio (documento solo locale: `docs/runbooks/release-acceptance.md`).

## Limiti del collaudo in produzione

Il candidato include identità delegata, RBAC, ambiti dei dati, idempotenza, revisioni, outbox, audit, backup/ripristino, identità di rilascio e rifiuto sicuro quando i requisiti non sono soddisfatti. Restano da completare in ambienti approvati:

- Deployment formale in cluster di API Python e worker, scansione delle immagini, SBOM, firme e controlli di ammissione.
- Collaudo congiunto di PostgreSQL, TimescaleDB, Redis, MinIO, Neo4j, LiteLLM e servizi di embedding.
- Contratti reali di dati SCADA, CMS, meteo ed EAM e integrazione delle autorizzazioni sul campo.
- Disaster recovery, test di carico, SLO, instradamento degli allarmi, DAST, test di penetrazione manuali e controlli dopo il rilascio.
- WCAG nel browser, regressione visiva e collaudo dei dispositivi supportati.
- Esame della licenza CARE, replay dall’archivio a oggetti di produzione e revisione manuale delle corrispondenze ontologiche tra parchi.

Cloudflare Sites ospita solo l’applicazione Web e il gateway d’identità, non il backend Python. Un rilascio Sites riuscito non sostituisce il collaudo del backend, delle dipendenze o dei sistemi sul campo. Lo stato dettagliato delle evidenze è registrato in [EXECUTION_PROGRESS.md](./EXECUTION_PROGRESS.md), [AUDIT_REPORT.md](./AUDIT_REPORT.md) e [UI_AUDIT_REPORT.md](./UI_AUDIT_REPORT.md).

## Contribuire

Consultare la [guida ai contributi (cinese)](./CONTRIBUTING.md) per configurazione di sviluppo, requisiti di verifica e processo PR, e la [politica di sicurezza (cinese)](./SECURITY.md) per segnalazione delle vulnerabilità e protezione delle credenziali.

Sono benvenuti Issue e Pull Request relativi a:

- Problemi reali di completamento dei flussi, autorizzazioni, idempotenza o recupero.
- Accessibilità, layout adattivi, visualizzazione dei dati e presentazione dello stato di esecuzione.
- Capacità con fonti reali, modello di autorizzazioni e criteri di accettazione.
- Test che riproducano problemi e verifichino comportamenti effettivi.

Non creare risultati apparentemente superati cancellando test falliti, indebolendo asserzioni, restituendo valori fissi nel codice, nascondendo silenziosamente errori o ripiegando su fixture.

## Licenza

Il codice proprio di OpenVigil è distribuito sotto la [Licenza Apache 2.0](./LICENSE).

Il dataset CARE v6 e gli artefatti derivati di distribuzione soggetti alla sua licenza non sono coperti da Apache 2.0 e non sono distribuiti con questo repository. Seguono [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), che richiede attribuzione, collegamento alla licenza, descrizione delle modifiche e condivisione allo stesso modo.

## Ringraziamenti

- [CARE v6](https://doi.org/10.5281/zenodo.15846963) — Christian Gück, Cyriana M. A. Roelofs / Fraunhofer IEE
- [EnergyFaultDetector](https://github.com/AEFDI/EnergyFaultDetector) — riferimento ufficiale fissato per la verifica del punteggio CARE
- PyScada, NetBird Dashboard, OpenClaw Mission Control, next-shadcn-dashboard-starter e Grafana — riferimenti per architettura dell’informazione, interazione e ricerca visiva

Consultare [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) per fonti terze complete, commit fissati, licenze e confini dell’implementazione clean-room.
