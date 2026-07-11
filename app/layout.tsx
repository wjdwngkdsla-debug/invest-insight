import type { Metadata } from "next";
import Link from "next/link";
import { Analytics } from "@vercel/analytics/next";
import NavTabs from "@/components/NavTabs";
import "./globals.css";

const siteUrl = "https://vericap.co.kr";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "IPO 락업 캘린더 | Vericap",
    template: "%s | Vericap",
  },
  description:
    "IPO 신규상장 종목의 락업 해제일, 보호예수 해제 일정, 의무보유확약 물량, 해제 비중과 시가총액 기준 해제 규모를 한눈에 확인하세요.",
  applicationName: "Vericap IPO 락업 캘린더",
  keywords: [
    "IPO 락업",
    "IPO 락업 캘린더",
    "락업 해제",
    "보호예수 해제",
    "의무보유확약",
    "IPO 기관 확약",
    "신규상장 일정",
    "상장주 락업",
    "공모주 락업",
    "Vericap",
  ],
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: "IPO 락업 캘린더 | Vericap",
    description:
      "신규상장 종목별 락업 해제일, 보호예수 해제 일정, 의무보유확약 물량과 해제 비중을 확인하세요.",
    url: siteUrl,
    siteName: "Vericap",
    locale: "ko_KR",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "IPO 락업 캘린더 | Vericap",
    description:
      "IPO 신규상장 종목의 락업 해제 일정, 보호예수 물량, 의무보유확약 정보를 한눈에 확인하세요.",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-snippet": -1,
      "max-image-preview": "large",
      "max-video-preview": -1,
    },
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-gray-50 text-gray-900">
        {/* 모든 페이지 공통 상단 — 브랜드(홈 링크) + 우측 콘텐츠 링크 */}
        <header className="mx-auto flex w-full max-w-[1480px] flex-wrap items-center justify-between gap-3 px-5 pb-2 pt-8">
          <div className="flex flex-wrap items-center gap-4">
            <Link href="/" className="text-2xl font-bold tracking-tight">
              IPO 락업 캘린더
            </Link>
            <NavTabs />
          </div>
          <Link
            href="https://blog.naver.com/vericap"
            target="_blank"
            rel="noopener noreferrer"
            className="whitespace-nowrap text-sm font-medium text-blue-600 hover:underline"
          >
            경제 콘텐츠 보러가기 ↗
          </Link>
        </header>

        <div className="flex-1">{children}</div>

        <footer className="border-t border-gray-200 bg-white px-4 py-8">
          <div className="mx-auto max-w-5xl space-y-2 text-xs leading-relaxed text-gray-500">
            <p>
              해제일은 매도 가능 시점이며 실제 매도 여부와 무관합니다. 해제일이 주말·거래소 휴장일인 경우 실제 매매는
              다음 거래일부터 가능합니다. 본 정보는 투자 권유를 목적으로 하지 않으며, 투자 판단의 책임은 이용자
              본인에게 있습니다.
            </p>
            <p>
              출처: 금융감독원 전자공시시스템(DART) · 한국거래소(KRX) · 공공데이터포털 금융위원회_주식발행정보
            </p>
          </div>
        </footer>
        <Analytics />
      </body>
    </html>
  );
}
