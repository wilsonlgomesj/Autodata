import { gql } from "@apollo/client";

export const SITES = gql`
  query Sites {
    sites {
      siteId
      displayName
      country
      timezone
      lat
      lon
    }
  }
`;

export const STRUCTURES = gql`
  query Structures($site: String!) {
    structures(siteId: $site) {
      siteId
      structureId
      kind
      displayName
      heightM
      crestLengthM
      riskClass
    }
  }
`;

export const SENSORS = gql`
  query Sensors($site: String!, $structure: String, $type: String) {
    sensors(siteId: $site, structureId: $structure, sensorType: $type) {
      siteId
      sensorId
      sensorType
      structureId
      sectionId
      deviceId
      displayName
      installedOn
      active
    }
  }
`;

export const LATEST = gql`
  query Latest($site: String!, $sensor: String!) {
    latestMeasurements(siteId: $site, sensorId: $sensor) {
      metric
      tSample
      value
      quality
      flags
    }
  }
`;

export const TIMESERIES = gql`
  query Timeseries(
    $site: String!
    $sensor: String!
    $metric: String!
    $tFrom: DateTime!
    $tTo: DateTime!
    $resolution: String!
  ) {
    timeseries(
      siteId: $site
      sensorId: $sensor
      metric: $metric
      tFrom: $tFrom
      tTo: $tTo
      resolution: $resolution
    ) {
      bucket
      n
      vMin
      vMax
      vAvg
    }
  }
`;

export const ALERTS = gql`
  query Alerts($site: String!, $level: String, $since: DateTime, $limit: Int) {
    alerts(siteId: $site, level: $level, since: $since, limit: $limit) {
      eventId
      siteId
      structureId
      ruleId
      ruleVersion
      level
      tTriggered
      tResolved
      sensors
    }
  }
`;

export const NOTIFICATIONS = gql`
  query Notifications($site: String!, $since: DateTime, $limit: Int) {
    notifications(siteId: $site, since: $since, limit: $limit) {
      dispatchId
      alertMsgId
      level
      channel
      target
      status
      error
      tAttempted
      latencyMs
    }
  }
`;

export const SENSORS_GEOJSON = gql`
  query SensorsGeoJson($site: String!) {
    sensorsGeojson(siteId: $site)
    structuresGeojson(siteId: $site)
    siteBoundary(siteId: $site)
  }
`;
