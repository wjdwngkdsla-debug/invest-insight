import { fetchAllCpi } from "@/lib/cpi";

export const revalidate = 86400;

export async function GET() {
  const data = await fetchAllCpi();
  return Response.json({ data });
}
