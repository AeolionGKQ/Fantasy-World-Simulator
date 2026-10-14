import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="page">
      <section className="empty-state">
        <div className="empty-symbol" aria-hidden="true">?</div>
        <h1>页面不存在</h1>
        <p>此档案路径无效，或对应内容已被删除。</p>
        <Link className="primary-button" to="/">返回档案总览</Link>
      </section>
    </div>
  );
}
