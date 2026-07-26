import { Save, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import type { GrowthProfile, GrowthProfileUpdate } from '../../api/growthApi';

type Props = {
  profile: GrowthProfile;
  canWrite: boolean;
  busy: boolean;
  message?: string;
  onSave: (profile: GrowthProfileUpdate) => void;
  onClose: () => void;
};

type FormState = {
  userRole: string;
  researchDomains: string;
  outputTypes: string;
  audiences: string;
  channels: string;
  language: string;
  voice: string;
  evidenceThreshold: number;
  publicationPolicy: string;
  promotionPolicy: string;
  primaryOrigins: string;
  trustedOrigins: string;
  communityOrigins: string;
  blockedOrigins: string;
  trustedSourceTypes: string;
  triageSourceTypes: string;
  primaryRetentionDays: number;
  trustedRetentionDays: number;
  communityRetentionDays: number;
  untrustedRetentionDays: number;
  externalWorkerEnabled: boolean;
  externalWorkerIds: string;
  externalWorkerModels: string;
  externalWorkerHosts: string;
  externalWorkerCapabilities: string;
  externalWorkerCredentialRef: string;
  externalWorkerEnvironments: string;
  externalWorkerMaxCalls: number;
  externalWorkerMaxConcurrent: number;
  externalWorkerMaxCost: number;
  externalWorkerTimeout: number;
};

function lines(values: string[] | undefined): string {
  return (values ?? []).join('\n');
}

function parseLines(value: string): string[] {
  return [...new Set(value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean))];
}

function retention(value: number): number {
  return Math.max(1, Math.min(3650, Number.isFinite(value) ? Math.trunc(value) : 30));
}

function formFromProfile(profile: GrowthProfile): FormState {
  const policy = profile.source_policy;
  const workerPolicy = profile.external_worker_policy;
  return {
    userRole: profile.user_role || '',
    researchDomains: lines(profile.research_domains),
    outputTypes: lines(profile.primary_output_types),
    audiences: lines(profile.target_audiences),
    channels: lines(profile.preferred_channels),
    language: profile.language || 'zh-CN',
    voice: profile.content_voice || '',
    evidenceThreshold: Number(profile.evidence_threshold ?? 80),
    publicationPolicy: profile.automatic_publication_policy || 'review',
    promotionPolicy: profile.method_promotion_policy || 'gated',
    primaryOrigins: lines(policy?.primary_origin_prefixes),
    trustedOrigins: lines(policy?.trusted_origin_prefixes),
    communityOrigins: lines(policy?.community_origin_prefixes),
    blockedOrigins: lines(policy?.blocked_origin_prefixes),
    trustedSourceTypes: lines(policy?.trusted_source_types ?? ['manual_upload']),
    triageSourceTypes: lines(policy?.require_triage_source_types ?? ['horizon_signal']),
    primaryRetentionDays: retention(Number(policy?.primary_retention_days ?? 730)),
    trustedRetentionDays: retention(Number(policy?.trusted_retention_days ?? 365)),
    communityRetentionDays: retention(Number(policy?.community_retention_days ?? 90)),
    untrustedRetentionDays: retention(Number(policy?.untrusted_retention_days ?? 30)),
    externalWorkerEnabled: Boolean(workerPolicy?.enabled),
    externalWorkerIds: lines(workerPolicy?.worker_ids),
    externalWorkerModels: lines(workerPolicy?.allowed_model_ids),
    externalWorkerHosts: lines(workerPolicy?.allowed_https_hosts),
    externalWorkerCapabilities: lines(workerPolicy?.allowed_capabilities),
    externalWorkerCredentialRef: workerPolicy?.credential_ref || '',
    externalWorkerEnvironments: lines(workerPolicy?.allowed_environments ?? ['test']),
    externalWorkerMaxCalls: Number(workerPolicy?.max_calls ?? 0),
    externalWorkerMaxConcurrent: Number(workerPolicy?.max_concurrent ?? 1),
    externalWorkerMaxCost: Number(workerPolicy?.max_cost_microusd ?? 0),
    externalWorkerTimeout: Number(workerPolicy?.timeout_seconds ?? 60),
  };
}

export function GrowthProfileEditor({ profile, canWrite, busy, message, onSave, onClose }: Props) {
  const [form, setForm] = useState<FormState>(() => formFromProfile(profile));

  useEffect(() => {
    setForm(formFromProfile(profile));
  }, [profile]);

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSave({
      expected_revision: Number(profile.revision ?? 0),
      user_role: form.userRole.trim(),
      research_domains: parseLines(form.researchDomains),
      primary_output_types: parseLines(form.outputTypes),
      target_audiences: parseLines(form.audiences),
      preferred_channels: parseLines(form.channels),
      language: form.language.trim() || 'zh-CN',
      content_voice: form.voice.trim(),
      evidence_threshold: Math.max(0, Math.min(100, Number(form.evidenceThreshold))),
      automatic_publication_policy: form.publicationPolicy,
      method_promotion_policy: form.promotionPolicy,
      source_policy: {
        primary_origin_prefixes: parseLines(form.primaryOrigins),
        trusted_origin_prefixes: parseLines(form.trustedOrigins),
        community_origin_prefixes: parseLines(form.communityOrigins),
        blocked_origin_prefixes: parseLines(form.blockedOrigins),
        trusted_source_types: parseLines(form.trustedSourceTypes),
        require_triage_source_types: parseLines(form.triageSourceTypes),
        primary_retention_days: retention(form.primaryRetentionDays),
        trusted_retention_days: retention(form.trustedRetentionDays),
        community_retention_days: retention(form.communityRetentionDays),
        untrusted_retention_days: retention(form.untrustedRetentionDays),
      },
      external_worker_policy: {
        enabled: form.externalWorkerEnabled,
        worker_ids: parseLines(form.externalWorkerIds),
        allowed_model_ids: parseLines(form.externalWorkerModels),
        allowed_https_hosts: parseLines(form.externalWorkerHosts),
        allowed_capabilities: parseLines(form.externalWorkerCapabilities),
        credential_ref: form.externalWorkerCredentialRef.trim(),
        allowed_environments: parseLines(form.externalWorkerEnvironments),
        max_calls: Math.max(0, Math.trunc(form.externalWorkerMaxCalls)),
        max_concurrent: Math.max(1, Math.min(20, Math.trunc(form.externalWorkerMaxConcurrent))),
        max_cost_microusd: Math.max(0, Math.trunc(form.externalWorkerMaxCost)),
        timeout_seconds: Math.max(1, Math.min(600, Math.trunc(form.externalWorkerTimeout))),
      },
    });
  };

  return <section className="growth-profile-editor" aria-label="Project knowledge profile editor">
    <header className="growth-profile-editor__header">
      <div><p>PROJECT PROFILE</p><h3>Project-specific generation rules</h3><span>Revision {profile.revision ?? 0}</span></div>
      <button type="button" className="growth-icon-button" onClick={onClose} aria-label="Close project profile editor" title="Close project profile editor"><X size={16} /></button>
    </header>
    <form onSubmit={submit}>
      <label><span>User role</span><input value={form.userRole} onChange={(event) => update('userRole', event.target.value)} placeholder="e.g. product researcher" /></label>
      <label><span>Research domains</span><textarea value={form.researchDomains} onChange={(event) => update('researchDomains', event.target.value)} placeholder="One domain per line" /></label>
      <label><span>Primary outputs</span><textarea value={form.outputTypes} onChange={(event) => update('outputTypes', event.target.value)} placeholder="SOP, report, article" /></label>
      <label><span>Target audiences</span><textarea value={form.audiences} onChange={(event) => update('audiences', event.target.value)} placeholder="One audience per line" /></label>
      <label><span>Preferred channels</span><textarea value={form.channels} onChange={(event) => update('channels', event.target.value)} placeholder="Obsidian, Feishu, newsletter" /></label>
      <label><span>Content voice</span><textarea value={form.voice} onChange={(event) => update('voice', event.target.value)} placeholder="Clear, evidence-backed, practical" /></label>
      <label><span>Language</span><input value={form.language} onChange={(event) => update('language', event.target.value)} placeholder="zh-CN" /></label>
      <label className="growth-profile-editor__range"><span>Evidence threshold <output>{form.evidenceThreshold}</output></span><input type="range" min="0" max="100" step="1" aria-label="Evidence threshold" aria-valuetext={`${form.evidenceThreshold} out of 100`} value={form.evidenceThreshold} onChange={(event) => update('evidenceThreshold', Number(event.target.value))} /></label>
      <label><span>Publication policy</span><select value={form.publicationPolicy} onChange={(event) => update('publicationPolicy', event.target.value)}><option value="review">Review before publish</option><option value="manual">Manual only</option><option value="disabled">Disabled</option></select></label>
      <label><span>Method promotion</span><select value={form.promotionPolicy} onChange={(event) => update('promotionPolicy', event.target.value)}><option value="gated">Gated evaluation</option><option value="manual">Manual promotion</option><option value="disabled">Disabled</option></select></label>
      <fieldset className="growth-profile-editor__source-policy">
        <legend>Source governance</legend>
        <label><span>Primary source origins</span><textarea value={form.primaryOrigins} onChange={(event) => update('primaryOrigins', event.target.value)} placeholder="One URL or path prefix per line" /></label>
        <label><span>Trusted source origins</span><textarea value={form.trustedOrigins} onChange={(event) => update('trustedOrigins', event.target.value)} placeholder="One URL or path prefix per line" /></label>
        <label><span>Community source origins</span><textarea value={form.communityOrigins} onChange={(event) => update('communityOrigins', event.target.value)} placeholder="Always enters review" /></label>
        <label><span>Blocked source origins</span><textarea value={form.blockedOrigins} onChange={(event) => update('blockedOrigins', event.target.value)} placeholder="Always rejected before indexing" /></label>
        <label><span>Trusted source types</span><input value={form.trustedSourceTypes} onChange={(event) => update('trustedSourceTypes', event.target.value)} placeholder="manual_upload, web_clip" /></label>
        <label><span>Always triage source types</span><input value={form.triageSourceTypes} onChange={(event) => update('triageSourceTypes', event.target.value)} placeholder="horizon_signal" /></label>
        <label><span>Primary retention days</span><input type="number" min="1" max="3650" value={form.primaryRetentionDays} onChange={(event) => update('primaryRetentionDays', Number(event.target.value))} /></label>
        <label><span>Trusted retention days</span><input type="number" min="1" max="3650" value={form.trustedRetentionDays} onChange={(event) => update('trustedRetentionDays', Number(event.target.value))} /></label>
        <label><span>Community retention days</span><input type="number" min="1" max="3650" value={form.communityRetentionDays} onChange={(event) => update('communityRetentionDays', Number(event.target.value))} /></label>
        <label><span>Untrusted retention days</span><input type="number" min="1" max="3650" value={form.untrustedRetentionDays} onChange={(event) => update('untrustedRetentionDays', Number(event.target.value))} /></label>
       </fieldset>
      <fieldset className="growth-profile-editor__source-policy">
        <legend>External worker governance</legend>
        <label><span>Enable non-production worker</span><input type="checkbox" checked={form.externalWorkerEnabled} onChange={(event) => update('externalWorkerEnabled', event.target.checked)} /></label>
        <label><span>Worker IDs</span><textarea value={form.externalWorkerIds} onChange={(event) => update('externalWorkerIds', event.target.value)} placeholder="One worker ID per line" /></label>
        <label><span>Allowed model IDs</span><textarea value={form.externalWorkerModels} onChange={(event) => update('externalWorkerModels', event.target.value)} placeholder="One pinned model ID per line" /></label>
        <label><span>Allowed HTTPS hosts</span><textarea value={form.externalWorkerHosts} onChange={(event) => update('externalWorkerHosts', event.target.value)} placeholder="worker.example" /></label>
        <label><span>Allowed capabilities</span><textarea value={form.externalWorkerCapabilities} onChange={(event) => update('externalWorkerCapabilities', event.target.value)} placeholder="sop_design" /></label>
        <label><span>Server credential reference</span><input value={form.externalWorkerCredentialRef} onChange={(event) => update('externalWorkerCredentialRef', event.target.value)} placeholder="provider_test" /></label>
        <label><span>Allowed environments</span><input value={form.externalWorkerEnvironments} onChange={(event) => update('externalWorkerEnvironments', event.target.value)} placeholder="test" /></label>
        <label><span>Maximum calls</span><input type="number" min="0" value={form.externalWorkerMaxCalls} onChange={(event) => update('externalWorkerMaxCalls', Number(event.target.value))} /></label>
        <label><span>Maximum concurrent</span><input type="number" min="1" max="20" value={form.externalWorkerMaxConcurrent} onChange={(event) => update('externalWorkerMaxConcurrent', Number(event.target.value))} /></label>
        <label><span>Maximum cost (microusd)</span><input type="number" min="0" value={form.externalWorkerMaxCost} onChange={(event) => update('externalWorkerMaxCost', Number(event.target.value))} /></label>
        <label><span>Timeout seconds</span><input type="number" min="1" max="600" value={form.externalWorkerTimeout} onChange={(event) => update('externalWorkerTimeout', Number(event.target.value))} /></label>
      </fieldset>
      <footer><span>{message || 'Changes are revisioned before future growth runs use them.'}</span><button type="submit" disabled={busy || !canWrite} title={canWrite ? 'Save project profile revision' : 'Write permission required'}><Save size={14} />{busy ? 'Saving...' : 'Save profile'}</button></footer>
    </form>
  </section>;
}
