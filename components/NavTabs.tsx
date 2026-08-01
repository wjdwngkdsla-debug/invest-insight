"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TAB_BASE = "rounded-lg px-3 py-1.5 text-sm font-bold transition-colors";
const TAB_IDLE = "text-gray-500 hover:bg-gray-100 hover:text-gray-900";

// 헤더 메뉴 탭 — 현재 페이지 탭만 파란 배경으로 강조.
// 인사이트는 외부 블로그라 활성 상태 없이 같은 탭 모양만 유지한다.
export default function NavTabs() {
  const pathname = usePathname();
  const ipoActive = pathname.startsWith("/ipo");
  return (
    <nav className="flex items-center gap-1">
      <Link href="/ipo" className={`${TAB_BASE} ${ipoActive ? "bg-blue-100 text-blue-600" : TAB_IDLE}`}>
        IPO 일정
      </Link>
      <Link
        href="https://blog.naver.com/vericap"
        target="_blank"
        rel="noopener noreferrer"
        className={`${TAB_BASE} ${TAB_IDLE} inline-flex items-center gap-1`}
      >
        인사이트
        <span aria-hidden className="text-[11px] leading-none text-gray-400">
          ↗
        </span>
      </Link>
    </nav>
  );
}
