import Link from "next/link";

const CHAPTERS = [
  {
    href: "/rates",
    emoji: "🏦",
    eyebrow: "RATES",
    title: "기준금리 (국가별)",
    description: "한·미·일·유럽·중국 기준금리 분기별 비교",
  },
  {
    href: "/cpi",
    emoji: "📈",
    eyebrow: "INFLATION",
    title: "소비자물가지수 CPI",
    description: "최근 3개년 분기별 CPI YoY 국가별 비교",
  },
  {
    href: "/semiconductor-kospi",
    emoji: "🔬",
    eyebrow: "TRADE",
    title: "반도체 수출액 ↔ KOSPI",
    description: "주요 교역국 합산 반도체 수출액과 KOSPI 상관관계",
  },
  {
    href: "/fx-export",
    emoji: "💱",
    eyebrow: "FX",
    title: "수출액 ↔ 주요 통화 환율",
    description: "달러·엔·유로·위안 환율과 전체 수출액",
  },
  {
    href: "/trade-foreign",
    emoji: "🌊",
    eyebrow: "FLOWS",
    title: "무역수지 ↔ 외국인 순매수",
    description: "월별 무역수지와 코스피 외국인 수급",
  },
  {
    href: "/oil-cpi",
    emoji: "🛢️",
    eyebrow: "COMMODITIES",
    title: "유가 ↔ 물가(CPI)",
    description: "WTI 유가와 한국 CPI YoY 실측 비교",
  },
];

export default function Home() {
  return (
    <main className="flex min-h-screen flex-1 flex-col bg-pitch-black">
      <section className="px-6 py-24 text-center sm:px-10 sm:py-32">
        <h1 className="mx-auto max-w-3xl text-[40px] font-semibold leading-tight tracking-tight text-white sm:text-[56px]">
          Vericap
        </h1>
        <a
          href="https://blog.naver.com/vericap"
          target="_blank"
          rel="noopener noreferrer"
          className="mx-auto mt-4 inline-block max-w-xl text-[17px] leading-relaxed text-lime underline underline-offset-4"
        >
          경제 인사이트 보러가기
        </a>
      </section>

      <section className="px-6 pb-16 sm:px-10 sm:pb-20">
        <div className="mx-auto grid max-w-5xl grid-cols-1 gap-4 sm:grid-cols-2">
          {CHAPTERS.map((c) => (
            <Link
              key={c.href}
              href={c.href}
              className="rounded-[18px] border border-[#2a2a2a] bg-[#1e1e1e] p-6 transition-transform active:scale-[0.98]"
            >
              <div className="mb-4 text-3xl">{c.emoji}</div>
              <span className="mb-2.5 inline-block rounded-full bg-lime px-2.5 py-1 text-[11px] font-bold tracking-tight text-lime-ink">
                {c.eyebrow}
              </span>
              <h2 className="mb-2 text-[19px] font-semibold tracking-tight text-white">{c.title}</h2>
              <p className="text-sm leading-relaxed text-[#9a9a9a]">{c.description}</p>
            </Link>
          ))}
        </div>
      </section>

      <footer className="px-6 py-16 text-center sm:px-10">
        <p className="text-xs text-[#5a5a5a]">
          한국은행 ECOS · FRED · 공공데이터포털 · Yahoo Finance 기반 · 매일 1회 자동 갱신
        </p>
      </footer>
    </main>
  );
}
