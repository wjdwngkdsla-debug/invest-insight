"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FxExportSeries, FxExportPoint } from "@/lib/fxExport";
import { formatNumber } from "@/lib/format";

const FX_LINES = [
  { pctKey: "usdPct", rateKey: "usdKrw", name: "원/달러", color: "#0066cc" },
  { pctKey: "jpyPct", rateKey: "jpyKrw", name: "원/100엔", color: "#2997ff" },
  { pctKey: "eurPct", rateKey: "eurKrw", name: "원/유로", color: "#9333ea" },
  { pctKey: "cnyPct", rateKey: "cnyKrw", name: "원/위안", color: "#ea580c" },
] as const;

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { dataKey: string; value: number; payload: FxExportPoint }[];
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload;

  return (
    <div className="rounded-lg border border-hairline bg-canvas p-3 text-xs shadow-sm">
      <p className="mb-2 font-semibold text-ink">기간: {label}</p>
      <p className="mb-2 text-ink-muted-80">전체 수출액: {formatNumber(point.exportAmount)}억 달러</p>
      {FX_LINES.map((line) => (
        <p key={line.pctKey} style={{ color: line.color }}>
          {line.name}: {formatNumber(point[line.rateKey])}원 ({point[line.pctKey] >= 0 ? "+" : ""}
          {point[line.pctKey]}%)
        </p>
      ))}
    </div>
  );
}

export function FxExportChart({ series }: { series: FxExportSeries }) {
  return (
    <div className="rounded-[18px] border border-hairline bg-canvas p-6">
      <h3 className="mb-1 text-[17px] font-semibold text-ink">{series.title}</h3>
      <p className="mb-4 text-xs text-ink-muted-48">
        환율은 영업일별 매매기준율의 월평균값 기준, 환율 라인은 구간 시작월 대비 등락률(%)이며 실제 환율은 마우스를 올리면 표시됩니다.
      </p>

      <div className="h-80 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series.data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="period" tick={{ fontSize: 12 }} />
            <YAxis
              yAxisId="left"
              tick={{ fontSize: 12 }}
              tickFormatter={formatNumber}
              label={{ value: "수출액(억 달러)", angle: -90, position: "insideLeft", fontSize: 11 }}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fontSize: 12 }}
              tickFormatter={(v) => `${v}%`}
              label={{ value: "환율 등락률(%)", angle: 90, position: "insideRight", fontSize: 11 }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="exportAmount"
              name="전체 수출액(억 달러)"
              stroke="#1d1d1f"
              strokeWidth={3}
              dot={false}
            />
            {FX_LINES.map((line) => (
              <Line
                key={line.pctKey}
                yAxisId="right"
                type="monotone"
                dataKey={line.pctKey}
                name={`${line.name} 등락률`}
                stroke={line.color}
                strokeWidth={1.5}
                dot={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
