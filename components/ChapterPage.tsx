import Link from "next/link";

export function ChapterPage({
  eyebrow,
  title,
  description,
  tone = "light",
  children,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  tone?: "light" | "parchment" | "dark";
  children: React.ReactNode;
}) {
  const toneClasses = {
    light: "bg-canvas text-ink",
    parchment: "bg-canvas-parchment text-ink",
    dark: "bg-surface-tile-1 text-white",
  }[tone];

  const eyebrowClasses = tone === "dark" ? "text-primary-on-dark" : "text-primary";
  const linkClasses = tone === "dark" ? "text-primary-on-dark" : "text-primary";

  return (
    <main className={`flex min-h-screen flex-1 flex-col ${toneClasses}`}>
      <div className="mx-auto w-full max-w-5xl px-6 py-16 sm:px-10 sm:py-20">
        <Link href="/" className={`mb-8 inline-block text-sm font-semibold ${linkClasses}`}>
          ← 전체 챕터로
        </Link>
        <p className={`mb-2 text-sm font-semibold tracking-tight ${eyebrowClasses}`}>{eyebrow}</p>
        <h1 className="mb-3 text-[34px] font-semibold leading-tight tracking-tight sm:text-[40px]">
          {title}
        </h1>
        {description && (
          <p className={`mb-8 max-w-2xl text-[17px] leading-relaxed ${tone === "dark" ? "text-body-muted" : "text-ink-muted-80"}`}>
            {description}
          </p>
        )}
        <div className="mt-8">{children}</div>
      </div>
    </main>
  );
}
