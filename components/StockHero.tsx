import Link from "next/link";
import type { StockLockup } from "@/lib/types";
import { StockLockupTiles } from "@/components/StockLockupTiles";
import { formatKrwEok } from "@/lib/format";

const DEFAULT_BLOG_URL = "https://blog.naver.com/vericap";

/** 공모가 대비 등락률 게이지 — 12시가 0%, 하락은 왼쪽·상승은 오른쪽으로 바늘이 돈다. */
function ReturnGauge({ pct }: { pct: number }) {
  const clamped = Math.max(-100, Math.min(100, pct));
  const angle = ((90 - (clamped / 100) * 90) * Math.PI) / 180;
  const cx = 100;
  const cy = 96;
  const r = 74;
  const point = (radius: number) => ({
    x: cx + radius * Math.cos(angle),
    y: cy - radius * Math.sin(angle),
  });
  const edge = point(r);
  const tip = point(r - 13);
  const up = pct >= 0;
  const stroke = up ? "#e11d48" : "#2563eb";

  return (
    <svg viewBox="0 0 200 110" className="h-[80px] w-[142px] md:h-[106px] md:w-[190px]" aria-hidden>
      <path d={`M ${cx - r},${cy} A ${r},${r} 0 0 1 ${cx + r},${cy}`} fill="none" stroke="rgba(15,23,42,0.10)" strokeWidth="8" strokeLinecap="round" />
      <path
        d={`M ${cx},${cy - r} A ${r},${r} 0 0 ${up ? 1 : 0} ${edge.x},${edge.y}`}
        fill="none"
        stroke={stroke}
        strokeWidth="8"
        strokeLinecap="round"
      />
      <line x1={cx} y1={cy - r - 7} x2={cx} y2={cy - r + 7} stroke="rgba(15,23,42,0.35)" strokeWidth="2" strokeLinecap="round" />
      <line x1={cx} y1={cy} x2={tip.x} y2={tip.y} stroke="#0f172a" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="5" fill="#0f172a" />
      <circle cx={cx} cy={cy} r="1.8" fill="#ffffff" />
    </svg>
  );
}

const iconProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  className: "h-4 w-4",
};

/** 유리 카드 — 배경 그라디언트가 비쳐 보이도록 반투명 + 블러 */
function GlassTile({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-white/60 bg-white/55 px-3 py-2.5 shadow-[0_6px_24px_-8px_rgba(30,41,59,0.18)] backdrop-blur-xl md:rounded-2xl md:px-4 md:py-3.5">
      <div className="flex items-center gap-1.5 md:gap-2">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-white/70 text-slate-500 shadow-sm md:h-7 md:w-7 md:rounded-lg">
          {icon}
        </span>
        <p className="break-keep text-[10.5px] font-medium leading-tight text-slate-500 md:truncate md:text-[11.5px]">{label}</p>
      </div>
      <p className="mt-1.5 break-keep text-[15px] font-bold leading-tight tracking-tight text-slate-900 md:mt-2.5 md:text-[18px]">{value}</p>
      <p className="mt-0.5 break-keep text-[9.5px] leading-[12px] text-slate-400 md:text-[10.5px] md:leading-[13px] md:h-[13px]">{sub || ""}</p>
    </div>
  );
}

export function StockHero({ stock, updated, initialNow }: { stock: StockLockup; updated: string; initialNow: number }) {
  const ipoPrice = stock.ipo_price || 0;
  const initialShares = stock.initial_shares || stock.shares;
  const ipoCap = ipoPrice * initialShares;
  const closeCap = stock.market_cap || stock.shares * stock.close_price;
  const changePct = ipoPrice ? ((stock.close_price - ipoPrice) / ipoPrice) * 100 : 0;
  const hasReturn = Boolean(ipoPrice && stock.close_price);
  const up = changePct >= 0;
  const contentUrl = stock.content_url || DEFAULT_BLOG_URL;
  const contentLabel = stock.content_url ? "종목 분석 보러가기" : "기업 분석 포스팅 보러가기";

  // 데스크톱은 카드 5장, 모바일은 같은 값을 한 패널의 5행으로 그린다.
  // mobileSub: 모바일에서는 공간이 없어 상장주식수 같은 부연은 생략하고 기준일만 남긴다.
  const metrics: { label: string; value: string; sub?: string; mobileSub?: string; icon: React.ReactNode }[] = [
    {
      label: "상장일",
      value: stock.listing_date || "미정",
      icon: <svg {...iconProps}><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M8 3v4M16 3v4M3 10h18" /></svg>,
    },
    {
      label: "공모가",
      value: ipoPrice ? `${ipoPrice.toLocaleString("ko-KR")}원` : "미확인",
      icon: <svg {...iconProps}><circle cx="12" cy="12" r="9" /><path d="M12 7v10M9.5 9.8h5M9.5 14.2h5" /></svg>,
    },
    {
      label: "최근 종가",
      value: stock.close_price ? `${stock.close_price.toLocaleString("ko-KR")}원` : "-",
      sub: `${updated.slice(5)} 기준`,
      mobileSub: `${updated.slice(5)} 기준`,
      icon: <svg {...iconProps}><path d="M3 16.5 9 10l4 4 7.5-7.5M15 6.5h5.5V12" /></svg>,
    },
    {
      label: "시가총액(상장일 공모가 기준)",
      value: ipoCap ? formatKrwEok(ipoCap) : "미확인",
      sub: initialShares ? `상장주식수 ${initialShares.toLocaleString("ko-KR")}주` : "",
      icon: <svg {...iconProps}><path d="M3 21h18M6 21V9m6 12V4m6 17v-8" /></svg>,
    },
    {
      label: "시가총액(최근 종가 기준)",
      value: closeCap ? formatKrwEok(closeCap) : "-",
      sub: stock.shares ? `상장주식수 ${stock.shares.toLocaleString("ko-KR")}주` : "",
      icon: <svg {...iconProps}><path d="M20.5 7.5v9l-8.5 4.5-8.5-4.5v-9L12 3z" /><path d="m3.8 7.4 8.2 4.4 8.2-4.4M12 21v-9.2" /></svg>,
    },
  ];

  return (
    <div className="relative overflow-hidden rounded-[24px] bg-slate-50 px-4 py-5 md:rounded-[32px] md:px-8 md:py-8">
      {/* 배경 메시 그라디언트 — 유리 카드가 이 색을 머금는다 */}
      <div aria-hidden className="pointer-events-none absolute -left-24 -top-28 h-80 w-80 rounded-full bg-indigo-400/30 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -right-20 -top-16 h-72 w-72 rounded-full bg-sky-400/25 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-24 left-1/4 h-72 w-72 rounded-full bg-violet-400/20 blur-3xl" />

      <div className="relative grid gap-5 md:grid-cols-[minmax(0,430px)_1fr] md:gap-10">
        {/* 좌: 배경 위에 그대로 얹은 종목 요약 */}
        <div className="flex flex-col justify-between gap-3 md:gap-4">
          <div>
            <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-900 md:text-[32px]">{stock.name}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-white/70 px-2.5 py-0.5 text-[11px] font-semibold text-slate-700 shadow-sm backdrop-blur">
                {stock.market}
              </span>
              <span className="text-[11px] font-medium text-slate-400">{stock.code}</span>
            </div>
          </div>

          <div className="flex items-end justify-between gap-1">
            <div className="min-w-0">
              <p className="text-[11px] font-medium text-slate-500">공모가 대비</p>
              {hasReturn ? (
                <>
                  <p className={`mt-1 text-[38px] font-bold leading-none tracking-tight md:text-[48px] ${up ? "text-rose-600" : "text-blue-600"}`}>
                    {up ? "+" : ""}
                    {changePct.toFixed(1)}
                    <span className="text-[21px] md:text-[26px]">%</span>
                  </p>
                  <p className="mt-2 whitespace-nowrap text-[11px] text-slate-500 md:text-[12px]">
                    {ipoPrice.toLocaleString("ko-KR")}원 → {stock.close_price.toLocaleString("ko-KR")}원
                  </p>
                </>
              ) : (
                <p className="mt-1 text-[26px] font-bold leading-none text-slate-400">미확인</p>
              )}
            </div>
            {hasReturn && (
              <div className="-mb-1 -mr-2 shrink-0">
                <ReturnGauge pct={changePct} />
              </div>
            )}
          </div>

          <StockLockupTiles events={stock.events} shares={stock.shares} initialNow={initialNow} />
        </div>

        {/* 모바일: 카드 6장을 쌓으면 첫 화면을 다 먹는다 → 2열 컴팩트 패널로 압축 */}
        <div className="md:hidden">
          <div className="grid grid-cols-2 gap-x-3 gap-y-2.5 rounded-2xl border border-white/60 bg-white/55 px-4 py-3.5 shadow-[0_6px_24px_-8px_rgba(30,41,59,0.18)] backdrop-blur-xl">
            {metrics.map((metric) => (
              <div key={metric.label} className="min-w-0">
                <p className="break-keep text-[10px] font-medium leading-tight text-slate-500">{metric.label}</p>
                <p className="mt-0.5 break-keep text-[13.5px] font-bold leading-tight text-slate-900">{metric.value}</p>
                {metric.mobileSub && (
                  <p className="text-[9.5px] leading-[12px] text-slate-400">{metric.mobileSub}</p>
                )}
              </div>
            ))}
          </div>
          <Link
            href={contentUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 flex items-center justify-center gap-2 rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 px-4 py-3 text-[13px] font-bold text-white shadow-[0_10px_28px_-10px_rgba(79,70,229,0.65)]"
          >
            {contentLabel}
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M7 17 17 7M9 7h8v8" /></svg>
          </Link>
        </div>

        {/* 데스크톱: 분석 CTA를 좌상단에 두고 지표 5칸이 뒤따른다 (2열 3행) */}
        <div className="hidden grid-cols-2 gap-3 md:grid">
          <Link
            href={contentUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="group flex flex-col justify-between rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 px-4 py-3.5 shadow-[0_10px_28px_-10px_rgba(79,70,229,0.65)] transition-shadow hover:shadow-[0_14px_32px_-10px_rgba(79,70,229,0.8)]"
          >
            <div className="flex items-start justify-between">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/20 text-white">
                <svg {...iconProps}><path d="M6 3h9l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" /><path d="M14 3v6h6M8.5 13h7M8.5 17h4.5" /></svg>
              </span>
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-indigo-700 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5">
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M7 17 17 7M9 7h8v8" /></svg>
              </span>
            </div>
            <p className="mt-3 text-[13px] font-bold leading-snug text-white">{contentLabel}</p>
          </Link>
          {metrics.map((metric) => (
            <GlassTile key={metric.label} label={metric.label} value={metric.value} sub={metric.sub} icon={metric.icon} />
          ))}
        </div>
      </div>
    </div>
  );
}
