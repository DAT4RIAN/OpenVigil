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
  X,
} from "lucide-react";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";

import { DataTable } from "@/components/data-display/data-table";
import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";
import { failureCases } from "@/lib/archive-data";
import {
  DEFAULT_KNOWLEDGE_QUESTION,
  type KnowledgeAssistantAnswer,
  type SourceCitation,
} from "@/lib/knowledge-assistant";
import { knowledgeDocuments } from "@/lib/knowledge-data";
import { featuredMission } from "@/lib/operations-data";
import type { KnowledgeDocument, KnowledgeDocumentType } from "@/lib/types";
import { useDemoWorkflow } from "@/lib/use-demo-workflow";

import styles from "./knowledge-base-page.module.css";

interface AssistantSuccessEnvelope {
  readonly ok: true;
  readonly data: { readonly answer: KnowledgeAssistantAnswer };
  readonly error: null;
  readonly meta: {
    readonly deterministic: true;
    readonly retrievalMode: "deterministic-keyword-demo";
    readonly realEmbedding: false;
  };
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
    envelope.meta?.deterministic === true &&
    envelope.meta.realEmbedding === false
  );
}

const formatDate = (value: string): string =>
  new Date(value).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });

function DocumentDrawer({
  document,
  citedPage,
  onClose,
}: {
  readonly document: KnowledgeDocument;
  readonly citedPage: number | null;
  readonly onClose: () => void;
}) {
  useEffect(() => {
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <>
      <button
        className={styles.backdrop}
        type="button"
        aria-label="关闭文档详情"
        onClick={onClose}
      />
      <aside
        aria-label={`${document.title} 文档详情`}
        aria-modal="true"
        className={styles.drawer}
        role="dialog"
      >
        <header className={styles.drawerHeader}>
          <div>
            <span>KNOWLEDGE DOCUMENT</span>
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
              {document.vectorized ? "已进入演示检索目录" : "浏览器派生 · 待持久化索引"}
            </span>
          </div>

          <section className={styles.previewPage}>
            <span>DOCUMENT PREVIEW · PAGE {citedPage ?? 1}</span>
            <h3>{document.equipment}</h3>
            <p>{document.summary}</p>
            <div>
              {document.tags.map((tag) => (
                <span key={tag}>{tag}</span>
              ))}
            </div>
          </section>

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
                <dd>{document.pageCount} 页</dd>
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
        <FileCheck2 size={14} /> {citation.docId} · P.{citation.page}
      </span>
      <strong>{citation.title}</strong>
      <small>{citation.summary}</small>
      <em>
        打开来源 <ArrowRight size={12} />
      </em>
    </button>
  );
}

export function KnowledgeBasePage() {
  const workflow = useDemoWorkflow();
  const [query, setQuery] = useState("");
  const [type, setType] = useState<"all" | KnowledgeDocumentType>("all");
  const [selectedDocument, setSelectedDocument] = useState<KnowledgeDocument | null>(null);
  const [citedPage, setCitedPage] = useState<number | null>(null);
  const [question, setQuestion] = useState(DEFAULT_KNOWLEDGE_QUESTION);
  const [answer, setAnswer] = useState<KnowledgeAssistantAnswer | null>(null);
  const [assistantError, setAssistantError] = useState<string | null>(null);
  const [assistantLoading, setAssistantLoading] = useState(false);
  const didAskDefault = useRef(false);

  const workflowDocument = useMemo<KnowledgeDocument | null>(() => {
    if (!workflow.knowledgeCaseId) return null;
    const knowledgeEvent = [...workflow.auditTrail]
      .reverse()
      .find((event) => event.kind === "knowledge");
    return {
      id: workflow.knowledgeCaseId,
      title: "WT-023 主轴承检查、处置与复测闭环案例",
      type: "incident-case",
      equipment: "WT-023 / 主轴承",
      manufacturer: "WindOps Browser Workflow",
      version: "Derived demo v1",
      updatedAt: knowledgeEvent?.timestamp ?? "2026-08-13T10:24:00+08:00",
      vectorized: false,
      pageCount: 14,
      language: "zh-CN",
      tags: ["WT-023", "主轴承", "闭环验证", "健康度 63→78", "浏览器派生"],
      summary:
        "由浏览器内 WT-023 演示工作流派生：人工审批、五项现场任务、复测验证与知识沉淀均已完成；主轴承健康度由 63 提升至 78。该记录尚未写入服务端数据库。",
      relatedTurbineIds: ["WT-023"],
      relatedMissionIds: [featuredMission.id],
    };
  }, [workflow.auditTrail, workflow.knowledgeCaseId]);

  const documents = useMemo(
    () => (workflowDocument ? [workflowDocument, ...knowledgeDocuments] : [...knowledgeDocuments]),
    [workflowDocument],
  );
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

  const openDocument = useCallback((document: KnowledgeDocument, page: number | null = null) => {
    setSelectedDocument(document);
    setCitedPage(page);
  }, []);
  const closeDocument = useCallback(() => {
    setSelectedDocument(null);
    setCitedPage(null);
  }, []);

  useEffect(() => {
    const parameters = new URLSearchParams(window.location.search);
    const documentId = parameters.get("document");
    const turbineId = parameters.get("turbineId");
    const document = documentId
      ? documents.find((candidate) => candidate.id === documentId)
      : undefined;
    const timer = window.setTimeout(() => {
      if (document) openDocument(document);
      else if (turbineId) setQuery(turbineId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [documents, openDocument]);

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
        accessorKey: "version",
        header: "版本",
        cell: ({ row }) => <span className={styles.mono}>{row.original.version}</span>,
      },
      {
        accessorKey: "pageCount",
        header: "页数",
        cell: ({ row }) => `${row.original.pageCount} 页`,
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
            {row.original.vectorized ? "已编目" : "待索引"}
          </span>
        ),
      },
    ],
    [openDocument],
  );

  const askQuestion = useCallback(async (value: string) => {
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
        turbineId: featuredMission.turbineId,
        missionId: featuredMission.id,
      });
      if (!isAssistantSuccess(payload)) throw new Error("知识助手返回了无效响应。");
      setAnswer(payload.data.answer);
    } catch (error) {
      setAssistantError(error instanceof Error ? error.message : "知识检索失败，请稍后重试。");
    } finally {
      setAssistantLoading(false);
    }
  }, []);

  useEffect(() => {
    if (didAskDefault.current) return;
    didAskDefault.current = true;
    void askQuestion(DEFAULT_KNOWLEDGE_QUESTION);
  }, [askQuestion]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void askQuestion(question);
  };
  const openCitation = (citation: SourceCitation) => {
    const document = documents.find((candidate) => candidate.id === citation.docId);
    if (document) openDocument(document, citation.page);
  };

  return (
    <AppShell activePath="/knowledge">
      <PageHeader
        eyebrow="Knowledge & Data"
        title="Knowledge Base"
        description="统一检索风机手册、维护规程、SCADA 报告和已闭环故障案例，并查看可追溯的来源引用。"
        breadcrumb={["Knowledge & Data", "Knowledge Base"]}
        meta={
          <>
            <StatusBadge value="ready" label={`${documents.length} DOCUMENTS`} tone="success" />
            <span className="page-meta-text">确定性演示数据 · 不是生产向量库</span>
          </>
        }
      />

      <section className={styles.metrics} aria-label="知识库统计">
        <article>
          <span>
            <Library size={17} />
          </span>
          <div>
            <small>DOCUMENTS</small>
            <strong>{documents.length}</strong>
          </div>
          <em>{workflowDocument ? "+1 workflow-derived" : "curated catalog"}</em>
        </article>
        <article>
          <span>
            <Database size={17} />
          </span>
          <div>
            <small>SEARCH-READY</small>
            <strong>{documents.filter((item) => item.vectorized).length}</strong>
          </div>
          <em>fixture metadata</em>
        </article>
        <article>
          <span>
            <Layers3 size={17} />
          </span>
          <div>
            <small>FAILURE CASES</small>
            <strong>{failureCases.length}</strong>
          </div>
          <em>closed-loop archive</em>
        </article>
        <article>
          <span>
            <Link2 size={17} />
          </span>
          <div>
            <small>WT-023 EVIDENCE</small>
            <strong>{featuredMission.evidenceIds.length}</strong>
          </div>
          <em>{featuredMission.id}</em>
        </article>
      </section>

      <div className={styles.layout}>
        <section className={styles.libraryPanel}>
          <header className={styles.panelHeader}>
            <div>
              <span>DOCUMENT CATALOG</span>
              <h2>知识文档</h2>
              <p>搜索、筛选、排序、分页与行选择均在当前确定性数据集上真实执行。</p>
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
            columns={columns}
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
              <small>KNOWLEDGE ASSISTANT</small>
              <h2>带来源的回答</h2>
            </div>
            <StatusBadge value="demo" label="DETERMINISTIC" tone="info" />
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
                  <Sparkles size={14} /> STRUCTURED ANSWER
                </span>
                <h3>{answer.answer.headline}</h3>
                <p>{answer.answer.summary}</p>
                <div>
                  <strong>{answer.answer.confidencePercent}%</strong>
                  <small>Mission diagnosis confidence</small>
                </div>
              </section>

              <div className={styles.findings}>
                {answer.answer.findings.map((finding) => (
                  <article key={finding.label}>
                    <span>{finding.label}</span>
                    <strong>{finding.value}</strong>
                    <p>{finding.interpretation}</p>
                    <small>{finding.evidenceIds.join(" · ")}</small>
                  </article>
                ))}
              </div>

              <section className={styles.conclusion}>
                <strong>结论与边界</strong>
                <p>{answer.answer.conclusion}</p>
              </section>

              <section className={styles.sources}>
                <div>
                  <span>SOURCE CITATIONS</span>
                  <small>{answer.citations.length} 个可追溯来源</small>
                </div>
                {answer.citations.map((citation) => (
                  <CitationButton
                    key={`${citation.docId}-${citation.page}`}
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
        <DocumentDrawer document={selectedDocument} citedPage={citedPage} onClose={closeDocument} />
      ) : null}
    </AppShell>
  );
}
