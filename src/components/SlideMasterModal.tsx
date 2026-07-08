import { X, Palette, Type, AlignCenter, AlignLeft, AlignRight, Calendar, Hash, FileText } from 'lucide-react';
import usePresentationStore from '../store/presentationStore';
import { SlideMaster } from '../types';

interface SlideMasterModalProps {
  onClose: () => void;
}

const SlideMasterModal = ({ onClose }: SlideMasterModalProps) => {
  const { presentation, updateMaster, applyMasterToSlides } = usePresentationStore();
  const master = presentation.master || {} as SlideMaster;

  const handleStyleChange = (section: 'titleStyle' | 'bodyStyle' | 'footerStyle', key: string, value: any) => {
    updateMaster({
      [section]: {
        ...(master[section] || {}),
        [key]: value,
      },
    });
  };

  const handleToggle = (key: keyof SlideMaster) => {
    updateMaster({ [key]: !master[key] });
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        <div className="bg-gradient-to-r from-indigo-600 to-purple-600 px-6 py-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <FileText size={20} />
              幻灯片母版设置
            </h2>
            <button onClick={onClose} className="text-white/80 hover:text-white">
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-6">
              <div className="bg-gray-50 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                  <Palette size={16} className="text-indigo-500" />
                  背景设置
                </h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">背景颜色</label>
                    <div className="flex items-center gap-3">
                      <input
                        type="color"
                        value={master.backgroundColor || '#ffffff'}
                        onChange={(e) => updateMaster({ backgroundColor: e.target.value })}
                        className="w-12 h-10 rounded-lg cursor-pointer border border-gray-200"
                      />
                      <input
                        type="text"
                        value={master.backgroundColor || '#ffffff'}
                        onChange={(e) => updateMaster({ backgroundColor: e.target.value })}
                        className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono"
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-gray-50 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                  <Type size={16} className="text-indigo-500" />
                  标题样式
                </h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">字号</label>
                    <input
                      type="range"
                      min="24"
                      max="72"
                      value={master.titleStyle?.fontSize || 48}
                      onChange={(e) => handleStyleChange('titleStyle', 'fontSize', Number(e.target.value))}
                      className="w-full"
                    />
                    <span className="text-xs text-gray-400">{master.titleStyle?.fontSize || 48}px</span>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">字体粗细</label>
                    <select
                      value={master.titleStyle?.fontWeight || '700'}
                      onChange={(e) => handleStyleChange('titleStyle', 'fontWeight', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                    >
                      <option value="400">正常</option>
                      <option value="500">中等</option>
                      <option value="600">半粗</option>
                      <option value="700">粗体</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">颜色</label>
                    <div className="flex items-center gap-3">
                      <input
                        type="color"
                        value={master.titleStyle?.color || '#1e3a5f'}
                        onChange={(e) => handleStyleChange('titleStyle', 'color', e.target.value)}
                        className="w-10 h-8 rounded cursor-pointer border border-gray-200"
                      />
                      <input
                        type="text"
                        value={master.titleStyle?.color || '#1e3a5f'}
                        onChange={(e) => handleStyleChange('titleStyle', 'color', e.target.value)}
                        className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-2">对齐方式</label>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleStyleChange('titleStyle', 'textAlign', 'left')}
                        className={`flex-1 px-3 py-2 rounded-lg text-sm transition-colors ${
                          master.titleStyle?.textAlign === 'left' 
                            ? 'bg-indigo-100 text-indigo-700' 
                            : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
                        }`}
                      >
                        <AlignLeft size={14} className="mx-auto" />
                      </button>
                      <button
                        onClick={() => handleStyleChange('titleStyle', 'textAlign', 'center')}
                        className={`flex-1 px-3 py-2 rounded-lg text-sm transition-colors ${
                          master.titleStyle?.textAlign === 'center' 
                            ? 'bg-indigo-100 text-indigo-700' 
                            : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
                        }`}
                      >
                        <AlignCenter size={14} className="mx-auto" />
                      </button>
                      <button
                        onClick={() => handleStyleChange('titleStyle', 'textAlign', 'right')}
                        className={`flex-1 px-3 py-2 rounded-lg text-sm transition-colors ${
                          master.titleStyle?.textAlign === 'right' 
                            ? 'bg-indigo-100 text-indigo-700' 
                            : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
                        }`}
                      >
                        <AlignRight size={14} className="mx-auto" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-gray-50 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                  <Type size={16} className="text-indigo-500" />
                  正文样式
                </h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">字号</label>
                    <input
                      type="range"
                      min="12"
                      max="32"
                      value={master.bodyStyle?.fontSize || 20}
                      onChange={(e) => handleStyleChange('bodyStyle', 'fontSize', Number(e.target.value))}
                      className="w-full"
                    />
                    <span className="text-xs text-gray-400">{master.bodyStyle?.fontSize || 20}px</span>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">颜色</label>
                    <div className="flex items-center gap-3">
                      <input
                        type="color"
                        value={master.bodyStyle?.color || '#374151'}
                        onChange={(e) => handleStyleChange('bodyStyle', 'color', e.target.value)}
                        className="w-10 h-8 rounded cursor-pointer border border-gray-200"
                      />
                      <input
                        type="text"
                        value={master.bodyStyle?.color || '#374151'}
                        onChange={(e) => handleStyleChange('bodyStyle', 'color', e.target.value)}
                        className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">行高</label>
                    <input
                      type="range"
                      min="1"
                      max="3"
                      step="0.1"
                      value={master.bodyStyle?.lineHeight || 1.8}
                      onChange={(e) => handleStyleChange('bodyStyle', 'lineHeight', Number(e.target.value))}
                      className="w-full"
                    />
                    <span className="text-xs text-gray-400">{master.bodyStyle?.lineHeight || 1.8}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-6">
              <div className="bg-gray-50 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                  <Type size={16} className="text-indigo-500" />
                  页脚样式
                </h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">字号</label>
                    <input
                      type="range"
                      min="10"
                      max="16"
                      value={master.footerStyle?.fontSize || 12}
                      onChange={(e) => handleStyleChange('footerStyle', 'fontSize', Number(e.target.value))}
                      className="w-full"
                    />
                    <span className="text-xs text-gray-400">{master.footerStyle?.fontSize || 12}px</span>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">颜色</label>
                    <div className="flex items-center gap-3">
                      <input
                        type="color"
                        value={master.footerStyle?.color || '#9ca3af'}
                        onChange={(e) => handleStyleChange('footerStyle', 'color', e.target.value)}
                        className="w-10 h-8 rounded cursor-pointer border border-gray-200"
                      />
                      <input
                        type="text"
                        value={master.footerStyle?.color || '#9ca3af'}
                        onChange={(e) => handleStyleChange('footerStyle', 'color', e.target.value)}
                        className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono"
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-gray-50 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                  <FileText size={16} className="text-indigo-500" />
                  页脚内容
                </h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-600 flex items-center gap-2">
                      <FileText size={14} />
                      显示页脚
                    </span>
                    <button
                      onClick={() => handleToggle('showFooter')}
                      className={`relative w-12 h-6 rounded-full transition-colors ${
                        master.showFooter ? 'bg-indigo-600' : 'bg-gray-300'
                      }`}
                    >
                      <div
                        className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform ${
                          master.showFooter ? 'left-7' : 'left-1'
                        }`}
                      />
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-600 flex items-center gap-2">
                      <Calendar size={14} />
                      显示日期
                    </span>
                    <button
                      onClick={() => handleToggle('showDate')}
                      className={`relative w-12 h-6 rounded-full transition-colors ${
                        master.showDate ? 'bg-indigo-600' : 'bg-gray-300'
                      }`}
                    >
                      <div
                        className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform ${
                          master.showDate ? 'left-7' : 'left-1'
                        }`}
                      />
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-600 flex items-center gap-2">
                      <Hash size={14} />
                      显示页码
                    </span>
                    <button
                      onClick={() => handleToggle('showPageNumber')}
                      className={`relative w-12 h-6 rounded-full transition-colors ${
                        master.showPageNumber ? 'bg-indigo-600' : 'bg-gray-300'
                      }`}
                    >
                      <div
                        className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform ${
                          master.showPageNumber ? 'left-7' : 'left-1'
                        }`}
                      />
                    </button>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">自定义页脚文本</label>
                    <input
                      type="text"
                      value={master.footerText || ''}
                      onChange={(e) => updateMaster({ footerText: e.target.value })}
                      placeholder="输入页脚文本..."
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                    />
                  </div>
                </div>
              </div>

              <div className="bg-gradient-to-br from-indigo-50 to-purple-50 rounded-xl p-4 border border-indigo-100">
                <h3 className="text-sm font-semibold text-indigo-700 mb-2">应用母版到所有幻灯片</h3>
                <p className="text-xs text-indigo-600 mb-4">
                  点击下方按钮将当前母版设置应用到所有幻灯片。标题样式将应用于顶部大字号文本，正文样式将应用于其他文本组件。
                </p>
                <button
                  onClick={applyMasterToSlides}
                  className="w-full px-4 py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 rounded-lg text-white text-sm font-medium hover:from-indigo-700 hover:to-purple-700 transition-all"
                >
                  应用到所有幻灯片
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="border-t border-gray-100 px-6 py-4 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors text-gray-700 text-sm font-medium"
          >
            取消
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 rounded-lg text-white text-sm font-medium hover:from-indigo-700 hover:to-purple-700 transition-all"
          >
            确定
          </button>
        </div>
      </div>
    </div>
  );
};

export default SlideMasterModal;
