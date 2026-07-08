import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";


export const metadata: Metadata = {
  title: "IPO 락업 캘린더",
  description: "신규 상장주 의무보유확약·보호예수 해제 일정을 제공합니다.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-cream text-ink">
        <link
          rel="stylesheet"
          precedence="default"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
        />
        <header>
          <div className="mx-auto flex max-w-[1440px] items-center px-6 py-5">
            <Link href="/" className="flex items-center gap-2 text-[17px] font-extrabold tracking-tight">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-lime ring-1 ring-black/10" aria-hidden />
              IPO 락업 캘린더
            </Link>
          </div>
        </header>

        <div className="flex-1">{children}</div>

        <footer className="border-t border-hairline px-6 py-10">
          <div className="mx-auto max-w-[1440px] space-y-2 text-xs leading-relaxed text-ink-muted">
            <p>
              해제일은 매도 가능 시점이며 실제 매도 여부와 무관합니다. 본 정보는 투자 권유를 목적으로 하지 않으며,
              투자 판단의 책임은 이용자 본인에게 있습니다.
            </p>
            <p>
              출처: 금융감독원 전자공시시스템(DART) · 한국거래소(KRX) · 공공데이터포털 금융위원회_주식발행정보
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
