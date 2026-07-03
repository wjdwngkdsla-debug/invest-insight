import { fetchAllBaseRates } from "@/lib/rates";

export const revalidate = 86400; // 1일 1회 갱신

export async function GET() {
  const data = await fetchAllBaseRates();
  return Response.json({ data });
}
