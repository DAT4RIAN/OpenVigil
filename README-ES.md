<p align="center">
  <img src="public/images/openvigil-logo.png" alt="OpenVigil" width="140">
</p>

<h1 align="center">OpenVigil</h1>
<p align="center"><a href="README.md">English</a> · <a href="README-CN.md">简体中文</a> · <a href="README-DE.md">Deutsch</a> · <b>Español</b> · <a href="README-FR.md">Français</a> · <a href="README-JA.md">日本語</a> · <a href="README-KO.md">한국어</a> · <a href="README-IT.md">Italiano</a></p>
<p align="center"><b>Plataforma multiagente para la operación y el mantenimiento inteligentes de parques eólicos</b><br>Conecta supervisión, diagnóstico, decisiones humanas y ejecución en campo en un flujo auditable.</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="Licencia Apache 2.0">
  <img src="https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=111827" alt="React 19.2">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/status-production%20candidate-f59e0b" alt="Candidato a producción">
</p>

<p align="center">
  <a href="#instalación">Instalación</a> ·
  <a href="#inicio-rápido">Inicio rápido</a> ·
  <a href="#funcionalidades">Funcionalidades</a> ·
  <a href="#arquitectura">Arquitectura</a> ·
  <a href="#configuración-de-modelos">Configuración de modelos</a> ·
  <a href="#desarrollo">Desarrollo</a> ·
  <a href="#licencia">Licencia</a>
</p>

---

<p align="center">
  <img src="public/openvigil-command-center.png" alt="Centro de operaciones de OpenVigil" width="960">
</p>

> _La información de operación eólica suele estar repartida entre activos, SCADA, alarmas, modelos, aprobaciones humanas, órdenes de trabajo y evidencias de campo. El reto es dar una fuente a cada juicio, un responsable a cada decisión y un resultado verificable a cada acción._
>
> _OpenVigil conecta «supervisión → alarmas → Mission → diagnóstico → decisiones humanas → órdenes de trabajo → evidencias de campo → reevaluación del estado → actualización del conocimiento» en un flujo trazable, recuperable y regido por permisos. La IA organiza evidencias y propone alternativas; las personas autorizan las acciones de alto riesgo._

## Estado del proyecto

> [!IMPORTANT]
> OpenVigil es actualmente una **implementación candidata a producción**, no un sistema ya desplegado en producción. El modo predeterminado `demo` ofrece demostraciones deterministas del producto. El modo `production` se conecta a un backend Python desplegado de forma independiente que mantiene el estado autoritativo y rechaza las operaciones cuando la identidad, la configuración, las dependencias o las API no cumplen los requisitos. Los parques reales, los sistemas de campo, los proveedores de modelos y los entornos de lanzamiento todavía requieren pruebas de aceptación conjuntas.

El producto se orienta a la operación y el mantenimiento inteligentes de parques eólicos. Las imágenes de inicio de sesión y el parque Demo ilustran un escenario; no definen el alcance del producto ni prueban la integración en campo o la aceptación en producción.

## Instalación

### Requisitos

- Node.js `>= 22.13.0`
- pnpm `11.21.0`, preferiblemente gestionado mediante Corepack
- Python `3.12.x`, necesario solo para `backend/`
- Docker Compose, opcional para iniciar las dependencias locales del backend Python

### Obtener el código

```bash
git clone --recurse-submodules https://github.com/DAT4RIAN/OpenVigil.git
cd OpenVigil

corepack enable
pnpm install --frozen-lockfile
```

El repositorio utiliza `pnpm-lock.yaml`. No genere ni incluya en commits `package-lock.json`, ni mezcle archivos de bloqueo de npm y pnpm en un mismo cambio.

## Inicio rápido

### Demostración del producto

```bash
pnpm dev
```

Abra `http://localhost:3000`. La Demo predeterminada incluye 64 aerogeneradores deterministas, el escenario de anomalía del rodamiento principal de WT-023, el estado del flujo en D1, flujos SSE finitos, WebSockets simulados y un entorno de ejecución de agentes con 17 herramientas. Permite demostraciones, capturas de pantalla y comprobaciones de regresión.

### Compilación para producción

```bash
pnpm build
pnpm start
```

`pnpm start` sirve el mismo artefacto de compilación usado para el lanzamiento. Sigue utilizando Demo por defecto. El modo de producción requiere un Sites Worker configurado, la dirección del backend Python, una identidad delegada, un ID de lanzamiento aprobado y el resumen criptográfico de la imagen. Las rutas aún no migradas no recurren a fixtures.

### Corte vertical del backend Python

Ejecute estos comandos en Windows PowerShell. La `.env` de la raíz es el único archivo de configuración local; créelo desde `.env.example` solo si aún no existe.

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

La única revisión final de migración actual es `0032_structural_workflow`. Desde `backend/`, ejecute `python scripts/verify_migration_head.py` para comprobar el grafo de migraciones y las declaraciones documentadas.

La importación de referencia solicita la clave de `operations_manager`. Después, inicie el relay de outbox, el worker Dramatiq, el worker de auditoría de lecturas y la API en cuatro terminales separados:

```powershell
windops-outbox-relay
dramatiq windops_backend.workers
windops-read-audit-worker
uvicorn windops_backend.main:app --host 127.0.0.1 --port 8000
```

### Inicio local reproducible en Windows

Tras instalar las dependencias del frontend y crear `backend/.venv`, ejecute estos comandos desde la raíz del repositorio:

```powershell
./scripts/Start-Local.ps1
./scripts/Status-Local.ps1
./scripts/Stop-Local.ps1
```

El primer inicio utiliza por defecto el puerto `3000` para el frontend y `8000` para la API. Use `-FrontendPort 3180 -ApiPort 8180` para elegir puertos disponibles. Los siguientes inicios reutilizan los puertos guardados y verifican los servicios existentes antes de crear procesos. Un conflicto de puerto o una identidad de proceso incorrecta detiene la operación; los scripts no terminan el proceso que ocupa el puerto.

Es un entorno de desarrollo aislado. El frontend permanece en Demo y el backend Python independiente utiliza `development / deterministic / static_tokens`. Esto no demuestra la conexión al gateway de producción ni la aceptación de modelos reales. Los scripts derivan un proyecto Compose independiente de la ruta del repositorio y utilizan PostgreSQL `25432`, Redis `26379`, MinIO `29000/29001` y Neo4j `27474/27687`, con todos los puertos ligados a direcciones de loopback.

Las credenciales locales generadas, la configuración Compose, las identidades de proceso y los registros se guardan en el directorio ignorado `.artifacts/local-stack/`. Esta configuración pertenece al inicio aislado: no lee ni sobrescribe la `.env` del usuario en la raíz ni importa automáticamente datos de referencia. El inicio manual habitual sigue usando la `.env` de la raíz. No comparta ni incluya este directorio de artefactos en commits.

El inicio espera a las dependencias, aplica migraciones Alembic, compila el frontend e inicia API, Dramatiq, relay de outbox, worker de auditoría de lecturas y frontend. Las comprobaciones de estado verifican la revisión final de migración, Redis, cinco buckets MinIO, Neo4j, autenticación de API, persistencia de la auditoría de lectura de la solicitud actual y página de acceso. Los fallos conservan dependencias, datos y registros para diagnóstico. `Stop-Local.ps1` verifica PID, fecha de creación, comando y pertenencia al repositorio antes de detener los procesos correspondientes y el proyecto Compose; conserva contenedores, credenciales y volúmenes de datos.

Tras cambiar los puntos de entrada de estilos o las migraciones de base de datos, ejecute `pnpm check:architecture --write` y revise el inventario de arquitectura actualizado. `pnpm check:architecture` y CI rechazan un inventario desactualizado.

## Funcionalidades

### Centro de operaciones

La página principal reúne KPI de la flota, una matriz de estado, tendencias de potencia, alarmas prioritarias, Missions activas y Agent Activity para mostrar qué ocurre en el parque y en qué trabaja la IA.

### Flujo de operación y mantenimiento

```text
SCADA / CMS / meteorología / alarmas manuales
              │
              ▼
       Alarma → Mission
              │
              ▼
  Evidencias y diagnóstico multiagente
              │
              ▼
  Alternativas y aprobación humana
              │
              ▼
  Orden de trabajo → tareas de campo ordenadas
              │
              ▼
  Reevaluación del estado → actualización del conocimiento
```

El escenario Demo WT-023 recorre el proceso completo: vibración y temperatura anómalas del rodamiento principal, creación de Mission, diagnóstico, comparación de alternativas, aprobación, orden de trabajo, cinco tareas de campo, recuperación del estado y captura de conocimiento. Todas las escrituras llevan claves de idempotencia, ID de correlación, revisiones esperadas y eventos de auditoría que solo se añaden.

Las recomendaciones ejecutables del backend Python deben vincularse mediante `execution_plan_id` a la plantilla de trabajo gobernada de la Mission actual; las acciones deben coincidir con ella. Las plantillas proceden de `analysis_profile.work_order_plan` o de la plantilla de inspección predeterminada del servidor; su contenido y alcance de activos determinan el identificador de vínculo. Los vínculos ausentes, desconocidos, obsoletos o incompatibles devuelven 409 durante la aprobación. Las decisiones antiguas sin vínculo deben revisarse. Las recomendaciones sin vínculo, como una sustitución, pueden mantenerse para discusión, pero no se convierten silenciosamente en órdenes de inspección. Las tareas, umbrales de medición, requisitos de seguridad, duración y reglas de cierre siempre proceden de la plantilla gobernada.

Los cinco tipos de revisión de IA comparten un `review_target` explícito que registra la alternativa candidata y la plantilla revisada. Las revisiones evalúan la ejecución de ese plan de mantenimiento. Las condiciones previas se guardan en `conditions` y las restricciones de operación del aerogenerador en `operating_constraints`. Una revisión no concede permiso de operación; la ejecución sigue requiriendo aprobación humana. Se conservan las revisiones válidas con resultado negativo; las revisiones históricas sin un objetivo explícito no se convierten automáticamente en nuevas revisiones verificadas.

El registro de ejecución de modelos reales guarda en `evaluation_result.request` el resumen criptográfico de la solicitud, el tamaño del mensaje en bytes UTF-8 y la configuración de tokens de salida, sin almacenar el cuerpo de la solicitud. Las respuestas también registran el motivo de finalización y el tamaño de la respuesta pública. Las respuestas marcadas como truncadas por el proveedor se rechazan incluso si pueden analizarse como JSON. Si falla un nodo posterior o se revierte la transacción de negocio, `completed_node_usage` conserva en el registro del fallo el consumo, la identidad del modelo y la latencia de los nodos anteriores exitosos de ese intento; no se conservan las decisiones revertidas. Un consumo desconocido en un nodo fallido impide considerar completo o gratuito el coste del intento. No se inventan registros históricos ausentes.

### Espacios de trabajo

| Espacio                           | Ruta                                 | Capacidades principales                                                                              |
| --------------------------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| Centro de operaciones             | `/`                                  | Estado de flota, objetos de riesgo, Missions y actividad de agentes                                  |
| Parque / Aerogenerador            | `/wind-farms`, `/turbines/:id`       | Topología de activos, estado, SCADA, alarmas y contexto de mantenimiento                             |
| SCADA / Alarmas                   | `/scada`, `/alarms`                  | Supervisión de series temporales, umbrales, códigos de calidad, anomalías y estado de gestión        |
| Agentes / Missions                | `/agents`, `/missions`               | Organización de agentes, colas, evidencias, cronología de colaboración y preparación para aprobación |
| Decisiones / Órdenes              | `/decisions`, `/work-orders`         | Comparación de alternativas, aprobación humana, controles de tareas y evidencias de campo            |
| Estado / Mantenimiento predictivo | `/health`, `/predictive-maintenance` | Matrices de estado, clasificación de riesgos, visualización de RUL y ventanas de mantenimiento       |
| Recursos / Mantenimiento          | `/resources`, `/maintenance`         | Equipos, repuestos, herramientas, ventanas meteorológicas, calendarios y conflictos                  |
| Conocimiento / Informes           | `/knowledge`, `/reports`             | Recuperación de evidencias, casos de conocimiento, vistas previas y exportación PDF/DOCX             |
| Datos / Modelos / Diagnóstico     | `/data`, `/models`, `/diagnosis`     | Gobernanza de datos, evaluación CARE, controles de modelos y procedencia del diagnóstico             |
| Gemelo digital / Ajustes          | `/digital-twin`, `/settings`         | Vistas operativas 2D, estado de ejecución, identidad y políticas de datos                            |

La página del gemelo digital aporta contexto operativo. No afirma ofrecer simulación física, control en tiempo real ni un modelo 3D de nivel ingenieril.

### Colaboración multiagente

Los 22 agentes de la Demo se organizan en tres capas:

| Capa      | Roles representativos                                                                             | Responsabilidades                                                               |
| --------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Decisión  | Análisis SCADA, diagnóstico de vibraciones, mantenimiento predictivo, estrategia de mantenimiento | Detectar anomalías, organizar evidencias y proponer diagnósticos y alternativas |
| Revisión  | Seguridad, ingeniería, economía, cumplimiento, recursos                                           | Revisar condiciones de seguridad, ingeniería, economía, cumplimiento y recursos |
| Ejecución | Órdenes de trabajo, equipos, repuestos, mantenimiento, informes, conocimiento                     | Convertir decisiones aprobadas en ejecución gobernada y retroalimentación       |

El backend Python utiliza un flujo LangGraph independiente y un catálogo SQL con 11 herramientas. La interfaz y las API muestran únicamente evidencias y conclusiones públicas, estructuradas y auditables. No muestran ni inventan la Chain-of-Thought oculta de un modelo.

### Benchmark CARE v6

CARE v6 proporciona una vía independiente de detección de anomalías sin conexión y evaluación gobernada. El repositorio no incluye datos brutos; los operadores deben aportar explícitamente una fuente autorizada de solo lectura.

| Área              | Implementación actual                                                                                                                                             |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Contrato de datos | 95 eventos, 36 activos dentro de sus parques, 5,242,948 filas; orden de importación fijo A → C → B                                                                |
| Calidad           | Valores brutos intactos; problemas registrados en una máscara separada; etiquetas de referencia disponibles para el evaluador solo tras congelar las predicciones |
| Almacenamiento    | Todas las señales en tablas anchas Parquet particionadas; solo ventanas de reproducción seleccionadas y acotadas entran al almacén temporal en línea              |
| Evaluación        | Evaluación leave-one-asset-out dentro de cada parque: 36 particiones, 95 eventos y 281,249 puntos de predicción                                                   |
| Gobernanza        | Datos, artefactos, modelos, evaluaciones, reproducciones y exportaciones ligados a identidades inmutables, resúmenes criptográficos y permisos                    |
| Límites           | Los resultados actuales no permiten afirmar generalización entre parques, RUL real, probabilidad de fallo a 30 días ni seguridad en campo                         |

El conjunto CARE y los artefactos derivados de distribución sujetos a su licencia siguen CC BY-SA 4.0. La licencia Apache 2.0 del código propio de OpenVigil no cubre estos activos de datos.

### API y datos en tiempo real

| Endpoint                                      | Finalidad                                                                                      |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `/api/runtime`                                | Modo actual, disponibilidad del backend e identidad de lanzamiento con datos sensibles ocultos |
| `/api/workflow/:assetId`                      | Instantáneas del flujo Demo, aprobaciones, órdenes y estado de auditoría                       |
| `/api/backend/:path+`                         | Gateway FastAPI limitado por lista de permitidos en producción                                 |
| `/api/v1/events/stream`                       | SSE de producción con reanudación por cursor y reconexión acotada                              |
| `/ws/scada`, `/ws/alarms`, `/ws/agent-events` | Canales Demo simulados; rechazan las operaciones en producción si no se cumplen los requisitos |

En solicitudes de producción, el Sites Worker emite tokens delegados de corta duración por usuario, vinculando método, destino, resumen del cuerpo y `jti` único. Los navegadores no acceden directamente a PostgreSQL, Redis, MinIO ni Neo4j.

## Arquitectura

```text
Navegador
   │
   ▼
Aplicación vinext / React 19
   │
   ├── Demo
   │     └── Cloudflare Worker + D1
   │           ├── fixtures deterministas
   │           ├── estado del flujo / auditoría
   │           └── SSE finito + WebSocket simulado
   │
   └── Producción
         └── Gateway de identidad de Sites
               │  JWT delegado / lista de permitidos / verificación de lanzamiento
               ▼
             FastAPI
               ├── PostgreSQL / TimescaleDB / pgvector
               ├── Redis / Dramatiq / outbox duradero
               ├── artefactos gobernados en MinIO
               ├── grafo de conocimiento derivado en Neo4j
               ├── razonamiento y embeddings con LiteLLM
               └── conectores SCADA / MQTT / HTTPS / EAM
```

D1 de Demo y PostgreSQL de producción son límites separados. No existe replicación implícita entre ellos; las consultas fallidas de producción no pueden mostrar datos Demo como alternativa.

### Tecnologías

| Capa              | Tecnologías                                                             |
| ----------------- | ----------------------------------------------------------------------- |
| Web               | React 19, TypeScript, vinext, Vite, Tailwind CSS                        |
| Interfaz de datos | TanStack Query, TanStack Table, Zustand, ECharts, Three.js              |
| Edge              | Cloudflare Worker, D1, SSE, WebSocket                                   |
| Backend           | Python 3.12, FastAPI, Pydantic, async SQLAlchemy, LangGraph             |
| Asíncrona         | PostgreSQL transactional outbox, Redis, Dramatiq                        |
| Datos             | PostgreSQL, TimescaleDB, pgvector, MinIO, Neo4j                         |
| IA                | LiteLLM, proveedores compatibles con OpenAI, vía de embeddings separada |
| Calidad           | Node test runner, Playwright, Pytest, Ruff, mypy, Bandit                |

Se conservan los identificadores estables de compatibilidad `windops_backend`, `WINDOPS_*`, `x-windops-*` y los espacios de nombres existentes de base de datos, almacenamiento de objetos y telemetría.

## Configuración de modelos

Toda la configuración local de modelos pertenece a la `.env` de la raíz del repositorio. La `.env.example` de la raíz es la única plantilla de campos. No cree otra configuración de entorno en `backend/` ni en otro lugar.

Antes de activar el razonamiento real, configure:

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
```

Proveedores de chat compatibles:

| `WINDOPS_LLM_PROVIDER` | Variable de URL base                | Variable de clave API                       | Variable de modelo          |
| ---------------------- | ----------------------------------- | ------------------------------------------- | --------------------------- |
| `siliconflow`          | `WINDOPS_SILICONFLOW_BASE_URL`      | `WINDOPS_SILICONFLOW_API_KEY`               | `WINDOPS_SILICONFLOW_MODEL` |
| `bailian`              | `WINDOPS_BAILIAN_BASE_URL`          | `WINDOPS_BAILIAN_API_KEY`                   | `WINDOPS_BAILIAN_MODEL`     |
| `deepseek`             | `WINDOPS_DEEPSEEK_BASE_URL`         | `WINDOPS_DEEPSEEK_API_KEY`                  | `WINDOPS_DEEPSEEK_MODEL`    |
| `default`              | Entorno LiteLLM/proveedor existente | Gestionada por el proveedor correspondiente | `WINDOPS_LITELLM_MODEL`     |

Ejemplo:

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
WINDOPS_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
WINDOPS_SILICONFLOW_API_KEY=
WINDOPS_SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

Alibaba Cloud Bailian utiliza por defecto `https://dashscope.aliyuncs.com/compatible-mode/v1`; DeepSeek, `https://api.deepseek.com`. La `base_url` debe usar HTTPS sin credenciales incrustadas. Guarde claves API solo en la `.env` ignorada de la raíz o en un gestor de secretos de producción.

OpenCode Go está destinado al tráfico de agentes de programación. El backend actual no lee `OPENCODE_GO_*`; `.env.example` conserva solo la dirección de referencia y los nombres de variables para evitar seleccionarlo como proveedor de diagnóstico eólico. Chat y embeddings usan conexiones separadas. La aplicación no reutiliza automáticamente el endpoint ni la clave de chat para embeddings. Si una cuenta está autorizada para ambos tipos de modelo, su clave puede configurarse por separado en ambos puntos de entrada.

El almacén vectorial existente requiere 1536 dimensiones. Configure por separado un servicio de embeddings compatible con OpenAI, por ejemplo un modelo Qwen de SiliconFlow que admita ese número de dimensiones:

```dotenv
WINDOPS_EMBEDDING_MODEL=openai/Qwen/Qwen3-Embedding-4B
WINDOPS_EMBEDDING_API_BASE=https://api.siliconflow.cn/v1
WINDOPS_EMBEDDING_API_KEY=
WINDOPS_EMBEDDING_DIMENSIONS=1536
```

Introduzca claves solo en configuración local privada o gestión de secretos del despliegue. Sin los ajustes explícitos de endpoint, clave y dimensiones anteriores, LiteLLM conserva su comportamiento de conexión predeterminado. Los endpoints explícitos deben usar HTTPS sin credenciales incrustadas. Los parámetros se envían al proveedor real y las respuestas deben contener índices completos y únicos, vectores de 1536 dimensiones y valores numéricos finitos. Los vectores no se rellenan ni se truncan. Consulte las dimensiones admitidas en la [API de embeddings de SiliconFlow](https://docs.siliconflow.cn/docs/api/embeddings-post).

La recuperación compara solo vectores del proveedor y modelo de embeddings actuales. Tras cambiar de modelo, regenere los vectores antiguos mediante la vía existente de indexación automática acotada o el `POST /api/v1/knowledge-graph/reindex` del administrador global de conocimiento. Los vectores antiguos sin reindexar se excluyen de la clasificación. La aceptación conjunta en producción usa la misma conexión que la indexación y las consultas.

### Evaluación de regresión con modelos reales

Ejecute desde `backend/` con `.venv` activado. El comando lee la configuración LiteLLM existente de la `.env` de la raíz, realiza llamadas reales al proveedor y genera cargos. No se aceptan sustitutos deterministas.

```powershell
python -m windops_backend.operations.reasoning_eval --cases evaluations/wind-diagnosis-v1.json --pricing evaluations/siliconflow-v3.2-pricing.json --report ../.artifacts/improvements/reasoning-current.json
```

Los seis casos sintéticos integrados cubren rodamiento principal, caja de engranajes, sensor de temperatura, datos ausentes, conflictos de identidad e inyección de prompts en textos de evidencia. La puntuación comprueba clasificación del fallo, componente, confianza, precisión de citas de apoyo, recuperación de citas obligatorias y abstención explícita; los errores y tiempos de espera no cuentan como abstención. Las etiquetas, `required_evidence` y `supporting_evidence` se excluyen del contexto del modelo. El `supporting_evidence` opcional identifica citas válidas adicionales; si falta, solo se consideran de apoyo las evidencias obligatorias. Esta muestra pequeña permite comprobar regresiones técnicas de prompts y modelos. No estima precisión diagnóstica en parques reales ni demuestra que las conclusiones en texto libre estén libres de todos los errores semánticos. La evaluación utiliza un prompt separado y una salida pública de diagnóstico, en lugar de aceptar el flujo de producción; el control de confianza de producción no cambia.

Los informes conservan todos los casos exitosos y fallidos, P95 de extremo a extremo incluyendo la primera carga de la biblioteca del proveedor, consumo y coste por intento, recuentos de costes desconocidos, subtotales conocidos, resúmenes de casos/prompts/código, estado Git e identidades de modelo solicitadas y devueltas. La falta de consumo, una identidad de modelo distinta o un timeout marca el coste total como `UNVERIFIED`, en vez de considerar el intento un éxito gratuito. Los costes son estimaciones de una tabla de precios fechada y con fuentes, sin descuentos de caché; no son registros de facturación. Al cambiar de modelo, proporcione un archivo de precios correspondiente.

Las solicitudes fijan `max_tokens=1024` y no se reintentan; una evaluación ejecuta como máximo 50 casos del conjunto. En la [API de SiliconFlow](https://docs.siliconflow.cn/docs/api/chat-completions-post), este parámetro limita la respuesta final sin incluir el consumo de pensamiento interno. `maximum_total_cost` es un umbral de parada comprobado después de recibir una respuesta. La última solicitud puede superarlo, y no puede contabilizar cargos no comunicados por el proveedor. Use límites del proveedor si necesita un presupuesto estricto de cuenta. El conjunto integrado de seis casos tiene un umbral de 1 CNY. Cualquier fallo de un control absoluto guarda el informe y termina con código distinto de cero; los casos fallidos no se eliminan ni se repiten automáticamente hasta aprobar.

Conserve un informe revisado que supere los controles absolutos y añada `--baseline <report-path>` para comparar regresiones. Con resúmenes de casos, versiones de informe y monedas de precio compatibles, las métricas de clasificación, abstención y citas no deben disminuir; P95 y coste estimado pueden subir como máximo un 20%. Una referencia incompatible o fallida no puede producir una regresión aprobada. Los casos de parques reales requieren un conjunto separado revisado por expertos y etiquetado `expert-reviewed-field-cases`.

## Desarrollo

`docs/` es un directorio de documentación exclusivamente local, excluido de commits Git y distribución GitHub. Los documentos de la raíz marcados como «documento solo local» remiten a materiales disponibles para mantenedores con copias locales; un clon limpio no los incluye. La política de artefactos requerida por CI está en `scripts/repository-artifact-policy.json` y prohíbe rastrear archivos bajo `docs/`. Las comprobaciones de formato no dependen de la documentación local.

### Web

```bash
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
pnpm test
```

Otros comandos útiles:

```bash
pnpm test:coverage
pnpm test:e2e
pnpm test:start-smoke
pnpm run check:repository-artifacts
```

`pnpm test` realiza una compilación de producción y comprueba el presupuesto del bundle antes de los tests de contratos Node. `pnpm test:e2e` utiliza Chromium real para verificar páginas clave, identidad, permisos y recuperación de errores.

### Pruebas del flujo de negocio con dependencias reales

Prepare Docker Engine/Compose, Node/pnpm y Python 3.12. Ejecute `uv sync --frozen --extra test --extra structural` en `backend/` y vuelva a la raíz:

```bash
pnpm exec playwright install chromium
pnpm test:e2e:business
```

El comando compila el frontend actual y crea un proyecto Compose separado de nombre aleatorio con puertos de loopback. Ejecuta PostgreSQL, Redis, MinIO, Neo4j, FastAPI, Dramatiq, relay de outbox y workers de auditoría de lecturas reales. Las solicitudes Chromium pasan por el Worker para verificar aprobaciones, denegaciones de permisos, reintentos tras fallos de red, repetición idempotente y cinco cargas de evidencias de campo. Al final se comprueban directamente registros de base de datos y hashes de objetos. Tanto en éxito como en fallo, el ejecutor elimina sus propios procesos y volúmenes sintéticos; no opera sobre el entorno local guardado.

Las observaciones y referencias son sintéticas. Diagnóstico y embeddings usan implementaciones deterministas de prueba; las identidades de proveedor de identidad, lanzamiento e imagen son configuraciones de prueba. Los procesos HTTP ejercitan las ramas reales de autenticación y almacenamiento de producción, mientras los workers mantienen el modo de modelo de prueba. Estas comprobaciones prueban el flujo técnico, no la precisión de modelos, un proveedor de identidad real ni la aceptación de un lanzamiento de producción. Informes y registros privados se guardan en `.artifacts/business-e2e/<run-id>/`; configuración, claves privadas y trazas pueden contener credenciales temporales. CI sube solo `report.json`. La suite predeterminada del navegador y el smoke test existente de rotación de configuración siguen separados.

Para cargas directas desde el navegador, configure `WINDOPS_ARTIFACT_UPLOAD_ORIGINS` del Worker con los orígenes HTTPS exactos de las URL de carga emitidas por el backend, separados por comas, y permita PUT/CORS desde el origen de la aplicación en el almacenamiento de objetos. La CSP predeterminada permite solo conexiones del mismo origen. La opción rechaza comodines, rutas, credenciales y directivas CSP; los valores inválidos devuelven 503 antes de ejecutar solicitudes de negocio. HTTP local solo se permite si página y almacenamiento usan ambos `http://127.0.0.1`, para las pruebas aisladas anteriores.

### Medición local del rendimiento de usuario

Primero inicie el entorno aislado siguiendo «Inicio local reproducible en Windows» y ejecute desde la raíz:

```powershell
./scripts/Start-Local.ps1
pnpm exec playwright install chromium
pnpm measure:performance --report .artifacts/improvements/performance.json
./scripts/Stop-Local.ps1
```

El script se conecta solo a los puertos de loopback registrados en `.artifacts/local-stack/configuration.json` de este repositorio. Lee la autenticación de la configuración aislada sin imprimir credenciales. No inicia ni detiene servicios ni modifica datos de negocio; las auditorías reales de lectura de API sí persisten. Use `--samples 10 --api-samples 40 --list-size 5000` para ajustar muestras y volumen de datos sintéticos. Se requieren al menos cinco muestras de navegador y 20 de API. Las ejecuciones son secuenciales y conservan cada muestra fallida.

Los informes distinguen tres tipos de evidencia:

- Mediciones Chromium a 1440px y 390px de la página principal, centro de diagnóstico y mantenimiento predictivo: FCP; tiempo hasta que el contenido designado es visible y transcurren dos fotogramas; LCP, desplazamientos de diseño y tareas largas hasta entonces; y latencia desde la entrada de búsqueda global hasta resultados visibles y dos fotogramas transcurridos. Cada muestra usa un contexto nuevo; las cachés de servidor y sistema pueden estar calientes. El viewport de 390px es una vista estrecha de navegador de escritorio, no un teléfono físico.
- Listas largas de alarmas: se inyectan 2,000 registros sintéticos con la estructura real de alarmas Demo en una respuesta de lectura solo durante esa ejecución. La página real y DataTable realizan actualización, paginación y filtrado. Las consultas Demo tienen caché de 30 segundos; cada muestra espera 31 segundos reales antes de activar la reconexión. Esta preparación se excluye de la latencia de actualización a renderizado y no se modifica el reloj del navegador. Se conservan número de registros, bytes de respuesta, resumen de datos y filas DOM reales.
- Una instancia FastAPI real independiente: solicitudes autenticadas a `/catalog`, `/turbines` y `/data-catalog`, con un calentamiento seguido de mediciones de respuesta completa y análisis JSON, P50/P95, cantidades devueltas y bytes. Una base vacía se registra explícitamente con cero filas. No demuestra rendimiento a escala de producción ni aceptación del camino frontend-backend de producción.

Los presupuestos locales fijos son FCP 2,500ms, contenido listo y actualización de listas 4,000ms, interacción 300ms, filtrado de listas grandes 1,000ms y P95 de API 500ms. Muestras ausentes, fallos de solicitud, errores de navegador o presupuestos superados guardan el informe y terminan con código distinto de cero. P95 usa nearest-rank y equivale al máximo con cinco muestras. Se registran CPU/sistema/navegador, viewport, volumen, estado Git y resúmenes de compilación/scripts. Contenido listo, corte de LCP e interacción medida sobre dos fotogramas son métricas experimentales locales; no sustituyen LCP completo, INP de usuarios reales ni aceptación formal de SLO.

### Python

Desde `backend/` con `backend/.venv` activado:

```powershell
python -m pytest tests -q
python -m ruff format --check src tests alembic scripts
python -m ruff check src tests alembic scripts
python -m mypy --no-incremental src
alembic upgrade head --sql
```

Para verificar dependencias CARE opcionales:

```powershell
uv sync --frozen --extra benchmark --extra test --extra dev
uv run windops-care-dependency-closure --requirements-lock requirements.container.txt --uv-lock uv.lock
uv run python -m pytest tests -q -k "care and not external_release"
```

Las pruebas SQLite usan embeddings deterministas, un verificador de artefactos en memoria y un sustituto de grafo en memoria. No reemplazan la aceptación con PostgreSQL, TimescaleDB, MinIO, Neo4j ni proveedores de modelos reales.

El número de pruebas procede del descubrimiento automático de comandos y CI. En ejecuciones locales habituales sin recursos externos, pueden omitirse pruebas `external_release`; esas omisiones no cuentan como aprobaciones de lanzamiento. Los entornos externos de aceptación designados deben fijar `WINDOPS_FAIL_ON_SKIPPED=1`, de modo que cualquier omisión sea un fallo, y conservar evidencias reales según la lista de aceptación de lanzamiento (documento solo local: `docs/runbooks/release-acceptance.md`).

## Límites de aceptación en producción

El candidato incluye identidad delegada, RBAC, ámbitos de datos, idempotencia, revisiones, outbox, auditoría, copia/restauración, identidades de lanzamiento y rechazo seguro ante requisitos incumplidos. Aún se debe completar en entornos aprobados:

- Despliegue formal en clúster de API Python y workers, análisis de imágenes, SBOM, firmas y controles de admisión.
- Aceptación conjunta de PostgreSQL, TimescaleDB, Redis, MinIO, Neo4j, LiteLLM y servicios de embeddings.
- Contratos reales de datos SCADA, CMS, meteorología y EAM e integración de permisos de campo.
- Recuperación ante desastres, carga, SLO, encaminamiento de alertas, DAST, pentesting manual y controles posteriores al lanzamiento.
- WCAG en navegador, regresión visual y aceptación de dispositivos compatibles.
- Revisión de licencia CARE, reproducción desde almacenamiento de producción y revisión manual de correspondencias ontológicas entre parques.

Cloudflare Sites aloja solo la aplicación Web y el gateway de identidad, no el backend Python. Un lanzamiento Sites exitoso no reemplaza la aceptación de backend, dependencias ni sistemas de campo. El estado detallado de evidencias está en [EXECUTION_PROGRESS.md](./EXECUTION_PROGRESS.md), [AUDIT_REPORT.md](./AUDIT_REPORT.md) y [UI_AUDIT_REPORT.md](./UI_AUDIT_REPORT.md).

## Contribuir

Consulte la [guía de contribución (chino)](./CONTRIBUTING.md) para entorno de desarrollo, validación y proceso PR, y la [política de seguridad (chino)](./SECURITY.md) para informar vulnerabilidades y proteger credenciales.

Se aceptan Issues y Pull Requests sobre:

- Problemas reales de cierre de flujos, permisos, idempotencia o recuperación.
- Accesibilidad, diseños adaptables, visualización de datos y presentación del estado de ejecución.
- Capacidades con fuentes reales, modelo de permisos y criterios de aceptación.
- Pruebas que reproduzcan problemas y verifiquen comportamiento real.

No fabrique resultados aprobados eliminando pruebas fallidas, debilitando aserciones, devolviendo valores codificados, ocultando errores silenciosamente o recurriendo a fixtures.

## Licencia

El código propio de OpenVigil se distribuye bajo la [Licencia Apache 2.0](./LICENSE).

El conjunto CARE v6 y sus artefactos derivados de distribución sujetos a su licencia no están cubiertos por Apache 2.0 ni se distribuyen con este repositorio. Siguen [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), que exige atribución, enlace a la licencia, descripción de cambios y CompartirIgual.

## Agradecimientos

- [CARE v6](https://doi.org/10.5281/zenodo.15846963) — Christian Gück, Cyriana M. A. Roelofs / Fraunhofer IEE
- [EnergyFaultDetector](https://github.com/AEFDI/EnergyFaultDetector) — referencia oficial fijada para verificar la puntuación CARE
- PyScada, NetBird Dashboard, OpenClaw Mission Control, next-shadcn-dashboard-starter y Grafana — referencias de arquitectura de información, interacción e investigación visual

Consulte [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) para fuentes completas de terceros, commits fijados, licencias y límites de implementación independiente.
