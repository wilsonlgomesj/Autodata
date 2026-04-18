import { ApolloClient, InMemoryCache, HttpLink, from } from "@apollo/client";
import { setContext } from "@apollo/client/link/context";
import { onError } from "@apollo/client/link/error";
import { buildMockLink } from "./mockLink";
import { sensorsGeoJson, siteBoundary, structuresGeoJson } from "./mocks";

export const DEMO_MODE =
  (import.meta.env.VITE_DEMO_MODE as string | undefined) === "true";

// API origin is configurable at build time; default to the dev stack.
export const API_ORIGIN =
  (import.meta.env.VITE_API_ORIGIN as string | undefined) ??
  "http://localhost:8080";

// Dev mode mirrors the backend's AUTH_DISABLED bypass. In dev we send
// X-Dev-User / X-Dev-Roles / X-Dev-Mfa headers that the backend trusts.
// In prod this slot is replaced with a real OIDC bearer token.
export interface DevIdentity {
  user: string;
  roles: string[];
  mfa: boolean;
  siteScope?: string[];
}

const LS_KEY = "autodata.identity";

export function loadIdentity(): DevIdentity {
  const raw = localStorage.getItem(LS_KEY);
  if (raw) {
    try {
      return JSON.parse(raw) as DevIdentity;
    } catch {
      // fall through to default
    }
  }
  return {
    user: "demo-operator",
    roles: ["operator", "engineer"],
    mfa: true,
  };
}

export function saveIdentity(id: DevIdentity): void {
  localStorage.setItem(LS_KEY, JSON.stringify(id));
}

const errorLink = onError(({ graphQLErrors, networkError }) => {
  if (graphQLErrors) {
    graphQLErrors.forEach((err) => console.warn("GraphQL error:", err.message));
  }
  if (networkError) console.warn("Network error:", networkError);
});

function transport() {
  // In demo mode we short-circuit all network I/O.
  if (DEMO_MODE) return buildMockLink();
  const httpLink = new HttpLink({
    uri: `${API_ORIGIN}/graphql`,
    credentials: "omit",
  });
  const authLink = setContext((_, { headers }) => {
    const id = loadIdentity();
    return {
      headers: {
        ...headers,
        "X-Dev-User": id.user,
        "X-Dev-Roles": id.roles.join(","),
        "X-Dev-Mfa": id.mfa ? "true" : "false",
      },
    };
  });
  return from([authLink, httpLink]);
}

export const apollo = new ApolloClient({
  link: from([errorLink, transport()]),
  cache: new InMemoryCache({
    typePolicies: {
      Site: { keyFields: ["siteId"] },
      Sensor: { keyFields: ["siteId", "sensorId"] },
      Structure: { keyFields: ["siteId", "structureId"] },
      AlertSummary: { keyFields: ["eventId"] },
    },
  }),
  defaultOptions: {
    watchQuery: { fetchPolicy: "cache-and-network" },
  },
});

// REST helper for GeoJSON endpoints.
// In demo mode returns mocks directly; otherwise goes to the real API.
export async function fetchJSON<T>(path: string): Promise<T> {
  if (DEMO_MODE) {
    if (path.endsWith("/sensors.geojson")) return sensorsGeoJson() as T;
    if (path.endsWith("/structures.geojson")) return structuresGeoJson() as T;
    if (path.endsWith("/site.geojson")) return siteBoundary() as T;
    throw new Error(`no demo mock for ${path}`);
  }

  const id = loadIdentity();
  const res = await fetch(`${API_ORIGIN}${path}`, {
    headers: {
      "X-Dev-User": id.user,
      "X-Dev-Roles": id.roles.join(","),
      "X-Dev-Mfa": id.mfa ? "true" : "false",
    },
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return (await res.json()) as T;
}
