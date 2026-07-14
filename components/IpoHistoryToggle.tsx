"use client";

import { useState, type ReactNode } from "react";

export function IpoHistoryToggle({
  current,
  history,
}: {
  current: ReactNode;
  history: ReactNode;
}) {
  const [showHistory, setShowHistory] = useState(false);

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <button
          type="button"
          onClick={() => setShowHistory((value) => !value)}
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          {showHistory ? "진행 일정 보기" : "이전 이력 보기"}
        </button>
      </div>
      {showHistory ? history : current}
    </div>
  );
}
