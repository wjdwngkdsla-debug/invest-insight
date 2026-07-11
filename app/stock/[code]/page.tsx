import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getStockByCode, getGroupedEventsByStock, getSiteData, dDay, displayStatus, type UpcomingGroup } from "@/lib/data";
import { BackButton } from "@/components/BackButton";







export function generateStaticParams() {
  return getSiteData().stocks.map((stock) => ({ code: stock.code }));
}




export async function generateMetadata({ params }: { params: Promise<{ code: string }> }): Promise<Metadata> {
  const { code } = await params;
  const stock = getStockByCode(code);
  if (!stock) return { title: "종목 정보 없음" };


  const sortedDates = stock.events
    .map((event) => event.tradable_date)
    .sort((a, b) => a.localeCompare(b));
  const firstDate = sortedDates[0];
  const totalQty = stock.events.reduce((sum, event) => sum + event.qty, 0);
  const title = `${stock.name} 락업 해제 일정`;
  const description = `${stock.name}(${stock.market}) IPO 락업 해제일, 보호예수 해제 일정, 의무보유확약 물량 ${totalQty.toLocaleString(
    "ko-KR",
  )}주${firstDate ? `, 주요 해제일 ${firstDate}` : ""} 정보를 확인하세요.`;


  return {
    title,
    description,
    alternates: {
      canonical: `/stock/${stock.code}`,
    },
    openGraph: {
      title: `${title} | Vericap`,
      description,
      url: `/stock/${stock.code}`,
      siteName: "Vericap",
      locale: "ko_KR",
      type: "article",
    },
  };
}




function formatQty(qty: number): string {
  return qty.toLocaleString("ko-KR");
}




function formatEok(won: number): string {
  return `${Math.round(won / 1e8).toLocaleString("ko-KR")}억원`;
}




const PERIOD_PRIORITY = ["15일", "1개월", "2개월", "3개월", "6개월", "12개월", "1년", "24개월", "2년", "30개월", "36개월", "3년"];




function groupTitle(group: UpcomingGroup): string {
  const period = PERIOD_PRIORITY.find((p) => group.periods.includes(p));
  if (period) return `${period} 락업 해제`;
  if (group.periods.length === 1) return `${group.periods[0]} 락업 해제`;
  return "락업 해제";
}




function renderBreakdown(group: UpcomingGroup) {
  if (group.breakdown.length === 0) return null;




  return (
    <div className="mt-1 space-y-0.5 text-right text-xs leading-snug text-gray-400">
      {group.breakdown.map((b) => (
        <p key={b.category}>
          <span className="mr-1">{b.category}</span>
          <span className="font-medium text-gray-500">
            {formatQty(b.qty)}주 ({b.pct}%)
          </span>
        </p>
      ))}
    </div>
  );
}




function renderGroup(group: UpcomingGroup, i: number, tone: "upcoming" | "past", today: Date) {
  const d = dDay(group.tradable_date, today);
  const status = displayStatus(group.tradable_date, today);
  return (
    <li
      key={`${group.tradable_date}-${i}`}
      className={`rounded-xl border px-5 py-4 shadow-sm ${
        tone === "upcoming" ? "border-gray-200 bg-white" : "border-gray-200 bg-gray-50"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 font-semibold text-gray-900">
            {tone === "upcoming" && (
              <span
                className={`rounded px-2 py-1 text-xs font-bold ${
                  d <= 3 ? "bg-red-100 text-red-700" : "bg-blue-100 text-blue-700"
                }`}
              >
                D-{d}
              </span>
            )}
            {groupTitle(group)}
          </p>
          <p className="mt-1 text-xs text-gray-400">{group.date_display}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <span
              className={`rounded-full px-2 py-0.5 font-medium ${
                status === "예정" ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-600"
              }`}
            >
              {status}
            </span>
          </div>
        </div>




        <div className="shrink-0 text-right">
          <p className="font-semibold text-gray-900">
            {formatQty(group.qty)}주 ({group.pct}%)
          </p>
          {renderBreakdown(group)}
        </div>
      </div>
    </li>
  );
}




export default async function StockPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const stock = getStockByCode(code);
  if (!stock) return notFound();




  const today = new Date();
  const { upcoming, past } = getGroupedEventsByStock(stock, today);
  const { updated } = getSiteData();




  const marketCapLabel = (
    <p className="text-lg font-bold text-gray-900">
      <span className="mr-1.5 text-xs font-normal text-gray-400">{updated.slice(5)} 종가 기준</span>
      시가총액 {formatEok(stock.shares * stock.close_price)}
    </p>
  );




  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-8">
        <BackButton />
        <span className="inline-flex rounded-full border border-gray-200 bg-white px-2.5 py-0.5 text-xs font-medium text-gray-500">
          {stock.market}
        </span>
        <h1 className="mt-3 text-[28px] font-bold leading-tight">{stock.name} 락업 해제 일정</h1>
        <p className="mt-1.5 text-sm text-gray-500">
          상장일 {stock.listing_date} · 상장주식수 {stock.shares.toLocaleString("ko-KR")}주
        </p>
      </div>




      {upcoming.length > 0 && (
        <section className="mb-8">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-lg font-bold">예정된 해제</h2>
            {marketCapLabel}
          </div>
          <ul className="space-y-3">{upcoming.map((group, i) => renderGroup(group, i, "upcoming", today))}</ul>
        </section>
      )}




      <section>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-bold">지난 해제 내역</h2>
          {upcoming.length === 0 && marketCapLabel}
        </div>
        {past.length === 0 ? (
          <p className="text-sm text-gray-400">아직 지난 해제 내역이 없습니다.</p>
        ) : (
          <ul className="space-y-3">{past.map((group, i) => renderGroup(group, i, "past", today))}</ul>
        )}
      </section>
    </main>
  );
}
