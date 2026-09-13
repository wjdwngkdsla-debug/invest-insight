import { loadTradeDatasets } from "@/lib/trade-server";
import { buildTradeUpdates } from "@/lib/trade-updates";
import { tradeProducts } from "@/lib/trade";

export const dynamic = "force-dynamic";
export async function GET() {
  const updates = buildTradeUpdates(await loadTradeDatasets(), tradeProducts);
  return Response.json({ version: 1, updates }, { headers: { "Cache-Control": "no-store" } });
}
