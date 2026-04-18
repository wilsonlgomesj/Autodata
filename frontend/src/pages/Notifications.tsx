import { useQuery } from "@apollo/client";
import { format } from "date-fns";
import { NOTIFICATIONS } from "@/api/queries";
import { LevelBadge } from "@/components/LevelBadge";
import { useSite } from "@/components/SiteContext";

const CHANNEL_COLORS: Record<string, string> = {
  email: "bg-blue-100 text-blue-900",
  sms: "bg-purple-100 text-purple-900",
  voice: "bg-red-100 text-red-900",
  webhook: "bg-emerald-100 text-emerald-900",
  teams: "bg-indigo-100 text-indigo-900",
  slack: "bg-pink-100 text-pink-900",
  push: "bg-orange-100 text-orange-900",
  siren: "bg-red-200 text-red-900",
};

export function Notifications() {
  const { site } = useSite();
  const { data, loading, refetch } = useQuery(NOTIFICATIONS, {
    variables: { site, limit: 200 },
    pollInterval: 10_000,
  });

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Notificações</h1>
          <p className="text-sm text-slate-500">
            Log append-only de dispatches com idempotência por{" "}
            <code>(alert_msg_id, route_id, channel)</code>.
          </p>
        </div>
        <button className="btn-ghost" onClick={() => refetch()}>
          atualizar
        </button>
      </header>

      <div className="card">
        {loading && <div className="text-slate-500 text-sm">carregando...</div>}
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-2">Hora</th>
              <th>Nível</th>
              <th>Canal</th>
              <th>Destino</th>
              <th>Status</th>
              <th>Latência</th>
              <th>Detalhes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(data?.notifications ?? []).map((n: any) => (
              <tr key={n.dispatchId}>
                <td className="py-2 text-slate-600">
                  {format(new Date(n.tAttempted), "dd/MM/yyyy HH:mm:ss")}
                </td>
                <td><LevelBadge level={n.level} /></td>
                <td>
                  <span
                    className={
                      "badge " +
                      (CHANNEL_COLORS[n.channel] ??
                        "bg-slate-100 text-slate-800")
                    }
                  >
                    {n.channel}
                  </span>
                </td>
                <td className="text-slate-700 font-mono text-xs">{n.target}</td>
                <td>
                  <span
                    className={
                      "badge " +
                      (n.status === "sent"
                        ? "bg-emerald-100 text-emerald-900"
                        : n.status === "failed"
                        ? "bg-red-100 text-red-900"
                        : "bg-slate-100 text-slate-800")
                    }
                  >
                    {n.status}
                  </span>
                </td>
                <td className="text-slate-600">
                  {n.latencyMs != null ? `${n.latencyMs} ms` : "—"}
                </td>
                <td className="text-xs text-slate-500">
                  {n.error || <span className="text-slate-300">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && (data?.notifications ?? []).length === 0 && (
          <div className="text-slate-500 text-sm py-4 text-center">
            sem dispatches na janela
          </div>
        )}
      </div>
    </div>
  );
}
