import { getFlatRows, getSiteData } from "@/lib/data";
import { CalendarTable } from "@/components/CalendarTable";

export default function CalendarPage() {
  const rows = getFlatRows();
  const { updated } = getSiteData();

  return (
    <main className="mx-auto max-w-6xl px-4 py-10">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">전체 락업 해제 일정</h1>
      </div>
      <CalendarTable rows={rows} priceDate={updated} />
    </main>
  );
}
