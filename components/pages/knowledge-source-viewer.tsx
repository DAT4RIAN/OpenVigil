"use client";

import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ArrowUpRight, RefreshCw, X } from "lucide-react";

import { Button } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";
import type { SourceCitation } from "@/lib/knowledge-assistant";
import { useAccessibleDialog } from "@/lib/use-accessible-dialog";
import {
  knowledgeSourceLocation,
  knowledgePageRegions,
  verifiedSourceHref,
  type NativeKnowledgePassage,
} from "@/lib/knowledge-source";

import styles from "./knowledge-base-page.module.css";

interface PassagePage {
  readonly passages: readonly NativeKnowledgePassage[];
  readonly next_cursor: number | null;
}

interface SourceDownload {
  readonly download_url: string;
  readonly expires_at: string;
  readonly artifact_sha256: string;
  readonly document_version: string;
  readonly page_number: number | null;
}

function SourceDownloadButton({
  documentId,
  passageId,
}: {
  readonly documentId: string;
  readonly passageId?: string;
}) {
  const [grant, setGrant] = useState<SourceDownload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (!grant) return;
    const delay = Date.parse(grant.expires_at) - Date.now();
    const timer = window.setTimeout(
      () => {
        setGrant(null);
        setError("原文链接已过期，请重新获取。");
      },
      Math.max(0, delay),
    );
    return () => window.clearTimeout(timer);
  }, [grant]);

  async function download() {
    if (controller.current) return;
    const pending = new AbortController();
    controller.current = pending;
    setLoading(true);
    setError(null);
    setGrant(null);
    try {
      const query = passageId ? `?passage_id=${encodeURIComponent(passageId)}` : "";
      const result = await apiGet<SourceDownload>(
        `/api/backend/knowledge/documents/${encodeURIComponent(documentId)}/source${query}`,
        pending.signal,
      );
      verifiedSourceHref(result.download_url, result.page_number);
      if (
        !Number.isFinite(Date.parse(result.expires_at)) ||
        Date.parse(result.expires_at) <= Date.now()
      ) {
        throw new Error("原文链接已过期，请重新获取。");
      }
      if (!pending.signal.aborted) setGrant(result);
    } catch (cause) {
      if (!pending.signal.aborted)
        setError(cause instanceof Error ? cause.message : "原文链接获取失败。");
    } finally {
      if (!pending.signal.aborted) setLoading(false);
      controller.current = null;
    }
  }

  return (
    <div className={styles.sourceDownload}>
      {grant ? (
        <a
          className="button button--secondary button--sm"
          href={verifiedSourceHref(grant.download_url, grant.page_number)}
          target="_blank"
          rel="noopener noreferrer"
        >
          <span className="button__content">
            打开原文件 <ArrowUpRight size={14} />
          </span>
        </a>
      ) : (
        <Button size="sm" loading={loading} onClick={() => void download()}>
          获取原文链接
        </Button>
      )}
      {grant ? <small>已核验 SHA-256 · {grant.document_version} · 链接五分钟有效</small> : null}
      {error ? <p role="alert">{error}</p> : null}
    </div>
  );
}

export function KnowledgeSourceViewer({
  documentId,
  citedPassageId,
  ingestionStatus,
  requiresNumericReview,
}: {
  readonly documentId: string;
  readonly citedPassageId: string | null;
  readonly ingestionStatus?: string;
  readonly requiresNumericReview?: boolean;
}) {
  const query = useInfiniteQuery({
    queryKey: ["native-knowledge-passages", documentId],
    initialPageParam: null as number | null,
    queryFn: ({ signal, pageParam }) =>
      apiGet<PassagePage>(
        `/api/backend/knowledge/documents/${encodeURIComponent(documentId)}/passages?limit=15${pageParam === null ? "" : `&cursor=${pageParam}`}`,
        signal,
      ),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const citation = useQuery({
    queryKey: ["native-knowledge-passage", citedPassageId],
    enabled: Boolean(citedPassageId),
    queryFn: ({ signal }) =>
      apiGet<NativeKnowledgePassage>(
        `/api/backend/knowledge/passages/${encodeURIComponent(citedPassageId ?? "")}`,
        signal,
      ),
  });
  const pages = query.data?.pages.flatMap((page) => page.passages) ?? [];
  const cited = citation.data?.document_id === documentId ? citation.data : null;
  const passages = cited
    ? [cited, ...pages.filter((piece) => piece.passage_id !== cited.passage_id)]
    : pages;
  const refetchPassages = query.refetch;
  useEffect(() => {
    if (ingestionStatus === "pending" || ingestionStatus === "indexed") {
      void refetchPassages({ cancelRefetch: false });
    }
  }, [ingestionStatus, refetchPassages]);
  const waitingForParse = ingestionStatus === "pending_parse" || ingestionStatus === "parsing";

  return (
    <section className={styles.drawerSection} aria-label="知识原文段落">
      <h3>原文证据</h3>
      <p className={styles.sourceNote}>页码与原生位置来自上传文件。原文摘录仅用于复核。</p>
      {requiresNumericReview ? (
        <p className={styles.sourceNote}>
          OCR 与布局解析结果需对照原件核对数字、正负号、小数点和单位。
        </p>
      ) : null}
      {ingestionStatus === "parse_failed" ? (
        <p role="alert">
          后台 PDF 解析失败，未生成可引用正文。请核对原件与解析服务，再登记新的文档版本。
        </p>
      ) : null}
      {query.isPending ? <p role="status">正在读取原文段落…</p> : null}
      {query.isError ? (
        <div role="alert">
          <p>{query.error.message}</p>
          <Button size="sm" onClick={() => void query.refetch()}>
            <RefreshCw size={13} />
            重试
          </Button>
        </div>
      ) : null}
      {citedPassageId && citation.isPending ? <p role="status">正在定位引用…</p> : null}
      {citedPassageId && citation.isError ? (
        <p role="alert">当前引用无法读取：{citation.error.message}</p>
      ) : null}
      {citation.data && citation.data.document_id !== documentId ? (
        <p role="alert">引用不属于当前文档，请从检索结果重新打开。</p>
      ) : null}
      {!query.isPending && !query.isError && passages.length === 0 ? (
        <p role="status">
          {waitingForParse
            ? "文档尚在后台解析，暂时没有可引用的段落。"
            : "暂无段落索引。历史正文没有可验证的文件位置。"}
        </p>
      ) : null}
      <SourceDownloadButton documentId={documentId} />
      {passages.map((passage) => (
        <article
          key={passage.passage_id}
          className={`${styles.previewPage} ${passage.passage_id === citedPassageId ? styles.citedPassage : ""}`}
        >
          <span>
            {knowledgeSourceLocation(passage)}
            {passage.passage_id === citedPassageId ? " · 当前引用" : ""}
          </span>
          <h3>{passage.section ?? "原文段落"}</h3>
          <p className={styles.passageText}>{passage.text}</p>
          {passage.native_locator.requires_numeric_review === true ? (
            <small className={styles.sourceNote}>解析摘录 · 数值与单位需人工核对</small>
          ) : null}
          {knowledgePageRegions(passage).map((region, index) => (
            <figure key={index} aria-label={`第 ${region.pageNumber} 页内引用区域`}>
              <svg
                role="img"
                aria-label="页面区域示意"
                viewBox={`0 0 ${region.width} ${region.height}`}
                width="80"
                height="104"
              >
                <rect
                  x="0"
                  y="0"
                  width={region.width}
                  height={region.height}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                />
                <rect
                  x={region.bbox[0]}
                  y={region.bbox[1]}
                  width={region.bbox[2] - region.bbox[0]}
                  height={region.bbox[3] - region.bbox[1]}
                  fill="currentColor"
                  fillOpacity="0.25"
                />
              </svg>
              <figcaption className={styles.sourceNote}>
                {passage.native_locator.location_precision === "table_region"
                  ? "表格区域"
                  : "引用区域"}{" "}
                · PDF 页面点坐标 (
                {region.bbox.map((coordinate) => coordinate.toFixed(1)).join(", ")})
              </figcaption>
            </figure>
          ))}
          <small className={styles.sourceNote}>
            {passage.document_version} ·{" "}
            {passage.source_sha256
              ? `文件 SHA-256 ${passage.source_sha256.slice(0, 12)}…`
              : "历史正文，文件位置未经验证"}
          </small>
          <SourceDownloadButton documentId={documentId} passageId={passage.passage_id} />
        </article>
      ))}
      {query.hasNextPage ? (
        <Button
          size="sm"
          loading={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage({ cancelRefetch: false })}
        >
          加载更多段落
        </Button>
      ) : null}
    </section>
  );
}

export function KnowledgeCitationDrawer({
  citation,
  onClose,
}: {
  readonly citation: Pick<SourceCitation, "docId" | "title" | "passageId">;
  readonly onClose: () => void;
}) {
  const dialogRef = useAccessibleDialog<HTMLElement>(onClose);
  const passageId = /^[a-f0-9-]{36}$/i.test(citation.passageId) ? citation.passageId : null;
  return (
    <>
      <button
        className={styles.backdrop}
        type="button"
        aria-label="关闭来源详情"
        onClick={onClose}
      />
      <aside
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={`${citation.title} 来源详情`}
        tabIndex={-1}
        className={styles.drawer}
      >
        <header className={styles.drawerHeader}>
          <div>
            <span>引用来源</span>
            <h2>{citation.title}</h2>
            <p>{citation.docId}</p>
          </div>
          <Button aria-label="关闭" size="icon" variant="ghost" onClick={onClose}>
            <X size={18} />
          </Button>
        </header>
        <div className={styles.drawerBody}>
          <KnowledgeSourceViewer documentId={citation.docId} citedPassageId={passageId} />
        </div>
      </aside>
    </>
  );
}
