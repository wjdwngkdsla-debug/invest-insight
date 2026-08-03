import type { Metadata } from "next";
import { getPastIpoItems, getSortedIpoItems, dateRange, yymmdd, bandPosition, type IpoItem } from "@/lib/ipo";
import { IpoStatusChip } from "@/components/IpoStatusChip";
import { PastDateGate } from "@/components/PastDateGate";
import { IpoHistoryToggle } from "@/components/IpoHistoryToggle";
import { formatKrwEok } from "@/lib/format";
import { getSiteData } from "@/lib/data";
import Link from "next/link";
































export const metadata: Metadata = {
  title: "IPO 일정 | IPO 락업 캘린더",
  description: "공모 진행 중인 종목의 수요예측·청약·상장 일정과 수요예측 결과를 제공합니다.",
};
































function formatOfferSize(item: IpoItem): string {
  const shares = item.offer_shares || 0;
  const price = item.final_price || item.band_high || 0;
  if (!shares || !price) return "미정";
  return formatKrwEok(shares * price);
}
















function ratioText(v?: number): string {
  return v ? `${v.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}:1` : "-";
}
















// 확약 표: 신청·배정 수량 + 기간별 신청 수량 대비 배정 비율
function CommitTable({ item }: { item: IpoItem }) {
  const apply = (item.commit_apply || []).filter((tier) => tier.visible !== false);
  const alloc = (item.commit_alloc || []).filter((tier) => tier.visible !== false);
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
















function IpoCard({ item, lockupHref }: { item: IpoItem; lockupHref?: string }) {
  const hasCommit = Boolean(item.commit_apply?.length || item.commit_alloc?.length);
  const band = item.band_low && item.band_high ? `${item.band_low.toLocaleString()}~${item.band_high.toLocaleString()}원` : "미정";
  const bandPos = bandPosition(item);
















  return (
    <div
      tabIndex={hasCommit ? 0 : undefined}
      className="group rounded-[20px] border border-gray-200 bg-white p-5 pb-4 shadow-[0_10px_35px_-26px_rgba(15,23,42,0.35)] outline-none transition-colors hover:border-gray-300 focus-within:border-gray-300"
    >
      <div className="flex flex-wrap items-center gap-2">
        <IpoStatusChip item={item} />
        {/* 락업 상세 페이지가 있는 종목은 이름을 눌러 바로 이동한다 */}
        {lockupHref ? (
          <Link
            href={lockupHref}
            className={`font-semibold text-gray-900 underline-offset-4 hover:text-blue-700 hover:underline ${item.withdrawn ? "text-gray-400 line-through" : ""}`}
          >
            {item.name}
          </Link>
        ) : (
          <span className={`font-semibold text-gray-900 ${item.withdrawn ? "text-gray-400 line-through" : ""}`}>{item.name}</span>
        )}
        <span className="rounded-full border border-gray-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700">
          {item.market || "시장 미정"}
        </span>
        <span className="text-xs text-gray-500">주관 {item.underwriter || "미정"}</span>
        {(Number(item.offering_attempt || 1) > 1 || item.content_url) && (
          <span className="ml-auto flex flex-wrap items-center justify-end gap-2">
            {!item.withdrawn && Number(item.offering_attempt || 1) > 1 && (
              <span className="inline-flex h-8 items-center rounded-full border border-amber-200 bg-amber-50 px-3 text-[11.5px] font-bold text-amber-700">
                ↻ {item.offering_attempt}차 공모 도전
              </span>
            )}
            {item.content_url && (
              <a
                href={item.content_url}
                target="_blank"
                rel="noopener noreferrer"
                className="group/cta inline-flex h-8 items-center gap-1.5 rounded-full bg-blue-600 px-3.5 text-[11.5px] font-semibold text-white transition-colors hover:bg-blue-700"
              >
                {item.name} 분석 콘텐츠 보러가기
                <svg viewBox="0 0 24 24" className="h-3 w-3 transition-transform group-hover/cta:-translate-y-0.5 group-hover/cta:translate-x-0.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M7 17 17 7M9 7h8v8" /></svg>
              </a>
            )}
          </span>
        )}
      </div>
















      {/* 일정 3종 — 색은 홈 캘린더와 연결되므로 유지하고, 테두리·라운드만 상세 페이지 타일과 통일 */}
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <div className="flex min-w-0 items-baseline justify-between rounded-xl border border-violet-100 bg-violet-50/70 px-3 py-2 sm:block sm:flex-[5]">
          <p className="text-[11px] font-medium text-violet-500">수요예측일</p>
          <p className="truncate text-[13px] font-bold text-violet-700 sm:mt-0.5">{dateRange(item.forecast_start, item.forecast_end)}</p>
        </div>
        <div className="flex min-w-0 items-baseline justify-between rounded-xl border border-amber-100 bg-amber-50/80 px-3 py-2 sm:block sm:flex-[2.2]">
          <p className="text-[11px] font-medium text-amber-700">청약일</p>
          <p className="truncate text-[13px] font-bold text-amber-800 sm:mt-0.5">{dateRange(item.sub_start, item.sub_end)}</p>
        </div>
        <div className="flex min-w-0 items-baseline justify-between rounded-xl border border-emerald-100 bg-emerald-50/80 px-3 py-2 sm:block sm:flex-[1.8]">
          <p className="text-[11px] font-medium text-emerald-700">상장일</p>
          <p className="truncate text-[13px] font-bold text-emerald-800 sm:mt-0.5">{item.listing_date ? yymmdd(item.listing_date) : "미정"}</p>
        </div>
      </div>
















      {/* 공모 지표 — 상세 페이지의 회색 스펙 패널과 같은 톤으로 묶는다 */}
      <div className="mt-2.5 flex flex-wrap gap-x-6 gap-y-1.5 rounded-xl border border-gray-200 bg-gray-50/80 px-3.5 py-2.5 text-[13px]">
        <span>
          <span className="text-slate-500">희망가액</span> <span className="font-bold text-slate-900">{band}</span>
        </span>
        <span>
          <span className="text-slate-500">확정공모가</span>{" "}
          <span className="font-bold text-slate-900">{item.final_price ? `${item.final_price.toLocaleString()}원` : "미정"}</span>
          {bandPos && <span className="ml-1 text-[11px] font-bold text-rose-600">{bandPos}</span>}
        </span>
        <span>
          <span className="text-slate-500">공모 규모</span> <span className="font-bold text-slate-900">{formatOfferSize(item)}</span>
        </span>
        <span>
          <span className="text-slate-500">수요예측</span> <span className="font-bold tabular-nums text-slate-900">{ratioText(item.demand_ratio)}</span>
        </span>
        <span>
          <span className="text-slate-500">개인청약</span> <span className="font-bold tabular-nums text-slate-900">{ratioText(item.sub_ratio)}</span>
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
  // 락업 상세 페이지가 실제로 생성된 종목코드만 링크한다(없는 코드로 보내면 404).
  const lockupCodes = new Set(getSiteData().stocks.map((stock) => stock.code));
  const hrefFor = (item: IpoItem) =>
    item.stock_code && lockupCodes.has(item.stock_code) ? `/stock/${item.stock_code}` : undefined;

  const currentCards = (
    <div className="space-y-3">
      {items.map((item) => (
        <PastDateGate key={item.corp_code} date={item.listing_date}>
          <IpoCard item={item} lockupHref={hrefFor(item)} />
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
        <div key={item.corp_code} data-ipo-history-card data-ipo-name={item.name}>
          <IpoCard item={item} lockupHref={hrefFor(item)} />
        </div>
      ))}
      {items.map((item) => (
        <PastDateGate key={`live-${item.corp_code}`} date={item.listing_date} showWhen="past">
          <div data-ipo-history-card data-ipo-name={item.name}>
            <IpoCard item={item} lockupHref={hrefFor(item)} />
          </div>
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
