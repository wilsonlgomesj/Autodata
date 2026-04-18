import { useQuery } from "@apollo/client";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { SITES } from "@/api/queries";
import { useSite } from "./SiteContext";

interface Site {
  siteId: string;
  displayName: string;
  country: string;
}

const navItems = [
  { to: "/", label: "Visão geral", end: true },
  { to: "/sensors", label: "Sensores" },
  { to: "/alerts", label: "Alertas" },
  { to: "/thresholds", label: "Thresholds" },
  { to: "/commands", label: "Comandos" },
  { to: "/notifications", label: "Notificações" },
];

export function Layout() {
  const { identity, setIdentity } = useAuth();
  const { site, setSite } = useSite();
  const { data } = useQuery<{ sites: Site[] }>(SITES);

  return (
    <div className="h-full flex flex-col">
      <header className="bg-slate-900 text-slate-100 border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-4 py-2 flex items-center gap-6">
          <div className="font-semibold tracking-tight">
            <span className="text-emerald-400">Auto</span>data
            <span className="ml-2 text-xs text-slate-400">
              telemetria geotécnica
            </span>
          </div>
          <nav className="flex gap-1 text-sm">
            {navItems.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md transition ${
                    isActive
                      ? "bg-slate-700 text-white"
                      : "text-slate-300 hover:bg-slate-800"
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <label className="label text-slate-400 !mb-0 mr-1">Site</label>
            <select
              className="bg-slate-800 border border-slate-700 rounded-md px-2 py-1 text-slate-100"
              value={site}
              onChange={(e) => setSite(e.target.value)}
            >
              {(data?.sites ?? []).map((s) => (
                <option key={s.siteId} value={s.siteId}>
                  {s.displayName}
                </option>
              ))}
            </select>
            <div className="flex items-center gap-2 px-3 py-1 rounded-md bg-slate-800 border border-slate-700">
              <span className="text-slate-300">{identity.user}</span>
              <span
                className="text-[10px] font-semibold uppercase tracking-wide cursor-pointer"
                title="Alternar MFA (simula token com/sem claim MFA)"
                onClick={() =>
                  setIdentity({ ...identity, mfa: !identity.mfa })
                }
              >
                <span
                  className={
                    identity.mfa
                      ? "text-emerald-400"
                      : "text-red-400"
                  }
                >
                  MFA {identity.mfa ? "ON" : "OFF"}
                </span>
              </span>
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
