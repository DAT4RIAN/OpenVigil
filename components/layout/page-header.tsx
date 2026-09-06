import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";

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
  breadcrumb?: string[];
  meta?: ReactNode;
}) {
  return (
    <header className="page-header">
      {breadcrumb?.length ? (
        <nav className="breadcrumb" aria-label="面包屑导航">
          {breadcrumb.map((item, index) => (
            <span key={`${item}-${index}`}>
              {index > 0 ? <ChevronRight size={13} aria-hidden="true" /> : null}
              <span aria-current={index === breadcrumb.length - 1 ? "page" : undefined}>{item}</span>
            </span>
          ))}
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

