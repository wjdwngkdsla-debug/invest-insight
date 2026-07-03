import { fetchSemiconductorVsKospi } from "@/lib/semiKospi";

export const revalidate = 86400;

export async function GET() {
  const data = await fetchSemiconductorVsKospi();
  return Response.json({ data });
}
