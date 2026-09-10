"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { API_ACCESS_EVENT, type ApiAccessFailure } from "@/lib/api-access-events";
import { chatGPTSignInPath } from "@/lib/auth-paths";
import type { WindOpsCapability, WindOpsIdentitySession } from "@/lib/identity-session";
import type { WindOpsRuntimeMode } from "@/lib/production-runtime";

interface IdentityContextValue {
  readonly runtimeMode: WindOpsRuntimeMode;
  readonly session: WindOpsIdentitySession | null;
  readonly can: (capability: WindOpsCapability) => boolean;
}

const IdentityContext = createContext<IdentityContextValue | null>(null);

function RecoveryBanner({
  failure,
  onDismiss,
}: {
  failure: ApiAccessFailure;
  onDismiss: () => void;
}) {
  const authentication = failure.kind === "authentication";
  const title = authentication
    ? "登录会话已失效"
    : failure.kind === "authorization"
      ? "当前账号没有执行此操作的权限"
      : failure.kind === "backend"
        ? "生产后端尚未就绪"
        : "网络连接失败";
  const retry = () => {
    if (authentication) {
      window.location.assign(
        chatGPTSignInPath(`${window.location.pathname}${window.location.search}`),
      );
      return;
    }
    window.location.reload();
  };
  return (
    <section className="access-recovery-banner" role="alert" data-access-kind={failure.kind}>
      <div>
        <strong>{title}</strong>
        <span>
          {failure.message} · {failure.code}
        </span>
      </div>
      <button type="button" onClick={retry}>
        {authentication ? "重新登录" : "重试"}
      </button>
      {!authentication ? (
        <button type="button" onClick={onDismiss} aria-label="关闭权限或连接提示">
          关闭
        </button>
      ) : null}
    </section>
  );
}

export function IdentityProvider({
  children,
  runtimeMode,
  session,
}: {
  readonly children: ReactNode;
  readonly runtimeMode: WindOpsRuntimeMode;
  readonly session: WindOpsIdentitySession | null;
}) {
  const [failure, setFailure] = useState<ApiAccessFailure | null>(null);
  const capabilities = useMemo(() => new Set(session?.capabilities ?? []), [session]);
  const can = useCallback(
    (capability: WindOpsCapability) => runtimeMode === "demo" || capabilities.has(capability),
    [capabilities, runtimeMode],
  );

  useEffect(() => {
    const handleFailure = (event: Event) => {
      const detail = (event as CustomEvent<ApiAccessFailure>).detail;
      if (detail) setFailure(detail);
    };
    window.addEventListener(API_ACCESS_EVENT, handleFailure);
    return () => window.removeEventListener(API_ACCESS_EVENT, handleFailure);
  }, []);

  const value = useMemo(() => ({ runtimeMode, session, can }), [can, runtimeMode, session]);
  return (
    <IdentityContext.Provider value={value}>
      {failure ? <RecoveryBanner failure={failure} onDismiss={() => setFailure(null)} /> : null}
      {children}
    </IdentityContext.Provider>
  );
}

export function useWindOpsIdentity(): IdentityContextValue {
  const value = useContext(IdentityContext);
  if (!value) throw new Error("useWindOpsIdentity must be used inside IdentityProvider");
  return value;
}
