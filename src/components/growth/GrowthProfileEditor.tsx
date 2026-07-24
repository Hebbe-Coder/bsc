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
};

function lines(values: string[] | undefined): string {
  return (values ?? []).join('\n');
}

function parseLines(value: string): string[] {
  return [...new Set(value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean))];
}

function formFromProfile(profile: GrowthProfile): FormState {
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
      <footer><span>{message || 'Changes are revisioned before future growth runs use them.'}</span><button type="submit" disabled={busy || !canWrite} title={canWrite ? 'Save project profile revision' : 'Write permission required'}><Save size={14} />{busy ? 'Saving...' : 'Save profile'}</button></footer>
    </form>
  </section>;
}
