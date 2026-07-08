import { Type, Image, BarChart3, Square, Table, Video, Layout, AlignLeft, AlignCenter, AlignRight, AlignJustify, ArrowRightLeft, Maximize, Minimize, FlipVertical, FlipHorizontal, RefreshCw } from 'lucide-react';
import usePresentationStore from '../store/presentationStore';
import { ComponentType, TransitionType } from '../types';

const componentList = [
  { type: 'text' as ComponentType, icon: Type, label: '文本', color: 'bg-blue-100 text-blue-600' },
  { type: 'image' as ComponentType, icon: Image, label: '图片', color: 'bg-green-100 text-green-600' },
  { type: 'chart' as ComponentType, icon: BarChart3, label: '图表', color: 'bg-purple-100 text-purple-600' },
  { type: 'shape' as ComponentType, icon: Square, label: '形状', color: 'bg-orange-100 text-orange-600' },
  { type: 'table' as ComponentType, icon: Table, label: '表格', color: 'bg-pink-100 text-pink-600' },
  { type: 'media' as ComponentType, icon: Video, label: '媒体', color: 'bg-red-100 text-red-600' },
];

const alignmentList = [
  { icon: AlignLeft, label: '左对齐' },
  { icon: AlignCenter, label: '居中' },
  { icon: AlignRight, label: '右对齐' },
  { icon: AlignJustify, label: '两端对齐' },
];

const layoutList = [
  { name: '标题', icon: Layout, template: 'title', description: '单栏标题' },
  { name: '标题+内容', icon: Layout, template: 'titleContent', description: '上下布局' },
  { name: '双栏', icon: Layout, template: 'twoColumn', description: '左右分栏' },
  { name: '三栏', icon: Layout, template: 'threeColumn', description: '三列布局' },
  { name: '标题+双栏', icon: Layout, template: 'titleTwoColumn', description: '标题+左右' },
  { name: '图表页', icon: Layout, template: 'titleChart', description: '标题+图表' },
  { name: '对比分析', icon: Layout, template: 'comparison', description: '数据表格' },
];

const transitionList: { type: TransitionType; label: string; icon: typeof ArrowRightLeft }[] = [
  { type: 'fade', label: '淡入', icon: ArrowRightLeft },
  { type: 'slide-left', label: '左滑', icon: ArrowRightLeft },
  { type: 'slide-right', label: '右滑', icon: ArrowRightLeft },
  { type: 'slide-up', label: '上滑', icon: ArrowRightLeft },
  { type: 'slide-down', label: '下滑', icon: ArrowRightLeft },
  { type: 'zoom-in', label: '放大', icon: Maximize },
  { type: 'zoom-out', label: '缩小', icon: Minimize },
  { type: 'cube', label: '立方体', icon: FlipVertical },
  { type: 'flip', label: '翻转', icon: FlipHorizontal },
  { type: 'rotate', label: '旋转', icon: RefreshCw },
];

const Sidebar = () => {
  const { presentation, addComponent, updateSlideTransition, applyLayoutTemplate } = usePresentationStore();
  const currentSlideIndex = presentation.currentSlideIndex;
  const currentSlide = presentation.slides[currentSlideIndex];

  const handleAddComponent = (type: ComponentType) => {
    addComponent(currentSlideIndex, type, 100, 100);
  };

  const handleTransitionChange = (type: TransitionType) => {
    updateSlideTransition(currentSlideIndex, type);
  };

  const handleLayoutTemplate = (templateName: string) => {
    applyLayoutTemplate(currentSlideIndex, templateName);
  };

  return (
    <div className="w-60 bg-white border-r border-gray-200 flex flex-col">
      <div className="p-4 border-b border-gray-200">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">组件库</h3>
        <div className="grid grid-cols-3 gap-2">
          {componentList.map((item) => (
            <button
              key={item.type}
              onClick={() => handleAddComponent(item.type)}
              className="flex flex-col items-center gap-1 p-3 rounded-xl hover:bg-gray-50 transition-all hover:shadow-sm group"
            >
              <div className={`p-2.5 rounded-lg ${item.color} group-hover:scale-110 transition-transform`}>
                <item.icon size={20} />
              </div>
              <span className="text-xs text-gray-600">{item.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="p-4 border-b border-gray-200">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">切换效果</h3>
        <div className="grid grid-cols-5 gap-1.5">
          {transitionList.map((item) => (
            <button
              key={item.type}
              onClick={() => handleTransitionChange(item.type)}
              className={`p-2 rounded-lg transition-all ${
                currentSlide?.transition === item.type
                  ? 'bg-blue-500 text-white shadow-md'
                  : 'bg-gray-50 hover:bg-gray-100 text-gray-600'
              }`}
              title={item.label}
            >
              <item.icon size={16} />
            </button>
          ))}
        </div>
        <div className="text-xs text-gray-500 mt-2 text-center">
          当前: {transitionList.find(t => t.type === currentSlide?.transition)?.label || '无'}
        </div>
      </div>

      <div className="p-4 border-b border-gray-200">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">对齐方式</h3>
        <div className="flex gap-2">
          {alignmentList.map((item, index) => (
            <button
              key={index}
              className="flex-1 p-2.5 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-gray-600"
              title={item.label}
            >
              <item.icon size={18} />
            </button>
          ))}
        </div>
      </div>

      <div className="p-4 flex-1 overflow-y-auto">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">布局模板</h3>
        <div className="space-y-2">
          {layoutList.map((item, index) => (
            <button
              key={index}
              onClick={() => handleLayoutTemplate(item.template)}
              className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-blue-50 hover:border-blue-200 border border-transparent transition-all text-left group"
            >
              <div className="p-2 rounded-lg bg-gray-100 group-hover:bg-blue-100 group-hover:text-blue-600 transition-colors">
                <item.icon size={18} className="text-gray-600" />
              </div>
              <div>
                <div className="text-sm font-medium text-gray-700 group-hover:text-blue-700 transition-colors">{item.name}</div>
                <div className="text-xs text-gray-500">{item.description}</div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
