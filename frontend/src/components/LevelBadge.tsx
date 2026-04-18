interface Props {
  level: string;
}
const COLORS: Record<string, string> = {
  NORMAL: "bg-emerald-100 text-emerald-800",
  ATENCAO: "bg-blue-100 text-blue-800",
  ALERTA: "bg-yellow-100 text-yellow-900",
  EMERGENCIA_N1: "bg-orange-100 text-orange-900",
  EMERGENCIA_N2: "bg-red-100 text-red-900",
};

export function LevelBadge({ level }: Props) {
  const cls = COLORS[level] ?? "bg-slate-100 text-slate-800";
  return <span className={`badge ${cls}`}>{level}</span>;
}
