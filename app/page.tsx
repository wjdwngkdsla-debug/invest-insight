import Link from "next/link";
import { CalendarTable } from "@/components/CalendarTable";
import { LockupCalendar, type CalendarEvent, type CalendarRangeEvent } from "@/components/LockupCalendar";
import { getFlatRows, getSiteData, getUpcomingEvents, type UpcomingGroup } from "@/lib/data";
import { getIpoSchedule } from "@/lib/ipo";
import { DdayBadge } from "@/components/DdayBadge";
import holidays from "@/data/holidays.json";



function formatQty(qty: number): string {
  return qty.toLocaleString("ko-KR");
}


function groupTitle(group: UpcomingGroup): string {
  if (group.periods.length === 1) return `${group.periods[0]} 락업 해제`;
  return "락업 해제";
}


// 공모가 대비 등락률 + 추세 화살표 — 상승 빨강, 하락 파랑 (국내 시장 관례)
function TrendBadge({ ipoPrice, closePrice }: { ipoPrice: number; closePrice: number }) {
  if (!ipoPrice || !closePrice) return null;
  const pct = ((closePrice - ipoPrice) / ipoPrice) * 100;
  const rounded = Math.round(pct * 10) / 10;
  const isUp = rounded >= 0;
  return (
    <span
      className={`flex shrink-0 flex-col items-center gap-0.5 ${isUp ? "text-red-600" : "text-blue-600"}`}
      title="공모가 대비 등락률"
    >
      <svg width="34" height="20" viewBox="0 0 34 20" fill="none" aria-hidden>
        {isUp ? (
          <>
            <path d="M3 16.5 L11 8.5 L16 12.5 L28 3.5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M21.5 3 H28.5 V10" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </>
        ) : (
          <>
            <path d="M3 3.5 L11 11.5 L16 7.5 L28 16.5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M21.5 17 H28.5 V10" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </>
        )}
      </svg>
      <span className="text-xs font-bold tabular-nums">
        {isUp ? "+" : ""}
        {rounded}%
      </span>
      <span className="text-[10px] leading-none text-gray-400">공모가 대비</span>
    </span>
  );
}


function EventHoverCard({ event }: { event: UpcomingGroup }) {
  return (
    <div className="event-popover pointer-events-none absolute left-[calc(100%+10px)] top-0 z-[100] hidden w-[320px] opacity-0 transition-opacity duration-150 lg:block">
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
  return (
    <li className="upcoming-event relative z-10 w-60 shrink-0 lg:w-auto">
      <Link
        href={`/stock/${event.stockCode}`}
        className="block rounded-lg border border-gray-200 bg-white p-4 transition-colors hover:border-gray-300 hover:bg-gray-50"
      >
        <span className="flex items-center gap-2">
          <DdayBadge date={event.tradable_date} />
          <span className="min-w-0 truncate text-xs text-gray-500">
            {event.tradable_date} · {groupTitle(event)}
          </span>
        </span>
        <div className="mt-3 flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate font-semibold text-gray-900">{event.stockName}</p>
            <p className="mt-1 text-sm text-gray-500">
              {formatQty(event.qty)}주 ({event.pct}%)
            </p>
          </div>
          <TrendBadge ipoPrice={event.ipoPrice} closePrice={event.closePrice} />
        </div>
      </Link>
      <EventHoverCard event={event} />
    </li>
  );
}


export default function Home() {
  const upcoming = getUpcomingEvents(30);
  const rows = getFlatRows();
  const { updated } = getSiteData();


  const calendarEvents: CalendarEvent[] = rows.map((row) => ({
    date: row.tradable_date,
    name: row.name,
    code: row.code,
  }));


  // IPO 일정 — 수요예측·청약은 기간 바, 상장은 단일일 배지 (/ipo 페이지와 같은 데이터)
  const calendarRanges: CalendarRangeEvent[] = [];
  for (const item of getIpoSchedule().items) {
    if (item.withdrawn || item.review_pending) continue;
    if (item.forecast_start) {
      calendarRanges.push({
        start: item.forecast_start,
        end: item.forecast_end || item.forecast_start,
        name: item.name,
        code: item.corp_code,
        kind: "forecast",
      });
    }
    if (item.sub_start) {
      calendarRanges.push({
        start: item.sub_start,
        end: item.sub_end || item.sub_start,
        name: item.name,
        code: item.corp_code,
        kind: "sub",
      });
    }
    if (item.listing_date) {
      calendarEvents.push({ date: item.listing_date, name: item.name, code: item.corp_code, kind: "listing" });
    }
  }


  return (
    <main className="mx-auto max-w-[1480px] px-5 py-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(220px,20%)_minmax(0,1fr)]">
        <aside className="relative min-w-0">
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
          <LockupCalendar events={calendarEvents} rangeEvents={calendarRanges} holidays={holidays as Record<string, string>} />


          <div className="mt-6">
            <CalendarTable rows={rows} priceDate={updated} />
          </div>
        </section>
      </div>
    </main>
  );
}
