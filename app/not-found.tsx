import Link from "next/link";
import { SearchX, Wind } from "lucide-react";

export default function NotFound() {
  return (
    <main className="route-state">
      <span className="route-state__brand">
        <Wind size={22} /> WindOps
      </span>
      <div className="route-state__icon">
        <SearchX size={25} />
      </div>
      <h1>没有找到该运行对象</h1>
      <p>机组或 Mission ID 不存在。可返回指挥中心重新检索。</p>
      <Link className="button button--primary button--md" href="/">
        返回 Operations Center
      </Link>
    </main>
  );
}
