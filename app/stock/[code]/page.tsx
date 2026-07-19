import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getStockByCode, getEventGroupsByStock, getSiteData } from "@/lib/data";
import { BackButton } from "@/components/BackButton";
import { StockEventSections } from "@/components/StockEventSections";


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
  const title = `${stock.name} 락업 해제 일정`;
  const description = `${stock.name}(${stock.market}) IPO 락업 해제일, 보호예수 해제 일정, 의무보유확약 물량 ${totalQty.toLocaleString(
    "ko-KR",
  )}주${firstDate ? `, 주요 해제일 ${firstDate}` : ""} 정보를 확인하세요.`;


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
    <main className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-8">
        <BackButton />
        <span className="inline-flex rounded-full border border-gray-200 bg-white px-2.5 py-0.5 text-xs font-medium text-gray-500">
          {stock.market}
        </span>
        <h1 className="mt-3 text-[28px] font-bold leading-tight">{stock.name} 락업 해제 일정</h1>
        <p className="mt-1.5 text-sm text-gray-500">
          상장일 {stock.listing_date} · 공모가{" "}
          {stock.ipo_price ? `${stock.ipo_price.toLocaleString("ko-KR")}원` : "미확인"}
        </p>
      </div>
      <StockEventSections
        groups={groups}
        initialNow={BUILD_NOW}
        updated={updated}
        marketCap={stock.market_cap || stock.shares * stock.close_price}
      />
    </main>
  );
}
