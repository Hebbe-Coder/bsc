'''Asset Schema — Pydantic models for the unified asset generation pipeline.

Asset Types: ppt | html | pdf | word | xlsx
Template Categories: consulting_strategy | product_pitch | operation_report | bidding_proposal

All outputs derive from a single BusinessGraph to ensure consistency across formats.
'''
from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
import uuid
import time

# ── Asset Types ──

class AssetType(str, Enum):
    PPT  = 'ppt'
    HTML = 'html'
    PDF  = 'pdf'
    WORD = 'word'
    XLSX = 'xlsx'

class AssetStatus(str, Enum):
    PENDING    = 'pending'
    GENERATING = 'generating'
    COMPLETED  = 'completed'
    FAILED     = 'failed'

class TemplateCategory(str, Enum):
    CONSULTING_STRATEGY = 'consulting_strategy'
    PRODUCT_PITCH       = 'product_pitch'
    OPERATION_REPORT    = 'operation_report'
    BIDDING_PROPOSAL    = 'bidding_proposal'

# ── Template Config ──

class TemplateConfig(BaseModel):
    '''Template definition for a specific output format & category.'''
    template_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ''
    category: TemplateCategory = TemplateCategory.BIDDING_PROPOSAL
    format: AssetType
    industry: str = 'general'
    description: str = ''
    version: str = '1.0.0'
    slide_structure: list[dict] = Field(default_factory=list)
    design_tokens: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: time.strftime('%Y-%m-%dT%H:%M:%S'))

class TemplateRegistry(BaseModel):
    '''Collection of available templates.'''
    templates: list[TemplateConfig] = Field(default_factory=list)
    default_ppt: str = 'bidding_proposal'
    default_html: str = 'operation_report'
    default_pdf: str = 'bidding_proposal'
    default_word: str = 'operation_report'
    default_xlsx: str = 'operation_report'
    updated_at: str = Field(default_factory=lambda: time.strftime('%Y-%m-%dT%H:%M:%S'))

# ── Asset Manifest ──

class AssetFile(BaseModel):
    '''Metadata for a single generated asset file.'''
    file_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    asset_type: AssetType
    file_name: str = ''
    file_path: str = ''
    size_bytes: int = 0
    status: AssetStatus = AssetStatus.PENDING
    error_message: str = ''
    generated_at: str = ''

class AssetManifest(BaseModel):
    '''Manifest tracking all generated assets for a single generation run.'''
    manifest_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    graph_id: str = ''
    project_id: str = ''
    template_category: TemplateCategory = TemplateCategory.BIDDING_PROPOSAL
    industry: str = 'general'
    assets: list[AssetFile] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    created_at: str = Field(default_factory=lambda: time.strftime('%Y-%m-%dT%H:%M:%S'))

# ── Generation Request / Response ──

class AssetGenerateRequest(BaseModel):
    '''Request to generate assets from a BusinessGraph.'''
    graph_id: str = ''
    project_id: str = ''
    output_types: list[AssetType] = Field(default_factory=lambda: [AssetType.PPT, AssetType.HTML])
    template_category: TemplateCategory = TemplateCategory.BIDDING_PROPOSAL
    industry: str = 'general'
    title: str = 'Business System Report'

class AssetGenerateResponse(BaseModel):
    '''Response after asset generation.'''
    manifest_id: str
    graph_id: str
    status: AssetStatus
    assets: list[AssetFile] = Field(default_factory=list)
    message: str = ''

class AssetDownloadResponse(BaseModel):
    '''Basic download confirmation.'''
    file_id: str
    file_name: str
    file_path: str
    download_url: str
