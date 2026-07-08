import { getUpcomingEvents, getFlatRows, getSiteData } from "@/lib/data";
import { UpcomingList } from "@/components/UpcomingList";
import { CalendarTable } from "@/components/CalendarTable";

export default function Home() {
  const upcoming = getUpcomingEvents(30);
  const rows = getFlatRows();
  const { updated } = getSiteData();

  return (
    <main className="mx-auto max-w-[1440px] px-6 py-6">
      <div className="flex flex-col gap-6 lg:flex-row">
        {/* 왼쪽: 임박 이벤트 (PC 기준 20%) */}
        <aside className="shrink-0 lg:w-1/5">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-lg font-bold">임박 이벤트</h2>
            <span className="text-[11px] text-ink-muted tabular-nums">{updated}</span>
          </div>
          <UpcomingList events={upcoming} />
        </aside>

        {/* 오른쪽: Vericap 배너 + 전체 일정 (PC 기준 80%) */}
        <section className="min-w-0 flex-1">
          <a
            href="https://blog.naver.com/vericap"
            target="_blank"
            rel="noopener noreferrer"
            className="card block rounded-2xl px-6 py-6 text-center transition-shadow hover:shadow-[0_2px_4px_rgba(23,21,15,0.04),0_16px_40px_-18px_rgba(23,21,15,0.18)]"
          >
            <span className="text-xl font-bold tracking-tight">Vericap 콘텐츠 보러가기</span>
          </a>

          <div className="mt-8">
            <CalendarTable rows={rows} priceDate={updated} />
          </div>
        </section>
      </div>
    </main>
  );
}
