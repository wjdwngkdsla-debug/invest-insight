import logoData from "@/data/value-chain/logos.json";

export const companyLogos: Record<string, { src: string; background?: string; canvasColor?: string; width?: number; height?: number }> = logoData.companies;
export const companyPlaceholder = "/theme-products/company-placeholder.png";
