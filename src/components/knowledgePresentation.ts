import type { KnowledgePage, KnowledgeSource, KnowledgeWorkspaceData } from '../api/knowledgeWorkspaceApi';

export type SourcePresentation = {
  headline: string;
  origin: string;
  provenance: string;
  score: string;
  typeLabel: string;
};

export function describeLocalRestConnection(localRest: KnowledgeWorkspaceData['local_rest'] | undefined): string {
  if (!localRest || localRest.state === 'unconfigured') return 'Optional Local REST connector is not configured';
  if (localRest.state === 'connected') {
    const source = localRest.configuration_source === 'plugin_config' ? 'using installed plugin configuration' : 'using explicit runtime configuration';
    return `Authenticated ${localRest.plugin_id} ${localRest.plugin_version || 'service'} via ${localRest.transport}, ${source}`;
  }
  if (localRest.state === 'authentication_failed') return 'Local REST service rejected the configured runtime token';
  if (localRest.state === 'configuration_invalid') return localRest.configuration_source === 'plugin_config'
    ? 'Installed Local REST plugin configuration is incomplete or secure TLS is disabled'
    : 'Local REST configuration must use an explicit local HTTPS endpoint';
  return 'Local REST service is unavailable; filesystem Vault sync remains active';
}

export function describeKnowledgeReleaseGate(gate: KnowledgeWorkspaceData['release_gate']): string {
  if (!gate) return 'Operational release evidence has not been evaluated';
  if (gate.status === 'release_ready') return 'All required operational evidence is verified';
  if (gate.status === 'not_release_ready') return `Release is blocked by ${gate.failed_evidence.length} failed evidence check${gate.failed_evidence.length === 1 ? '' : 's'}`;
  const pending = gate.missing_evidence.length + gate.pending_evidence.length;
  return `${pending} required evidence check${pending === 1 ? '' : 's'} still need durable operational proof`;
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  horizon_signal: 'Horizon radar',
  obsidian_markdown: 'Obsidian note',
  obsidian_file: 'Obsidian import',
  manual_upload: 'Manual capture',
  feishu_document: 'Feishu document',
  feishu_minutes: 'Feishu minutes',
};

function compactSourceText(value: string, limit = 112): string {
  const normalized = value.replace(/\s+/g, ' ').trim();
  return normalized.length > limit ? `${normalized.slice(0, limit - 1).trimEnd()}...` : normalized;
}

function metadataString(metadata: Record<string, unknown>, key: string): string {
  const value = metadata[key];
  return typeof value === 'string' ? value.trim() : '';
}

function metadataRecord(metadata: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = metadata[key];
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function sourceHost(origin: string): string {
  try {
    return new URL(origin).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

function sourceDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'date unavailable' : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function describeKnowledgeSource(source: KnowledgeSource): SourcePresentation {
  const metadata = source.metadata || {};
  const horizonMetadata = metadataRecord(metadata, 'horizon_metadata');
  const origin = source.origin || source.vault_path || source.id;
  const host = sourceHost(origin);
  const sourceName = metadataString(horizonMetadata, 'source_name') || metadataString(metadata, 'source_name') || host;
  const headline = compactSourceText(
    metadataString(metadata, 'title')
      || metadataString(metadata, 'headline')
      || metadataString(horizonMetadata, 'title')
      || metadataString(metadata, 'ai_summary')
      || (host ? `${host} signal` : origin),
  );
  const rawScore = metadata.ai_score;
  const score = typeof rawScore !== 'number' || !Number.isFinite(rawScore)
    ? ''
    : rawScore <= 1
      ? `${Math.round(rawScore * 100)}/100`
      : rawScore <= 10
        ? `${Number.isInteger(rawScore) ? rawScore : rawScore.toFixed(1)}/10`
        : rawScore <= 100
          ? `${Math.round(rawScore)}/100`
          : String(Math.round(rawScore));
  const typeLabel = SOURCE_TYPE_LABELS[source.source_type] || source.source_type.replace(/[_-]+/g, ' ');
  return {
    headline,
    origin,
    provenance: [sourceName || 'local Vault', typeLabel, sourceDate(source.captured_at)].join(' / '),
    score,
    typeLabel,
  };
}

export function selectDefaultKnowledgePage(pages: KnowledgePage[]): KnowledgePage | null {
  return pages.find((page) => page.path === 'wiki/overview.md' || page.page_kind === 'overview')
    || pages.find((page) => !['log', 'index'].includes(page.page_kind))
    || pages[0]
    || null;
}
