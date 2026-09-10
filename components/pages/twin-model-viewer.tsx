"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { StatusBadge } from "@/components/data-display/status-badge";
import { Card, CardHeader } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";

import styles from "./digital-twin-page.module.css";

type TwinArtifactAccess = {
  readonly turbine_id: string;
  readonly artifact_sha256: string;
  readonly content_type: string;
  readonly download_url: string;
  readonly expires_at: string;
};

function disposeObject(root: THREE.Object3D) {
  root.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return;
    node.geometry.dispose();
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    for (const material of materials) {
      for (const value of Object.values(material)) {
        if (value instanceof THREE.Texture) value.dispose();
      }
      material.dispose();
    }
  });
}

export function TwinModelViewer({ turbineId }: { readonly turbineId: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const accessQuery = useQuery({
    queryKey: ["twin-model-access", turbineId],
    queryFn: ({ signal }) =>
      apiGet<TwinArtifactAccess>(
        `/api/backend/turbines/${encodeURIComponent(turbineId)}/twin-profile/artifacts/view`,
        signal,
      ),
    retry: false,
    staleTime: 4 * 60 * 1000,
  });
  const unsupportedError =
    accessQuery.data &&
    !["model/gltf-binary", "model/gltf+json"].includes(accessQuery.data.content_type)
      ? `浏览器渲染器不支持 ${accessQuery.data.content_type}；请上传 GLB/glTF。`
      : null;
  const displayedRenderError = unsupportedError ?? renderError;

  useEffect(() => {
    const host = hostRef.current;
    const access = accessQuery.data;
    if (!host || !access) return;
    if (!["model/gltf-binary", "model/gltf+json"].includes(access.content_type)) return;
    const resetErrorTimer = window.setTimeout(() => setRenderError(null), 0);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x09111f);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 10_000);
    camera.position.set(2.8, 1.8, 3.4);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    host.replaceChildren(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x24324a, 2.2));
    const keyLight = new THREE.DirectionalLight(0xffffff, 3.2);
    keyLight.position.set(4, 6, 3);
    scene.add(keyLight);
    const grid = new THREE.GridHelper(10, 20, 0x3b82f6, 0x1e293b);
    scene.add(grid);

    let model: THREE.Object3D | null = null;
    let frame = 0;
    let cancelled = false;
    const resize = () => {
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();

    const loader = new GLTFLoader();
    loader.setCrossOrigin("anonymous");
    loader.load(
      access.download_url,
      (gltf) => {
        if (cancelled) {
          disposeObject(gltf.scene);
          return;
        }
        model = gltf.scene;
        const bounds = new THREE.Box3().setFromObject(model);
        const size = bounds.getSize(new THREE.Vector3());
        const center = bounds.getCenter(new THREE.Vector3());
        const maximumDimension = Math.max(size.x, size.y, size.z, 0.001);
        const scale = 2.4 / maximumDimension;
        model.scale.setScalar(scale);
        model.position.sub(center.multiplyScalar(scale));
        model.position.y -= new THREE.Box3().setFromObject(model).min.y;
        scene.add(model);
        controls.target.set(0, Math.max(size.y * scale * 0.35, 0.3), 0);
        controls.update();
      },
      undefined,
      () => {
        if (!cancelled) {
          setRenderError("三维制品加载失败。请检查 MinIO CORS、签名有效期以及 glTF 外部依赖。");
        }
      },
    );

    const render = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = window.requestAnimationFrame(render);
    };
    render();

    return () => {
      cancelled = true;
      window.clearTimeout(resetErrorTimer);
      observer.disconnect();
      window.cancelAnimationFrame(frame);
      controls.dispose();
      if (model) disposeObject(model);
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [accessQuery.data]);

  return (
    <Card className={styles.viewerPanel}>
      <CardHeader
        eyebrow="经校验三维制品"
        title="交互式 GLB / glTF 模型"
        description="后端重新校验对象内容与 SHA-256 后签发 5 分钟只读 URL；支持旋转、缩放和平移。"
        action={
          <StatusBadge
            value={accessQuery.isError || displayedRenderError ? "degraded" : "verified"}
            label={
              accessQuery.isPending
                ? "校验中"
                : accessQuery.isError
                  ? "读取失败"
                  : displayedRenderError
                    ? "渲染失败"
                    : "哈希已验证"
            }
            tone={accessQuery.isError || displayedRenderError ? "critical" : "success"}
          />
        }
      />
      <div ref={hostRef} className={styles.modelViewer} aria-label={`${turbineId} 三维孪生模型`} />
      {accessQuery.isError ? (
        <p className={styles.viewerError} role="alert">
          无法取得已验证的三维制品访问凭证。
        </p>
      ) : null}
      {displayedRenderError ? (
        <p className={styles.viewerError} role="alert">
          {displayedRenderError}
        </p>
      ) : null}
      {accessQuery.data ? (
        <footer className={styles.viewerMeta}>
          <span>SHA-256 {accessQuery.data.artifact_sha256}</span>
          <span>
            访问凭证到期 {new Date(accessQuery.data.expires_at).toLocaleTimeString("zh-CN")}
          </span>
        </footer>
      ) : null}
    </Card>
  );
}
