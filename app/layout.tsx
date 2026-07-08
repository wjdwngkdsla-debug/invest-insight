import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/next";
import "./globals.css";


export const metadata: Metadata = {
  title: "IPO 락업 해제 캘린더",
  description: "신규 상장주 의무보유확약·보호예수 해제 일정을 제공합니다.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-gray-50 text-gray-900">
        <div className="flex-1">{children}</div>

        <footer className="border-t border-gray-200 bg-white px-4 py-8">
          <div className="mx-auto max-w-5xl space-y-2 text-xs leading-relaxed text-gray-500">
            <p>
              해제일은 매도 가능 시점이며 실제 매도 여부와 무관합니다. 본 정보는 투자 권유를 목적으로 하지 않으며,
              투자 판단의 책임은 이용자 본인에게 있습니다.
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
