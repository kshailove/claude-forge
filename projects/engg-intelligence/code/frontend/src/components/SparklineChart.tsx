import {
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  YAxis,
} from "recharts";

interface SparklineChartProps {
  data: number[];
  color?: string;
  height?: number;
}

export function SparklineChart({
  data,
  color = "#6366f1",
  height = 40,
}: SparklineChartProps) {
  if (!data || data.length === 0) {
    return (
      <div
        style={{ height }}
        className="flex items-center justify-center text-xs text-muted-foreground"
      >
        No data
      </div>
    );
  }

  const chartData = data.map((value, i) => ({ day: i + 1, value }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData}>
        <YAxis domain={[0, 100]} hide />
        <Tooltip
          formatter={(v: number) => [`${v.toFixed(0)}`, "Score"]}
          labelFormatter={(label: number) => `Day ${label}`}
          contentStyle={{
            fontSize: "11px",
            padding: "4px 8px",
            borderRadius: "4px",
          }}
        />
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 3 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
