import { useMutation } from "@apollo/client";
import { useState } from "react";
import { ISSUE_COMMAND } from "@/api/mutations";
import { useSite } from "@/components/SiteContext";
import { useAuth } from "@/auth/AuthContext";

const ACTIONS = [
  { value: "set_sampling_mode", label: "Mudar modo de amostragem",
    params: { mode: "ATENCAO" } },
  { value: "reboot", label: "Reiniciar RTU", params: {} },
  { value: "calibrate", label: "Disparar calibração", params: { channel: 1 } },
  { value: "firmware_update", label: "Atualização de firmware",
    params: { url: "https://artifacts.example.com/rtu-fw-2.5.0.bin" } },
  { value: "request_snapshot", label: "Solicitar snapshot",
    params: { duration_s: 60 } },
  { value: "enable_maintenance", label: "Entrar em modo manutenção", params: {} },
  { value: "disable_maintenance", label: "Sair do modo manutenção", params: {} },
];

export function Commands() {
  const { site } = useSite();
  const { identity, hasRole } = useAuth();

  const [gateway, setGateway] = useState("gw-bx-001");
  const [device, setDevice] = useState("rtu-bx-c1");
  const [actionIdx, setActionIdx] = useState(0);
  const [paramsJson, setParamsJson] = useState(
    JSON.stringify(ACTIONS[0].params, null, 2),
  );
  const [ttl, setTtl] = useState(600);

  const [issue, state] = useMutation(ISSUE_COMMAND);

  const canIssue = identity.mfa && hasRole("operator");

  function applyAction(i: number) {
    setActionIdx(i);
    setParamsJson(JSON.stringify(ACTIONS[i].params, null, 2));
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-slate-900">Comandos</h1>
      <p className="text-sm text-slate-500">
        Comandos são enviados via MQTT QoS 1 para o RTU alvo. Todas as ações
        são auditadas com <code>correlation_id</code>. Requer <b>MFA</b> e papel
        <b> operator</b>.
      </p>

      <div className="card space-y-4 max-w-2xl">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Gateway</label>
            <input
              className="input"
              value={gateway}
              onChange={(e) => setGateway(e.target.value)}
            />
          </div>
          <div>
            <label className="label">Device (RTU)</label>
            <input
              className="input"
              value={device}
              onChange={(e) => setDevice(e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="label">Ação</label>
          <select
            className="input"
            value={actionIdx}
            onChange={(e) => applyAction(Number(e.target.value))}
          >
            {ACTIONS.map((a, i) => (
              <option key={a.value} value={i}>
                {a.label} ({a.value})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="label">Parâmetros (JSON)</label>
          <textarea
            className="input font-mono text-xs min-h-32"
            value={paramsJson}
            onChange={(e) => setParamsJson(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">TTL (segundos)</label>
            <input
              type="number"
              min={30}
              max={86400}
              className="input"
              value={ttl}
              onChange={(e) => setTtl(Number(e.target.value))}
            />
          </div>
        </div>

        {state.data?.issueCommand && (
          <div
            className={
              "text-sm px-3 py-2 rounded " +
              (state.data.issueCommand.ok
                ? "bg-emerald-50 text-emerald-900"
                : "bg-red-50 text-red-900")
            }
          >
            {state.data.issueCommand.message}
            {state.data.issueCommand.correlationId && (
              <div className="text-xs text-slate-500 mt-1">
                correlation_id: {state.data.issueCommand.correlationId}
              </div>
            )}
          </div>
        )}
        {state.error && (
          <div className="text-sm px-3 py-2 rounded bg-red-50 text-red-900">
            {state.error.message}
          </div>
        )}

        <div className="flex items-center justify-between">
          <div className="text-xs text-slate-500">
            {canIssue
              ? "Sessão válida para emitir comandos."
              : "Sua sessão não possui MFA ou papel operator."}
          </div>
          <button
            className="btn-primary"
            disabled={!canIssue || state.loading}
            onClick={() =>
              issue({
                variables: {
                  input: {
                    siteId: site,
                    gateway,
                    device: device || null,
                    action: ACTIONS[actionIdx].value,
                    paramsJson,
                    ttlS: ttl,
                  },
                },
              })
            }
          >
            {state.loading ? "enviando..." : "emitir comando"}
          </button>
        </div>
      </div>
    </div>
  );
}
