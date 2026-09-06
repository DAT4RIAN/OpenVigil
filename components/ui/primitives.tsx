"use client";

import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "icon";

export function Button({
  className,
  variant = "secondary",
  size = "md",
  loading,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}) {
  return (
    <button
      className={cn("button", `button--${variant}`, `button--${size}`, className)}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? <LoaderCircle aria-hidden="true" className="spin" size={15} /> : null}
      {children}
    </button>
  );
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("card", className)} {...props} />;
}

export function CardHeader({
  eyebrow,
  title,
  description,
  action,
  className,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("card-header", className)}>
      <div className="card-header__copy">
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {action ? <div className="card-header__action">{action}</div> : null}
    </div>
  );
}

export function Progress({ value, tone = "primary", label }: { value: number; tone?: string; label?: string }) {
  return (
    <div className="progress-wrap" aria-label={label ?? `进度 ${value}%`}>
      <div className="progress-track">
        <span className={cn("progress-value", `progress-value--${tone}`)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
    </div>
  );
}

export function Avatar({ label, tone = "blue", size = "md" }: { label: string; tone?: string; size?: "sm" | "md" }) {
  const initials = label
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
  return (
    <span className={cn("avatar", `avatar--${tone}`, `avatar--${size}`)} aria-hidden="true">
      {initials}
    </span>
  );
}

export function KeyValue({ label, value, mono = false }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="key-value">
      <span>{label}</span>
      <strong className={cn(mono && "mono")}>{value}</strong>
    </div>
  );
}

export function EmptyState({ icon, title, description }: { icon: ReactNode; title: string; description: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">{icon}</div>
      <strong>{title}</strong>
      <p>{description}</p>
    </div>
  );
}

