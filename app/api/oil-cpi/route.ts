import { fetchOilVsCpi } from "@/lib/oilCpi";

export const revalidate = 86400;

export async function GET() {
  const data = await fetchOilVsCpi();
  return Response.json({ data });
}
