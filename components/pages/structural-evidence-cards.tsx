"use client";

import { useState } from "react";
import { Button } from "@/components/ui/primitives";
import { structuralFact, type StructuralEvidenceCard } from "@/lib/structural-workflow";
import { KnowledgeSourceViewer } from "./knowledge-source-viewer";
import styles from "./structural-page.module.css";

export function StructuralEvidenceCards({
  cards,
}: {
  readonly cards: readonly StructuralEvidenceCard[];
}) {
  const [source, setSource] = useState<string | null>(null);
  return (
    <div className={styles.list}>
      {cards.map((card) => (
        <article className={styles.item} key={card.evidence_id}>
          <h3>
            {card.reference.kind} · {card.reference.relation}
          </h3>
          <small>{card.evidence_id}</small>
          <dl className={styles.facts}>
            <dt>资产 / 构件</dt>
            <dd>
              {card.turbine_id} / {card.component_id}
            </dd>
            <dt>采集窗口</dt>
            <dd>{structuralFact(card.time_window)}</dd>
            <dt>实际测量</dt>
            <dd>
              {card.measurements
                .map((item) => `${item.name}: ${item.value ?? "未量化"} ${item.unit}`)
                .join("；") || "原文依据"}
            </dd>
            <dt>方法 / 校准</dt>
            <dd>{structuralFact(card.method)}</dd>
            <dt>质量门禁</dt>
            <dd>{structuralFact(card.quality)}</dd>
            <dt>不确定性</dt>
            <dd>{structuralFact(card.uncertainty)}</dd>
            <dt>适用域</dt>
            <dd>{structuralFact(card.applicability)}</dd>
            <dt>有效期</dt>
            <dd>{card.valid_until ?? "未提供"}</dd>
            <dt>原始 SHA-256</dt>
            <dd>{structuralFact(card.source.sha256)}</dd>
            <dt>来源指纹</dt>
            <dd>{card.source_fingerprint}</dd>
          </dl>
          {card.reference.quote ? <blockquote>{card.reference.quote}</blockquote> : null}
          {typeof card.source.document_id === "string" ? (
            <>
              <Button
                size="sm"
                onClick={() => setSource(source === card.evidence_id ? null : card.evidence_id)}
              >
                定位原文
              </Button>
              {source === card.evidence_id ? (
                <KnowledgeSourceViewer
                  documentId={card.source.document_id}
                  citedPassageId={card.reference.source_id}
                />
              ) : null}
            </>
          ) : null}
        </article>
      ))}
    </div>
  );
}
