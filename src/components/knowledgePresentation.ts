import type { KnowledgePage, KnowledgeSource } from '../api/knowledgeWorkspaceApi';

export type SourcePresentation = {
  headline: string;
  origin: string;
  provenance: string;
  score: string;
  typeLabel: string;
};

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
