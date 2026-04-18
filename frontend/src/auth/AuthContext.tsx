import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { DevIdentity, loadIdentity, saveIdentity } from "@/api/client";

interface AuthValue {
  identity: DevIdentity;
  setIdentity: (id: DevIdentity) => void;
  hasRole: (role: string) => boolean;
}

const Ctx = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentityState] = useState<DevIdentity>(loadIdentity);

  const setIdentity = useCallback((id: DevIdentity) => {
    saveIdentity(id);
    setIdentityState(id);
  }, []);

  const hasRole = useCallback(
    (role: string) => identity.roles.includes(role),
    [identity.roles],
  );

  const value = useMemo(
    () => ({ identity, setIdentity, hasRole }),
    [identity, setIdentity, hasRole],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be inside AuthProvider");
  return v;
}
