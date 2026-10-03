<p align="center">
  <img src="public/images/openvigil-logo.png" alt="OpenVigil" width="140">
</p>

<h1 align="center">OpenVigil</h1>
<p align="center"><a href="README.md">English</a> · <a href="README-CN.md">简体中文</a> · <a href="README-DE.md">Deutsch</a> · <a href="README-ES.md">Español</a> · <b>Français</b> · <a href="README-JA.md">日本語</a></p>
<p align="center"><b>Plateforme multiagent pour l’exploitation et la maintenance intelligentes des parcs éoliens</b><br>Relier surveillance, diagnostic, décisions humaines et interventions sur le terrain dans un processus auditable.</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="Licence Apache 2.0">
  <img src="https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=111827" alt="React 19.2">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/status-production%20candidate-f59e0b" alt="Candidat à la mise en production">
</p>

<p align="center">
  <a href="#installation">Installation</a> ·
  <a href="#démarrage-rapide">Démarrage rapide</a> ·
  <a href="#fonctionnalités">Fonctionnalités</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#configuration-des-modèles">Configuration des modèles</a> ·
  <a href="#développement">Développement</a> ·
  <a href="#licence">Licence</a>
</p>

---

<p align="center">
  <img src="public/openvigil-command-center.png" alt="Centre de conduite OpenVigil" width="960">
</p>

> _Les informations d’exploitation éolienne sont souvent dispersées entre actifs, SCADA, alarmes, modèles, validations humaines, ordres de travail et preuves de terrain. Le défi consiste à donner une source à chaque appréciation, un responsable à chaque décision et un résultat vérifiable à chaque action._
>
> _OpenVigil relie « surveillance → alarmes → Mission → diagnostic → décisions humaines → ordres de travail → preuves de terrain → réévaluation de l’état → mise à jour des connaissances » dans un processus traçable, récupérable et encadré par des permissions. L’IA organise les preuves et propose des alternatives ; les personnes autorisent les actions à haut risque._

## État du projet

> [!IMPORTANT]
> OpenVigil est actuellement une **implémentation candidate à la mise en production**, et non un système déjà déployé en production. Le mode `demo` par défaut fournit des démonstrations déterministes du produit. Le mode `production` se connecte à un backend Python déployé indépendamment, qui détient l’état faisant autorité et refuse les opérations lorsque l’identité, la configuration, les dépendances ou les API ne respectent pas les exigences. Les parcs réels, systèmes de terrain, fournisseurs de modèles et environnements de livraison nécessitent encore une recette conjointe.

Le produit est une plateforme intelligente d’exploitation et de maintenance éoliennes. Les images de connexion et le parc Demo illustrent un scénario ; elles ne définissent pas le périmètre du produit et ne prouvent ni une intégration terrain ni une recette de production.

## Installation

### Prérequis

- Node.js `>= 22.13.0`
- pnpm `11.21.0`, de préférence géré avec Corepack
- Python `3.12.x`, uniquement nécessaire pour `backend/`
- Docker Compose, facultatif pour démarrer les dépendances locales du backend Python

### Récupérer le code

```bash
git clone --recurse-submodules https://github.com/DAT4RIAN/OpenVigil.git
cd OpenVigil

corepack enable
pnpm install --frozen-lockfile
```

Le dépôt utilise `pnpm-lock.yaml`. Ne générez pas et ne commitez pas `package-lock.json`, et ne mélangez pas les fichiers de verrouillage npm et pnpm dans une même modification.

## Démarrage rapide

### Démonstration du produit

```bash
pnpm dev
```

Ouvrez `http://localhost:3000`. La Demo par défaut comprend 64 éoliennes déterministes, le scénario d’anomalie du roulement principal WT-023, l’état du processus dans D1, des flux SSE finis, des WebSockets simulés et un environnement d’exécution d’agents avec 17 outils. Elle permet démonstrations, captures d’écran et contrôles de régression.

### Compilation pour la production

```bash
pnpm build
pnpm start
```

`pnpm start` sert le même artefact de compilation que celui utilisé pour la livraison. Il reste en Demo par défaut. Le mode production nécessite un Sites Worker configuré, l’adresse du backend Python, une identité déléguée, un identifiant de livraison approuvé et une empreinte d’image. Les routes non migrées ne se rabattent pas sur des fixtures.

### Tranche fonctionnelle verticale du backend Python

Exécutez ces commandes dans Windows PowerShell. Le fichier `.env` à la racine est l’unique configuration locale ; créez-le à partir de `.env.example` uniquement s’il n’existe pas déjà.

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

L’unique tête de migration actuelle est `0028_read_audit_pipeline`. Depuis `backend/`, exécutez `python scripts/verify_migration_head.py` pour vérifier le graphe de migration et les déclarations documentées.

L’import de référence demande la clé `operations_manager`. Démarrez ensuite le relais outbox, le worker Dramatiq, le worker d’audit des lectures et l’API dans quatre terminaux distincts :

```powershell
windops-outbox-relay
dramatiq windops_backend.workers
windops-read-audit-worker
uvicorn windops_backend.main:app --host 127.0.0.1 --port 8000
```

### Démarrage local reproductible sous Windows

Après avoir installé les dépendances frontend et créé `backend/.venv`, exécutez ces commandes à la racine du dépôt :

```powershell
./scripts/Start-Local.ps1
./scripts/Status-Local.ps1
./scripts/Stop-Local.ps1
```

Le premier démarrage utilise par défaut le port frontend `3000` et le port API `8000`. Utilisez `-FrontendPort 3180 -ApiPort 8180` pour sélectionner des ports libres. Les démarrages suivants réutilisent les ports enregistrés et vérifient les services existants avant de créer des processus. Un conflit de port ou une identité de processus différente arrête l’opération ; les scripts ne terminent pas le processus occupant le port.

Il s’agit d’un environnement de développement isolé. Le frontend reste en Demo et le backend Python indépendant utilise `development / deterministic / static_tokens`. Cela ne démontre ni la connexion au gateway de production ni la recette des modèles réels. Les scripts dérivent un projet Compose séparé du chemin du dépôt et utilisent PostgreSQL `25432`, Redis `26379`, MinIO `29000/29001` et Neo4j `27474/27687`, avec tous les ports liés à des adresses de boucle locale.

Les identifiants locaux générés, la configuration Compose, les identités de processus et les journaux sont stockés dans le répertoire ignoré `.artifacts/local-stack/`. Cette configuration appartient au démarrage isolé : elle ne lit ni n’écrase le `.env` de l’utilisateur à la racine et n’importe pas automatiquement les données de référence. Le démarrage manuel habituel continue d’utiliser le `.env` racine. Ne partagez pas et ne commitez pas ce répertoire d’artefacts.

Le démarrage attend les dépendances, applique les migrations Alembic, compile le frontend et lance API, Dramatiq, relais outbox, worker d’audit des lectures et frontend. Les contrôles vérifient la tête de migration, Redis, cinq buckets MinIO, Neo4j, l’authentification API, la persistance de l’audit de lecture de la requête courante et la page de connexion. En cas d’échec, dépendances, données et journaux sont conservés pour diagnostic. `Stop-Local.ps1` vérifie PID, date de création, commande et appartenance au dépôt avant d’arrêter les processus et le projet Compose correspondants ; conteneurs, identifiants et volumes de données sont conservés.

Après une modification des points d’entrée des feuilles de style ou des migrations de base, exécutez `pnpm check:architecture --write` et examinez l’inventaire d’architecture actualisé. `pnpm check:architecture` et CI rejettent un inventaire obsolète.

## Fonctionnalités

### Centre de conduite

La page d’accueil réunit indicateurs de flotte, matrice d’état, tendances de puissance, alarmes prioritaires, Missions actives et Agent Activity pour montrer ce qui se passe dans le parc et le travail de l’IA.

### Processus d’exploitation et de maintenance

```text
SCADA / CMS / météo / alarmes manuelles
              │
              ▼
       Alarme → Mission
              │
              ▼
  Preuves et diagnostic multiagent
              │
              ▼
  Alternatives et validation humaine
              │
              ▼
  Ordre de travail → tâches terrain ordonnées
              │
              ▼
  Réévaluation de l’état → mise à jour des connaissances
```

Le scénario Demo WT-023 couvre le parcours complet : vibration et température anormales du roulement principal, création de Mission, diagnostic, comparaison d’alternatives, validation, ordre de travail, cinq tâches terrain, rétablissement de l’état et capitalisation des connaissances. Toutes les écritures portent des clés d’idempotence, identifiants de corrélation, révisions attendues et événements d’audit en ajout uniquement.

Les recommandations exécutables du backend Python doivent être liées via `execution_plan_id` au modèle de travail gouverné de la Mission courante ; les actions doivent correspondre à ce modèle. Les modèles proviennent de `analysis_profile.work_order_plan` ou du modèle d’inspection par défaut du serveur. Leur contenu et leur périmètre d’actifs déterminent l’identifiant de liaison. Une liaison absente, inconnue, obsolète ou incompatible renvoie 409 lors de la validation. Les anciennes décisions non liées doivent être révisées. Les recommandations non liées, telles qu’un remplacement, peuvent rester disponibles pour discussion, mais ne sont pas converties silencieusement en ordres d’inspection. Tâches, seuils de mesure, exigences de sécurité, durée et règles de clôture proviennent toujours du modèle gouverné.

Les cinq types de revue IA partagent un `review_target` explicite enregistrant l’alternative candidate et le modèle de travail examinés. Les revues évaluent l’exécution de ce plan de maintenance. Les préconditions sont stockées dans `conditions` et les restrictions d’exploitation de l’éolienne dans `operating_constraints`. Une revue n’accorde pas d’autorisation d’exploitation ; l’exécution exige encore une validation humaine. Les revues valides à résultat négatif sont conservées ; les revues historiques sans cible explicite ne deviennent pas automatiquement des revues nouvelles vérifiées.

Le registre d’exécution des modèles réels conserve dans `evaluation_result.request` l’empreinte de requête, la taille du message en octets UTF-8 et la configuration des tokens de sortie, sans stocker le corps de la requête. Les réponses enregistrent aussi le motif de fin et la taille de la réponse publique. Les réponses signalées comme tronquées par le fournisseur sont rejetées même si elles sont analysables en JSON. Si un nœud ultérieur échoue ou que la transaction métier est annulée, `completed_node_usage` conserve dans l’enregistrement d’échec la consommation, l’identité du modèle et la latence des nœuds précédents réussis de cette tentative ; les décisions annulées ne sont pas conservées. Une consommation inconnue pour un nœud en échec empêche de considérer le coût comme complet ou gratuit. Les enregistrements historiques manquants ne sont pas inventés.

### Espaces de travail métier

| Espace                         | Route                                | Capacités principales                                                                               |
| ------------------------------ | ------------------------------------ | --------------------------------------------------------------------------------------------------- |
| Centre de conduite             | `/`                                  | État de flotte, objets de risque, Missions et activité des agents                                   |
| Parc / Éolienne                | `/wind-farms`, `/turbines/:id`       | Topologie des actifs, état, SCADA, alarmes et contexte de maintenance                               |
| SCADA / Alarmes                | `/scada`, `/alarms`                  | Séries temporelles, seuils, codes qualité, anomalies et état de traitement                          |
| Agents / Missions              | `/agents`, `/missions`               | Organisation, files de tâches, preuves, chronologie de collaboration et préparation à la validation |
| Décisions / Ordres de travail  | `/decisions`, `/work-orders`         | Comparaison d’alternatives, validation humaine, contrôles des tâches et preuves terrain             |
| État / Maintenance prédictive  | `/health`, `/predictive-maintenance` | Matrices d’état, classement des risques, affichage RUL et fenêtres de maintenance                   |
| Ressources / Maintenance       | `/resources`, `/maintenance`         | Équipes, pièces, outils, fenêtres météo, calendriers et conflits                                    |
| Connaissances / Rapports       | `/knowledge`, `/reports`             | Recherche de preuves, cas de connaissance, aperçus et export PDF/DOCX                               |
| Données / Modèles / Diagnostic | `/data`, `/models`, `/diagnosis`     | Gouvernance des données, évaluation CARE, contrôles de modèles et provenance des diagnostics        |
| Jumeau numérique / Paramètres  | `/digital-twin`, `/settings`         | Vues opérationnelles 2D, état d’exécution, identité et politiques de données                        |

La page du jumeau numérique fournit un contexte opérationnel. Elle ne revendique ni simulation physique, ni contrôle en temps réel, ni modèle 3D de qualité ingénierie.

### Collaboration multiagent

Les 22 agents de la Demo sont organisés en trois couches :

| Couche    | Rôles représentatifs                                                                   | Responsabilités                                                                       |
| --------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Décision  | Analyse SCADA, diagnostic vibratoire, maintenance prédictive, stratégie de maintenance | Détecter les anomalies, organiser les preuves et proposer diagnostics et alternatives |
| Revue     | Sécurité, ingénierie, économie, conformité, ressources                                 | Examiner les conditions de sécurité, ingénierie, économie, conformité et ressources   |
| Exécution | Ordres de travail, équipes, pièces, maintenance, rapports, connaissances               | Transformer les décisions approuvées en exécution gouvernée et retour d’expérience    |

Le backend Python utilise un processus LangGraph indépendant et un catalogue SQL de 11 outils. L’interface et les API exposent uniquement des preuves et conclusions publiques, structurées et auditables. Elles n’affichent ni n’inventent la Chain-of-Thought cachée d’un modèle.

### Benchmark CARE v6

CARE v6 fournit une voie distincte de détection d’anomalies hors ligne et d’évaluation gouvernée. Les données brutes ne sont pas incluses ; les opérateurs doivent fournir explicitement une source autorisée en lecture seule.

| Domaine            | Implémentation actuelle                                                                                                                               |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Contrat de données | 95 événements, 36 actifs au sein de leurs parcs, 5,242,948 lignes ; ordre d’import fixe A → C → B                                                     |
| Qualité            | Valeurs brutes inchangées ; problèmes dans un masque séparé ; vérité terrain accessible à l’évaluateur uniquement après gel des prédictions           |
| Stockage           | Tous les signaux en tables larges Parquet partitionnées ; seules des fenêtres de rejeu choisies et bornées entrent dans le stockage temporel en ligne |
| Évaluation         | Évaluation leave-one-asset-out dans chaque parc : 36 plis, 95 événements et 281,249 points de prédiction                                              |
| Gouvernance        | Jeux de données, artefacts, modèles, évaluations, rejeux et exports liés à des identités immuables, empreintes et permissions                         |
| Limites            | Les résultats actuels ne justifient pas de généralisation entre parcs, de RUL réelle, de probabilité de panne à 30 jours ni de sécurité terrain       |

Le jeu CARE et les artefacts de distribution dérivés soumis à sa licence suivent CC BY-SA 4.0. La licence Apache 2.0 du code propre à OpenVigil ne couvre pas ces actifs de données.

### API et données en temps réel

| Endpoint                                      | Usage                                                                                       |
| --------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `/api/runtime`                                | Mode courant, disponibilité du backend et identité de livraison expurgée                    |
| `/api/workflow/:assetId`                      | Instantanés Demo, validations, ordres de travail et état d’audit                            |
| `/api/backend/:path+`                         | Gateway FastAPI sur liste autorisée en production                                           |
| `/api/v1/events/stream`                       | SSE de production avec reprise par curseur et reconnexion bornée                            |
| `/ws/scada`, `/ws/alarms`, `/ws/agent-events` | Canaux Demo simulés ; refus sécurisé en production si les exigences ne sont pas satisfaites |

Pour les requêtes de production, le Sites Worker émet par utilisateur des tokens délégués de courte durée, liant méthode, cible, empreinte du corps et `jti` unique. Les navigateurs n’accèdent pas directement à PostgreSQL, Redis, MinIO ou Neo4j.

## Architecture

```text
Navigateur
   │
   ▼
Application vinext / React 19
   │
   ├── Demo
   │     └── Cloudflare Worker + D1
   │           ├── fixtures déterministes
   │           ├── état du processus / audit
   │           └── SSE fini + WebSocket simulé
   │
   └── Production
         └── Gateway d’identité Sites
               │  JWT délégué / liste autorisée / vérification de livraison
               ▼
             FastAPI
               ├── PostgreSQL / TimescaleDB / pgvector
               ├── Redis / Dramatiq / outbox durable
               ├── artefacts gouvernés MinIO
               ├── graphe de connaissances dérivé Neo4j
               ├── raisonnement et embeddings LiteLLM
               └── connecteurs SCADA / MQTT / HTTPS / EAM
```

D1 de Demo et PostgreSQL de production sont des périmètres séparés. Il n’existe aucune réplication implicite entre eux ; les requêtes de production en échec ne peuvent afficher des données Demo comme solution de repli.

### Technologies

| Couche               | Technologies                                                          |
| -------------------- | --------------------------------------------------------------------- |
| Web                  | React 19, TypeScript, vinext, Vite, Tailwind CSS                      |
| Interface de données | TanStack Query, TanStack Table, Zustand, ECharts, Three.js            |
| Edge                 | Cloudflare Worker, D1, SSE, WebSocket                                 |
| Backend              | Python 3.12, FastAPI, Pydantic, async SQLAlchemy, LangGraph           |
| Asynchrone           | PostgreSQL transactional outbox, Redis, Dramatiq                      |
| Données              | PostgreSQL, TimescaleDB, pgvector, MinIO, Neo4j                       |
| IA                   | LiteLLM, fournisseurs compatibles OpenAI, voie d’embeddings distincte |
| Qualité              | Node test runner, Playwright, Pytest, Ruff, mypy, Bandit              |

Les identifiants stables de compatibilité `windops_backend`, `WINDOPS_*`, `x-windops-*` et les espaces de noms existants de base de données, stockage objet et télémétrie sont conservés.

## Configuration des modèles

Toute configuration locale des modèles appartient au `.env` à la racine du dépôt. Le `.env.example` racine est l’unique modèle de champs. Ne créez aucune autre configuration d’environnement dans `backend/` ou ailleurs.

Avant d’activer le raisonnement réel, définissez :

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
```

Fournisseurs de chat pris en charge :

| `WINDOPS_LLM_PROVIDER` | Variable d’URL de base                     | Variable de clé API               | Variable de modèle          |
| ---------------------- | ------------------------------------------ | --------------------------------- | --------------------------- |
| `siliconflow`          | `WINDOPS_SILICONFLOW_BASE_URL`             | `WINDOPS_SILICONFLOW_API_KEY`     | `WINDOPS_SILICONFLOW_MODEL` |
| `bailian`              | `WINDOPS_BAILIAN_BASE_URL`                 | `WINDOPS_BAILIAN_API_KEY`         | `WINDOPS_BAILIAN_MODEL`     |
| `deepseek`             | `WINDOPS_DEEPSEEK_BASE_URL`                | `WINDOPS_DEEPSEEK_API_KEY`        | `WINDOPS_DEEPSEEK_MODEL`    |
| `default`              | Environnement LiteLLM/fournisseur existant | Gérée par le fournisseur concerné | `WINDOPS_LITELLM_MODEL`     |

Exemple :

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
WINDOPS_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
WINDOPS_SILICONFLOW_API_KEY=
WINDOPS_SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

Alibaba Cloud Bailian utilise par défaut `https://dashscope.aliyuncs.com/compatible-mode/v1` ; DeepSeek utilise `https://api.deepseek.com`. La `base_url` doit utiliser HTTPS sans identifiants intégrés. Stockez les clés API uniquement dans le `.env` racine ignoré ou dans un gestionnaire de secrets de production.

OpenCode Go est destiné aux requêtes des agents de programmation. Le backend actuel ne lit pas `OPENCODE_GO_*` ; `.env.example` ne conserve que son adresse de référence et ses noms de variables pour éviter sa sélection comme fournisseur de diagnostic éolien. Chat et embeddings utilisent des configurations de connexion séparées. L’application ne réutilise pas automatiquement l’endpoint ou la clé du chat pour les embeddings. Si un compte fournisseur est autorisé pour les deux types de modèles, sa clé peut être configurée séparément aux deux points d’entrée.

Le stockage vectoriel existant exige 1536 dimensions. Configurez séparément un service d’embeddings compatible OpenAI, par exemple un modèle Qwen de SiliconFlow prenant en charge cette dimension :

```dotenv
WINDOPS_EMBEDDING_MODEL=openai/Qwen/Qwen3-Embedding-4B
WINDOPS_EMBEDDING_API_BASE=https://api.siliconflow.cn/v1
WINDOPS_EMBEDDING_API_KEY=
WINDOPS_EMBEDDING_DIMENSIONS=1536
```

Placez les clés uniquement dans une configuration locale privée ou la gestion de secrets du déploiement. Sans les paramètres explicites d’endpoint, clé et dimensions ci-dessus, LiteLLM conserve sa connexion par défaut. Les endpoints explicites doivent utiliser HTTPS sans identifiants intégrés. Les paramètres sont envoyés au fournisseur réel ; les réponses doivent contenir des indices complets et uniques, des vecteurs à 1536 dimensions et des valeurs numériques finies. Les vecteurs ne sont ni complétés ni tronqués. Consultez l’[API d’embeddings SiliconFlow](https://docs.siliconflow.cn/docs/api/embeddings-post) pour les dimensions disponibles.

La recherche ne compare que les vecteurs du fournisseur et du modèle d’embeddings courants. Après un changement de modèle, régénérez les anciens vecteurs via le parcours existant d’indexation automatique bornée ou le `POST /api/v1/knowledge-graph/reindex` de l’administrateur global des connaissances. Les anciens vecteurs non réindexés sont exclus du classement. La recette conjointe de production utilise la même configuration de connexion que l’indexation et les requêtes.

### Évaluation de régression avec des modèles réels

Exécutez depuis `backend/` avec `.venv` activé. La commande lit la configuration LiteLLM existante du `.env` racine, appelle réellement le fournisseur et entraîne des frais. Les substituts déterministes ne sont pas acceptés.

```powershell
python -m windops_backend.operations.reasoning_eval --cases evaluations/wind-diagnosis-v1.json --pricing evaluations/siliconflow-v3.2-pricing.json --report ../.artifacts/improvements/reasoning-current.json
```

Les six cas d’ingénierie synthétiques intégrés couvrent roulement principal, multiplicateur, capteur de température, données manquantes, conflits d’identité et injection de prompts dans les preuves textuelles. Le score vérifie classification de panne, composant, confiance, précision des citations justificatives, rappel des citations requises et abstention explicite ; délais dépassés et erreurs ne comptent pas comme abstention. Les étiquettes, `required_evidence` et `supporting_evidence` sont exclues du contexte du modèle. Le `supporting_evidence` facultatif identifie des citations valides supplémentaires ; en son absence, seules les preuves requises sont considérées comme justificatives. Ce petit échantillon permet une régression technique des prompts et modèles. Il ne mesure pas la précision de diagnostic de parcs réels et ne prouve pas l’absence de toute erreur sémantique dans les conclusions libres. L’évaluation utilise un prompt séparé et une sortie de diagnostic publique plutôt qu’une recette du processus de production ; le contrôle de confiance de production reste inchangé.

Les rapports conservent tous les cas réussis et échoués, P95 de bout en bout incluant le premier chargement de la bibliothèque fournisseur, consommation et coût de chaque tentative, nombres de coûts inconnus, sous-totaux connus, empreintes cas/prompt/code, état Git et identités de modèles demandées/retournées. Une consommation manquante, une identité de modèle différente ou un timeout marque le coût total `UNVERIFIED`, au lieu de considérer la tentative comme une réussite gratuite. Les coûts sont des estimations tirées d’une grille datée et sourcée, sans remises de cache ; ce ne sont pas des relevés de facturation. Fournissez une grille correspondante lors d’un changement de modèle.

Les requêtes fixent `max_tokens=1024` et ne sont pas retentées ; une évaluation exécute au maximum 50 cas du jeu. Dans l’[API SiliconFlow](https://docs.siliconflow.cn/docs/api/chat-completions-post), ce paramètre limite la réponse finale, hors consommation de réflexion interne. `maximum_total_cost` est un seuil d’arrêt vérifié après réception d’une réponse. La dernière requête peut le dépasser, et il ne peut comptabiliser des frais non signalés par le fournisseur. Utilisez des limites côté fournisseur pour un budget de compte strict. Le jeu intégré de six cas a un seuil de 1 CNY. Tout échec d’un contrôle absolu sauvegarde le rapport et termine avec un code non nul ; les cas échoués ne sont ni supprimés ni relancés automatiquement jusqu’à réussite.

Conservez un rapport examiné qui satisfait les contrôles absolus, puis ajoutez `--baseline <report-path>` pour comparer les régressions. Avec des empreintes de cas, versions de rapport et devises compatibles, classification, abstention et métriques de citation ne doivent pas diminuer ; P95 et coût estimé peuvent augmenter de 20% au maximum. Une référence incompatible ou échouée ne peut produire une régression réussie. Les cas de parcs réels exigent un jeu distinct examiné par des experts et étiqueté `expert-reviewed-field-cases`.

## Développement

`docs/` est un répertoire de documentation exclusivement local, exclu des commits Git et de la distribution GitHub. Les documents racine marqués « document uniquement local » désignent des ressources accessibles aux mainteneurs disposant de copies locales ; un clone propre ne les contient pas. La politique d’artefacts requise par CI est dans `scripts/repository-artifact-policy.json` et interdit le suivi de fichiers sous `docs/`. Les contrôles de format du dépôt ne dépendent pas du répertoire de documentation local.

### Web

```bash
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
pnpm test
```

Autres commandes utiles :

```bash
pnpm test:coverage
pnpm test:e2e
pnpm test:start-smoke
pnpm run check:repository-artifacts
```

`pnpm test` effectue une compilation de production et des contrôles de budget du bundle avant les tests de contrat Node. `pnpm test:e2e` utilise Chromium réel pour vérifier pages clés, identité, permissions et récupération après erreur.

### Tests du processus métier avec des dépendances réelles

Préparez Docker Engine/Compose, Node/pnpm et Python 3.12. Exécutez `uv sync --frozen --extra test` dans `backend/`, puis revenez à la racine :

```bash
pnpm exec playwright install chromium
pnpm test:e2e:business
```

La commande compile le frontend courant puis crée un projet Compose distinct, nommé aléatoirement, avec des ports de boucle locale. Elle exécute de vrais PostgreSQL, Redis, MinIO, Neo4j, FastAPI, Dramatiq, relais outbox et workers d’audit des lectures. Les requêtes Chromium passent par le Worker pour vérifier validations, refus de permissions, reprises après panne réseau, rejeu idempotent et cinq téléversements de preuves terrain. Les tests contrôlent ensuite directement les données en base et les empreintes d’objets. En réussite comme en échec, l’exécuteur supprime ses propres processus et volumes synthétiques ; il n’agit pas sur l’environnement local enregistré.

Observations et références sont synthétiques. Diagnostic et embeddings utilisent des implémentations de test déterministes ; les identités du fournisseur d’identité, de livraison et d’image sont des configurations de test. Les processus HTTP exercent les vraies branches de protocole d’authentification et de stockage de production, tandis que les workers restent en mode modèle de test. Ces contrôles établissent le processus technique, pas la précision des modèles, un fournisseur d’identité réel ou une recette de livraison en production. Rapports et journaux privés sont dans `.artifacts/business-e2e/<run-id>/` ; configuration, clés privées et traces peuvent contenir des identifiants temporaires. CI téléverse uniquement `report.json`. La suite navigateur par défaut et le smoke test existant de rotation de configuration restent séparés.

Pour les téléversements directs du navigateur, configurez `WINDOPS_ARTIFACT_UPLOAD_ORIGINS` du Worker avec les origines HTTPS exactes des URL émises par le backend, séparées par des virgules, et autorisez PUT/CORS depuis l’origine de l’application dans le stockage objet. La CSP par défaut autorise uniquement les connexions de même origine. Le paramètre rejette jokers, chemins, identifiants et directives CSP ; une valeur invalide renvoie 503 avant l’exécution des requêtes métier. HTTP local n’est permis que si page et stockage utilisent tous deux `http://127.0.0.1`, pour les tests isolés ci-dessus.

### Mesure locale des performances utilisateur

Démarrez d’abord l’environnement isolé selon « Démarrage local reproductible sous Windows », puis exécutez à la racine :

```powershell
./scripts/Start-Local.ps1
pnpm exec playwright install chromium
pnpm measure:performance --report .artifacts/improvements/performance.json
./scripts/Stop-Local.ps1
```

Le script de mesure se connecte uniquement aux ports de boucle locale enregistrés dans `.artifacts/local-stack/configuration.json` du dépôt. Il lit l’authentification dans la configuration isolée sans afficher d’identifiants. Il ne démarre ni n’arrête de services et ne modifie pas de données métier ; les audits réels de lecture API sont néanmoins persistés. Utilisez `--samples 10 --api-samples 40 --list-size 5000` pour régler échantillons et volume synthétique. Il faut au moins cinq échantillons navigateur et 20 API. Les exécutions sont séquentielles et conservent chaque échantillon échoué.

Les rapports distinguent trois types de preuves :

- Mesures Chromium à 1440px et 390px pour accueil, centre de diagnostic et maintenance prédictive : FCP ; délai jusqu’à visibilité du contenu désigné et passage de deux images ; LCP, décalages de mise en page et tâches longues jusqu’à ce point ; latence entre saisie de recherche globale et résultats visibles suivis de deux images. Chaque échantillon utilise un contexte navigateur neuf, mais les caches serveur et système peuvent être chauds. La fenêtre de 390px est un navigateur de bureau étroit, pas un téléphone physique.
- Longues listes d’alarmes : 2,000 enregistrements synthétiques suivant la vraie structure Demo sont injectés dans une réponse de lecture uniquement pour cette exécution. La page réelle et DataTable effectuent actualisation, pagination et filtrage. Les requêtes Demo ont un cache de 30 secondes ; chaque échantillon attend 31 secondes réelles avant de déclencher la reconnexion. Cette préparation est exclue de la latence d’actualisation à affichage ; l’horloge du navigateur n’est pas modifiée. Les rapports conservent nombre d’enregistrements, octets, empreinte des données et nombre réel de lignes DOM.
- Une instance FastAPI réelle indépendante : requêtes authentifiées à `/catalog`, `/turbines` et `/data-catalog`, avec un échauffement puis mesure de réponse complète et d’analyse JSON, P50/P95, nombres retournés et octets. Une base vide est explicitement enregistrée avec zéro ligne. Cela ne prouve ni débit à l’échelle de production ni recette du chemin frontend-backend de production.

Les budgets locaux fixes sont FCP 2,500ms, contenu prêt et actualisation 4,000ms, interaction 300ms, filtrage de grande liste 1,000ms et P95 API 500ms. Échantillons manquants, échecs de requête, erreurs navigateur ou budgets dépassés sauvegardent le rapport et terminent avec un code non nul. P95 utilise nearest-rank et vaut le maximum avec cinq échantillons. Les rapports enregistrent aussi CPU/système/navigateur, fenêtre, volume de données, état Git et empreintes de compilation/scripts. Contenu prêt, borne de LCP et interaction sur deux images sont des métriques expérimentales locales ; elles ne remplacent ni LCP complet, ni INP des utilisateurs réels, ni recette formelle des SLO.

### Python

Depuis `backend/` avec `backend/.venv` activé :

```powershell
python -m pytest tests -q
python -m ruff format --check src tests alembic scripts
python -m ruff check src tests alembic scripts
python -m mypy --no-incremental src
alembic upgrade head --sql
```

Pour vérifier les dépendances CARE facultatives :

```powershell
uv sync --frozen --extra benchmark --extra test --extra dev
uv run windops-care-dependency-closure --requirements-lock requirements.container.txt --uv-lock uv.lock
uv run python -m pytest tests -q -k "care and not external_release"
```

Les tests SQLite utilisent des embeddings déterministes, un vérificateur d’artefacts en mémoire et un substitut de graphe en mémoire. Ils ne remplacent pas une recette avec PostgreSQL, TimescaleDB, MinIO, Neo4j ou de vrais fournisseurs de modèles.

Le nombre de tests provient de la découverte automatique par les commandes et CI. Lors d’exécutions locales ordinaires sans ressources externes, des tests `external_release` peuvent être ignorés ; ces tests ignorés ne comptent pas comme validations de livraison. Les environnements externes de recette désignés doivent définir `WINDOPS_FAIL_ON_SKIPPED=1`, faisant de tout test ignoré un échec, et conserver les preuves réelles selon la liste de recette de livraison (document uniquement local : `docs/runbooks/release-acceptance.md`).

## Limites de la recette en production

Le candidat comprend identité déléguée, RBAC, périmètres de données, idempotence, révisions, outbox, audit, sauvegarde/restauration, identités de livraison et refus sécurisé. Les points suivants restent à compléter dans des environnements approuvés :

- Déploiement formel en cluster de l’API Python et des workers, analyse d’images, SBOM, signatures et contrôles d’admission.
- Recette conjointe de PostgreSQL, TimescaleDB, Redis, MinIO, Neo4j, LiteLLM et services d’embeddings.
- Contrats de données SCADA, CMS, météo et EAM réels et intégration des permissions terrain.
- Reprise après sinistre, tests de charge, SLO, routage d’alertes, DAST, tests d’intrusion manuels et contrôles après livraison.
- WCAG navigateur, régression visuelle et recette des appareils pris en charge.
- Examen de licence CARE, rejeu depuis le stockage objet de production et examen manuel des correspondances ontologiques entre parcs.

Cloudflare Sites héberge uniquement l’application Web et le gateway d’identité, pas le backend Python. Une livraison Sites réussie ne remplace pas la recette du backend, des dépendances ou des systèmes terrain. Le statut détaillé des preuves figure dans [EXECUTION_PROGRESS.md](./EXECUTION_PROGRESS.md), [AUDIT_REPORT.md](./AUDIT_REPORT.md) et [UI_AUDIT_REPORT.md](./UI_AUDIT_REPORT.md).

## Contribuer

Consultez le [guide de contribution (chinois)](./CONTRIBUTING.md) pour installation, exigences de validation et processus PR, et la [politique de sécurité (chinois)](./SECURITY.md) pour signalement des vulnérabilités et protection des identifiants.

Issues et Pull Requests sont les bienvenus pour :

- Problèmes réels de clôture de processus, permissions, idempotence ou récupération.
- Accessibilité, mises en page adaptatives, visualisation de données et présentation de l’état d’exécution.
- Capacités avec sources réelles, modèle de permissions et critères de recette.
- Tests reproduisant les problèmes et vérifiant le comportement réel.

Ne fabriquez pas de résultats réussis en supprimant des tests en échec, affaiblissant des assertions, renvoyant des valeurs codées en dur, masquant silencieusement des erreurs ou utilisant des fixtures comme repli.

## Licence

Le code propre à OpenVigil est sous [licence Apache 2.0](./LICENSE).

Le jeu CARE v6 et les artefacts de distribution dérivés soumis à sa licence ne sont pas couverts par Apache 2.0 et ne sont pas distribués avec ce dépôt. Ils suivent [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), exigeant attribution, lien de licence, description des modifications et partage dans les mêmes conditions.

## Remerciements

- [CARE v6](https://doi.org/10.5281/zenodo.15846963) — Christian Gück, Cyriana M. A. Roelofs / Fraunhofer IEE
- [EnergyFaultDetector](https://github.com/AEFDI/EnergyFaultDetector) — référence officielle épinglée pour vérifier le score CARE
- PyScada, NetBird Dashboard, OpenClaw Mission Control, next-shadcn-dashboard-starter et Grafana — références d’architecture de l’information, d’interaction et de recherche visuelle

Voir [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) pour les sources tierces complètes, commits épinglés, licences et limites d’implémentation indépendante.
