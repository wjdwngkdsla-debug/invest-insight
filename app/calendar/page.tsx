import { getFlatRows, getSiteData } from "@/lib/data";
import { CalendarTable } from "@/components/CalendarTable";

export default function CalendarPage() {
  const rows = getFlatRows();
  const { updated } = getSiteData();

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-[28px] font-bold leading-tight">전체 락업 해제 일정</h1>
        <p className="mt-1 text-sm text-ink-muted">업데이트 {updated}</p>
      </div>
      <CalendarTable rows={rows} priceDate={updated} />
    </main>
  );
}
