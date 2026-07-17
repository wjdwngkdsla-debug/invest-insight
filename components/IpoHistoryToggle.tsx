"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

export function IpoHistoryToggle({
  current,
  history,
}: {
  current: ReactNode;
  history: ReactNode;
}) {
  const [showHistory, setShowHistory] = useState(false);
  const [query, setQuery] = useState("");
  const historyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showHistory) return;
    const keyword = query.trim().toLowerCase();
    const cards = historyRef.current?.querySelectorAll<HTMLElement>("[data-ipo-history-card]") || [];
    cards.forEach((card) => {
      const name = (card.dataset.ipoName || "").toLowerCase();
      card.hidden = Boolean(keyword && !name.includes(keyword));
    });
  }, [query, showHistory]);

  return (
    <div>
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        {showHistory ? (
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="종목명 검색"
            className="h-9 w-full rounded-md border border-gray-300 bg-white px-3 text-sm outline-none placeholder:text-gray-400 focus:border-blue-500 sm:max-w-[260px]"
          />
        ) : (
          <span aria-hidden className="hidden sm:block" />
        )}
        <button
          type="button"
          onClick={() => {
            setShowHistory((value) => !value);
            setQuery("");
          }}
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          {showHistory ? "진행 일정 보기" : "이전 이력 보기"}
        </button>
      </div>
      {showHistory ? <div ref={historyRef}>{history}</div> : current}
    </div>
  );
}
