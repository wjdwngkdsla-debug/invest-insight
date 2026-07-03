import { fetchFxVsExport } from "@/lib/fxExport";

export const revalidate = 86400;

export async function GET() {
  const data = await fetchFxVsExport();
  return Response.json({ data });
}
