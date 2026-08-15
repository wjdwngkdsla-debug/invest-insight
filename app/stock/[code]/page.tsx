import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getStockByCode, getEventGroupsByStock, getSiteData } from "@/lib/data";
import { StockDetailClient } from "@/components/StockDetailClient";


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
      <StockDetailClient stock={stock} groups={groups} updated={updated} initialNow={BUILD_NOW} />
    </main>
  );
}
