import { Undo2, Redo2, Plus, Download, Palette, Save, Trash2, Copy, ChevronLeft, ChevronRight, Sparkles, Loader2, X, FileText, LayoutTemplate, Store, Settings, Play, Zap, FileJson, FileImage, FileText as FileTextIcon, Upload, Image, FileCode, FileDown, LayoutGrid, Bot } from 'lucide-react';
import usePresentationStore from '../store/presentationStore';
import { themes, themeList } from '../theme/themes';
import { ThemeType } from '../types';
import { useState } from 'react';
import { downloadHTML } from '../utils/htmlExporter';
import { downloadMarkdown, downloadJSON, downloadCurrentSlideAsPNG, downloadAllSlidesAsPNG, triggerImport, downloadPDFWithProgress, downloadPPTXWithProgress } from '../utils/exporter';
import SkillPlanModal from './SkillPlanModal';
import TemplateSelector from './TemplateSelector';
import SkillMarket from './SkillMarket';
import ModelConfigModal from './ModelConfigModal';
import AnimationPreview from './AnimationPreview';
import SkillExecutionPanel from './SkillExecutionPanel';
import SlideMasterModal from './SlideMasterModal';
import BscCompilerPanel from './BscCompilerPanel';
import ChatInterface from './ChatInterface';

const Toolbar = () => {
  const { presentation, setTheme, setCurrentSlideIndex, addSlide, deleteSlide, duplicateSlide, reset, isLoading, error, setError, undo, redo, canUndo, canRedo, importPresentation } = usePresentationStore();
  const [showThemeMenu, setShowThemeMenu] = useState(false);
  const [showBscCompiler, setShowBscCompiler] = useState(false);
  const [showChatInterface, setShowChatInterface] = useState(false);
  const [showSkillPlanModal, setShowSkillPlanModal] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [showSkillMarket, setShowSkillMarket] = useState(false);
  const [showModelConfig, setShowModelConfig] = useState(false);
  const [showAnimationPreview, setShowAnimationPreview] = useState(false);
  const [showSkillExecutionPanel, setShowSkillExecutionPanel] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [showImportSuccess, setShowImportSuccess] = useState(false);
  const [showMasterModal, setShowMasterModal] = useState(false);
  const [showExportSettings, setShowExportSettings] = useState(false);
  const [exportProgress, setExportProgress] = useState<{ percent: number; current: number; total: number; type: 'pdf' | 'pptx' } | null>(null);
  const [exportResolution, setExportResolution] = useState<'low' | 'medium' | 'high'>('high');
  const [exportIncludeFooter, setExportIncludeFooter] = useState(true);
  const [exportIncludeCoverPage, setExportIncludeCoverPage] = useState(false);
  const [exportWatermark, setExportWatermark] = useState('');
  const [exportWatermarkOpacity, setExportWatermarkOpacity] = useState(0.15);

  const currentSlide = presentation.slides[presentation.currentSlideIndex];

  const handlePrevSlide = () => {
    setCurrentSlideIndex(presentation.currentSlideIndex - 1);
  };

  const handleNextSlide = () => {
    setCurrentSlideIndex(presentation.currentSlideIndex + 1);
  };

  const handleExportHTML = () => {
    downloadHTML(presentation);
    setShowExportMenu(false);
  };

  const handleExportPDF = async () => {
    setShowExportMenu(false);
    setShowExportSettings(true);
  };

  const handleExportPDFWithSettings = async () => {
    setShowExportSettings(false);
    const totalPages = presentation.slides.length + (exportIncludeCoverPage ? 1 : 0);
    setExportProgress({ percent: 0, current: 0, total: totalPages, type: 'pdf' });
    
    await downloadPDFWithProgress(
      presentation,
      (percent, current, total) => {
        setExportProgress({ percent, current, total, type: 'pdf' });
        if (percent >= 100) {
          setTimeout(() => setExportProgress(null), 1500);
        }
      },
      {
        resolution: exportResolution,
        includeFooter: exportIncludeFooter,
        includeCoverPage: exportIncludeCoverPage,
        watermark: exportWatermark || undefined,
        watermarkOpacity: exportWatermarkOpacity,
        pageRange: 'all',
      }
    );
  };

  const handleExportPPTX = async () => {
    setShowExportMenu(false);
    setExportProgress({ percent: 0, current: 0, total: presentation.slides.length, type: 'pptx' });
    
    await downloadPPTXWithProgress(
      presentation,
      (percent, current, total) => {
        setExportProgress({ percent, current, total, type: 'pptx' });
        if (percent >= 100) {
          setTimeout(() => setExportProgress(null), 1500);
        }
      },
      {
        includeFooter: exportIncludeFooter,
      }
    );
  };

  const handleExportJSON = () => {
    downloadJSON(presentation);
    setShowExportMenu(false);
  };

  const handleExportMarkdown = () => {
    downloadMarkdown(presentation);
    setShowExportMenu(false);
  };

  const handleExportCurrentSlidePNG = async () => {
    await downloadCurrentSlideAsPNG(presentation);
    setShowExportMenu(false);
  };

  const handleExportAllSlidesPNG = async () => {
    await downloadAllSlidesAsPNG(presentation);
    setShowExportMenu(false);
  };

  const handleImport = () => {
    triggerImport(
      (pres) => {
        importPresentation(pres);
        setShowExportMenu(false);
        setShowImportSuccess(true);
        setTimeout(() => setShowImportSuccess(false), 3000);
      },
      () => {
        setError('导入失败：无效的演示文稿文件');
        setShowExportMenu(false);
      }
    );
  };

  return (
    <>
      <div className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <button 
              onClick={undo}
              disabled={!canUndo()}
              className="p-2 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-gray-600" 
              title="撤销"
            >
              <Undo2 size={18} />
            </button>
            <button 
              onClick={redo}
              disabled={!canRedo()}
              className="p-2 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-gray-600" 
              title="重做"
            >
              <Redo2 size={18} />
            </button>
          </div>
          <div className="w-px h-6 bg-gray-300 mx-2" />
          <button className="p-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-600" title="保存">
            <Save size={18} />
          </button>
          <button onClick={reset} className="p-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-600" title="新建">
            <Plus size={18} />
          </button>
          <button onClick={() => setShowTemplateModal(true)} className="p-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-600" title="从模板创建">
            <LayoutTemplate size={18} />
          </button>
          <button onClick={() => setShowSkillMarket(true)} className="p-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-600" title="技能市场">
            <Store size={18} />
          </button>
          <button onClick={() => setShowSkillExecutionPanel(true)} className="p-2 rounded-lg hover:bg-purple-50 transition-colors text-purple-600" title="AI技能">
            <Zap size={18} />
          </button>
          <button onClick={() => setShowModelConfig(true)} className="p-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-600" title="模型配置">
            <Settings size={18} />
          </button>
          <button onClick={() => setShowMasterModal(true)} className="p-2 rounded-lg hover:bg-indigo-50 transition-colors text-indigo-600" title="母版设置">
            <LayoutGrid size={18} />
          </button>
        </div>

        <div className="flex items-center gap-4">
          <button 
            onClick={handlePrevSlide} 
            disabled={presentation.currentSlideIndex === 0}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-gray-600"
          >
            <ChevronLeft size={20} />
          </button>
          <div className="text-sm font-medium text-gray-700 min-w-[120px] text-center">
            {presentation.currentSlideIndex + 1} / {presentation.slides.length}
          </div>
          <button 
            onClick={handleNextSlide} 
            disabled={presentation.currentSlideIndex === presentation.slides.length - 1}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-gray-600"
          >
            <ChevronRight size={20} />
          </button>
          <div className="w-px h-6 bg-gray-300 mx-2" />
          <button onClick={() => addSlide()} className="p-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-600" title="添加幻灯片">
            <Plus size={18} />
          </button>
          <button 
            onClick={() => duplicateSlide(presentation.currentSlideIndex)} 
            disabled={!currentSlide}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-gray-600" 
            title="复制幻灯片"
          >
            <Copy size={18} />
          </button>
          <button 
            onClick={() => deleteSlide(presentation.currentSlideIndex)} 
            disabled={presentation.slides.length <= 1}
            className="p-2 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-red-500" 
            title="删除幻灯片"
          >
            <Trash2 size={18} />
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button 
            onClick={() => setShowChatInterface(true)}
            disabled={isLoading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 transition-all text-white text-sm disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-xl"
          >
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Bot size={16} />}
            <span>{isLoading ? '生成中...' : '智能助手'}</span>
          </button>
          <button 
            onClick={() => setShowBscCompiler(true)}
            disabled={isLoading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 transition-all text-white text-sm disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-xl"
          >
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            <span>{isLoading ? '生成中...' : 'BSC编译'}</span>
          </button>
          <div className="w-px h-6 bg-gray-300 mx-2" />
          <div className="relative">
            <button 
              onClick={() => setShowThemeMenu(!showThemeMenu)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-gray-700 text-sm"
            >
              <Palette size={16} />
              <span>{themes[presentation.theme].name}</span>
            </button>
            {showThemeMenu && (
              <div className="absolute top-full left-0 mt-2 bg-white rounded-xl shadow-lg border border-gray-200 p-2 z-50 w-40">
                {themeList.map((theme) => (
                  <button
                    key={theme}
                    onClick={() => {
                      setTheme(theme as ThemeType);
                      setShowThemeMenu(false);
                    }}
                    className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left text-sm ${
                      presentation.theme === theme ? 'bg-gray-100 font-medium' : ''
                    }`}
                  >
                    <div 
                      className="w-4 h-4 rounded-full border border-gray-200" 
                      style={{ backgroundColor: themes[theme].primary }}
                    />
                    {themes[theme].name}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="w-px h-6 bg-gray-300 mx-2" />
          <button 
            onClick={() => setShowAnimationPreview(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-500 hover:bg-blue-600 transition-colors text-white text-sm"
          >
            <Play size={16} />
            <span>动画预览</span>
          </button>
          <div className="relative">
            <button 
              onClick={() => setShowExportMenu(!showExportMenu)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-green-500 hover:bg-green-600 transition-colors text-white text-sm"
            >
              <Download size={16} />
              <span>导出</span>
            </button>
            {showExportMenu && (
              <div className="absolute top-full right-0 mt-2 bg-white rounded-xl shadow-lg border border-gray-200 p-2 z-50 w-52">
                <button
                  onClick={handleImport}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-blue-50 transition-colors text-left text-sm"
                >
                  <Upload size={16} className="text-blue-500" />
                  <span>导入演示文稿</span>
                </button>
                <div className="h-px bg-gray-100 my-2" />
                <button
                  onClick={handleExportHTML}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left text-sm"
                >
                  <FileCode size={16} className="text-purple-500" />
                  <span>导出为 HTML</span>
                </button>
                <button
                  onClick={handleExportPDF}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left text-sm"
                >
                  <FileImage size={16} className="text-red-500" />
                  <span>导出为 PDF</span>
                </button>
                <button
                  onClick={handleExportPPTX}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left text-sm"
                >
                  <FileTextIcon size={16} className="text-orange-500" />
                  <span>导出为 PPTX</span>
                </button>
                <div className="h-px bg-gray-100 my-2" />
                <button
                  onClick={handleExportCurrentSlidePNG}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left text-sm"
                >
                  <Image size={16} className="text-orange-500" />
                  <span>当前页为 PNG</span>
                </button>
                <button
                  onClick={handleExportAllSlidesPNG}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left text-sm"
                >
                  <FileDown size={16} className="text-cyan-500" />
                  <span>全部导出为 PNG</span>
                </button>
                <div className="h-px bg-gray-100 my-2" />
                <button
                  onClick={handleExportJSON}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left text-sm"
                >
                  <FileJson size={16} className="text-blue-500" />
                  <span>导出为 JSON</span>
                </button>
                <button
                  onClick={handleExportMarkdown}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left text-sm"
                >
                  <FileText size={16} className="text-green-500" />
                  <span>导出为 Markdown</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border-b border-red-200 px-4 py-2 flex items-center gap-2">
          <span className="text-red-600 text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600">
            <X size={16} />
          </button>
        </div>
      )}

      {showImportSuccess && (
        <div className="bg-green-50 border-b border-green-200 px-4 py-2 flex items-center gap-2">
          <span className="text-green-600 text-sm">✓ 演示文稿导入成功</span>
        </div>
      )}

      {showBscCompiler && (
        <BscCompilerPanel 
          isOpen={showBscCompiler}
          onClose={() => setShowBscCompiler(false)}
        />
      )}

      {showChatInterface && (
        <ChatInterface 
          isOpen={showChatInterface}
          onClose={() => setShowChatInterface(false)}
        />
      )}

      {showSkillPlanModal && (
        <SkillPlanModal 
          onClose={() => { setShowSkillPlanModal(false); }}
          prdContent=""
        />
      )}

      {showTemplateModal && (
        <TemplateSelector 
          onClose={() => setShowTemplateModal(false)}
        />
      )}

      {showSkillMarket && (
        <SkillMarket 
          onClose={() => setShowSkillMarket(false)}
        />
      )}

      {showModelConfig && (
        <ModelConfigModal 
          onClose={() => setShowModelConfig(false)}
        />
      )}

      {showAnimationPreview && <AnimationPreview onClose={() => setShowAnimationPreview(false)} />}
      
      {showMasterModal && <SlideMasterModal onClose={() => setShowMasterModal(false)} />}
      
      {showSkillExecutionPanel && (
        <SkillExecutionPanel 
          isOpen={showSkillExecutionPanel}
          onClose={() => setShowSkillExecutionPanel(false)}
        />
      )}

      {showExportSettings && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden max-h-[90vh] flex flex-col">
            <div className="bg-gradient-to-r from-red-500 to-orange-500 px-6 py-4 flex-shrink-0">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <FileImage size={20} />
                  PDF导出设置
                </h2>
                <button onClick={() => setShowExportSettings(false)} className="text-white/80 hover:text-white">
                  <X size={20} />
                </button>
              </div>
            </div>
            <div className="p-6 space-y-6 overflow-y-auto flex-1">
              <div>
                <label className="text-sm font-medium text-gray-700 mb-3 block">导出分辨率</label>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { value: 'low' as const, label: '低', desc: '快速导出' },
                    { value: 'medium' as const, label: '中', desc: '平衡质量' },
                    { value: 'high' as const, label: '高', desc: '最佳质量' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      onClick={() => setExportResolution(option.value)}
                      className={`p-3 rounded-xl border-2 transition-all text-center ${
                        exportResolution === option.value
                          ? 'border-blue-500 bg-blue-50 text-blue-600'
                          : 'border-gray-200 hover:border-gray-300 text-gray-600'
                      }`}
                    >
                      <div className="font-semibold">{option.label}</div>
                      <div className="text-xs opacity-70">{option.desc}</div>
                    </button>
                  ))}
                </div>
              </div>
              
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-sm font-medium text-gray-700">包含封面页</label>
                  <p className="text-xs text-gray-500 mt-1">在文档开头添加精美的封面页</p>
                </div>
                <button
                  onClick={() => setExportIncludeCoverPage(!exportIncludeCoverPage)}
                  className={`w-12 h-6 rounded-full transition-colors relative ${
                    exportIncludeCoverPage ? 'bg-blue-500' : 'bg-gray-300'
                  }`}
                >
                  <div
                    className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform shadow ${
                      exportIncludeCoverPage ? 'translate-x-7' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <label className="text-sm font-medium text-gray-700">包含页码页脚</label>
                  <p className="text-xs text-gray-500 mt-1">在每页底部添加页码和日期</p>
                </div>
                <button
                  onClick={() => setExportIncludeFooter(!exportIncludeFooter)}
                  className={`w-12 h-6 rounded-full transition-colors relative ${
                    exportIncludeFooter ? 'bg-blue-500' : 'bg-gray-300'
                  }`}
                >
                  <div
                    className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform shadow ${
                      exportIncludeFooter ? 'translate-x-7' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 mb-2 block">水印文字</label>
                <input
                  type="text"
                  value={exportWatermark}
                  onChange={(e) => setExportWatermark(e.target.value)}
                  placeholder="输入水印文字（如：内部资料）"
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 text-sm"
                />
                {exportWatermark && (
                  <div className="mt-3">
                    <label className="text-sm font-medium text-gray-700 mb-2 block">水印透明度</label>
                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min="0.05"
                        max="0.5"
                        step="0.05"
                        value={exportWatermarkOpacity}
                        onChange={(e) => setExportWatermarkOpacity(parseFloat(e.target.value))}
                        className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
                      />
                      <span className="text-sm text-gray-600 w-12 text-right">{Math.round(exportWatermarkOpacity * 100)}%</span>
                    </div>
                  </div>
                )}
              </div>

              <div className="bg-blue-50 rounded-xl p-4">
                <div className="text-sm font-medium text-blue-800 mb-1">导出预览</div>
                <div className="text-xs text-blue-600 space-y-1">
                  <div>将导出 {presentation.slides.length + (exportIncludeCoverPage ? 1 : 0)} 页幻灯片</div>
                  <div>文件格式：PDF | 分辨率：{exportResolution === 'high' ? '高' : exportResolution === 'medium' ? '中' : '低'}</div>
                  {exportWatermark && <div>水印：{exportWatermark}</div>}
                </div>
              </div>
            </div>
            <div className="border-t border-gray-100 px-6 py-4 flex justify-end gap-3 flex-shrink-0">
              <button
                onClick={() => setShowExportSettings(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors text-gray-700 text-sm font-medium"
              >
                取消
              </button>
              <button
                onClick={handleExportPDFWithSettings}
                className="px-4 py-2 bg-gradient-to-r from-red-500 to-orange-500 rounded-lg hover:from-red-600 hover:to-orange-600 transition-all text-white text-sm font-medium flex items-center gap-2"
              >
                <FileImage size={16} />
                开始导出
              </button>
            </div>
          </div>
        </div>
      )}

      {exportProgress && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-4 p-6">
            <div className="text-center">
              <div className={`w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center ${
                exportProgress.type === 'pdf' ? 'bg-red-100' : 'bg-orange-100'
              }`}>
                <Loader2 size={28} className={`animate-spin ${
                  exportProgress.type === 'pdf' ? 'text-red-500' : 'text-orange-500'
                }`} />
              </div>
              <h3 className="text-lg font-semibold text-gray-800 mb-2">
                {exportProgress.type === 'pdf' ? '正在导出PDF...' : '正在导出PPTX...'}
              </h3>
              <p className="text-sm text-gray-500 mb-4">
                第 {exportProgress.current} / {exportProgress.total} 页
              </p>
              <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-300 ${
                    exportProgress.type === 'pdf' 
                      ? 'bg-gradient-to-r from-red-500 to-orange-500' 
                      : 'bg-gradient-to-r from-orange-500 to-amber-500'
                  }`}
                  style={{ width: `${exportProgress.percent}%` }}
                />
              </div>
              <p className={`text-sm mt-2 font-medium ${
                exportProgress.type === 'pdf' ? 'text-red-600' : 'text-orange-600'
              }`}>
                {Math.round(exportProgress.percent)}%
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default Toolbar;
