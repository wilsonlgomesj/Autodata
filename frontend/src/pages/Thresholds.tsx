import { useMutation, useQuery } from "@apollo/client";
import { useState } from "react";
import { SENSORS } from "@/api/queries";
import { UPDATE_THRESHOLD } from "@/api/mutations";
import { useSite } from "@/components/SiteContext";
import { useAuth } from "@/auth/AuthContext";

const METRIC_BY_TYPE: Record<string, string> = {
  piezometer_vw: "pressure_kpa",
  inclinometer_ipi_mems: "tilt_x_deg",
  rain_gauge_tipping: "rainfall_mm",
  flow_meter_weir: "flow_rate_ls",
};

export function Thresholds() {
  const { site } = useSite();
  const { identity, hasRole } = useAuth();

  const { data } = useQuery(SENSORS, { variables: { site } });

  const [sensor, setSensor] = useState("");
  const [metric, setMetric] = useState("");
  const [atencao, setAtencao] = useState(380);
  const [alerta, setAlerta] = useState(420);
  const [em1, setEm1] = useState(460);
  const [em2, setEm2] = useState(500);
  const [direction, setDirection] = useState("above");
  const [hysteresis, setHysteresis] = useState(5);
  const [approvalRef, setApprovalRef] = useState("");

  const [submit, state] = useMutation(UPDATE_THRESHOLD);

  const canEdit = identity.mfa && hasRole("engineer");

  function onSelectSensor(id: string) {
    setSensor(id);
    const s = (data?.sensors ?? []).find((x: any) => x.sensorId === id);
    if (s) setMetric(METRIC_BY_TYPE[s.sensorType] ?? "pressure_kpa");
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-slate-900">Thresholds</h1>
      <p className="text-sm text-slate-500">
        Edição de limites do PSB. Toda alteração é <b>time-versioned</b>: a
        versão atual é fechada com <code>effective_to=now()</code> e uma nova
        entrada é inserida, preservando o histórico. Requer <b>MFA</b> e papel
        <b> engineer</b>.
      </p>

      <div className="card space-y-4 max-w-2xl">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Sensor</label>
            <select
              className="input"
              value={sensor}
              onChange={(e) => onSelectSensor(e.target.value)}
            >
              <option value="">selecione...</option>
              {(data?.sensors ?? []).map((s: any) => (
                <option key={s.sensorId} value={s.sensorId}>
                  {s.displayName} ({s.sensorId})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Métrica</label>
            <input
              className="input"
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-cols-4 gap-4">
          <Field label="Atenção" v={atencao} set={setAtencao} />
          <Field label="Alerta" v={alerta} set={setAlerta} />
          <Field label="Emer. N1" v={em1} set={setEm1} />
          <Field label="Emer. N2" v={em2} set={setEm2} />
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="label">Direção</label>
            <select
              className="input"
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
            >
              <option value="above">above</option>
              <option value="below">below</option>
              <option value="absolute">absolute</option>
            </select>
          </div>
          <div>
            <label className="label">Histerese (%)</label>
            <input
              type="number"
              min={0}
              max={50}
              step={0.5}
              className="input"
              value={hysteresis}
              onChange={(e) => setHysteresis(Number(e.target.value))}
            />
          </div>
          <div>
            <label className="label">Aprovação (ref)</label>
            <input
              className="input"
              value={approvalRef}
              onChange={(e) => setApprovalRef(e.target.value)}
              placeholder="PSB-BX-REV4"
            />
          </div>
        </div>

        {state.data?.updateThreshold && (
          <div
            className={
              "text-sm px-3 py-2 rounded " +
              (state.data.updateThreshold.ok
                ? "bg-emerald-50 text-emerald-900"
                : "bg-red-50 text-red-900")
            }
          >
            {state.data.updateThreshold.message}
          </div>
        )}
        {state.error && (
          <div className="text-sm px-3 py-2 rounded bg-red-50 text-red-900">
            {state.error.message}
          </div>
        )}

        <div className="flex items-center justify-between">
          <div className="text-xs text-slate-500">
            {canEdit
              ? "Sessão válida para editar thresholds."
              : "Sua sessão não possui MFA ou papel engineer."}
          </div>
          <button
            className="btn-primary"
            disabled={!canEdit || !sensor || !metric || state.loading}
            onClick={() =>
              submit({
                variables: {
                  input: {
                    siteId: site,
                    sensorId: sensor,
                    metric,
                    levels: {
                      atencao,
                      alerta,
                      emergenciaN1: em1,
                      emergenciaN2: em2,
                    },
                    direction,
                    hysteresisPct: hysteresis,
                    approvalRef,
                  },
                },
              })
            }
          >
            {state.loading ? "enviando..." : "salvar threshold"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  v,
  set,
}: {
  label: string;
  v: number;
  set: (n: number) => void;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        type="number"
        className="input"
        value={v}
        onChange={(e) => set(Number(e.target.value))}
      />
    </div>
  );
}
