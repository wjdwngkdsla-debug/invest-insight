"use client";

import { useEffect, useRef, useState } from "react";
import { Bell, CheckCheck, X } from "lucide-react";
import type { TradeUpdate } from "@/lib/trade-updates";

const STORAGE_KEY = "vericap.trade.updates.v1";
export default function TradeUpdates({ onSelect }: { onSelect: (id: string) => void }) {
  const [updates, setUpdates] = useState<TradeUpdate[]>([]);
  const [seen, setSeen] = useState<string[]>([]);
  const [enabled, setEnabled] = useState(true);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("loading");
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let alive = true;
    let controller: AbortController;
    const refresh = async () => {
      controller?.abort(); controller = new AbortController();
      try {
        const response = await fetch("/api/trade/updates", { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("unavailable");
        const data = await response.json();
        if (!Array.isArray(data.updates)) throw new Error("invalid");
        if (alive) { setUpdates(data.updates); setStatus("ready"); }
      } catch (error) {
        if (alive && !(error instanceof DOMException && error.name === "AbortError")) setStatus("error");
      }
    };
    queueMicrotask(() => {
      if (!alive) return;
      try {
        const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
        setSeen(Array.isArray(stored.seen) ? stored.seen.filter((s: unknown) => typeof s === "string").slice(-100) : []);
        setEnabled(stored.enabled !== false);
      } catch { /* Private browsing or invalid preferences must not hide statistics. */ }
    });
    void refresh(); window.addEventListener("focus", refresh);
    return () => { alive = false; controller?.abort(); window.removeEventListener("focus", refresh); };
  }, []);
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => { if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", close); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", escape); };
  }, [open]);
  const save = (ids: string[], nextEnabled = enabled) => {
    const next = [...new Set(ids)].slice(-100);
    setSeen(next); setEnabled(nextEnabled);
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ seen: next, enabled: nextEnabled })); } catch { /* Preferences remain available for this visit. */ }
  };
  const unread = enabled ? updates.filter(u => !seen.includes(u.id)).length : 0;
  return <div className="trade-updates" ref={root}>
    <button className="trade-notification-button" aria-label="수출 통계 업데이트 알림" aria-expanded={open} onClick={() => setOpen(v => !v)}><Bell size={17} />{unread > 0 && <span className="trade-notification-count" aria-label={`읽지 않은 업데이트 ${unread}개`}>{unread}</span>}</button>
    {open && <div className="trade-notification-panel" role="region" aria-label="수출 통계 업데이트 목록">
      <div className="trade-notification-heading"><strong>수출 통계 업데이트</strong><button aria-label="알림 닫기" onClick={() => setOpen(false)}><X size={16} /></button></div>
      <label className="trade-notification-setting"><input type="checkbox" checked={enabled} onChange={e => save(seen, e.target.checked)} />새 통계 알림 표시</label>
      {status === "loading" ? <p>업데이트 확인 중</p> : status === "error" ? <p role="status">업데이트 목록을 불러오지 못했습니다.</p> : !updates.length ? <p>등록된 업데이트가 없습니다.</p> : <ul>{updates.map(u => <li key={u.id}><button onClick={() => { onSelect(u.productId); save([...seen, u.id]); setOpen(false); }}><span><b>{u.name}</b>{!seen.includes(u.id) && enabled && <i aria-label="새 업데이트" />}</span><span>{u.month.replace("-", ".")} 수출 통계</span>{u.checkedAt && <small>확인 {u.checkedAt.slice(0, 10)}</small>}</button></li>)}</ul>}
      <button className="trade-read-all" onClick={() => save([...seen, ...updates.map(u => u.id)])}><CheckCheck size={14} />모두 읽음</button>
    </div>}
  </div>;
}
