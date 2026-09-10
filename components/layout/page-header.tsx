import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";

type BreadcrumbItem = string | { readonly label: string; readonly href: string };

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  breadcrumb,
  meta,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
  breadcrumb?: BreadcrumbItem[];
  meta?: ReactNode;
}) {
  return (
    <header className="page-header">
      {breadcrumb?.length ? (
        <nav className="breadcrumb" aria-label="面包屑导航">
          {breadcrumb.map((item, index) => {
            const label = typeof item === "string" ? item : item.label;
            const current = index === breadcrumb.length - 1;
            return (
              <span key={`${label}-${index}`}>
                {index > 0 ? <ChevronRight size={13} aria-hidden="true" /> : null}
                {typeof item === "string" ? (
                  <span aria-current={current ? "page" : undefined}>{label}</span>
                ) : (
                  <a href={item.href} aria-label={`返回${label}`}>
                    {label}
                  </a>
                )}
              </span>
            );
          })}
        </nav>
      ) : null}
      <div className="page-header__row">
        <div className="page-header__copy">
          {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
          <h1>{title}</h1>
          <p>{description}</p>
          {meta ? <div className="page-header__meta">{meta}</div> : null}
        </div>
        {actions ? <div className="page-header__actions">{actions}</div> : null}
      </div>
    </header>
  );
}
