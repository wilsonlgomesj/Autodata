import { useMutation, useQuery } from "@apollo/client";
import { useState } from "react";
import { format } from "date-fns";
import { ACK_ALERT } from "@/api/mutations";
import { ALERTS } from "@/api/queries";
import { LevelBadge } from "@/components/LevelBadge";
import { useSite } from "@/components/SiteContext";
import { useAuth } from "@/auth/AuthContext";

const LEVELS = ["", "ATENCAO", "ALERTA", "EMERGENCIA_N1", "EMERGENCIA_N2"];

export function Alerts() {
  const { site } = useSite();
  const { identity } = useAuth();
  const [level, setLevel] = useState("");
  const [target, setTarget] = useState<string | null>(null);
  const [comment, setComment] = useState("");

  const { data, loading, refetch } = useQuery(ALERTS, {
    variables: { site, level: level || null, limit: 200 },
    pollInterval: 10_000,
  });

  const [ack, ackState] = useMutation(ACK_ALERT, {
    onCompleted: () => {
      setTarget(null);
      setComment("");
      refetch();
    },
  });

  const canAck = identity.mfa;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-slate-900">Alertas</h1>

      <div className="card flex items-end gap-4">
        <div>
          <label className="label">Nível</label>
          <select
            className="input"
            value={level}
            onChange={(e) => setLevel(e.target.value)}
          >
            {LEVELS.map((l) => (
              <option key={l} value={l}>
                {l || "todos"}
              </option>
            ))}
          </select>
        </div>
        <button className="btn-ghost" onClick={() => refetch()}>
          atualizar
        </button>
      </div>

      <div className="card">
        {loading && <div className="text-slate-500 text-sm">carregando...</div>}
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-2">Disparo</th>
              <th>Nível</th>
              <th>Regra</th>
              <th>Sensores</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(data?.alerts ?? []).map((a: any) => (
              <tr key={a.eventId}>
                <td className="py-2 text-slate-600">
                  {format(new Date(a.tTriggered), "dd/MM/yyyy HH:mm:ss")}
                </td>
                <td><LevelBadge level={a.level} /></td>
                <td className="text-slate-800">
                  {a.ruleId}
                  <span className="text-xs text-slate-400 ml-1">{a.ruleVersion}</span>
                </td>
                <td className="text-slate-600">{a.sensors.join(", ")}</td>
                <td>
                  {a.tResolved ? (
                    <span className="badge bg-slate-100 text-slate-700">resolvido</span>
                  ) : (
                    <span className="badge bg-orange-100 text-orange-900">aberto</span>
                  )}
                </td>
                <td className="text-right">
                  {!a.tResolved && (
                    <button
                      className="btn-ghost"
                      onClick={() => setTarget(a.eventId)}
                    >
                      reconhecer
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {target && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onClick={() => setTarget(null)}
        >
          <div
            className="bg-white rounded-lg p-6 w-[480px]"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold mb-2">Reconhecer alerta</h2>
            <p className="text-sm text-slate-500 mb-3">
              O reconhecimento exige autenticação MFA. Sua sessão atual
              {canAck ? " carrega claim MFA." : " não carrega claim MFA — habilite o toggle no topo."}
            </p>
            <label className="label">Comentário</label>
            <textarea
              className="input min-h-24"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="ex: vistoriado em campo às 14h30, sem indícios adicionais"
            />
            {ackState.error && (
              <div className="text-red-600 text-sm mt-2">
                {ackState.error.message}
              </div>
            )}
            <div className="flex justify-end gap-2 mt-4">
              <button
                className="btn-ghost"
                onClick={() => setTarget(null)}
                disabled={ackState.loading}
              >
                cancelar
              </button>
              <button
                className="btn-primary"
                disabled={!canAck || !comment || ackState.loading}
                onClick={() =>
                  ack({
                    variables: { id: target, comment },
                  })
                }
              >
                {ackState.loading ? "enviando..." : "confirmar reconhecimento"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
