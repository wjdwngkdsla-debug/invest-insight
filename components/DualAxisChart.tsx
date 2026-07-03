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
import type { DualAxisSeries } from "@/lib/types";
import { formatNumber } from "@/lib/format";

export function DualAxisChart({ series }: { series: DualAxisSeries }) {
  return (
    <div className="rounded-[18px] border border-hairline bg-canvas p-6">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-[17px] font-semibold text-ink">{series.title}</h3>
        {series.correlation !== undefined && (
          <span className="rounded-full bg-surface-pearl px-3 py-1 text-xs font-semibold text-ink-muted-80">
            상관계수 r = {series.correlation}
          </span>
        )}
      </div>

      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series.data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="period" tick={{ fontSize: 12 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 12 }} tickFormatter={formatNumber} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} tickFormatter={formatNumber} />
            <Tooltip
              labelFormatter={(label) => `기간: ${label}`}
              formatter={(value) => (typeof value === "number" ? formatNumber(value) : value)}
            />
            <Legend />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="left"
              name={series.leftLabel}
              stroke={series.leftColor ?? "#0066cc"}
              strokeWidth={2}
              dot={false}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="right"
              name={series.rightLabel}
              stroke={series.rightColor ?? "#2997ff"}
              strokeWidth={2}
              dot={false}
            />
            {series.right2Label && (
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="right2"
                name={series.right2Label}
                stroke={series.right2Color ?? "#16a34a"}
                strokeWidth={2}
                dot={false}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
