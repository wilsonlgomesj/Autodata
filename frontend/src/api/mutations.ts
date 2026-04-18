import { gql } from "@apollo/client";

export const ACK_ALERT = gql`
  mutation AckAlert($id: String!, $comment: String!) {
    acknowledgeAlert(eventId: $id, comment: $comment) {
      ok
      message
      eventId
      correlationId
    }
  }
`;

export const UPDATE_THRESHOLD = gql`
  mutation UpdateThreshold($input: UpdateThresholdInput!) {
    updateThreshold(input: $input) {
      ok
      message
      correlationId
    }
  }
`;

export const ISSUE_COMMAND = gql`
  mutation IssueCommand($input: IssueCommandInput!) {
    issueCommand(input: $input) {
      ok
      message
      correlationId
    }
  }
`;
