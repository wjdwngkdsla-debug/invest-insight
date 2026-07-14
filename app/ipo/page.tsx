import type { Metadata } from "next";
import { getPastIpoItems, getSortedIpoItems, dateRange, mmdd, bandPosition, type IpoItem } from "@/lib/ipo";
import { IpoStatusChip } from "@/components/IpoStatusChip";
import { PastDateGate } from "@/components/PastDateGate";
import { IpoHistoryToggle } from "@/components/IpoHistoryToggle";
































export const metadata: Metadata = {
  title: "IPO 일정 | IPO 락업 캘린더",
  description: "공모 진행 중인 종목의 수요예측·청약·상장 일정과 수요예측 결과를 제공합니다.",
};
































function formatOfferSize(item: IpoItem): string {
  const shares = item.offer_shares || 0;
  const price = item.final_price || item.band_high || 0;
  if (!shares || !price) return "미정";
  const amount = Math.round((shares * price) / 100_000_000);
  return `${amount.toLocaleString()}억원`;
}
















function ratioText(v?: number): string {
  return v ? `${v.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}:1` : "-";
}
















// 확약 표: 신청·배정 수량 + 기간별 신청 수량 대비 배정 비율
function CommitTable({ item }: { item: IpoItem }) {
  const apply = item.commit_apply || [];
  const alloc = item.commit_alloc || [];
  if (!apply.length && !alloc.length) return null;
















  const periods = [...new Set([...apply.map((t) => t.period), ...alloc.map((t) => t.period)])];
  const totalAlloc = alloc.reduce((sum, t) => sum + (t.qty || 0), 0);
  const totalApply = apply.reduce((sum, t) => sum + (t.qty || 0), 0);
  const rows = periods.map((period) => {
    const a = apply.find((t) => t.period === period);
    const b = alloc.find((t) => t.period === period);
    // 배정률 = 신청 물량 중 실제로 배정받은 비율
    const allocRate = a?.qty && b?.qty ? (b.qty / a.qty) * 100 : null;
    // 배정 비중 = 전체 기관 배정 중 이 구간의 몫 (합 100%)
    const allocShare = b?.qty && totalAlloc ? (b.qty / totalAlloc) * 100 : null;
    return { period, applyQty: a?.qty ?? null, allocQty: b?.qty ?? null, allocRate, allocShare };
  });
  const commitShare = rows.filter((r) => r.period !== "미확약").reduce((s, r) => s + (r.allocShare ?? 0), 0);
  const uncommitShare = rows.find((r) => r.period === "미확약")?.allocShare ?? 0;
















  return (
    <div className="mt-3 border-t border-gray-100 pt-3">
      <p className="text-xs font-bold text-gray-700">기간별 기관 확약 현황 (의무보유확약)</p>
      <table className="mt-1.5 w-full table-fixed border-collapse text-xs">
        <thead>
          <tr className="text-gray-400">
            <td className="w-[12%] py-1">기간</td>
            <td className="w-[22%] py-1 text-right">신청 수량</td>
            <td className="w-[13%] py-1 text-right">배정률</td>
            <td className="w-[18%] py-1 text-right">배정 수량</td>
            <td className="w-[35%] py-1 pl-4">배정 비중</td>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const muted = row.period === "미확약";
            return (
              <tr key={row.period} className={muted ? "text-gray-400" : ""}>
                <td className={`py-1 ${muted ? "" : "font-semibold"}`}>{row.period}</td>
                <td className="py-1 text-right tabular-nums">{row.applyQty !== null ? row.applyQty.toLocaleString() : "미정"}</td>
                <td className="py-1 text-right tabular-nums text-gray-400">{row.allocRate !== null ? `${row.allocRate.toFixed(2)}%` : "-"}</td>
                <td className={`py-1 text-right tabular-nums ${muted ? "" : "font-semibold"}`}>
                  {row.allocQty !== null ? row.allocQty.toLocaleString() : "미정"}
                </td>
                <td className="py-1 pl-4">
                  {row.allocShare !== null ? (
                    <span className="flex items-center gap-2">
                      <span className="h-1.5 flex-1 rounded-full bg-gray-100">
                        <span
                          className={`block h-1.5 rounded-full ${muted ? "bg-gray-300" : "bg-blue-600"}`}
                          style={{ width: `${Math.max(2, Math.round(row.allocShare))}%` }}
                        />
                      </span>
                      <span className={`min-w-[44px] text-right font-bold tabular-nums ${muted ? "text-gray-400" : "text-blue-600"}`}>
                        {row.allocShare.toFixed(2)}%
                      </span>
                    </span>
                  ) : (
                    <span className="text-gray-300">미정</span>
                  )}
                </td>
              </tr>
            );
          })}
          {totalAlloc > 0 && (
            <tr className="border-t border-gray-100">
              <td className="py-1.5 font-semibold">합계</td>
              <td className="py-1.5 text-right tabular-nums text-gray-500">{totalApply.toLocaleString()}</td>
              <td className="py-1.5 text-right text-gray-300">-</td>
              <td className="py-1.5 text-right font-semibold tabular-nums">{totalAlloc.toLocaleString()}</td>
              <td className="py-1.5 pl-4 font-semibold text-gray-700">
                확약 {commitShare.toFixed(1)}% · 미확약 {uncommitShare.toFixed(1)}%
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
















function IpoCard({ item }: { item: IpoItem }) {
  const hasCommit = Boolean(item.commit_apply?.length || item.commit_alloc?.length);
  const band = item.band_low && item.band_high ? `${item.band_low.toLocaleString()}~${item.band_high.toLocaleString()}원` : "미정";
  const bandPos = bandPosition(item);
















  return (
    <div
      tabIndex={hasCommit ? 0 : undefined}
      className="group rounded-lg border border-gray-200 bg-white p-5 pb-4 outline-none transition-colors hover:border-gray-300 focus-within:border-gray-300"
    >
      <div className="flex flex-wrap items-center gap-2">
        <IpoStatusChip item={item} />
        <span className={`font-semibold text-gray-900 ${item.withdrawn ? "line-through text-gray-400" : ""}`}>{item.name}</span>
        <span className="text-xs text-gray-500">
          {item.market || "시장 미정"} · 주관 {item.underwriter || "미정"}
        </span>
        {item.content_url && (
          <a
            href={item.content_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2.5 py-1 text-[12px] font-semibold text-blue-700 transition-colors hover:bg-blue-100"
          >
            {item.name} 분석 콘텐츠 보러가기 <span aria-hidden>↗</span>
          </a>
        )}
      </div>
















      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <div className="flex min-w-0 items-baseline justify-between rounded-lg bg-violet-50/70 px-3 py-2 sm:block sm:flex-[5]">
          <p className="text-[11px] text-violet-500">수요예측일</p>
          <p className="truncate text-[13px] font-bold text-violet-700">{dateRange(item.forecast_start, item.forecast_end)}</p>
        </div>
        <div className="flex min-w-0 items-baseline justify-between rounded-lg bg-amber-50 px-3 py-2 sm:block sm:flex-[2.2]">
          <p className="text-[11px] text-amber-800">청약일</p>
          <p className="truncate text-[13px] font-bold text-amber-800">{dateRange(item.sub_start, item.sub_end)}</p>
        </div>
        <div className="flex min-w-0 items-baseline justify-between rounded-lg bg-emerald-50 px-3 py-2 sm:block sm:flex-[1.8]">
          <p className="text-[11px] text-emerald-800">상장일</p>
          <p className="truncate text-[13px] font-bold text-emerald-800">{item.listing_date ? mmdd(item.listing_date) : "미정"}</p>
        </div>
      </div>
















      <div className="mt-2.5 flex flex-wrap gap-x-6 gap-y-1 px-0.5 text-[13px]">
        <span>
          <span className="text-gray-500">희망가액</span> <span className="font-semibold">{band}</span>
        </span>
        <span>
          <span className="text-gray-500">확정공모가</span>{" "}
          <span className="font-semibold">{item.final_price ? `${item.final_price.toLocaleString()}원` : "미정"}</span>
          {bandPos && <span className="ml-1 text-[11px] font-bold text-red-600">{bandPos}</span>}
        </span>
        <span>
          <span className="text-gray-500">공모 규모</span> <span className="font-semibold">{formatOfferSize(item)}</span>
        </span>
        <span>
          <span className="text-gray-500">수요예측</span> <span className="font-semibold tabular-nums">{ratioText(item.demand_ratio)}</span>
        </span>
        <span>
          <span className="text-gray-500">개인청약</span> <span className="font-semibold tabular-nums">{ratioText(item.sub_ratio)}</span>
        </span>
      </div>
















      {hasCommit && (
        <>
          <div className="mt-3 flex justify-end">
            <span className="text-[11px] text-gray-400 transition-opacity group-hover:opacity-0 group-focus-within:opacity-0">
              기관 확약 현황 ▾
            </span>
          </div>
          <div className="max-h-0 overflow-hidden transition-all duration-300 group-hover:max-h-96 group-focus-within:max-h-96">
            <CommitTable item={item} />
          </div>
        </>
      )}
    </div>
  );
}
















export default function IpoSchedulePage() {
  const items = getSortedIpoItems();
  const pastItems = getPastIpoItems();

  const currentCards = (
    <div className="space-y-3">
      {items.map((item) => (
        <PastDateGate key={item.corp_code} date={item.listing_date}>
          <IpoCard item={item} />
        </PastDateGate>
      ))}
      {items.length === 0 && (
        <p className="rounded-lg border border-gray-200 bg-white p-6 text-sm text-gray-400">진행 중인 공모가 없습니다.</p>
      )}
    </div>
  );

  const historyCards = (
    <div className="space-y-3">
      {pastItems.map((item) => (
        <IpoCard key={item.corp_code} item={item} />
      ))}
      {items.map((item) => (
        <PastDateGate key={`live-${item.corp_code}`} date={item.listing_date} showWhen="past">
          <IpoCard item={item} />
        </PastDateGate>
      ))}
      {pastItems.length === 0 && items.length === 0 && (
        <p className="rounded-lg border border-gray-200 bg-white p-6 text-sm text-gray-400">이전 IPO 이력이 없습니다.</p>
      )}
    </div>
  );
















  return (
    <main className="mx-auto w-full max-w-[900px] px-5 py-6">
      <IpoHistoryToggle current={currentCards} history={historyCards} />
    </main>
  );
}
