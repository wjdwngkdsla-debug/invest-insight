import type { Metadata } from "next";
import { ValueChainDemo } from "@/components/ValueChainDemo";

export const metadata: Metadata = {
  title: "시장 테마맵 | 테마주·관련주 지도 - Vericap",
  description:
    "시장 이슈별 관련주를 검색 관심도, 거래대금, 수익률 기준으로 비교합니다. HBM, AI 데이터센터, 로봇, 방산, 유가 등 국내 주식 테마를 한눈에 확인하세요.",
  alternates: { canonical: "/value-chain" },
  keywords: [
    "테마맵",
    "시장 테마맵",
    "테마주",
    "관련주",
    "관련주 지도",
    "시장 이슈",
    "반도체 밸류체인",
    "HBM 관련주",
    "AI 데이터센터 관련주",
    "방산 관련주",
    "유가 관련주",
    "국내 주식 테마",
  ],
  openGraph: {
    title: "시장 테마맵 | 테마주·관련주 지도 - Vericap",
    description:
      "시장 이슈별 관련 국내 종목을 검색 관심도, 거래대금, 수익률 기준으로 비교합니다.",
    url: "https://vericap.co.kr/value-chain",
    siteName: "Vericap",
    locale: "ko_KR",
    type: "website",
  },
};

export default function ValueChainPage() {
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: "시장 테마맵 · 테마주 관련주 지도",
    url: "https://vericap.co.kr/value-chain",
    inLanguage: "ko-KR",
    isPartOf: {
      "@type": "WebSite",
      name: "Vericap",
      url: "https://vericap.co.kr",
    },
    about: [
      "국내 주식 테마",
      "시장 테마맵",
      "반도체 밸류체인",
      "시장 이슈",
      "관련주 비교",
      "검색 관심도",
      "거래대금",
      "수익률",
    ],
    description:
      "시장 이슈별 관련 국내 종목을 검색 관심도, 거래대금, 수익률 기준으로 비교하는 Vericap 테마주 지도입니다.",
  };

  return (
    <main className="w-full px-0 py-3 sm:px-5 sm:py-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />
      <ValueChainDemo />
    </main>
  );
}
