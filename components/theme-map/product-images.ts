import { companyPlaceholder } from "@/lib/company-logos";
import sectorImages from "@/data/value-chain/sector-images.json";
import issues from "@/data/value-chain/issues.json";

type SectorImage = { src: string; tile?: number };
const sectorVisuals: Record<string, SectorImage> = sectorImages;
const sectorTopicIds = Object.fromEntries(issues.map(issue => [issue.id, issue.topicId]));

// Sector artwork is independent of company logos and company placeholders.
export function sectorImage(id: string) {
  const topicId = sectorTopicIds[id] ?? id.replace(/^topic-/, "");
  const visual = sectorVisuals[topicId] ?? sectorVisuals.wafer;
  return visual.tile === undefined ? { src: visual.src } : {
    src: visual.src,
    position: `${(visual.tile % 3) * 50}% ${Math.floor(visual.tile / 3) * 100}%`,
    size: "300% 200%",
  };
}

// Add a company ID and a local image path here to replace its product-group visual.
export const companyProductImages: Record<string, string> = {};

export function productImage(id: string, description: string) {
  if (companyProductImages[id]) return { src: companyProductImages[id] };
  const tile = /삼성전자/.test(description) ? 0
    : /로봇|감속|모터|자동화/.test(description) ? 4
    : /변압|전력|전선|에너지|발전|유가/.test(description) ? 5
    : /테스트|소켓|리노|ISC|핀/.test(description) ? 3
    : /한미|본딩|후공정|패키징|장비/.test(description) ? 2
    : /하이닉스|메모리|HBM|D램/.test(description) ? 1
    : /반도체|파운드리|웨이퍼|칩/.test(description) ? 0 : -1;
  if (tile < 0) return { src: companyPlaceholder };
  return {
    src: "/theme-products/product-atlas.png",
    position: `${(tile % 3) * 50}% ${Math.floor(tile / 3) * 100}%`,
    size: "300% 200%",
  };
}
