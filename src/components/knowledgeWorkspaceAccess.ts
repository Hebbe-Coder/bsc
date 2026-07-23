import type { KnowledgeWorkspaceData } from '../api/knowledgeWorkspaceApi';

export type StudioAccessState = 'required' | 'checking' | 'rejected' | 'failed' | 'verified';

export type StudioAccessStatus = {
  state: StudioAccessState;
  label: string;
  detail: string;
  verified: boolean;
};

export function resolveStudioAccessStatus(
  runtimeAccessKey: string,
  workspace: KnowledgeWorkspaceData | null,
  loading: boolean,
  error: string,
): StudioAccessStatus {
  if (!runtimeAccessKey.trim()) {
    return { state: 'required', label: 'Studio access required', detail: 'Enter the runtime access key in Studio.', verified: false };
  }
  if (loading) {
    return { state: 'checking', label: 'Verifying Studio access', detail: 'Checking the project-scoped API session.', verified: false };
  }
  if (/\b(?:401|403)\b|auth(?:entication|orization)?|forbidden|permission/i.test(error)) {
    return { state: 'rejected', label: 'Studio access rejected', detail: 'The runtime access key was rejected by the API.', verified: false };
  }
  if (error) {
    return { state: 'failed', label: 'Studio access unavailable', detail: 'The project workspace could not be loaded.', verified: false };
  }
  if (workspace) {
    return { state: 'verified', label: 'Studio access verified', detail: `Authenticated project role: ${workspace.access.role || 'reader'}.`, verified: true };
  }
  return { state: 'checking', label: 'Verifying Studio access', detail: 'Waiting for the project workspace response.', verified: false };
}
