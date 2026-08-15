import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getStockByCode, getEventGroupsByStock, getSiteData } from "@/lib/data";
import { listingShares } from "@/lib/returns";
import { BackButton } from "@/components/BackButton";
import { StockEventSections } from "@/components/StockEventSections";
import { StockHero } from "@/components/StockHero";


const BUILD_NOW = Date.now();







export function generateStaticParams() {
  return getSiteData().stocks.map((stock) => ({ code: stock.code }));
}




export async function generateMetadata({ params }: { params: Promise<{ code: string }> }): Promise<Metadata> {
  const { code } = await params;
  const stock = getStockByCode(code);
  if (!stock) return { title: "종목 정보 없음" };


  const sortedDates = stock.events
    .map((event) => event.tradable_date)
    .sort((a, b) => a.localeCompare(b));
  const firstDate = sortedDates[0];
  const totalQty = stock.events.reduce((sum, event) => sum + event.qty, 0);
  const quantityUnit = stock.events.some((event) => event.unit === "DR") ? "DR" : "주";
  const title = `${stock.name} 락업 해제 일정`;
  const description = `${stock.name}(${stock.market}) IPO 락업 해제일, 보호예수 해제 일정, 의무보유확약 물량 ${totalQty.toLocaleString(
    "ko-KR",
  )}${quantityUnit}${firstDate ? `, 주요 해제일 ${firstDate}` : ""} 정보를 확인하세요.`;


  return {
    title,
    description,
    alternates: {
      canonical: `/stock/${stock.code}`,
    },
    openGraph: {
      title: `${title} | Vericap`,
      description,
      url: `/stock/${stock.code}`,
      siteName: "Vericap",
      locale: "ko_KR",
      type: "article",
    },
  };
}




export default async function StockPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const stock = getStockByCode(code);
  if (!stock) return notFound();




  const groups = getEventGroupsByStock(stock);
  const { updated } = getSiteData();




  return (
    <main className="mx-auto max-w-[1040px] px-5 py-6">
      <div className="mb-4">
        <BackButton />
      </div>
      <StockHero stock={stock} updated={updated} initialNow={BUILD_NOW} />
      <h2 className="sr-only">{stock.name} 락업 해제 일정</h2>
      {/* 아래 목록은 위 지표 섹션과 다른 면(surface)으로 분리한다 — 레퍼런스의 섹션 구분 디테일 */}
      <section className="mt-4 rounded-[24px] border border-slate-200/70 bg-slate-50/70 px-4 py-5 shadow-[0_2px_20px_-14px_rgba(15,23,42,0.4)] md:mt-5 md:rounded-[32px] md:px-8 md:py-7">
        {/* 비중이 상장일 상장주식수 기준이므로 함께 보여주는 주식수도 같은 기준으로 맞춘다 */}
        <StockEventSections
          groups={groups}
          initialNow={BUILD_NOW}
          shares={listingShares(stock)}
          adjustmentEvents={stock.adjustment_events}
        />
      </section>
    </main>
  );
}
