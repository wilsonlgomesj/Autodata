import { DEMO_MODE } from "@/api/client";

export function DemoBanner() {
  if (!DEMO_MODE) return null;
  return (
    <div className="bg-amber-500 text-amber-950 text-sm">
      <div className="max-w-7xl mx-auto px-4 py-1.5 flex items-center gap-2">
        <span className="font-semibold">DEMO offline</span>
        <span className="text-amber-900/90">
          · dados fictícios · nenhuma chamada de rede · mutações refletem apenas
          na sessão atual
        </span>
      </div>
    </div>
  );
}
