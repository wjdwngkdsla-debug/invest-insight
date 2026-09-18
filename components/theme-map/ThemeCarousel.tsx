"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ArrowUpRight, Pause, Play, ChartNoAxesCombined } from "lucide-react";
import RoundCarousel from "@/components/originkit/RoundCarousel";
import { productImage, sectorImage } from "./product-images";
import { CompanyIdentity, CompanyLogo } from "./CompanyLogo";
import { companyLogos } from "@/lib/company-logos";

interface Item {
  id: string;
  name: string;
  role: string;
  type: "company" | "issue";
  category: string;
}

export default function ThemeCarousel<T extends Item>({ center, companyId, items, onOpenPanel, onOpenItem }: {
  center: { title: string; category: string };
  companyId?: string | null;
  items: T[];
  onOpenPanel: () => void;
  onOpenItem: (item: T) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 900, height: 620 });
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (!host.current) return;
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(host.current);
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(motion.matches);
    update();
    motion.addEventListener("change", update);
    return () => { observer.disconnect(); motion.removeEventListener("change", update); };
  }, []);
  const count = items.length;
  const cardItems = count > 0 && count < 3 ? [...items, ...items, ...items].slice(0, 3) : items;
  const width = Math.round(Math.max(155, Math.min(290, size.width * (size.width < 700 ? .6 : .3), (size.height - 200) * .82)));
  return <section ref={host} className="theme-carousel" aria-label={`${center.title} 관련 종목`}>
    <div className="theme-carousel-heading">
      <div><span className="theme-eyebrow">{center.category} · {count}개 {center.category === "관련주" ? "테마" : "관련주"}</span><h1>{companyId ? <CompanyIdentity id={companyId} name={center.title} size={42} /> : center.title}</h1></div>
      <button className="theme-compare" onClick={onOpenPanel}><ChartNoAxesCombined size={15} />비교 보기<ArrowUpRight size={14} /></button>
    </div>
    <div className="theme-carousel-scene">
      {count ? <RoundCarousel
        images={cardItems.map(item => {
          if (item.type === "issue") return sectorImage(item.id);
          const logo = item.type === "company" ? companyLogos[item.id] : undefined;
          return logo ? { src: logo.src, size: `${Math.min(width * .66, logo.width ?? 96)}px auto`, position: "center 35%", background: logo.canvasColor ?? (logo.background === "dark" ? "#23313d" : "#ffffff") } : productImage(item.id, `${item.name} ${item.role}`);
        })}
        imageWidth={width} imageHeight={Math.round(width * 1.16)} spacing={size.width > 1000 ? 8 : 3.8}
        speed={paused || reduced ? 0 : 1.08} sensitivity={.55} tilt={-6}
        perspective={1800} cornerRadius={18} innerDim={2.5} background="#070809"
        step={step}
        renderItem={index => {
          const item = cardItems[index];
          const logo = item.type === "company" ? companyLogos[item.id] : undefined;
          const logoSize = Math.min(width * .66, logo?.width ?? 96, logo?.height ? (width * .5) * ((logo.width ?? 96) / logo.height) : 160);
          return <button className="theme-product-card" style={logo ? { backgroundColor: logo.canvasColor ?? (logo.background === "dark" ? "#23313d" : "#ffffff") } : undefined} data-visual={logo ? "logo" : "product"} onClick={() => onOpenItem(item)} aria-label={`${item.name} ${item.type === "company" ? "관련 테마" : "관련주"} 보기`}>
            {logo ? <span className="theme-brand-media"><CompanyLogo id={item.id} name={item.name} size={logoSize} className="theme-brand-logo" /></span> : null}
            <span className="theme-product-category">{item.type === "company" ? "관련주" : item.category}</span>
            <span className="theme-product-caption"><strong>{item.name}</strong><span>{item.role}</span><ArrowUpRight size={18} /></span>
          </button>;
        }}
      /> : <p className="theme-no-companies">등록된 관련 종목이 없습니다.</p>}
    </div>
    <div className="theme-carousel-bottom">
      <div className="theme-company-index">{items.map(item => <button key={item.id} onClick={() => onOpenItem(item)}>{item.type === "company" ? <CompanyIdentity id={item.id} name={item.name} size={24} /> : item.name}</button>)}</div>
      <div className="theme-carousel-controls">
        <button aria-label="이전 카드" title="이전 카드" onClick={() => { setPaused(true); setStep(s => s - 1); }}><ArrowLeft size={17} /></button>
        <button aria-label={paused || reduced ? "자동 회전 재생" : "자동 회전 일시정지"} title={paused || reduced ? "자동 회전 재생" : "자동 회전 일시정지"} onClick={() => { setReduced(false); setPaused(!(paused || reduced)); }}>{paused || reduced ? <Play size={15} /> : <Pause size={15} />}</button>
        <button aria-label="다음 카드" title="다음 카드" onClick={() => { setPaused(true); setStep(s => s + 1); }}><ArrowRight size={17} /></button>
      </div>
    </div>
  </section>;
}
