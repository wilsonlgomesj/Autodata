import { useQuery } from "@apollo/client";
import { useParams, Link } from "react-router-dom";
import { useMemo, useState } from "react";
import { LATEST, SENSORS, TIMESERIES } from "@/api/queries";
import { TimeseriesChart } from "@/components/TimeseriesChart";
import { useSite } from "@/components/SiteContext";

const WINDOWS = [
  { label: "Últimas 6h",  hours: 6,   res: "raw" },
  { label: "Últimas 24h", hours: 24,  res: "1min" },
  { label: "Últimos 7d",  hours: 168, res: "1h" },
  { label: "Últimos 30d", hours: 720, res: "1h" },
];

export function SensorDetail() {
  const { sensorId = "" } = useParams();
  const { site } = useSite();
  const [windowIdx, setWindowIdx] = useState(1);
  const [metric, setMetric] = useState("");

  const sensors = useQuery(SENSORS, { variables: { site } });
  const sensor = (sensors.data?.sensors ?? []).find(
    (s: any) => s.sensorId === sensorId,
  );

  const latest = useQuery(LATEST, {
    variables: { site, sensor: sensorId },
    pollInterval: 10_000,
  });

  const chosenMetric = metric || (latest.data?.latestMeasurements?.[0]?.metric ?? "");

  const { tFrom, tTo } = useMemo(() => {
    const now = new Date();
    const from = new Date(now.getTime() - WINDOWS[windowIdx].hours * 3600_000);
    return { tFrom: from.toISOString(), tTo: now.toISOString() };
  }, [windowIdx]);

  const ts = useQuery(TIMESERIES, {
    variables: {
      site,
      sensor: sensorId,
      metric: chosenMetric,
      tFrom,
      tTo,
      resolution: WINDOWS[windowIdx].res,
    },
    skip: !chosenMetric,
    pollInterval: 15_000,
  });

  return (
    <div className="space-y-4">
      <div>
        <Link to="/sensors" className="text-xs text-slate-500 hover:text-slate-900">
          ← sensores
        </Link>
        <h1 className="text-2xl font-semibold text-slate-900">
          {sensor?.displayName ?? sensorId}
        </h1>
        <div className="text-sm text-slate-500">
          {sensor?.sensorType} · {sensor?.structureId} · {sensor?.sectionId}
        </div>
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div className="flex gap-2">
            {WINDOWS.map((w, i) => (
              <button
                key={w.label}
                className={
                  i === windowIdx ? "btn-primary" : "btn-ghost"
                }
                onClick={() => setWindowIdx(i)}
              >
                {w.label}
              </button>
            ))}
          </div>
          <div>
            <label className="label !mb-0 mr-2 inline-block">Métrica</label>
            <select
              className="input w-48 inline-block"
              value={chosenMetric}
              onChange={(e) => setMetric(e.target.value)}
            >
              {(latest.data?.latestMeasurements ?? []).map((m: any) => (
                <option key={m.metric} value={m.metric}>
                  {m.metric}
                </option>
              ))}
            </select>
          </div>
        </div>
        <TimeseriesChart data={ts.data?.timeseries ?? []} />
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold mb-3">Últimas leituras</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-2">Métrica</th>
              <th>Valor</th>
              <th>Qualidade</th>
              <th>Flags</th>
              <th>Amostragem</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(latest.data?.latestMeasurements ?? []).map((m: any) => (
              <tr key={m.metric}>
                <td className="py-2 font-medium">{m.metric}</td>
                <td>{m.value != null ? m.value.toFixed(3) : "—"}</td>
                <td>
                  <span
                    className={
                      "badge " +
                      (m.quality === "GOOD"
                        ? "bg-emerald-100 text-emerald-800"
                        : m.quality === "SUSPECT"
                        ? "bg-yellow-100 text-yellow-900"
                        : "bg-red-100 text-red-900")
                    }
                  >
                    {m.quality}
                  </span>
                </td>
                <td className="text-xs text-slate-500">
                  {(m.flags ?? []).join(", ") || "—"}
                </td>
                <td className="text-slate-500">
                  {new Date(m.tSample).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
