import type { Metadata } from "next";
import { ValueChainDemo } from "@/components/ValueChainDemo";

export const metadata: Metadata = {
  title: "밸류체인 · 테마주 지도 | Vericap",
  description:
    "반도체, AI 데이터센터, HBM, 방산, 유가 등 시장 이슈와 관련 국내 종목을 검색 관심도, 거래대금, 수익률 기준으로 비교하는 테마주 지도입니다.",
  alternates: { canonical: "/value-chain" },
  keywords: [
    "밸류체인",
    "테마주",
    "관련주",
    "시장 이슈",
    "반도체 밸류체인",
    "HBM 관련주",
    "AI 데이터센터 관련주",
    "방산 관련주",
    "유가 관련주",
    "국내 주식 테마",
  ],
  openGraph: {
    title: "밸류체인 · 테마주 지도 | Vericap",
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
    name: "밸류체인 · 테마주 지도",
    url: "https://vericap.co.kr/value-chain",
    inLanguage: "ko-KR",
    isPartOf: {
      "@type": "WebSite",
      name: "Vericap",
      url: "https://vericap.co.kr",
    },
    about: [
      "국내 주식 테마",
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
    <main className="w-full px-5 py-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />
      <ValueChainDemo />
    </main>
  );
}
