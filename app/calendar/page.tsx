import { getFlatRows, getSiteData } from "@/lib/data";
import { CalendarTable } from "@/components/CalendarTable";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "전체 IPO 락업 해제 일정",
  description:
    "IPO 신규상장 종목의 전체 락업 해제 일정, 보호예수 해제일, 의무보유확약 물량, 해제 비중과 시가총액 기준 해제 규모를 확인하세요.",
  alternates: {
    canonical: "/calendar",
  },
  openGraph: {
    title: "전체 IPO 락업 해제 일정 | Vericap",
    description:
      "상장주 락업 해제일, 보호예수 해제 일정, IPO 기관 의무보유확약 물량을 전체 캘린더로 확인하세요.",
    url: "/calendar",
    siteName: "Vericap",
    locale: "ko_KR",
    type: "website",
  },
};

// D-day/상태가 하루 단위로 갱신되도록 정적 페이지를 주기적으로 재생성
export const revalidate = 3600;

export default function CalendarPage() {
  const rows = getFlatRows();
  const { updated } = getSiteData();

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-[28px] font-bold leading-tight">전체 락업 해제 일정</h1>
        <p className="mt-1 text-sm text-gray-500">업데이트 {updated}</p>
      </div>
      <CalendarTable rows={rows} priceDate={updated} />
    </main>
  );
}
