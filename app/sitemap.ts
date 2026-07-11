import type { MetadataRoute } from "next";
import { getSiteData } from "@/lib/data";


const siteUrl = "https://vericap.co.kr";


export default function sitemap(): MetadataRoute.Sitemap {
  const data = getSiteData();
  const lastModified = data.updated ? new Date(data.updated) : new Date();


  const staticRoutes: MetadataRoute.Sitemap = [
    {
      url: siteUrl,
      lastModified,
      changeFrequency: "daily",
      priority: 1,
    },
    {
      url: `${siteUrl}/ipo`,
      lastModified,
      changeFrequency: "daily",
      priority: 0.8,
    },
  ];


  const stockRoutes: MetadataRoute.Sitemap = data.stocks.map((stock) => ({
    url: `${siteUrl}/stock/${encodeURIComponent(stock.code)}`,
    lastModified,
    changeFrequency: "daily",
    priority: 0.7,
  }));


  return [...staticRoutes, ...stockRoutes];
}
