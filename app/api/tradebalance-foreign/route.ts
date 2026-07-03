import { fetchTradeBalanceVsForeign } from "@/lib/tradeForeign";

export const revalidate = 86400;

export async function GET() {
  const data = await fetchTradeBalanceVsForeign();
  return Response.json({ data });
}
