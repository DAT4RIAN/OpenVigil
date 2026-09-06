"use client";

import { useState } from "react";
import { TriangleAlert as AlarmTriangle, ArrowRight, Bot, Check, CheckCircle2, ChevronRight, CircleDollarSign, FileSearch, PackageCheck, RefreshCcw, Scale, ShieldCheck, Ship, Sparkles, UserCheck, Users, CloudSun as WeatherSun, Wrench, Zap } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { Button, Card, CardHeader, KeyValue } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/data-display/status-badge";
import { decisions, evidenceItems, featuredDecision, featuredMission, weatherWindows } from "@/lib";
import type { DecisionAlternative } from "@/lib/types";
import { cn } from "@/lib/utils";

const solutionIcons = [ShieldCheck, Scale, Zap];

function AlternativeCard({ option, selected, onSelect, index }: { option: DecisionAlternative; selected: boolean; onSelect: () => void; index: number }) {
  const Icon = solutionIcons[index] ?? Scale;
  return <button className={cn("alternative-card", selected && "alternative-card--selected", option.recommended && "alternative-card--recommended")} onClick={onSelect}>
    {option.recommended ? <span className="recommended-ribbon"><Sparkles size={11} /> AI RECOMMENDED</span> : null}
    <div className="alternative-card__header"><span className="alternative-icon"><Icon size={18} /></span><span><small>{option.label}</small><strong>{option.title}</strong></span><span className="radio-mark">{selected ? <Check size={11} /> : null}</span></div>
    <p>{option.description}</p>
    <div className="alternative-metrics"><div><small>安全风险</small><StatusBadge value={option.safetyRisk} label={option.safetyRisk.toUpperCase()} tone={option.safetyRisk === "low" ? "success" : option.safetyRisk === "medium" ? "warning" : "critical"} compact /></div><div><small>停机时间</small><strong>{option.estimatedDowntimeHours} h</strong></div><div><small>预计成本</small><strong>¥{(option.estimatedCostCny / 10000).toFixed(1)}万</strong></div><div><small>发电损失</small><strong>{option.estimatedEnergyLossMWh} MWh</strong></div><div><small>恶化概率</small><strong className={option.deteriorationRiskPercent > 30 ? "critical-text" : ""}>{option.deteriorationRiskPercent}%</strong></div></div>
    <div className="alternative-rationale"><Bot size={13} /><span>{option.rationale}</span></div>
  </button>;
}

export function DecisionCenterPage() {
  const [selectedId, setSelectedId] = useState(featuredDecision.recommendedAlternativeId);
  const [approval, setApproval] = useState<"pending" | "approved" | "revision">("approved");
  const selected = featuredDecision.alternatives.find((option) => option.id === selectedId) ?? featuredDecision.alternatives[0];
  const window = weatherWindows.find((item) => item.id === selected?.weatherWindowId) ?? weatherWindows[0];
  const relatedEvidence = evidenceItems.filter((item) => featuredDecision.evidenceIds.includes(item.id));

  return <AppShell activePath="/decisions">
    <PageHeader eyebrow="AI Operations" title="Decision Center" description="基于安全、成本、停机损失、天气与资源的可解释运维决策" breadcrumb={["AI Operations", "Decision Center"]} meta={<><StatusBadge value="under-review" label="2 DECISIONS REQUIRE REVIEW" tone="warning" pulse /><span className="page-meta-text">Human approval policy · High-risk actions locked</span></>} actions={<><Button variant="secondary"><FileSearch size={15} /> Evidence Policy</Button><Button variant="primary"><ShieldCheck size={15} /> Review Queue</Button></>} />

    <section className="decision-layout">
      <aside className="decision-queue"><div className="decision-queue__header"><div><span className="eyebrow">REVIEW QUEUE</span><h2>待决策事件</h2></div><span>{decisions.length}</span></div>{decisions.map((decision, index) => <button className={cn("decision-queue-item", decision.id === featuredDecision.id && "active")} key={decision.id}><span className={cn("decision-queue-priority", decision.risk === "critical" && "critical")}>{index + 1}</span><span><small className="mono">{decision.id}</small><strong>{decision.incident}</strong><em>{decision.turbineId} · {decision.status}</em></span><ChevronRight size={14} /></button>)}<div className="decision-queue__footer"><CheckCircle2 size={14} /><span><strong>12 项今日已完成</strong><small>平均审批 18 分钟</small></span></div></aside>

      <main className="decision-workspace">
        <Card className="decision-incident"><div className="decision-incident__icon"><AlarmTriangle size={21} /></div><div className="decision-incident__copy"><span className="eyebrow">INCIDENT · {featuredMission.id}</span><h2>{featuredDecision.incident}</h2><p>{featuredDecision.diagnosis}</p></div><div className="decision-confidence"><small>AI CONFIDENCE</small><strong>{featuredDecision.confidencePercent}%</strong><span>High</span></div><a href={`/missions/${featuredMission.id}`}>Mission Detail <ArrowRight size={13} /></a></Card>

        <section className="decision-evidence-bar"><div><FileSearch size={15} /><span><small>EVIDENCE</small><strong>{relatedEvidence.length} 结构化证据</strong></span></div>{relatedEvidence.slice(0, 4).map((item) => <span className="evidence-source-chip" key={item.id}>{item.type.replaceAll("-", " ")}</span>)}<button>查看全部 <ArrowRight size={12} /></button></section>

        <Card className="alternative-panel"><CardHeader eyebrow="ALTERNATIVE SOLUTIONS" title="候选运维方案" description="选择方案以更新右侧风险与资源评估" action={<span className="comparison-label"><Scale size={13} /> 多目标权衡模型 v3.2</span>} /><div className="alternative-grid">{featuredDecision.alternatives.map((option, index) => <AlternativeCard key={option.id} option={option} index={index} selected={selectedId === option.id} onSelect={() => setSelectedId(option.id)} />)}</div></Card>

        <Card className="decision-explain"><CardHeader eyebrow="WHY THIS PLAN" title="AI 推荐依据" description="公开的结构化依据，不包含模型隐藏推理" /><div className="decision-factor-grid"><div><span className="factor-icon factor-icon--success"><ShieldCheck size={15} /></span><span><strong>降低安全风险</strong><small>降载可将短期灾难性故障概率从 34% 降至 12%</small></span></div><div><span className="factor-icon factor-icon--info"><WeatherSun size={15} /></span><span><strong>匹配作业窗口</strong><small>8 月 14 日 08:00–16:00 满足风速与浪高限制</small></span></div><div><span className="factor-icon factor-icon--warning"><CircleDollarSign size={15} /></span><span><strong>控制经济损失</strong><small>相比立即停机，预计减少发电损失 34.8 MWh</small></span></div><div><span className="factor-icon factor-icon--maintenance"><PackageCheck size={15} /></span><span><strong>资源已就绪</strong><small>备件、船舶、人员与专用工具均可在窗口前到位</small></span></div></div></Card>
      </main>

      <aside className="decision-review-column">
        <Card className="selected-plan-card"><CardHeader eyebrow="SELECTED PLAN" title={selected?.label ?? "方案 B"} /><div className="selected-plan-title"><span><Sparkles size={16} /></span><div><strong>{selected?.title}</strong><small>{selected?.recommended ? "AI 首选方案" : "人工选择方案"}</small></div></div><div className="selected-plan-facts"><KeyValue label="安全风险" value={<StatusBadge value={selected?.safetyRisk ?? "medium"} label={(selected?.safetyRisk ?? "medium").toUpperCase()} tone="warning" compact />} /><KeyValue label="预计成本" value={`¥${((selected?.estimatedCostCny ?? 0) / 10000).toFixed(1)} 万`} /><KeyValue label="停机时间" value={`${selected?.estimatedDowntimeHours} 小时`} /><KeyValue label="发电损失" value={`${selected?.estimatedEnergyLossMWh} MWh`} /><KeyValue label="故障恶化概率" value={`${selected?.deteriorationRiskPercent}%`} /></div></Card>

        <Card className="execution-readiness"><CardHeader eyebrow="EXECUTION READINESS" title="作业条件" /><div className="readiness-detail"><span><WeatherSun size={16} /></span><div><small>WEATHER WINDOW</small><strong>{new Date(window?.startsAt ?? "2026-08-14").toLocaleDateString("zh-CN", { month: "short", day: "numeric" })} · 08:00–16:00</strong><em>风速 {window?.windSpeedMps} m/s · 浪高 {window?.waveHeightM} m</em></div><StatusBadge value="suitable" label="适合" tone="success" compact /></div><div className="execution-resource-list"><span><Users size={13} /><strong>叶轮机械班组 A</strong><Check size={12} /></span><span><Ship size={13} /><strong>海巡运维 07</strong><Check size={12} /></span><span><PackageCheck size={13} /><strong>主轴承备件 × 1</strong><Check size={12} /></span><span><Wrench size={13} /><strong>专用液压工具</strong><Check size={12} /></span></div></Card>

        <Card className={cn("decision-approval", approval !== "pending" && "decision-approval--done")}><CardHeader eyebrow="HUMAN APPROVAL" title="授权执行" description="操作将写入不可变审计记录" />{approval === "pending" ? <><div className="approval-policy"><ShieldCheck size={15} /><span><strong>审批策略 HITL-HIGH-02</strong><small>高风险检修方案需要值班工程师批准</small></span></div><label className="approval-field"><span>审批理由</span><textarea defaultValue={`同意执行${selected?.label}。已确认安全措施、资源和气象窗口。`} /></label><div className="decision-approval__actions"><Button variant="secondary" onClick={() => setApproval("revision")}><RefreshCcw size={14} /> Request Revision</Button><Button variant="primary" onClick={() => setApproval("approved")}><UserCheck size={14} /> Approve Plan</Button></div></> : <div className="decision-approved-result"><span>{approval === "approved" ? <CheckCircle2 size={26} /> : <RefreshCcw size={26} />}</span><h3>{approval === "approved" ? "方案已批准" : "已请求 AI 修订"}</h3><p>{approval === "approved" ? "李明远已批准方案 B；工单 WO-20260823-017 已创建并排程。" : "Decision Committee 将重新计算候选方案。"}</p><small>李明远 · 值班总工程师 · 09:02</small><Button variant="secondary" onClick={() => setApproval("pending")}>重放审批环节</Button></div>}</Card>
      </aside>
    </section>
  </AppShell>;
}
