// Compatibility facade. Runtime routes import their owning domain directly.
export { productionAgentsResponse } from "./production-adapters/agents.ts";
export {
  productionMissionsResponse,
  productionAlarmsResponse,
  productionDecisionsResponse,
  productionWorkOrdersResponse,
} from "./production-adapters/workflow.ts";
export { productionKnowledgeDocumentsResponse } from "./production-adapters/knowledge.ts";
export {
  productionModelsResponse,
  productionPredictiveAssessmentsResponse,
} from "./production-adapters/models.ts";
export { productionResourcesResponse } from "./production-adapters/resources.ts";
export {
  productionTurbinesResponse,
  productionScadaHistoryResponse,
  productionScadaMeasurementsResponse,
  productionHealthAssessmentsResponse,
} from "./production-adapters/telemetry.ts";
export {
  productionDiagnosesResponse,
  productionMaintenancePlansResponse,
  productionDigitalTwinResponse,
  productionReportsResponse,
  productionDataCatalogResponse,
} from "./production-adapters/operations.ts";
