import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format } from "date-fns";

export interface TimePoint {
  bucket: string;
  vMin: number | null;
  vMax: number | null;
  vAvg: number | null;
}

export interface Thresholds {
  atencao?: number | null;
  alerta?: number | null;
  emergenciaN1?: number | null;
  emergenciaN2?: number | null;
}

interface Props {
  data: TimePoint[];
  thresholds?: Thresholds;
  unit?: string;
}

export function TimeseriesChart({ data, thresholds, unit }: Props) {
  if (data.length === 0) {
    return (
      <div className="text-slate-500 text-sm">
        sem dados na janela selecionada
      </div>
    );
  }
  const rows = data.map((d) => ({ ...d, t: new Date(d.bucket).getTime() }));

  return (
    <div className="h-72">
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="t"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(v) => format(new Date(v), "dd/MM HH:mm")}
            minTickGap={40}
            stroke="#94a3b8"
            fontSize={11}
          />
          <YAxis
            stroke="#94a3b8"
            fontSize={11}
            tickFormatter={(v) => (unit ? `${v}${unit}` : String(v))}
          />
          <Tooltip
            labelFormatter={(v) => format(new Date(v as number), "dd/MM/yyyy HH:mm")}
            formatter={(v: any) =>
              typeof v === "number" ? v.toFixed(2) + (unit ?? "") : v
            }
          />
          <Line
            type="monotone"
            dataKey="vAvg"
            stroke="#0f172a"
            dot={false}
            strokeWidth={2}
            name="média"
          />
          <Line
            type="monotone"
            dataKey="vMin"
            stroke="#94a3b8"
            strokeDasharray="4 4"
            dot={false}
            name="mín"
          />
          <Line
            type="monotone"
            dataKey="vMax"
            stroke="#94a3b8"
            strokeDasharray="4 4"
            dot={false}
            name="máx"
          />
          {thresholds?.atencao != null && (
            <ReferenceLine y={thresholds.atencao} stroke="#3b82f6" label="Atenção" />
          )}
          {thresholds?.alerta != null && (
            <ReferenceLine y={thresholds.alerta} stroke="#eab308" label="Alerta" />
          )}
          {thresholds?.emergenciaN1 != null && (
            <ReferenceLine y={thresholds.emergenciaN1} stroke="#f97316" label="Emer. N1" />
          )}
          {thresholds?.emergenciaN2 != null && (
            <ReferenceLine y={thresholds.emergenciaN2} stroke="#ef4444" label="Emer. N2" />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
