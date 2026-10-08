"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, MouseEvent } from "react";
import {
  ArrowRight,
  BookMarked,
  Bot,
  CheckCircle2,
  Database,
  FileCheck2,
  FileSearch,
  Filter,
  Layers3,
  Library,
  Link2,
  LoaderCircle,
  Search,
  Send,
  ShieldAlert,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import { useQuery } from "@tanstack/react-query";

import { DataTable } from "@/components/data-display/data-table";
import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/primitives";
import { apiGet, apiPost } from "@/lib/api-client";
import { failureCases } from "@/lib/archive-data";
import {
  DEFAULT_KNOWLEDGE_QUESTION,
  type KnowledgeAssistantAnswer,
  type SourceCitation,
} from "@/lib/knowledge-assistant";
import { knowledgeDocuments } from "@/lib/knowledge-data";
import { featuredMission } from "@/lib/operations-data";
import type { KnowledgeDocument, KnowledgeDocumentType } from "@/lib/types";
import { useAccessibleDialog } from "@/lib/use-accessible-dialog";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";
import { knowledgeIngestionLabel, knowledgeSourceLocation } from "@/lib/knowledge-source";
import { StructuralArtifactCommand as KnowledgeArtifactCommand } from "@/lib/structural-artifact-command";
import { KnowledgeCitationDrawer, KnowledgeSourceViewer } from "./knowledge-source-viewer";

import styles from "./knowledge-base-page.module.css";

interface AssistantSuccessEnvelope {
  readonly ok: true;
  readonly data: { readonly answer: KnowledgeAssistantAnswer };
  readonly error: null;
  readonly meta: {
    readonly deterministic: boolean;
    readonly retrievalMode:
      | "deterministic-d1-passage-retrieval"
      | "fixture-passage-fallback"
      | "production-pgvector-neo4j-hybrid";
    readonly realEmbedding: boolean;
  };
}

interface KnowledgeDocumentsEnvelope {
  readonly data: {
    readonly documents: readonly KnowledgeDocument[];
  };
}

interface KnowledgeParserCapabilities {
  readonly docling_pdf_configured: boolean;
  readonly max_artifact_bytes: number;
}

const typeLabel: Record<KnowledgeDocumentType, string> = {
  "equipment-manual": "设备手册",
  "maintenance-procedure": "维护规程",
  "incident-case": "事件案例",
  "failure-case": "故障案例",
  "technical-standard": "技术标准",
  "manufacturer-bulletin": "厂商通告",
  "historical-work-order": "历史工单",
  "inspection-report": "巡检报告",
  "scada-analysis-report": "SCADA 报告",
};

const availableTypes = [...new Set(knowledgeDocuments.map((document) => document.type))].sort();

function isAssistantSuccess(value: unknown): value is AssistantSuccessEnvelope {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const envelope = value as Partial<AssistantSuccessEnvelope>;
  return (
    envelope.ok === true &&
    envelope.error === null &&
    typeof envelope.data?.answer?.answer?.summary === "string" &&
    Array.isArray(envelope.data.answer.citations) &&
    typeof envelope.meta?.deterministic === "boolean" &&
    typeof envelope.meta.realEmbedding === "boolean"
  );
}

const formatDate = (value: string): string =>
  !Number.isFinite(Date.parse(value))
    ? "未提供"
    : new Date(value).toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });

function DocumentDrawer({
  document,
  citedPage,
  citedPassageId,
  runtimeMode,
  onClose,
}: {
  readonly document: KnowledgeDocument;
  readonly citedPage: number | null;
  readonly citedPassageId: string | null;
  readonly runtimeMode: "demo" | "production";
  readonly onClose: () => void;
}) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose);

  return (
    <>
      <button
        className={styles.backdrop}
        type="button"
        aria-label="关闭文档详情"
        onClick={onClose}
      />
      <aside
        ref={dialogRef}
        aria-label={`${document.title} 文档详情`}
        aria-modal="true"
        className={styles.drawer}
        role="dialog"
        tabIndex={-1}
      >
        <header className={styles.drawerHeader}>
          <div>
            <span>知识文档</span>
            <h2>{document.title}</h2>
            <p>{document.id}</p>
          </div>
          <Button aria-label="关闭" size="icon" variant="ghost" onClick={onClose}>
            <X size={18} />
          </Button>
        </header>

        <div className={styles.drawerBody}>
          <div className={styles.documentState}>
            <StatusBadge value={document.type} label={typeLabel[document.type]} tone="info" />
            <span className={document.vectorized ? styles.indexed : styles.pendingIndex}>
              {document.vectorized ? <CheckCircle2 size={13} /> : <LoaderCircle size={13} />}
              {runtimeMode === "production"
                ? document.vectorized
                  ? "已索引"
                  : knowledgeIngestionLabel(document.ingestionStatus)
                : document.vectorized
                  ? "已进入演示检索目录"
                  : "浏览器派生 · 待持久化索引"}
            </span>
          </div>

          {runtimeMode === "production" ? (
            <KnowledgeSourceViewer
              documentId={document.id}
              citedPassageId={citedPassageId}
              ingestionStatus={document.ingestionStatus}
              requiresNumericReview={document.requiresNumericReview}
            />
          ) : (
            <section className={styles.previewPage}>
              <span>文档预览 · 第 {citedPage ?? 1} 页</span>
              <h3>{document.equipment}</h3>
              <p>{document.summary}</p>
              <div>
                {document.tags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            </section>
          )}

          <section className={styles.drawerSection}>
            <h3>文档属性</h3>
            <dl>
              <div>
                <dt>版本</dt>
                <dd>{document.version}</dd>
              </div>
              <div>
                <dt>制造商</dt>
                <dd>{document.manufacturer ?? "内部资料"}</dd>
              </div>
              <div>
                <dt>页数</dt>
                <dd>{document.pageCount === null ? "未提供" : `${document.pageCount} 页`}</dd>
              </div>
              <div>
                <dt>语言</dt>
                <dd>{document.language}</dd>
              </div>
              <div>
                <dt>更新日期</dt>
                <dd>{formatDate(document.updatedAt)}</dd>
              </div>
            </dl>
          </section>

          <section className={styles.drawerSection}>
            <h3>关联对象</h3>
            <div className={styles.relatedLinks}>
              {document.relatedTurbineIds.map((turbineId) => (
                <a key={turbineId} href={`/turbines/${turbineId}`}>
                  {turbineId} <ArrowRight size={12} />
                </a>
              ))}
              {document.relatedMissionIds.map((missionId) => (
                <a key={missionId} href={`/missions/${missionId}`}>
                  {missionId} <ArrowRight size={12} />
                </a>
              ))}
            </div>
          </section>
        </div>
      </aside>
    </>
  );
}

function CitationButton({
  citation,
  onOpen,
}: {
  readonly citation: SourceCitation;
  readonly onOpen: (citation: SourceCitation) => void;
}) {
  return (
    <button className={styles.citation} type="button" onClick={() => onOpen(citation)}>
      <span>
        <FileCheck2 size={14} /> {citation.docId} ·{" "}
        {knowledgeSourceLocation({
          page_number: citation.page,
          native_locator: citation.nativeLocator ?? {},
        })}
      </span>
      <strong>{citation.title}</strong>
      <small>{citation.summary}</small>
      <em>
        打开来源 <ArrowRight size={12} />
      </em>
    </button>
  );
}

export function KnowledgeBasePage({ runtimeMode }: { runtimeMode: "demo" | "production" }) {
  const workflow = useDemoWorkflow();
  const [query, setQuery] = useState("");
  const [type, setType] = useState<"all" | KnowledgeDocumentType>("all");
  const [selectedDocument, setSelectedDocument] = useState<KnowledgeDocument | null>(null);
  const [citedPage, setCitedPage] = useState<number | null>(null);
  const [citedPassageId, setCitedPassageId] = useState<string | null>(null);
  const [unlistedCitation, setUnlistedCitation] = useState<Pick<
    SourceCitation,
    "docId" | "title" | "passageId"
  > | null>(null);
  const [question, setQuestion] = useState(
    runtimeMode === "production"
      ? "当前知识库有哪些已验证的维护证据？"
      : DEFAULT_KNOWLEDGE_QUESTION,
  );
  const [answer, setAnswer] = useState<KnowledgeAssistantAnswer | null>(null);
  const [assistantError, setAssistantError] = useState<string | null>(null);
  const [assistantLoading, setAssistantLoading] = useState(false);
  const didAskDefault = useRef(false);
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadUnknown, setUploadUnknown] = useState(false);
  const artifactCommand = useRef(new KnowledgeArtifactCommand());
  const uploadFlight = useRef(false);
  const frozenUpload = useRef<{
    readonly file: File;
    readonly documentId: string;
    readonly contentType: string;
    readonly parser: "docling" | "native";
  } | null>(null);
  const [parseScannedPdf, setParseScannedPdf] = useState(false);
  const parserCapabilities = useQuery({
    queryKey: ["knowledge-parser-capabilities", runtimeMode],
    enabled: runtimeMode === "production",
    queryFn: ({ signal }) =>
      apiGet<KnowledgeParserCapabilities>("/api/backend/knowledge/parser-capabilities", signal),
  });
  const documentQuery = useQuery({
    queryKey: ["knowledge-documents", runtimeMode],
    queryFn: ({ signal }) => apiGet<KnowledgeDocumentsEnvelope>("/api/knowledge-documents", signal),
    initialData: runtimeMode === "demo" ? { data: { documents: knowledgeDocuments } } : undefined,
    refetchInterval: (query) =>
      runtimeMode === "production" &&
      query.state.data?.data.documents.some((document) =>
        ["pending_parse", "parsing", "pending"].includes(document.ingestionStatus ?? ""),
      )
        ? 2500
        : false,
  });

  const workflowDocument = useMemo<KnowledgeDocument | null>(() => {
    if (runtimeMode === "production") return null;
    if (!workflow.knowledgeCaseId) return null;
    const knowledgeEvent = [...workflow.auditTrail]
      .reverse()
      .find((event) => event.kind === "knowledge");
    return {
      id: workflow.knowledgeCaseId,
      title: "WT-023 主轴承检查、处置与复测闭环案例",
      type: "incident-case",
      equipment: "WT-023 / 主轴承",
      manufacturer: "OpenVigil D1 Workflow",
      version: "Server closed-loop v1",
      updatedAt: knowledgeEvent?.timestamp ?? "2026-08-13T10:24:00+08:00",
      vectorized: false,
      pageCount: 14,
      language: "zh-CN",
      tags: ["WT-023", "主轴承", "闭环验证", "健康度 63→78", "D1 持久化"],
      summary:
        "由 WT-023 服务器工作流派生：人工审批、五项现场任务、复测验证与知识沉淀均已完成；主轴承健康度由 63 提升至 78，审计记录持久化在 D1。",
      relatedTurbineIds: ["WT-023"],
      relatedMissionIds: [featuredMission.id],
    };
  }, [runtimeMode, workflow.auditTrail, workflow.knowledgeCaseId]);

  const documents = useMemo(() => {
    const catalog = documentQuery.data?.data.documents ?? [];
    return workflowDocument ? [workflowDocument, ...catalog] : [...catalog];
  }, [documentQuery.data?.data.documents, workflowDocument]);
  const filteredDocuments = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("zh-CN");
    return documents.filter((document) => {
      if (type !== "all" && document.type !== type) return false;
      if (!normalizedQuery) return true;
      return [
        document.id,
        document.title,
        document.type,
        document.equipment,
        document.manufacturer ?? "",
        document.summary,
        ...document.tags,
      ]
        .join(" ")
        .toLocaleLowerCase("zh-CN")
        .includes(normalizedQuery);
    });
  }, [documents, query, type]);

  const openDocument = useCallback(
    (document: KnowledgeDocument, page: number | null = null, passage: string | null = null) => {
      setSelectedDocument(document);
      setCitedPage(page);
      setCitedPassageId(passage);
      setUnlistedCitation(null);
    },
    [],
  );
  const closeDocument = useCallback(() => {
    setSelectedDocument(null);
    setCitedPage(null);
    setCitedPassageId(null);
    setUnlistedCitation(null);
  }, []);

  useEffect(() => {
    const parameters = new URLSearchParams(window.location.search);
    const documentId = parameters.get("document");
    const passageId = parameters.get("passage");
    const turbineId = parameters.get("turbineId");
    const document = documentId
      ? documents.find((candidate) => candidate.id === documentId)
      : undefined;
    const timer = window.setTimeout(() => {
      if (document)
        openDocument(
          document,
          null,
          passageId && /^[a-f0-9-]{36}$/i.test(passageId) ? passageId : null,
        );
      else if (documentId && runtimeMode === "production" && documentQuery.isSuccess)
        setUnlistedCitation({
          docId: documentId,
          title: documentId,
          passageId: passageId ?? `${documentId}#body`,
        });
      else if (turbineId) setQuery(turbineId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [documents, openDocument, runtimeMode, documentQuery.isSuccess]);

  const columns = useMemo<LegacyColumnDef<KnowledgeDocument, unknown>[]>(
    () => [
      {
        accessorKey: "title",
        header: "文档",
        cell: ({ row }) => (
          <button
            className={styles.documentLink}
            type="button"
            onClick={(event: MouseEvent<HTMLButtonElement>) => {
              event.stopPropagation();
              openDocument(row.original);
            }}
          >
            <span>
              {row.original.type === "incident-case" ? (
                <BookMarked size={15} />
              ) : (
                <FileSearch size={15} />
              )}
            </span>
            <span>
              <strong>{row.original.title}</strong>
              <small>{row.original.id}</small>
            </span>
          </button>
        ),
        size: 320,
      },
      {
        accessorKey: "type",
        header: "类型",
        cell: ({ row }) => <span className={styles.typeChip}>{typeLabel[row.original.type]}</span>,
      },
      {
        accessorKey: "equipment",
        header: "设备 / 范围",
      },
      {
        accessorKey: "manufacturer",
        header: "制造商",
        cell: ({ row }) => row.original.manufacturer || "—",
      },
      {
        accessorKey: "version",
        header: "版本",
        cell: ({ row }) => <span className={styles.mono}>{row.original.version}</span>,
      },
      {
        accessorKey: "pageCount",
        header: "页数",
        cell: ({ row }) =>
          row.original.pageCount === null ? "未提供" : `${row.original.pageCount} 页`,
      },
      {
        accessorKey: "updatedAt",
        header: "更新日期",
        cell: ({ row }) => formatDate(row.original.updatedAt),
      },
      {
        accessorKey: "vectorized",
        header: "检索状态",
        cell: ({ row }) => (
          <span className={row.original.vectorized ? styles.indexed : styles.pendingIndex}>
            {row.original.vectorized ? <CheckCircle2 size={12} /> : <LoaderCircle size={12} />}
            {row.original.vectorized
              ? "已编目"
              : knowledgeIngestionLabel(row.original.ingestionStatus)}
          </span>
        ),
      },
    ],
    [openDocument],
  );

  const askQuestion = useCallback(
    async (value: string) => {
      const normalized = value.trim();
      if (!normalized) {
        setAssistantError("请输入问题后再检索。");
        return;
      }
      setAssistantLoading(true);
      setAssistantError(null);
      try {
        const payload: unknown = await apiPost("/api/knowledge-assistant", {
          question: normalized,
          turbineId: runtimeMode === "demo" ? featuredMission.turbineId : "",
          missionId: runtimeMode === "demo" ? featuredMission.id : "",
        });
        if (!isAssistantSuccess(payload)) throw new Error("知识助手返回了无效响应。");
        setAnswer(payload.data.answer);
      } catch (error) {
        setAssistantError(error instanceof Error ? error.message : "知识检索失败，请稍后重试。");
      } finally {
        setAssistantLoading(false);
      }
    },
    [runtimeMode],
  );

  useEffect(() => {
    if (didAskDefault.current) return;
    didAskDefault.current = true;
    void askQuestion(question);
  }, [askQuestion, question]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void askQuestion(question);
  };
  const openCitation = (citation: SourceCitation) => {
    const document = documents.find((candidate) => candidate.id === citation.docId);
    const passageId = /^[a-f0-9-]{36}$/i.test(citation.passageId) ? citation.passageId : null;
    if (document) openDocument(document, citation.page, passageId);
    else if (runtimeMode === "production") {
      setSelectedDocument(null);
      setUnlistedCitation(citation);
    }
  };
  const uploadKnowledgeDocument = async (file: File) => {
    if (uploadFlight.current) return;
    const extension = file.name.split(".").pop()?.toLowerCase();
    const contentType =
      file.type ||
      (extension === "md"
        ? "text/markdown"
        : extension === "txt"
          ? "text/plain"
          : extension === "pdf"
            ? "application/pdf"
            : extension === "docx"
              ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              : "");
    const supported = new Set([
      "text/plain",
      "text/markdown",
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]);
    if (!supported.has(contentType)) {
      setUploadError("仅支持 UTF-8 TXT/Markdown、PDF 和 DOCX 文档。");
      return;
    }
    if (
      !artifactCommand.current.resultUnknown &&
      file.size > (parserCapabilities.data?.max_artifact_bytes ?? 50 * 1024 * 1024)
    ) {
      setUploadError("知识制品不能超过 50 MiB。");
      return;
    }
    const selectedParser =
      contentType === "application/pdf" && parseScannedPdf ? "docling" : "native";
    if (
      !artifactCommand.current.resultUnknown &&
      selectedParser === "docling" &&
      parserCapabilities.data?.docling_pdf_configured !== true
    ) {
      setUploadError("扫描件解析尚未配置，请先确认后台解析服务。");
      return;
    }
    setUploading(true);
    uploadFlight.current = true;
    setUploadError(null);
    try {
      if (!artifactCommand.current.resultUnknown) {
        frozenUpload.current = {
          file,
          documentId: `KD-${crypto.randomUUID()}`,
          contentType,
          parser: selectedParser,
        };
      }
      const frozen = frozenUpload.current;
      if (!frozen) throw new Error("没有可核验的知识提交。");
      const title = frozen.file.name.replace(/\.[^.]+$/, "");
      await artifactCommand.current.run(
        {
          file: frozen.file,
          presignPath: "/api/backend/knowledge/documents/uploads/presign",
          presignBody: { document_id: frozen.documentId, content_type: frozen.contentType },
          commandPath: "/api/backend/knowledge/documents",
          commandBody: {
            document_id: frozen.documentId,
            title,
            document_type: "maintenance-procedure",
            document_version: "1",
            content_type: frozen.contentType,
            parser: frozen.parser,
            metadata: { summary: title, language: "zh-CN", tags: ["uploaded"] },
          },
        },
        (value): value is { document_id: string; ingestion_status: string } =>
          value !== null &&
          typeof value === "object" &&
          (value as Record<string, unknown>).document_id === frozen.documentId &&
          typeof (value as Record<string, unknown>).ingestion_status === "string",
      );
      frozenUpload.current = null;
      await documentQuery.refetch();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "知识制品上传失败。");
    } finally {
      setUploading(false);
      uploadFlight.current = false;
      setUploadUnknown(artifactCommand.current.resultUnknown);
      if (uploadInputRef.current) uploadInputRef.current.value = "";
    }
  };

  return (
    <AppShell runtimeMode={runtimeMode} activePath="/knowledge">
      <PageHeader
        eyebrow="知识与数据"
        title="知识库"
        description="统一检索风机手册、维护规程、SCADA 报告和已闭环故障案例，并查看可追溯的来源引用。"
        breadcrumb={["知识与数据", "知识库"]}
        meta={
          <>
            <StatusBadge value="ready" label={`${documents.length} 份文档`} tone="success" />
            <span className="page-meta-text">
              {runtimeMode === "production"
                ? "PostgreSQL 制品台账 · pgvector + Neo4j 混合检索"
                : "确定性演示数据 · 不是生产向量库"}
            </span>
          </>
        }
        actions={
          runtimeMode === "production" ? (
            <>
              <label>
                <input
                  type="checkbox"
                  checked={parseScannedPdf}
                  disabled={
                    uploading ||
                    uploadUnknown ||
                    parserCapabilities.data?.docling_pdf_configured !== true
                  }
                  onChange={(event) => setParseScannedPdf(event.target.checked)}
                />{" "}
                PDF 扫描件解析
              </label>
              <input
                ref={uploadInputRef}
                hidden
                type="file"
                accept=".txt,.md,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void uploadKnowledgeDocument(file);
                }}
              />
              <Button
                variant="primary"
                disabled={uploading || uploadUnknown}
                onClick={() => uploadInputRef.current?.click()}
              >
                <Upload size={15} /> {uploading ? "校验并上传中…" : "上传知识制品"}
              </Button>
            </>
          ) : undefined
        }
      />

      {documentQuery.isError ? (
        <section className="controlled-entry-note" role="alert">
          <ShieldAlert size={16} />
          <span>
            <strong>生产知识目录暂时不可用</strong>
            <small>未回退到演示文档，请检查 Python 后端、对象存储与身份授权。</small>
          </span>
        </section>
      ) : null}
      {runtimeMode === "production" && parserCapabilities.isError ? (
        <section className="controlled-entry-note" role="alert">
          <ShieldAlert size={16} />
          <span>
            <strong>扫描件解析配置暂时无法读取</strong>
            <small>后台读取失败，确认连接恢复后可重新获取配置。</small>
          </span>
          <Button
            variant="secondary"
            disabled={parserCapabilities.isFetching}
            onClick={() => void parserCapabilities.refetch()}
          >
            重试解析配置
          </Button>
        </section>
      ) : null}
      {runtimeMode === "production" && parseScannedPdf ? (
        <p className={styles.sourceNote}>
          PDF 将在后台解析。OCR 文字和表格中的数字、正负号、小数点与单位需对照原件复核。
        </p>
      ) : null}
      {runtimeMode === "production" && parserCapabilities.isError ? (
        <p role="status" className={styles.sourceNote}>
          扫描件解析配置暂时无法读取。普通文字文档仍可上传。
        </p>
      ) : null}
      {uploadError ? (
        <section className="controlled-entry-note" role="alert">
          <ShieldAlert size={16} />
          <span>
            <strong>{uploadUnknown ? "知识提交响应未确认" : "知识制品未写入"}</strong>
            <small>{uploadError}</small>
          </span>
        </section>
      ) : null}
      {uploadUnknown ? (
        <section className="controlled-entry-note" role="alert">
          <span>
            <strong>提交结果尚待核验</strong>
            <small>已保留原文件、文档身份与幂等键。核验同一提交期间不能更换输入。</small>
          </span>
          <Button
            disabled={uploading}
            onClick={() => {
              if (frozenUpload.current) void uploadKnowledgeDocument(frozenUpload.current.file);
            }}
          >
            核验同一提交
          </Button>
        </section>
      ) : null}

      <section className={styles.metrics} aria-label="知识库统计">
        <article>
          <span>
            <Library size={17} />
          </span>
          <div>
            <small>文档数</small>
            <strong>{documents.length}</strong>
          </div>
          <em>
            {runtimeMode === "production"
              ? "权威制品台账"
              : workflowDocument
                ? "+1 条工作流沉淀"
                : "精选目录"}
          </em>
        </article>
        <article>
          <span>
            <Database size={17} />
          </span>
          <div>
            <small>可检索</small>
            <strong>{documents.filter((item) => item.vectorized).length}</strong>
          </div>
          <em>{runtimeMode === "production" ? "真实 embedding 状态" : "演示元数据"}</em>
        </article>
        <article>
          <span>
            <Layers3 size={17} />
          </span>
          <div>
            <small>故障案例</small>
            <strong>{runtimeMode === "production" ? "—" : failureCases.length}</strong>
          </div>
          <em>闭环归档</em>
        </article>
        <article>
          <span>
            <Link2 size={17} />
          </span>
          <div>
            <small>WT-023 证据</small>
            <strong>
              {runtimeMode === "production" ? "—" : featuredMission.evidenceIds.length}
            </strong>
          </div>
          <em>{runtimeMode === "production" ? "按检索范围计算" : featuredMission.id}</em>
        </article>
      </section>

      <div className={styles.layout}>
        <section className={styles.libraryPanel}>
          <header className={styles.panelHeader}>
            <div>
              <span>文档目录</span>
              <h2>知识文档</h2>
              <p>
                {runtimeMode === "production"
                  ? "目录来自服务端制品台账；索引状态、模型和来源哈希均为实际持久化结果。"
                  : "搜索、筛选、排序、分页与行选择均在当前确定性数据集上真实执行。"}
              </p>
            </div>
            {workflowDocument ? (
              <span className={styles.workflowReady}>
                <Sparkles size={13} /> 闭环案例已派生
              </span>
            ) : null}
          </header>

          <div className={styles.filters}>
            <label className={styles.searchField}>
              <Search size={15} aria-hidden="true" />
              <input
                aria-label="搜索知识文档"
                placeholder="搜索标题、ID、设备、标签或摘要…"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              {query ? (
                <button aria-label="清除搜索" type="button" onClick={() => setQuery("")}>
                  <X size={13} />
                </button>
              ) : null}
            </label>
            <label className={styles.selectField}>
              <Filter size={14} aria-hidden="true" />
              <select
                aria-label="按文档类型筛选"
                value={type}
                onChange={(event) => setType(event.target.value as "all" | KnowledgeDocumentType)}
              >
                <option value="all">全部类型</option>
                {availableTypes.map((documentType) => (
                  <option key={documentType} value={documentType}>
                    {typeLabel[documentType]}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <DataTable
            bulkActions={[
              {
                label: "复制文档 ID",
                onActivate: async (rows) =>
                  navigator.clipboard.writeText(rows.map((row) => row.id).join(", ")),
              },
            ]}
            columns={columns}
            csvExport={{
              filename: "openvigil-knowledge-documents.csv",
              columns: [
                { label: "Document ID", value: (row) => row.id },
                { label: "Title", value: (row) => row.title },
                { label: "Type", value: (row) => row.type },
                { label: "Equipment", value: (row) => row.equipment },
                { label: "Manufacturer", value: (row) => row.manufacturer },
                { label: "Version", value: (row) => row.version },
                { label: "Updated", value: (row) => row.updatedAt },
              ],
            }}
            data={filteredDocuments}
            emptyMessage="没有符合搜索与类型筛选条件的文档"
            getRowId={(document) => document.id}
            initialSorting={[{ id: "updatedAt", desc: true }]}
            pageSize={6}
            selectedRowId={selectedDocument?.id}
            onRowActivate={(document) => openDocument(document)}
          />
        </section>

        <aside className={styles.assistantPanel} aria-label="知识助手">
          <header className={styles.assistantHeader}>
            <span>
              <Bot size={18} />
            </span>
            <div>
              <small>知识助手</small>
              <h2>带来源的回答</h2>
            </div>
            <StatusBadge value="demo" label="确定性检索" tone="info" />
          </header>

          <form className={styles.questionForm} onSubmit={onSubmit}>
            <label htmlFor="knowledge-question">向 WT-023 知识域提问</label>
            <div>
              <textarea
                id="knowledge-question"
                maxLength={500}
                rows={3}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
              />
              <Button
                aria-label="发送问题"
                loading={assistantLoading}
                size="icon"
                type="submit"
                variant="primary"
              >
                <Send size={15} />
              </Button>
            </div>
          </form>

          {assistantError ? (
            <div className={styles.assistantError} role="alert">
              <ShieldAlert size={16} />
              <span>
                <strong>检索失败</strong>
                <small>{assistantError}</small>
              </span>
            </div>
          ) : null}

          {assistantLoading && !answer ? (
            <div className={styles.loadingAnswer} aria-live="polite">
              <LoaderCircle className="spin" size={18} />
              正在对固定知识目录执行关键词打分…
            </div>
          ) : null}

          {answer ? (
            <div className={styles.answer} aria-live="polite">
              <section className={styles.answerSummary}>
                <span>
                  <Sparkles size={14} /> 结构化回答
                </span>
                <h3>{answer.answer.headline}</h3>
                <p>{answer.answer.summary}</p>
                <div>
                  <strong>{answer.answer.confidencePercent}%</strong>
                  <small>Mission 诊断置信度</small>
                </div>
              </section>

              <div className={styles.findings}>
                {answer.answer.findings.map((finding) => (
                  <article key={finding.label}>
                    <span>{finding.label}</span>
                    <strong>{finding.value}</strong>
                    <p>{finding.interpretation}</p>
                    <small>
                      {[...finding.evidenceIds, ...finding.passageIds].join(" · ") ||
                        "无可追溯段落"}
                    </small>
                  </article>
                ))}
              </div>

              <section className={styles.conclusion}>
                <strong>结论与边界</strong>
                <p>{answer.answer.conclusion}</p>
              </section>

              <section className={styles.sources}>
                <div>
                  <span>来源引用</span>
                  <small>{answer.citations.length} 个可追溯来源</small>
                </div>
                {answer.citations.map((citation) => (
                  <CitationButton
                    key={citation.passageId}
                    citation={citation}
                    onOpen={openCitation}
                  />
                ))}
              </section>

              <div className={styles.disclaimer}>
                <ShieldAlert size={14} />
                <p>{answer.disclaimer}</p>
              </div>
            </div>
          ) : null}
        </aside>
      </div>

      {selectedDocument ? (
        <DocumentDrawer
          key={selectedDocument.id}
          document={
            documents.find((document) => document.id === selectedDocument.id) ?? selectedDocument
          }
          citedPage={citedPage}
          citedPassageId={citedPassageId}
          runtimeMode={runtimeMode}
          onClose={closeDocument}
        />
      ) : null}
      {unlistedCitation ? (
        <KnowledgeCitationDrawer
          key={unlistedCitation.passageId}
          citation={unlistedCitation}
          onClose={closeDocument}
        />
      ) : null}
    </AppShell>
  );
}
