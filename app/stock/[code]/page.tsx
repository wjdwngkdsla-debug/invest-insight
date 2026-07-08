import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getStockByCode, getGroupedEventsByStock, dDay, type UpcomingGroup } from "@/lib/data";

export async function generateMetadata({ params }: { params: Promise<{ code: string }> }): Promise<Metadata> {
  const { code } = await params;
  const stock = getStockByCode(code);
  if (!stock) return { title: "종목 정보 없음" };
  return {
    title: `${stock.name} 락업 해제 일정`,
    description: `${stock.name}(${stock.market}) 의무보유확약·보호예수 해제 일정 및 물량 정보`,
  };
}

function statusBadge(status: string): string {
  if (status === "예정") return "bg-blue-100 text-blue-700";
  if (status === "반환확인" || status === "반환확인_API수정") return "bg-green-100 text-green-700";
  if (status === "수동확인" || status === "수동/API불일치") return "bg-amber-100 text-amber-700";
  return "bg-cream-deep text-ink-soft";
}

function formatQty(qty: number): string {
  return qty.toLocaleString("ko-KR");
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
    <div className="mt-1 space-y-0.5 text-right text-xs leading-snug text-ink-muted">
      {group.breakdown.map((b) => (
        <p key={b.category}>
          <span className="mr-1">{b.category}</span>
          <span className="font-medium text-ink-soft tabular-nums">
            {formatQty(b.qty)}주 ({b.pct}%)
          </span>
        </p>
      ))}
    </div>
  );
}

function renderGroup(group: UpcomingGroup, i: number, tone: "upcoming" | "past", today: Date) {
  const d = dDay(group.tradable_date, today);
  return (
    <li
      key={`${group.tradable_date}-${i}`}
      className={`card rounded-2xl px-5 py-4 ${tone === "past" ? "opacity-80" : ""}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 font-semibold">
            {tone === "upcoming" && (
              <span
                className={`rounded-full px-2.5 py-1 text-xs font-bold tabular-nums ${
                  d <= 3 ? "bg-[#fde5d8] text-alert" : "bg-ink text-white"
                }`}
              >
                D-{d}
              </span>
            )}
            {groupTitle(group)}
          </p>
          <p className="mt-1 text-xs text-ink-muted tabular-nums">{group.date_display}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <span className={`rounded-full px-2 py-0.5 font-medium ${statusBadge(group.status)}`}>{group.status}</span>
          </div>
        </div>

        <div className="shrink-0 text-right">
          <p className="font-semibold text-ink tabular-nums">
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

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-8">
        <span className="inline-flex rounded-full border border-hairline bg-card px-2.5 py-0.5 text-xs font-medium text-ink-muted">
          {stock.market}
        </span>
        <h1 className="mt-3 text-[28px] font-bold leading-tight">{stock.name} 락업 해제 일정</h1>
        <p className="mt-1.5 text-sm text-ink-muted tabular-nums">
          상장일 {stock.listing_date} · 상장주식수 {stock.shares.toLocaleString("ko-KR")}주
        </p>
      </div>

      {upcoming.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-bold">예정된 해제</h2>
          <ul className="space-y-3">{upcoming.map((group, i) => renderGroup(group, i, "upcoming", today))}</ul>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-lg font-bold">지난 해제 내역</h2>
        {past.length === 0 ? (
          <p className="text-sm text-ink-muted">아직 지난 해제 내역이 없습니다.</p>
        ) : (
          <ul className="space-y-3">{past.map((group, i) => renderGroup(group, i, "past", today))}</ul>
        )}
      </section>
    </main>
  );
}
