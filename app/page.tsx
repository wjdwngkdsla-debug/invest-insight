import Link from "next/link";
import { CalendarTable } from "@/components/CalendarTable";
import { dDay, getFlatRows, getUpcomingEvents, type UpcomingGroup } from "@/lib/data";

// D-day가 하루 단위로 갱신되도록 정적 페이지를 주기적으로 재생성
export const revalidate = 3600;

function formatQty(qty: number): string {
  return qty.toLocaleString("ko-KR");
}

function groupTitle(group: UpcomingGroup): string {
  if (group.periods.length === 1) return `${group.periods[0]} 락업 해제`;
  return "락업 해제";
}

function EventHoverCard({ event }: { event: UpcomingGroup }) {
  return (
    <div className="event-popover pointer-events-none absolute left-[calc(100%+10px)] top-0 z-[100] w-[320px] opacity-0 transition-opacity duration-150">
      <Link
        href={`/stock/${event.stockCode}`}
        className="block rounded-lg border border-gray-200 bg-white p-5 shadow-xl hover:border-gray-300"
      >
        <div className="flex items-center justify-between gap-4">
          <p className="min-w-0 truncate text-lg font-bold text-gray-900">{event.stockName}</p>
          <p className="shrink-0 whitespace-nowrap font-semibold text-gray-900">
            {formatQty(event.qty)}주 ({event.pct}%)
          </p>
        </div>

        <div className="mt-4 space-y-2 border-t border-gray-100 pt-4 text-sm">
          {event.breakdown.map((item) => (
            <div key={item.category} className="flex items-center justify-between gap-4">
              <span className="font-medium text-gray-700">{item.category}</span>
              <span className="whitespace-nowrap text-right text-gray-600">
                {formatQty(item.qty)}주 ({item.pct}%)
              </span>
            </div>
          ))}
        </div>
      </Link>
    </div>
  );
}

function UpcomingEventCard({ event }: { event: UpcomingGroup }) {
  const days = dDay(event.tradable_date);
  const isNear = days <= 3;

  return (
    <li className="upcoming-event relative z-10">
      <Link
        href={`/stock/${event.stockCode}`}
        className="block rounded-lg border border-gray-200 bg-white p-4 transition-colors hover:border-gray-300 hover:bg-gray-50"
      >
        <span className="flex items-center gap-2">
          <span
            className={`inline-flex shrink-0 rounded px-2 py-1 text-xs font-bold ${
              isNear ? "bg-red-100 text-red-700" : "bg-blue-100 text-blue-700"
            }`}
          >
            D-{days}
          </span>
          <span className="min-w-0 truncate text-xs text-gray-500">
            {event.tradable_date} · {groupTitle(event)}
          </span>
        </span>
        <p className="mt-3 font-semibold text-gray-900">{event.stockName}</p>
        <p className="mt-1 text-sm text-gray-500">
          {formatQty(event.qty)}주 ({event.pct}%)
        </p>
      </Link>
      <EventHoverCard event={event} />
    </li>
  );
}

export default function Home() {
  const upcoming = getUpcomingEvents(30);
  const rows = getFlatRows();

  return (
    <main className="mx-auto max-w-[1480px] px-5 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold">IPO 락업 캘린더</h1>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(220px,20%)_minmax(0,1fr)]">
        <aside className="relative">
          {upcoming.length === 0 ? (
            <p className="rounded-lg border border-gray-200 bg-white p-6 text-sm text-gray-400">
              30일 이내 예정된 해제 이벤트가 없습니다.
            </p>
          ) : (
            <ul className="flex gap-3 overflow-x-auto pb-2 lg:block lg:space-y-3 lg:overflow-visible lg:pb-0">
              {upcoming.map((event, index) => (
                <UpcomingEventCard
                  key={`${event.stockCode}-${event.tradable_date}-${index}`}
                  event={event}
                />
              ))}
            </ul>
          )}
        </aside>

        <section className="min-w-0">
          <Link
            href="https://blog.naver.com/vericap"
            target="_blank"
            rel="noopener noreferrer"
            className="mb-6 flex min-h-24 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 px-6 text-center text-2xl font-bold text-blue-700 shadow-sm transition-colors hover:border-blue-300 hover:bg-blue-100"
          >
            Vericap 콘텐츠 보러가기
          </Link>

          <CalendarTable rows={rows} />
        </section>
      </div>
    </main>
  );
}
