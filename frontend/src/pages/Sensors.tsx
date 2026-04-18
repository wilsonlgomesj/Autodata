import { useQuery } from "@apollo/client";
import { Link } from "react-router-dom";
import { useState } from "react";
import { SENSORS } from "@/api/queries";
import { useSite } from "@/components/SiteContext";

const SENSOR_TYPES = [
  "",
  "piezometer_vw",
  "inclinometer_ipi_mems",
  "rain_gauge_tipping",
  "gnss_rover",
  "flow_meter_weir",
  "extensometer_magnetic",
  "seismograph_mems",
];

export function Sensors() {
  const { site } = useSite();
  const [type, setType] = useState("");
  const [structure, setStructure] = useState<string>("");

  const { data, loading } = useQuery(SENSORS, {
    variables: { site, type: type || null, structure: structure || null },
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-slate-900">Sensores</h1>

      <div className="card flex gap-4 items-end">
        <div>
          <label className="label">Tipo</label>
          <select
            className="input"
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            {SENSOR_TYPES.map((t) => (
              <option key={t} value={t}>
                {t || "todos os tipos"}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Estrutura</label>
          <input
            className="input w-64"
            value={structure}
            onChange={(e) => setStructure(e.target.value)}
            placeholder="filtrar por structure_id"
          />
        </div>
      </div>

      <div className="card">
        {loading && <div className="text-slate-500 text-sm">carregando...</div>}
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-2">Sensor</th>
              <th>Tipo</th>
              <th>Estrutura</th>
              <th>Seção</th>
              <th>RTU</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(data?.sensors ?? []).map((s: any) => (
              <tr key={s.sensorId} className="hover:bg-slate-50">
                <td className="py-2">
                  <div className="font-medium text-slate-900">{s.displayName}</div>
                  <div className="text-xs text-slate-500">{s.sensorId}</div>
                </td>
                <td className="text-slate-700">{s.sensorType}</td>
                <td className="text-slate-700">{s.structureId}</td>
                <td className="text-slate-700">{s.sectionId}</td>
                <td className="text-slate-700">{s.deviceId}</td>
                <td>
                  {s.active ? (
                    <span className="badge bg-emerald-100 text-emerald-800">
                      ativo
                    </span>
                  ) : (
                    <span className="badge bg-slate-100 text-slate-700">
                      desativado
                    </span>
                  )}
                </td>
                <td className="text-right">
                  <Link
                    to={`/sensors/${s.sensorId}`}
                    className="text-slate-500 hover:text-slate-900 text-xs"
                  >
                    detalhes →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
