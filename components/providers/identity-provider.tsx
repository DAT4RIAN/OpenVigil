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
import {
  API_ACCESS_EVENT,
  API_ACCESS_RECOVERY_EVENT,
  type ApiAccessFailure,
  type ApiAccessRecovery,
} from "@/lib/api-access-events";
import { chatGPTSignInPath } from "@/lib/auth-paths";
import type { OpenVigilCapability, OpenVigilIdentitySession } from "@/lib/identity-session";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";

interface IdentityContextValue {
  readonly runtimeMode: OpenVigilRuntimeMode;
  readonly session: OpenVigilIdentitySession | null;
  readonly can: (capability: OpenVigilCapability) => boolean;
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
  readonly runtimeMode: OpenVigilRuntimeMode;
  readonly session: OpenVigilIdentitySession | null;
}) {
  const [failure, setFailure] = useState<ApiAccessFailure | null>(null);
  const capabilities = useMemo(() => new Set(session?.capabilities ?? []), [session]);
  const can = useCallback(
    (capability: OpenVigilCapability) => runtimeMode === "demo" || capabilities.has(capability),
    [capabilities, runtimeMode],
  );

  useEffect(() => {
    const handleFailure = (event: Event) => {
      const detail = (event as CustomEvent<ApiAccessFailure>).detail;
      if (detail) setFailure(detail);
    };
    const handleRecovery = (event: Event) => {
      const detail = (event as CustomEvent<ApiAccessRecovery>).detail;
      if (!detail) return;
      setFailure((current) => {
        if (!current || current.scope !== detail.scope) return current;
        if (
          current.operationKey &&
          detail.operationKey &&
          current.operationKey !== detail.operationKey
        ) {
          return current;
        }
        return null;
      });
    };
    window.addEventListener(API_ACCESS_EVENT, handleFailure);
    window.addEventListener(API_ACCESS_RECOVERY_EVENT, handleRecovery);
    return () => {
      window.removeEventListener(API_ACCESS_EVENT, handleFailure);
      window.removeEventListener(API_ACCESS_RECOVERY_EVENT, handleRecovery);
    };
  }, []);

  const value = useMemo(() => ({ runtimeMode, session, can }), [can, runtimeMode, session]);
  return (
    <IdentityContext.Provider value={value}>
      {failure ? <RecoveryBanner failure={failure} onDismiss={() => setFailure(null)} /> : null}
      {children}
    </IdentityContext.Provider>
  );
}

export function useOpenVigilIdentity(): IdentityContextValue {
  const value = useContext(IdentityContext);
  if (!value) throw new Error("useOpenVigilIdentity must be used inside IdentityProvider");
  return value;
}
