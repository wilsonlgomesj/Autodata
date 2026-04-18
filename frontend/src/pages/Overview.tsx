import { useQuery } from "@apollo/client";
import { Link } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import { ptBR } from "date-fns/locale";
import { ALERTS, SENSORS, STRUCTURES } from "@/api/queries";
import { LevelBadge } from "@/components/LevelBadge";
import { SensorMap } from "@/components/SensorMap";
import { useSite } from "@/components/SiteContext";

export function Overview() {
  const { site } = useSite();

  const structures = useQuery(STRUCTURES, { variables: { site } });
  const sensors = useQuery(SENSORS, { variables: { site } });
  const alerts = useQuery(ALERTS, {
    variables: { site, limit: 10 },
    pollInterval: 10_000,
  });

  const activeAlerts = (alerts.data?.alerts ?? []).filter(
    (a: any) => a.tResolved == null,
  );

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            Visão Geral
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Status em tempo real da instrumentação e alertas ativos
          </p>
        </div>
      </header>

      <section className="grid grid-cols-4 gap-4">
        <Kpi
          title="Estruturas"
          value={structures.data?.structures?.length ?? "—"}
          hint="monitoradas"
        />
        <Kpi
          title="Sensores ativos"
          value={
            (sensors.data?.sensors ?? []).filter((s: any) => s.active).length ||
            "—"
          }
          hint="ligados"
        />
        <Kpi
          title="Alertas ativos"
          value={activeAlerts.length}
          hint={activeAlerts.length > 0 ? "requerem atenção" : "tudo sob controle"}
          accent={activeAlerts.length > 0 ? "red" : "green"}
        />
        <Kpi
          title="Alertas 24h"
          value={alerts.data?.alerts?.length ?? 0}
          hint="no período"
        />
      </section>

      <section className="card">
        <h2 className="text-lg font-semibold text-slate-900 mb-3">
          Mapa da instrumentação
        </h2>
        <SensorMap />
      </section>

      <section className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-slate-900">
            Alertas recentes
          </h2>
          <Link to="/alerts" className="text-sm text-slate-500 hover:text-slate-900">
            ver todos →
          </Link>
        </div>
        {alerts.loading && <div className="text-slate-500 text-sm">carregando...</div>}
        {!alerts.loading && (alerts.data?.alerts ?? []).length === 0 && (
          <div className="text-slate-500 text-sm">nenhum alerta no momento</div>
        )}
        <div className="divide-y divide-slate-100">
          {(alerts.data?.alerts ?? []).slice(0, 6).map((a: any) => (
            <div key={a.eventId} className="py-2 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <LevelBadge level={a.level} />
                <div>
                  <div className="text-sm font-medium text-slate-800">
                    {a.ruleId}
                  </div>
                  <div className="text-xs text-slate-500">
                    {a.sensors.join(", ")} ·{" "}
                    {formatDistanceToNow(new Date(a.tTriggered), {
                      addSuffix: true,
                      locale: ptBR,
                    })}
                  </div>
                </div>
              </div>
              <Link
                to="/alerts"
                className="text-xs text-slate-500 hover:text-slate-900"
              >
                detalhes
              </Link>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Kpi({
  title,
  value,
  hint,
  accent,
}: {
  title: string;
  value: string | number;
  hint?: string;
  accent?: "red" | "green";
}) {
  const color =
    accent === "red"
      ? "text-red-600"
      : accent === "green"
      ? "text-emerald-600"
      : "text-slate-900";
  return (
    <div className="card">
      <div className="label">{title}</div>
      <div className={`text-3xl font-semibold ${color}`}>{value}</div>
      {hint && <div className="text-xs text-slate-500 mt-1">{hint}</div>}
    </div>
  );
}
