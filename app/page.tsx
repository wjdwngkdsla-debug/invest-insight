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
  const { updated, stocks } = getSiteData();

  const biggest = upcoming.reduce<(typeof upcoming)[number] | null>(
    (max, g) => (max === null || g.pct > max.pct ? g : max),
    null
  );

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-8">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-card px-3 py-1 text-xs font-medium text-ink-muted">
          업데이트 {updated}
        </span>
        <h1 className="mt-4 text-[32px] font-bold leading-tight sm:text-[38px]">
          30일 이내 락업 해제 예정
        </h1>
        <p className="mt-2 text-[15px] text-ink-muted">
          신규 상장주의 의무보유확약·보호예수 해제 일정을 한눈에 확인하세요.
        </p>
      </div>

      <div className="mb-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="tile-green flex min-h-[150px] flex-col justify-end rounded-3xl p-6 text-white">
          <p className="text-sm font-medium text-white/85">30일 내 해제 이벤트</p>
          <p className="mt-1 text-[44px] font-bold leading-none tracking-tight tabular-nums">
            {upcoming.length}
            <span className="ml-1 text-xl font-semibold text-white/85">건</span>
          </p>
        </div>
        <div className="tile-orange flex min-h-[150px] flex-col justify-end rounded-3xl p-6 text-white">
          <p className="text-sm font-medium text-white/85">
            최대 단일 물량{biggest ? ` · ${biggest.stockName}` : ""}
          </p>
          <p className="mt-1 text-[44px] font-bold leading-none tracking-tight tabular-nums">
            {biggest ? biggest.pct : 0}
            <span className="ml-1 text-xl font-semibold text-white/85">%</span>
          </p>
        </div>
        <div className="card flex min-h-[150px] flex-col justify-end rounded-3xl p-6">
          <p className="text-sm font-medium text-ink-muted">추적 종목</p>
          <p className="mt-1 text-[44px] font-bold leading-none tracking-tight tabular-nums text-ink">
            {stocks.length}
            <span className="ml-1 text-xl font-semibold text-ink-muted">개</span>
          </p>
        </div>
      </div>

      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-lg font-bold">임박한 일정</h2>
        <Link
          href="/calendar"
          className="rounded-full border border-hairline bg-card px-3.5 py-1.5 text-xs font-medium text-ink-soft transition-colors hover:bg-cream-deep"
        >
          전체 일정 →
        </Link>
      </div>

      {upcoming.length === 0 ? (
        <p className="card rounded-2xl p-10 text-center text-ink-muted">
          30일 이내 예정된 해제 이벤트가 없습니다.
        </p>
      ) : (
        <ul className="space-y-3">
          {upcoming.map((ev, i) => {
            const d = dDay(ev.tradable_date);
            const isHighPct = ev.pct >= 5;
            return (
              <li key={`${ev.stockCode}-${ev.tradable_date}-${i}`}>
                <Link
                  href={`/stock/${ev.stockCode}`}
                  className="card flex items-center justify-between rounded-2xl px-5 py-4 transition-shadow hover:shadow-[0_2px_4px_rgba(23,21,15,0.04),0_16px_40px_-18px_rgba(23,21,15,0.18)]"
                >
                  <div className="flex items-center gap-4">
                    <span
                      className={`shrink-0 rounded-full px-3 py-1.5 text-center text-xs font-bold tabular-nums ${
                        d <= 3 ? "bg-[#fde5d8] text-alert" : "bg-ink text-white"
                      }`}
                    >
                      D-{d}
                    </span>
                    <div>
                      <p className="flex items-center gap-2 text-[15px] font-semibold">
                        {ev.stockName}
                        <span className="rounded-full border border-hairline px-2 py-0.5 text-[11px] font-medium text-ink-muted">
                          {ev.market}
                        </span>
                      </p>
                      <p className="mt-0.5 text-xs text-ink-muted">
                        {ev.tradable_date} · {groupTitle(ev.periods)}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={`text-[15px] font-semibold tabular-nums ${isHighPct ? "text-alert" : "text-ink"}`}>
                      {formatQty(ev.qty)}주
                    </p>
                    <p className={`text-xs tabular-nums ${isHighPct ? "text-alert" : "text-ink-muted"}`}>
                      ({ev.pct}%)
                    </p>
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
