"use client";

import {
  ArrowRight,
  Check,
  ChevronDown,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
  Wind,
} from "lucide-react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type MouseEvent } from "react";
import { chatGPTSignInPath, safeRelativeReturnPath } from "@/lib/auth-paths";
import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";
import styles from "./login-page.module.css";

function LoginContent({ runtimeMode }: { readonly runtimeMode: OpenVigilRuntimeMode }) {
  const searchParams = useSearchParams();
  const returnTo = safeRelativeReturnPath(searchParams.get("return_to") ?? "/");
  const demo = runtimeMode === "demo";
  const destination = demo ? returnTo : chatGPTSignInPath(returnTo);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const reset = () => setPending(false);
    window.addEventListener("pageshow", reset);
    return () => window.removeEventListener("pageshow", reset);
  }, []);

  const navigate = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (pending) {
      event.preventDefault();
      return;
    }
    if (!navigator.onLine) {
      event.preventDefault();
      setError("网络连接已断开。请恢复连接后重试。");
      return;
    }
    setError(null);
    setPending(true);
  };

  return (
    <main className={styles.shell}>
      <section className={styles.hero} aria-label="OpenVigil 风电智能运维">
        <Image
          className={styles.heroImage}
          src="/images/login-onshore-wind-farm.png"
          alt="AI 生成的风电场意境图：晨光中，白色风机沿草地与山脊展开，检修道路连接机组"
          width={1122}
          height={1402}
          priority
          unoptimized
        />
        <div className={styles.heroBrand}>
          <span className={styles.brandMark}>
            <Wind size={24} aria-hidden="true" />
          </span>
          <span>OpenVigil</span>
        </div>
        <div className={styles.heroCopy}>
          <span className={styles.heroLabel}>持续守望 · 有据决策</span>
          <h2>
            看见风场全貌，
            <br />
            让每次决策有据可循。
          </h2>
          <p>
            连接异常信号、诊断证据与现场行动，
            <br />
            让人与智能体共同守护每一台风机。
          </p>
          <div className={styles.heroTopics}>
            <span>全场态势</span>
            <span>协同诊断</span>
            <span>运维闭环</span>
          </div>
        </div>
        <span className={styles.imageCredit}>风电场 · AI 生成视觉</span>
      </section>

      <section className={styles.panel} aria-labelledby="login-title">
        <header className={styles.panelHeader}>
          <span className={styles.mobileBrand}>
            <Wind size={20} aria-hidden="true" /> OpenVigil
          </span>
          <span className={styles.environment}>
            <span />
            {demo ? "演示环境" : "生产环境"}
          </span>
        </header>

        <div className={styles.content}>
          <span className={styles.welcomeIcon}>
            <Wind size={28} aria-hidden="true" />
          </span>
          <p className={styles.kicker}>风电智能运维平台</p>
          <h1 id="login-title">欢迎回到 OpenVigil</h1>
          <p className={styles.intro}>
            {demo
              ? "进入演示工作台，探索从异常发现到运维闭环的完整流程。"
              : "使用已获授权的账号登录，继续你的风场运维工作。"}
          </p>

          <div className={styles.identityCard}>
            <span className={styles.identityIcon}>
              <ShieldCheck size={22} aria-hidden="true" />
            </span>
            <div>
              <strong>{demo ? "产品演示工作区" : "统一身份登录"}</strong>
              <p>{demo ? "演示数据 · 无需账号" : "通过 ChatGPT 验证身份与访问权限"}</p>
            </div>
            <Check size={16} className={styles.check} aria-hidden="true" />
          </div>

          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}
          <a
            className={styles.primaryAction}
            href={destination}
            onClick={navigate}
            aria-disabled={pending}
            aria-busy={pending}
          >
            {pending ? (
              <LoaderCircle size={19} className="spin" aria-hidden="true" />
            ) : (
              <LockKeyhole size={18} aria-hidden="true" />
            )}
            <span>
              {pending
                ? demo
                  ? "正在进入工作台…"
                  : "正在前往身份验证…"
                : demo
                  ? "进入演示工作台"
                  : "使用 ChatGPT 登录"}
            </span>
            {!pending ? <ArrowRight size={18} aria-hidden="true" /> : null}
          </a>
          <p className={styles.assurance}>
            <LockKeyhole size={13} aria-hidden="true" />
            {demo ? "演示入口不授予生产环境访问权限" : "身份验证完成后，按你的角色开放工作区"}
          </p>
          <span className={styles.srOnly} role="status">
            {pending ? "正在跳转，请稍候" : ""}
          </span>

          <details className={styles.help}>
            <summary>
              需要访问帮助？
              <ChevronDown size={15} aria-hidden="true" />
            </summary>
            <p>
              {demo
                ? "此入口仅用于产品演示。需要访问真实风场数据，请联系平台管理员获取生产环境地址和账号授权。"
                : "请使用管理员授权的 ChatGPT 账号。若登录后提示无访问权限，请联系平台管理员确认账号与角色配置。"}
            </p>
          </details>
        </div>

        <footer className={styles.footer}>
          <span>OpenVigil</span>
          <span>开放协作，持续守望。</span>
        </footer>
      </section>
    </main>
  );
}

export function LoginPage({ runtimeMode }: { readonly runtimeMode: OpenVigilRuntimeMode }) {
  return (
    <Suspense
      fallback={
        <main className={styles.loading} aria-busy="true">
          正在加载登录页面…
        </main>
      }
    >
      <LoginContent runtimeMode={runtimeMode} />
    </Suspense>
  );
}
