/**
 * ApolloLink that returns canned responses for the offline demo mode.
 * Dispatches on operation.operationName. Keeps a 50ms artificial latency
 * so loading states render briefly.
 */

import { ApolloLink, Observable, type FetchResult } from "@apollo/client";
import {
  DEMO_ALERTS,
  DEMO_NOTIFICATIONS,
  DEMO_SENSORS,
  DEMO_SITES,
  DEMO_STRUCTURES,
  generateTimeseries,
  latestFor,
  sensorsGeoJson,
  siteBoundary,
  structuresGeoJson,
} from "./mocks";

type Vars = Record<string, unknown>;

/**
 * Local "state" mutated by mutations so the user sees their actions stick.
 * Example: acknowledging an alert updates that alert's ack fields.
 */
const state = {
  alerts: [...DEMO_ALERTS],
  ackCount: 0,
  thresholdUpdates: [] as Array<{ sensorId: string; metric: string }>,
  commandsIssued: [] as Array<{ action: string; target: string }>,
};

function ok<T>(data: T): FetchResult {
  return { data: data as unknown as Record<string, unknown> };
}

function error(message: string): FetchResult {
  return {
    data: null as unknown as Record<string, unknown>,
    errors: [{ message, extensions: {}, path: [], nodes: [] } as any],
  };
}

const handlers: Record<string, (vars: Vars) => FetchResult> = {
  Sites: () => ok({ sites: DEMO_SITES }),

  Structures: () => ok({ structures: DEMO_STRUCTURES }),

  Sensors: (v) => {
    let rows = DEMO_SENSORS;
    if (v.type) rows = rows.filter((s) => s.sensorType === v.type);
    if (v.structure) rows = rows.filter((s) => s.structureId === v.structure);
    return ok({ sensors: rows });
  },

  Latest: (v) => ok({ latestMeasurements: latestFor(String(v.sensor)) }),

  Timeseries: (v) => {
    const tFrom = new Date(String(v.tFrom));
    const tTo = new Date(String(v.tTo));
    const res = String(v.resolution);
    const bucketMs =
      res === "raw" ? 30_000 : res === "1min" ? 60_000 : 3600_000;
    return ok({
      timeseries: generateTimeseries(
        String(v.sensor),
        String(v.metric),
        tFrom,
        tTo,
        bucketMs,
      ),
    });
  },

  Alerts: (v) => {
    let rows = state.alerts;
    if (v.level) rows = rows.filter((a) => a.level === v.level);
    const limit = typeof v.limit === "number" ? v.limit : 200;
    return ok({ alerts: rows.slice(0, limit) });
  },

  Notifications: (v) => {
    const limit = typeof v.limit === "number" ? v.limit : 200;
    return ok({ notifications: DEMO_NOTIFICATIONS.slice(0, limit) });
  },

  SensorsGeoJson: () =>
    ok({
      sensorsGeojson: sensorsGeoJson(),
      structuresGeojson: structuresGeoJson(),
      siteBoundary: siteBoundary(),
    }),

  // Mutations — simulate acceptance. They don't actually persist across
  // reloads, but they reflect for the current session so the user sees
  // meaningful feedback.
  AckAlert: (v) => {
    const id = String(v.id);
    const target = state.alerts.find((a) => a.eventId === id);
    if (!target) {
      return ok({
        acknowledgeAlert: {
          ok: false,
          message: "alert not found or already acknowledged",
          eventId: null,
          correlationId: null,
          __typename: "MutationResult",
        },
      });
    }
    target.tResolved = new Date().toISOString();
    state.ackCount++;
    return ok({
      acknowledgeAlert: {
        ok: true,
        message: "alert acknowledged (demo mode — no persistence)",
        eventId: id,
        correlationId: ulidish(),
        __typename: "MutationResult",
      },
    });
  },

  UpdateThreshold: (v) => {
    const input = (v.input as any) || {};
    const levels = input.levels || {};
    if (input.direction === "above") {
      const seq = [
        levels.atencao, levels.alerta, levels.emergenciaN1, levels.emergenciaN2,
      ].filter((x: unknown) => typeof x === "number");
      const sorted = [...seq].sort((a: number, b: number) => a - b);
      if (JSON.stringify(seq) !== JSON.stringify(sorted)) {
        return ok({
          updateThreshold: {
            ok: false,
            message:
              "levels must be monotonic-ascending for direction=above",
            correlationId: null,
            __typename: "MutationResult",
          },
        });
      }
    }
    state.thresholdUpdates.push({
      sensorId: input.sensorId,
      metric: input.metric,
    });
    return ok({
      updateThreshold: {
        ok: true,
        message:
          "threshold updated (demo mode — no persistence, just illustrative)",
        correlationId: ulidish(),
        __typename: "MutationResult",
      },
    });
  },

  IssueCommand: (v) => {
    const input = (v.input as any) || {};
    try {
      if (input.paramsJson) JSON.parse(input.paramsJson);
    } catch {
      return ok({
        issueCommand: {
          ok: false,
          message: "invalid params_json",
          correlationId: null,
          __typename: "MutationResult",
        },
      });
    }
    state.commandsIssued.push({
      action: input.action,
      target: `${input.gateway}/${input.device ?? ""}`,
    });
    return ok({
      issueCommand: {
        ok: true,
        message: `command queued (demo mode) — would publish to cmd/${input.siteId}/${input.gateway}`,
        correlationId: ulidish(),
        __typename: "MutationResult",
      },
    });
  },
};

function ulidish(): string {
  const alpha = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
  let s = "";
  for (let i = 0; i < 26; i++) s += alpha[Math.floor(Math.random() * 32)];
  return s;
}

export function buildMockLink(): ApolloLink {
  return new ApolloLink((operation) => {
    const name = operation.operationName ?? "";
    const handler = handlers[name];
    return new Observable<FetchResult>((obs) => {
      const timeout = setTimeout(() => {
        if (!handler) {
          obs.next(error(`no mock handler for operation ${name}`));
          obs.complete();
          return;
        }
        try {
          obs.next(handler(operation.variables ?? {}));
          obs.complete();
        } catch (e: any) {
          obs.next(error(`mock ${name} threw: ${e?.message ?? e}`));
          obs.complete();
        }
      }, 50);
      return () => clearTimeout(timeout);
    });
  });
}
