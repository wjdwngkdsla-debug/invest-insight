"use client";

import { useRouter } from "next/navigation";

export function BackButton() {
  const router = useRouter();

  // 직접 링크로 들어와 방문 기록이 없으면 홈으로 보낸다
  function goBack() {
    if (window.history.length > 1) router.back();
    else router.push("/");
  }

  return (
    <button
      onClick={goBack}
      aria-label="뒤로가기"
      className="mb-3 flex h-9 w-9 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-600 shadow-sm transition-colors hover:bg-gray-50 hover:text-gray-900"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
        <path d="M10 3L5 8l5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}
