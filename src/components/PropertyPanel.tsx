import { Type, Palette, AlignLeft, AlignCenter, AlignRight, AlignJustify, Timer, Play, BarChart3, PieChart, LineChart, Radar, Gauge, Funnel, Calendar, ScatterChart, Circle, MoveHorizontal, MoveVertical, Grid3X3, ArrowUpToLine, ArrowDownToLine, Minus } from 'lucide-react';
import usePresentationStore from '../store/presentationStore';
import { themes } from '../theme/themes';
import { animationPresets } from '../theme/animations';
import { AnimationType, EasingType, ChartType } from '../types';

const fontFamilies = ['Inter', 'Roboto', 'Noto Sans SC', 'Microsoft YaHei', 'SimHei', 'Arial'];
const fontWeights = ['400', '500', '600', '700', '800'];
const easingOptions: { value: EasingType; label: string }[] = [
  { value: 'ease', label: 'ease' },
  { value: 'easeIn', label: 'ease-in' },
  { value: 'easeOut', label: 'ease-out' },
  { value: 'easeInOut', label: 'ease-in-out' },
];

const chartTypes: { type: ChartType; label: string; icon: typeof BarChart3 }[] = [
  { type: 'bar', label: '柱状图', icon: BarChart3 },
  { type: 'bar-horizontal', label: '横向柱状图', icon: BarChart3 },
  { type: 'line', label: '折线图', icon: LineChart },
  { type: 'area', label: '面积图', icon: LineChart },
  { type: 'pie', label: '饼图', icon: PieChart },
  { type: 'radar', label: '雷达图', icon: Radar },
  { type: 'polar', label: '极坐标图', icon: Circle },
  { type: 'gauge', label: '仪表盘', icon: Gauge },
  { type: 'funnel', label: '漏斗图', icon: Funnel },
  { type: 'gantt', label: '甘特图', icon: Calendar },
  { type: 'scatter', label: '散点图', icon: ScatterChart },
];

const PropertyPanel = () => {
  const { presentation, selectedComponentId, updateComponent, deleteComponent, centerComponent, snapToGrid, alignComponents, distributeComponents } = usePresentationStore();
  
  const currentSlide = presentation.slides[presentation.currentSlideIndex];
  const selectedComponent = currentSlide?.components.find(c => c.id === selectedComponentId);
  const theme = themes[presentation.theme];

  if (!selectedComponent) {
    return (
      <div className="w-72 bg-white border-l border-gray-200 p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">属性</h3>
        <div className="flex flex-col items-center justify-center h-full text-gray-400">
          <div className="text-4xl mb-4">🎯</div>
          <div className="text-sm">选择一个组件</div>
          <div className="text-xs mt-2">查看和编辑属性</div>
        </div>
      </div>
    );
  }

  const handleStyleChange = (key: string, value: any) => {
    updateComponent(selectedComponent.id, {
      style: { ...selectedComponent.style, [key]: value },
    });
  };

  const handleAnimationChange = (key: string, value: any) => {
    updateComponent(selectedComponent.id, {
      animation: { ...selectedComponent.animation, [key]: value },
    });
  };

  return (
    <div className="w-72 bg-white border-l border-gray-200 flex flex-col">
      <div className="p-4 border-b border-gray-200">
        <h3 className="text-sm font-semibold text-gray-700">属性</h3>
        <div className="flex items-center justify-between mt-2">
          <span className="text-xs text-gray-500 capitalize">{selectedComponent.type}</span>
          <button 
            onClick={() => deleteComponent(selectedComponent.id)}
            className="text-red-500 hover:text-red-600 text-xs font-medium"
          >
            删除
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {selectedComponent.type === 'text' && (
          <div className="p-4 space-y-4">
            <div>
              <label className="flex items-center gap-2 text-xs font-medium text-gray-600 mb-2">
                <Type size={14} />
                字体
              </label>
              <select
                value={selectedComponent.style.fontFamily}
                onChange={(e) => handleStyleChange('fontFamily', e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {fontFamilies.map(font => (
                  <option key={font} value={font}>{font}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="flex items-center gap-2 text-xs font-medium text-gray-600 mb-2">
                <Type size={14} />
                字号
              </label>
              <input
                type="number"
                value={selectedComponent.style.fontSize}
                onChange={(e) => handleStyleChange('fontSize', parseInt(e.target.value) || 16)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                min={8}
                max={120}
              />
            </div>

            <div>
              <label className="flex items-center gap-2 text-xs font-medium text-gray-600 mb-2">
                <Type size={14} />
                字重
              </label>
              <select
                value={selectedComponent.style.fontWeight}
                onChange={(e) => handleStyleChange('fontWeight', e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {fontWeights.map(weight => (
                  <option key={weight} value={weight}>{weight} {weight === '400' ? '(常规)' : weight === '700' ? '(粗体)' : ''}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="flex items-center gap-2 text-xs font-medium text-gray-600 mb-2">
                <Palette size={14} />
                颜色
              </label>
              <div className="flex gap-2">
                <input
                  type="color"
                  value={selectedComponent.style.color}
                  onChange={(e) => handleStyleChange('color', e.target.value)}
                  className="w-10 h-10 rounded-lg border border-gray-300 cursor-pointer"
                />
                <input
                  type="text"
                  value={selectedComponent.style.color}
                  onChange={(e) => handleStyleChange('color', e.target.value)}
                  className="flex-1 px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div>
              <label className="flex items-center gap-2 text-xs font-medium text-gray-600 mb-2">
                对齐方式
              </label>
              <div className="flex gap-2">
                {[AlignLeft, AlignCenter, AlignRight, AlignJustify].map((Icon, index) => {
                  const alignments: ('left' | 'center' | 'right' | 'justify')[] = ['left', 'center', 'right', 'justify'];
                  return (
                    <button
                      key={index}
                      onClick={() => handleStyleChange('textAlign', alignments[index])}
                      className={`flex-1 p-2 rounded-lg border transition-colors ${
                        selectedComponent.style.textAlign === alignments[index]
                          ? 'border-blue-500 bg-blue-50 text-blue-600'
                          : 'border-gray-300 hover:bg-gray-50 text-gray-600'
                      }`}
                    >
                      <Icon size={16} />
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {selectedComponent.type === 'chart' && (
          <div className="p-4 space-y-4">
            <div>
              <label className="flex items-center gap-2 text-xs font-medium text-gray-600 mb-3">
                <BarChart3 size={14} />
                图表类型
              </label>
              <div className="grid grid-cols-3 gap-2">
                {chartTypes.map(({ type, label, icon: Icon }) => (
                  <button
                    key={type}
                    onClick={() => updateComponent(selectedComponent.id, {
                      data: { ...selectedComponent.data, type }
                    })}
                    className={`flex flex-col items-center gap-1 p-3 rounded-lg border transition-colors ${
                      selectedComponent.data?.type === type
                        ? 'border-blue-500 bg-blue-50 text-blue-600'
                        : 'border-gray-200 hover:border-gray-300 text-gray-600'
                    }`}
                  >
                    <Icon size={18} />
                    <span className="text-xs">{label}</span>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-gray-600 mb-2 block">图表标题</label>
              <input
                type="text"
                value={selectedComponent.data?.title || ''}
                onChange={(e) => updateComponent(selectedComponent.id, {
                  data: { ...selectedComponent.data, title: e.target.value }
                })}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="输入图表标题"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-600 mb-2 block">数据标签</label>
              <textarea
                value={(selectedComponent.data?.labels || []).join('\n')}
                onChange={(e) => updateComponent(selectedComponent.id, {
                  data: { ...selectedComponent.data, labels: e.target.value.split('\n').filter(l => l.trim()) }
                })}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 h-24 resize-none"
                placeholder="每行一个标签"
              />
            </div>
          </div>
        )}

        <div className="p-4 space-y-3 border-t border-gray-200">
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-gray-600">对齐工具</label>
            <button
              onClick={() => centerComponent(selectedComponent.id)}
              className="text-xs px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors"
            >
              居中
            </button>
          </div>
          <div className="grid grid-cols-3 gap-1">
            <button
              onClick={() => alignComponents('left')}
              className="p-2 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-gray-600"
              title="左对齐"
            >
              <AlignLeft size={16} />
            </button>
            <button
              onClick={() => alignComponents('center')}
              className="p-2 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-gray-600"
              title="水平居中"
            >
              <AlignCenter size={16} />
            </button>
            <button
              onClick={() => alignComponents('right')}
              className="p-2 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-gray-600"
              title="右对齐"
            >
              <AlignRight size={16} />
            </button>
            <button
              onClick={() => alignComponents('top')}
              className="p-2 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-gray-600"
              title="顶部对齐"
            >
              <ArrowUpToLine size={16} />
            </button>
            <button
              onClick={() => alignComponents('middle')}
              className="p-2 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-gray-600"
              title="垂直居中"
            >
              <Minus size={16} />
            </button>
            <button
              onClick={() => alignComponents('bottom')}
              className="p-2 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-gray-600"
              title="底部对齐"
            >
              <ArrowDownToLine size={16} />
            </button>
          </div>
          <div className="flex gap-1">
            <button
              onClick={() => distributeComponents('horizontal')}
              className="flex-1 p-2 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-gray-600 text-xs flex items-center justify-center gap-1"
              title="水平分布"
            >
              <MoveHorizontal size={14} />
              水平分布
            </button>
            <button
              onClick={() => distributeComponents('vertical')}
              className="flex-1 p-2 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-gray-600 text-xs flex items-center justify-center gap-1"
              title="垂直分布"
            >
              <MoveVertical size={14} />
              垂直分布
            </button>
          </div>
          <button
            onClick={() => snapToGrid(selectedComponent.id)}
            className="w-full p-2 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-gray-600 text-xs flex items-center justify-center gap-2"
          >
            <Grid3X3 size={14} />
            对齐到网格
          </button>
        </div>

        <div className="p-4 space-y-4 border-t border-gray-200">
          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-gray-600 mb-2">
              <Palette size={14} />
              背景色
            </label>
            <div className="flex gap-2">
              <input
                type="color"
                value={selectedComponent.style.backgroundColor}
                onChange={(e) => handleStyleChange('backgroundColor', e.target.value)}
                className="w-10 h-10 rounded-lg border border-gray-300 cursor-pointer"
              />
              <input
                type="text"
                value={selectedComponent.style.backgroundColor}
                onChange={(e) => handleStyleChange('backgroundColor', e.target.value)}
                className="flex-1 px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="transparent"
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-600 mb-2 block">圆角</label>
            <input
              type="range"
              value={selectedComponent.style.borderRadius}
              onChange={(e) => handleStyleChange('borderRadius', parseInt(e.target.value))}
              className="w-full"
              min={0}
              max={50}
            />
            <span className="text-xs text-gray-500">{selectedComponent.style.borderRadius}px</span>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-600 mb-2 block">边框宽度</label>
            <input
              type="range"
              value={selectedComponent.style.borderWidth}
              onChange={(e) => handleStyleChange('borderWidth', parseInt(e.target.value))}
              className="w-full"
              min={0}
              max={10}
            />
            <span className="text-xs text-gray-500">{selectedComponent.style.borderWidth}px</span>
          </div>

          {selectedComponent.style.borderWidth > 0 && (
            <div>
              <label className="flex items-center gap-2 text-xs font-medium text-gray-600 mb-2">
                <Palette size={14} />
                边框颜色
              </label>
              <div className="flex gap-2">
                <input
                  type="color"
                  value={selectedComponent.style.borderColor}
                  onChange={(e) => handleStyleChange('borderColor', e.target.value)}
                  className="w-10 h-10 rounded-lg border border-gray-300 cursor-pointer"
                />
                <input
                  type="text"
                  value={selectedComponent.style.borderColor}
                  onChange={(e) => handleStyleChange('borderColor', e.target.value)}
                  className="flex-1 px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          )}
        </div>

        <div className="p-4 space-y-4 border-t border-gray-200">
          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-gray-600 mb-2">
              <Play size={14} />
              动画效果
            </label>
            <select
              value={selectedComponent.animation.type}
              onChange={(e) => handleAnimationChange('type', e.target.value as AnimationType)}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {animationPresets.map(preset => (
                <option key={preset.type} value={preset.type}>{preset.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-gray-600 mb-2">
              <Timer size={14} />
              延迟
            </label>
            <input
              type="number"
              value={selectedComponent.animation.delay}
              onChange={(e) => handleAnimationChange('delay', parseInt(e.target.value) || 0)}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="ms"
            />
          </div>

          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-gray-600 mb-2">
              <Timer size={14} />
              持续时间
            </label>
            <input
              type="number"
              value={selectedComponent.animation.duration}
              onChange={(e) => handleAnimationChange('duration', parseInt(e.target.value) || 500)}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="ms"
            />
          </div>

          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-gray-600 mb-2">
              <Timer size={14} />
              缓动函数
            </label>
            <select
              value={selectedComponent.animation.easing}
              onChange={(e) => handleAnimationChange('easing', e.target.value as EasingType)}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {easingOptions.map(easing => (
                <option key={easing.value} value={easing.value}>{easing.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="p-4 border-t border-gray-200">
          <label className="text-xs font-medium text-gray-600 mb-2 block">位置</label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <span className="text-xs text-gray-500">X</span>
              <input
                type="number"
                value={selectedComponent.x}
                onChange={(e) => updateComponent(selectedComponent.id, { x: parseInt(e.target.value) || 0 })}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <span className="text-xs text-gray-500">Y</span>
              <input
                type="number"
                value={selectedComponent.y}
                onChange={(e) => updateComponent(selectedComponent.id, { y: parseInt(e.target.value) || 0 })}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        <div className="p-4 border-t border-gray-200">
          <label className="text-xs font-medium text-gray-600 mb-2 block">尺寸</label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <span className="text-xs text-gray-500">宽度</span>
              <input
                type="number"
                value={selectedComponent.width}
                onChange={(e) => updateComponent(selectedComponent.id, { width: parseInt(e.target.value) || 50 })}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                min={50}
              />
            </div>
            <div>
              <span className="text-xs text-gray-500">高度</span>
              <input
                type="number"
                value={selectedComponent.height}
                onChange={(e) => updateComponent(selectedComponent.id, { height: parseInt(e.target.value) || 50 })}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                min={50}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PropertyPanel;
