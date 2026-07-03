"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CountrySeries } from "@/lib/types";

const LINE_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c"];

function formatNumber(value: number): string {
  return value.toLocaleString("ko-KR", { maximumFractionDigits: 2 });
}

export function CountryIndicatorCard({
  unit,
  countries,
}: {
  unit: string;
  countries: CountrySeries[];
}) {
  const charted = countries.filter((c) => c.charted);
  const tableOnly = countries.filter((c) => !c.charted);

  // 차트용 데이터: period를 기준으로 국가별 값 병합
  const periods = Array.from(new Set(charted.flatMap((c) => c.series.map((p) => p.period)))).sort();
  const chartData = periods.map((period) => {
    const row: Record<string, string | number | null> = { period };
    for (const c of charted) {
      const point = c.series.find((p) => p.period === period);
      row[c.label] = point?.value ?? null;
    }
    return row;
  });

  const estimatePeriod = charted[0]?.series.find((p) => p.isEstimate)?.period;

  const axisEndPeriods = new Set(
    charted.map((c) => c.series.filter((p) => !p.isEstimate).at(-1)?.period).filter(Boolean)
  );
  const hasMisalignedAxis = axisEndPeriods.size > 1;

  return (
    <div className="rounded-[18px] border border-hairline bg-canvas p-6">
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 20, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="period" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} unit={unit} />
            <Tooltip
              labelFormatter={(label) => `기간: ${label}`}
              formatter={(value) => (typeof value === "number" ? formatNumber(value) : value)}
            />
            <Legend />
            {estimatePeriod && (
              <ReferenceLine
                x={estimatePeriod}
                stroke="#cccccc"
                strokeDasharray="3 3"
                label={{ value: "추정치", position: "top", fontSize: 10, fill: "#7a7a7a" }}
              />
            )}
            {charted.map((c, i) => (
              <Line
                key={c.country}
                type="monotone"
                dataKey={c.label}
                stroke={LINE_COLORS[i % LINE_COLORS.length]}
                strokeWidth={2}
                dot={(props) => {
                  const isEstimate = props.payload.period === estimatePeriod;
                  return (
                    <circle
                      key={`${c.country}-${props.index}`}
                      cx={props.cx}
                      cy={props.cy}
                      r={3}
                      fill={isEstimate ? "#fff" : LINE_COLORS[i % LINE_COLORS.length]}
                      stroke={LINE_COLORS[i % LINE_COLORS.length]}
                      strokeWidth={isEstimate ? 2 : 0}
                    />
                  );
                }}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {estimatePeriod && (
        <p className="mt-1 text-xs text-ink-muted-48">
          * {estimatePeriod}는 추정치(직전 추세 연장, 시장 컨센서스 아님)
        </p>
      )}
      {hasMisalignedAxis && (
        <p className="mt-1 text-xs text-ink-muted-48">
          * 일부 국가는 데이터 공급 지연으로 최신 구간이 다른 국가와 겹치지 않을 수 있습니다 (표의 &quot;기준월&quot; 참고)
        </p>
      )}

      <div className="mt-6 overflow-x-auto border-t border-hairline pt-4">
        <table className="w-full text-[14px]">
          <thead>
            <tr className="border-b border-hairline text-left text-ink-muted-48">
              <th className="py-2 pr-4 font-semibold">국가</th>
              <th className="py-2 pr-4 font-semibold">현재값</th>
              <th className="py-2 pr-4 font-semibold">기준월</th>
            </tr>
          </thead>
          <tbody>
            {[...charted, ...tableOnly].map((c) => (
              <tr key={c.country} className="border-b border-divider-soft">
                <td className="py-2 pr-4">
                  {c.flag} {c.label}
                  {c.charted && <span className="ml-1 text-xs text-primary">(차트)</span>}
                </td>
                <td className="py-2 pr-4 font-semibold">
                  {c.current != null ? `${formatNumber(c.current)}${unit}` : "-"}
                </td>
                <td className="py-2 pr-4 text-ink-muted-48">{c.currentPeriod ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
