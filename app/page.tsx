import Link from "next/link";
import { getUpcomingEvents, getSiteData, dDay } from "@/lib/data";

function formatQty(qty: number): string {
  return qty.toLocaleString("ko-KR");
}

function groupTitle(periods: string[]): string {
  if (periods.length === 1) return `${periods[0]} 락업 해제`;
  return "락업 해제";
}

export default function Home() {
  const upcoming = getUpcomingEvents(30);
  const { updated } = getSiteData();

  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <div className="mb-6 flex items-baseline justify-between">
        <h1 className="text-2xl font-bold">30일 이내 락업 해제 예정 정보</h1>
        <span className="text-xs text-gray-400">업데이트: {updated}</span>
      </div>

      {upcoming.length === 0 ? (
        <p className="rounded-lg border border-gray-200 bg-white p-8 text-center text-gray-400">
          30일 이내 예정된 해제 이벤트가 없습니다.
        </p>
      ) : (
        <ul className="space-y-2">
          {upcoming.map((ev, i) => {
            const d = dDay(ev.tradable_date);
            const isHighPct = ev.pct >= 5;
            return (
              <li key={`${ev.stockCode}-${ev.tradable_date}-${i}`}>
                <Link
                  href={`/stock/${ev.stockCode}`}
                  className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3 transition-colors hover:border-gray-300 hover:bg-gray-50"
                >
                  <div className="flex items-center gap-4">
                    <span className={`w-14 shrink-0 rounded px-2 py-1 text-center text-xs font-bold ${d <= 3 ? "bg-red-100 text-red-700" : "bg-blue-100 text-blue-700"}`}>
                      D-{d}
                    </span>
                    <div>
                      <p className="font-semibold">
                        {ev.stockName} <span className="ml-1 text-xs font-normal text-gray-400">{ev.market}</span>
                      </p>
                      <p className="text-xs text-gray-400">
                        {ev.tradable_date} · {groupTitle(ev.periods)}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={`font-semibold ${isHighPct ? "text-red-600" : "text-gray-900"}`}>{formatQty(ev.qty)}주</p>
                    <p className={`text-xs ${isHighPct ? "text-red-500" : "text-gray-400"}`}>({ev.pct}%)</p>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
