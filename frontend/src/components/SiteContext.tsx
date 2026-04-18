import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

interface SiteCtxValue {
  site: string;
  setSite: (s: string) => void;
}
const Ctx = createContext<SiteCtxValue | null>(null);

const LS_KEY = "autodata.site";
const DEFAULT_SITE = "mineradora-x-barragem-norte";

export function SiteProvider({ children }: { children: ReactNode }) {
  const [site, setSiteState] = useState<string>(
    () => localStorage.getItem(LS_KEY) ?? DEFAULT_SITE,
  );
  const setSite = (s: string) => {
    localStorage.setItem(LS_KEY, s);
    setSiteState(s);
  };
  const value = useMemo(() => ({ site, setSite }), [site]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSite() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSite must be inside SiteProvider");
  return v;
}
