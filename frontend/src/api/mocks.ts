/**
 * Offline demo data — returned by the mock Apollo link when
 * VITE_DEMO_MODE=true. All field names match the GraphQL schema's camelCase.
 *
 * The aim is a demo that feels alive: timeseries are generated from the
 * current wall-clock so charts stay fresh no matter when the page is
 * loaded, alerts include one active and a couple resolved, notifications
 * span multiple channels.
 */

// ---------------------------------------------------------------------------
// Static fixtures (structures, sensors, sites) — lifted from the SQL seed.
// ---------------------------------------------------------------------------

export const DEMO_SITE = {
  siteId: "mineradora-x-barragem-norte",
  displayName: "Complexo Norte — Barragem X",
  country: "BR",
  timezone: "America/Sao_Paulo",
  lat: -19.9167,
  lon: -43.9345,
};

export const DEMO_SITES = [DEMO_SITE];

export const DEMO_STRUCTURES = [
  {
    siteId: DEMO_SITE.siteId,
    structureId: "barragem-principal",
    kind: "earth_dam",
    displayName: "Barragem Principal",
    heightM: 45.0,
    crestLengthM: 600.0,
    riskClass: "B",
  },
];

type SensorRow = {
  siteId: string;
  sensorId: string;
  sensorType: string;
  structureId: string;
  sectionId: string;
  deviceId: string;
  displayName: string;
  installedOn: string;
  active: boolean;
  lat: number;
  lon: number;
};

const SECTION_CENTER_LAT = -19.9167;
const SECTION_CENTER_LON = -43.9340;

function mk(
  sensorId: string,
  sensorType: string,
  sectionId: string,
  deviceId: string,
  displayName: string,
  dLat: number,
  dLon: number,
): SensorRow {
  return {
    siteId: DEMO_SITE.siteId,
    sensorId,
    sensorType,
    structureId: "barragem-principal",
    sectionId,
    deviceId,
    displayName,
    installedOn: "2024-06-10T00:00:00Z",
    active: true,
    lat: SECTION_CENTER_LAT + dLat,
    lon: SECTION_CENTER_LON + dLon,
  };
}

export const DEMO_SENSORS: SensorRow[] = [
  // Seção 1
  mk("pz-sec01-fund-01", "piezometer_vw",          "sec-01-ombreira-esq", "rtu-bx-e1", "PZ fundação S1",         -0.0005, -0.0015),
  mk("pz-sec01-cont-01", "piezometer_vw",          "sec-01-ombreira-esq", "rtu-bx-e1", "PZ contato S1",          -0.0003, -0.0015),
  mk("pz-sec01-nuc-01",  "piezometer_vw",          "sec-01-ombreira-esq", "rtu-bx-e1", "PZ núcleo médio S1",     -0.0001, -0.0015),
  // Seção 2 (par redundante na fundação)
  mk("pz-sec02-fund-01", "piezometer_vw",          "sec-02-centro",        "rtu-bx-c1", "PZ fundação S2 (gêmeo A)", -0.0005, -0.0001),
  mk("pz-sec02-fund-02", "piezometer_vw",          "sec-02-centro",        "rtu-bx-c1", "PZ fundação S2 (gêmeo B)", -0.0005,  0.0001),
  mk("pz-sec02-cont-01", "piezometer_vw",          "sec-02-centro",        "rtu-bx-c1", "PZ contato S2",          -0.0003,  0.0000),
  mk("pz-sec02-nuc-01",  "piezometer_vw",          "sec-02-centro",        "rtu-bx-c1", "PZ núcleo médio S2",     -0.0001,  0.0000),
  // Seção 3
  mk("pz-sec03-fund-01", "piezometer_vw",          "sec-03-ombreira-dir",  "rtu-bx-d1", "PZ fundação S3",         -0.0005,  0.0014),
  mk("pz-sec03-cont-01", "piezometer_vw",          "sec-03-ombreira-dir",  "rtu-bx-d1", "PZ contato S3",          -0.0003,  0.0014),
  mk("pz-sec03-nuc-01",  "piezometer_vw",          "sec-03-ombreira-dir",  "rtu-bx-d1", "PZ núcleo médio S3",     -0.0001,  0.0014),
  // Inclinômetros
  mk("ipi-crista-sec01-01", "inclinometer_ipi_mems", "sec-01-ombreira-esq", "rtu-bx-e1", "IPI crista S1",         0.0004, -0.0016),
  mk("ipi-crista-sec02-01", "inclinometer_ipi_mems", "sec-02-centro",        "rtu-bx-c1", "IPI crista S2",         0.0004,  0.0000),
  mk("ipi-crista-sec03-01", "inclinometer_ipi_mems", "sec-03-ombreira-dir",  "rtu-bx-d1", "IPI crista S3",         0.0004,  0.0014),
  mk("ipi-jusante-sec02-01","inclinometer_ipi_mems", "sec-02-centro",        "rtu-bx-c1", "IPI talude jusante S2", -0.0008, 0.0000),
  mk("ipi-jusante-sec03-01","inclinometer_ipi_mems", "sec-03-ombreira-dir",  "rtu-bx-d1", "IPI talude jusante S3", -0.0008, 0.0014),
  // Pluviômetros
  mk("rain-crista-01",    "rain_gauge_tipping",     "sec-02-centro", "gw-bx-001", "Pluviômetro crista",       0.0004,  0.0002),
  mk("rain-jusante-01",   "rain_gauge_tipping",     "sec-02-centro", "gw-bx-001", "Pluviômetro pé de jusante", -0.0011, 0.0002),
];

// ---------------------------------------------------------------------------
// Timeseries — deterministic-but-fresh generator
// ---------------------------------------------------------------------------

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function seeded(seed: number) {
  let s = seed || 1;
  return () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  };
}

function baselineFor(sensorId: string, metric: string): number {
  if (metric === "pressure_kpa") {
    if (sensorId.includes("fund")) return 312;
    if (sensorId.includes("cont")) return 240;
    return 160;
  }
  if (metric === "frequency_hz") return 2345;
  if (metric === "temp_c") return 25;
  if (metric === "tilt_x_deg") return 0.08;
  if (metric === "tilt_y_deg") return -0.02;
  if (metric === "rainfall_mm") return 0;
  return 0;
}

function sigmaFor(metric: string): number {
  if (metric === "pressure_kpa") return 1.2;
  if (metric === "frequency_hz") return 2.0;
  if (metric === "temp_c") return 0.3;
  if (metric.startsWith("tilt")) return 0.01;
  if (metric === "rainfall_mm") return 0.5;
  return 0.1;
}

/**
 * Returns N timeseries points between tFrom..tTo at `bucketMs` spacing,
 * with a small drift so the chart has a visible signal, and an optional
 * rising trend so thresholds are almost touched (visible reference lines).
 */
export function generateTimeseries(
  sensorId: string,
  metric: string,
  tFrom: Date,
  tTo: Date,
  bucketMs: number,
): Array<{ bucket: string; n: number; vMin: number; vMax: number; vAvg: number }> {
  const base = baselineFor(sensorId, metric);
  const sig = sigmaFor(metric);
  const rng = seeded(hash(sensorId + metric));
  const points: Array<{
    bucket: string; n: number; vMin: number; vMax: number; vAvg: number;
  }> = [];

  const span = tTo.getTime() - tFrom.getTime();
  const count = Math.min(600, Math.max(6, Math.floor(span / bucketMs)));
  const step = span / count;

  // For one chosen fundação PZ we inject a slow rise towards the attention
  // line (380 kPa) so the threshold bands are visibly relevant in the chart.
  const risingSensor = sensorId === "pz-sec02-fund-01" && metric === "pressure_kpa";

  for (let i = 0; i < count; i++) {
    const t = new Date(tFrom.getTime() + step * i);
    const rise = risingSensor ? (i / count) * 55 : 0; // +55 kPa over window
    const drift = Math.sin((i / count) * Math.PI * 2) * sig * 3;
    const noise = (rng() - 0.5) * sig * 2;
    const mean = base + rise + drift + noise;
    points.push({
      bucket: t.toISOString(),
      n: 1,
      vMin: mean - sig,
      vMax: mean + sig,
      vAvg: mean,
    });
  }
  return points;
}

// ---------------------------------------------------------------------------
// Latest measurements per sensor (for SensorDetail)
// ---------------------------------------------------------------------------

export function latestFor(sensorId: string): Array<{
  metric: string; tSample: string; value: number; quality: string; flags: string[];
}> {
  const s = DEMO_SENSORS.find((x) => x.sensorId === sensorId);
  if (!s) return [];
  const now = new Date().toISOString();
  if (s.sensorType === "piezometer_vw") {
    return [
      { metric: "pressure_kpa", tSample: now, value: baselineFor(sensorId, "pressure_kpa") + 5,
        quality: sensorId === "pz-sec02-fund-01" ? "SUSPECT" : "GOOD",
        flags: sensorId === "pz-sec02-fund-01" ? ["RATE"] : [] },
      { metric: "frequency_hz", tSample: now, value: 2348.5, quality: "GOOD", flags: [] },
      { metric: "temp_c",       tSample: now, value: 25.3,   quality: "GOOD", flags: [] },
    ];
  }
  if (s.sensorType === "inclinometer_ipi_mems") {
    return [
      { metric: "tilt_x_deg", tSample: now, value: 0.08, quality: "GOOD", flags: [] },
      { metric: "tilt_y_deg", tSample: now, value: -0.02, quality: "GOOD", flags: [] },
      { metric: "temp_c",      tSample: now, value: 23.8, quality: "GOOD", flags: [] },
    ];
  }
  if (s.sensorType === "rain_gauge_tipping") {
    return [
      { metric: "rainfall_mm",   tSample: now, value: 0.0,  quality: "GOOD", flags: [] },
      { metric: "cumulative_mm", tSample: now, value: 47.8, quality: "GOOD", flags: [] },
    ];
  }
  return [];
}

// ---------------------------------------------------------------------------
// Alerts (mix of open/resolved)
// ---------------------------------------------------------------------------

export const DEMO_ALERTS = (() => {
  const now = Date.now();
  return [
    {
      eventId: "11111111-2222-3333-4444-555555555555",
      siteId: DEMO_SITE.siteId,
      structureId: "barragem-principal",
      ruleId: "pz-fund-atencao",
      ruleVersion: "v1.0.0",
      level: "ATENCAO",
      tTriggered: new Date(now - 1000 * 60 * 18).toISOString(),
      tResolved: null,
      sensors: ["pz-sec02-fund-01"],
    },
    {
      eventId: "22222222-3333-4444-5555-666666666666",
      siteId: DEMO_SITE.siteId,
      structureId: "barragem-principal",
      ruleId: "ipi-crista-alerta",
      ruleVersion: "v1.0.0",
      level: "ALERTA",
      tTriggered: new Date(now - 1000 * 60 * 120).toISOString(),
      tResolved: null,
      sensors: ["ipi-crista-sec03-01"],
    },
    {
      eventId: "33333333-4444-5555-6666-777777777777",
      siteId: DEMO_SITE.siteId,
      structureId: "barragem-principal",
      ruleId: "pz-fund-atencao",
      ruleVersion: "v1.0.0",
      level: "ATENCAO",
      tTriggered: new Date(now - 1000 * 60 * 60 * 9).toISOString(),
      tResolved: new Date(now - 1000 * 60 * 60 * 8).toISOString(),
      sensors: ["pz-sec03-fund-01"],
    },
    {
      eventId: "44444444-5555-6666-7777-888888888888",
      siteId: DEMO_SITE.siteId,
      structureId: "barragem-principal",
      ruleId: "chuva-porpressao",
      ruleVersion: "v1.0.0",
      level: "ATENCAO",
      tTriggered: new Date(now - 1000 * 60 * 60 * 26).toISOString(),
      tResolved: new Date(now - 1000 * 60 * 60 * 22).toISOString(),
      sensors: ["pz-sec02-fund-01", "rain-crista-01"],
    },
  ];
})();

// ---------------------------------------------------------------------------
// Notifications (dispatch log)
// ---------------------------------------------------------------------------

export const DEMO_NOTIFICATIONS = (() => {
  const now = Date.now();
  return [
    { dispatchId: 1001, alertMsgId: "01HK0000000000000000000001", level: "ATENCAO",
      channel: "email", target: "geotec@mineradora-x.com",
      status: "sent", error: null,
      tAttempted: new Date(now - 1000 * 60 * 18).toISOString(), latencyMs: 412 },
    { dispatchId: 1002, alertMsgId: "01HK0000000000000000000001", level: "ATENCAO",
      channel: "webhook", target: "https://hook.example.com/incidents",
      status: "sent", error: null,
      tAttempted: new Date(now - 1000 * 60 * 18).toISOString(), latencyMs: 128 },
    { dispatchId: 1003, alertMsgId: "01HK0000000000000000000002", level: "ALERTA",
      channel: "sms", target: "+5531999000001",
      status: "sent", error: null,
      tAttempted: new Date(now - 1000 * 60 * 120).toISOString(), latencyMs: 680 },
    { dispatchId: 1004, alertMsgId: "01HK0000000000000000000002", level: "ALERTA",
      channel: "email", target: "ops@mineradora-x.com",
      status: "sent", error: null,
      tAttempted: new Date(now - 1000 * 60 * 120).toISOString(), latencyMs: 396 },
    { dispatchId: 1005, alertMsgId: "01HK0000000000000000000002", level: "ALERTA",
      channel: "voice", target: "+5531999000001",
      status: "failed",
      error: "provider timeout after 10s",
      tAttempted: new Date(now - 1000 * 60 * 120).toISOString(), latencyMs: 10012 },
    { dispatchId: 1006, alertMsgId: "01HK0000000000000000000003", level: "ATENCAO",
      channel: "email", target: "geotec@mineradora-x.com",
      status: "sent", error: null,
      tAttempted: new Date(now - 1000 * 60 * 60 * 9).toISOString(), latencyMs: 355 },
  ];
})();

// ---------------------------------------------------------------------------
// GeoJSON for the map
// ---------------------------------------------------------------------------

export function sensorsGeoJson() {
  return {
    type: "FeatureCollection",
    features: DEMO_SENSORS.map((s) => ({
      type: "Feature",
      id: s.sensorId,
      geometry: { type: "Point", coordinates: [s.lon, s.lat] },
      properties: {
        sensor_id: s.sensorId,
        sensor_type: s.sensorType,
        display_name: s.displayName,
        structure_id: s.structureId,
        section_id: s.sectionId,
      },
    })),
  };
}

export function structuresGeoJson() {
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: "barragem-principal",
        geometry: {
          type: "Polygon",
          coordinates: [[
            [-43.9362, -19.9168],
            [-43.9318, -19.9168],
            [-43.9318, -19.9172],
            [-43.9362, -19.9172],
            [-43.9362, -19.9168],
          ]],
        },
        properties: {
          structure_id: "barragem-principal",
          kind: "earth_dam",
          display_name: "Barragem Principal",
        },
      },
    ],
  };
}

export function siteBoundary() {
  return {
    boundary: {
      type: "Polygon",
      coordinates: [[
        [-43.9420, -19.9120],
        [-43.9280, -19.9120],
        [-43.9280, -19.9220],
        [-43.9420, -19.9220],
        [-43.9420, -19.9120],
      ]],
    },
    point: {
      type: "Point",
      coordinates: [DEMO_SITE.lon, DEMO_SITE.lat],
    },
  };
}
