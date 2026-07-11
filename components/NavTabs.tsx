"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// 헤더 메뉴 탭 — 현재 페이지 탭만 파란 배경으로 강조
export default function NavTabs() {
  const pathname = usePathname();
  const active = pathname.startsWith("/ipo");
  return (
    <Link
      href="/ipo"
      className={`rounded-lg px-3 py-1.5 text-sm font-bold transition-colors ${
        active ? "bg-blue-100 text-blue-600" : "text-gray-500 hover:bg-gray-100 hover:text-gray-900"
      }`}
    >
      IPO 일정
    </Link>
  );
}
