import { useState } from 'react';
import { X, Check, Sparkles, Layout, Palette } from 'lucide-react';
import { templates, Template } from '../templates/templates';
import usePresentationStore from '../store/presentationStore';
import { PresentationGenerationSkill } from '../skill';

interface TemplateSelectorProps {
  onClose: () => void;
}

const layoutLabels: Record<Template['layout'], string> = {
  classic: '经典',
  modern: '现代',
  minimal: '极简',
  creative: '创意',
};

const TemplateSelector = ({ onClose }: TemplateSelectorProps) => {
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  const [filterLayout, setFilterLayout] = useState<Template['layout'] | 'all'>('all');
  const { importPresentation, setLoading, setError } = usePresentationStore();

  const filteredTemplates = filterLayout === 'all' 
    ? templates 
    : templates.filter(t => t.layout === filterLayout);

  const handleSelectTemplate = (template: Template) => {
    setSelectedTemplate(template);
  };

  const handleCreate = async () => {
    if (!selectedTemplate) return;
    
    setLoading(true);
    
    try {
      const skill = new PresentationGenerationSkill();
      const result = await skill.execute({
        business_domain: selectedTemplate.name + '演示',
        objectives_detail: [],
        metrics: [],
        charts: [],
        risks: [],
        growth_opportunities: [],
      }, { theme: selectedTemplate.theme });

      if (result.success && result.data.presentation) {
        importPresentation(result.data.presentation);
      }
      
      onClose();
    } catch (error) {
      setError('创建失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl mx-4 overflow-hidden">
        <div className="bg-gradient-to-r from-purple-500 to-pink-500 px-6 py-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Sparkles size={20} />
              选择演示模板
            </h2>
            <button onClick={onClose} className="text-white/80 hover:text-white">
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="p-6">
          <div className="flex items-center gap-4 mb-6">
            <div className="flex items-center gap-2">
              <Layout size={18} className="text-gray-500" />
              <span className="text-sm text-gray-600">布局筛选:</span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setFilterLayout('all')}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  filterLayout === 'all' 
                    ? 'bg-purple-500 text-white' 
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                全部
              </button>
              {(Object.keys(layoutLabels) as Template['layout'][]).map(layout => (
                <button
                  key={layout}
                  onClick={() => setFilterLayout(layout)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    filterLayout === layout 
                      ? 'bg-purple-500 text-white' 
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {layoutLabels[layout]}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredTemplates.map(template => (
              <div
                key={template.id}
                onClick={() => handleSelectTemplate(template)}
                className={`relative cursor-pointer rounded-xl overflow-hidden border-2 transition-all hover:shadow-lg ${
                  selectedTemplate?.id === template.id 
                    ? 'border-purple-500 shadow-lg' 
                    : 'border-gray-200 hover:border-purple-300'
                }`}
              >
                <div className="aspect-video bg-gray-100">
                  <img 
                    src={template.thumbnail} 
                    alt={template.name}
                    className="w-full h-full object-cover"
                  />
                </div>
                <div className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-semibold text-gray-800">{template.name}</h3>
                    {selectedTemplate?.id === template.id && (
                      <Check size={20} className="text-purple-500" />
                    )}
                  </div>
                  <p className="text-sm text-gray-500 mb-3">{template.description}</p>
                  <div className="flex items-center gap-2">
                    <Palette size={14} className="text-gray-400" />
                    <div className="flex gap-1">
                      <div 
                        className="w-4 h-4 rounded-full border border-gray-200"
                        style={{ backgroundColor: template.colors.primary }}
                      />
                      <div 
                        className="w-4 h-4 rounded-full border border-gray-200"
                        style={{ backgroundColor: template.colors.secondary }}
                      />
                      <div 
                        className="w-4 h-4 rounded-full border border-gray-200"
                        style={{ backgroundColor: template.colors.accent }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="flex gap-3 mt-6">
            <button
              onClick={onClose}
              className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl hover:bg-gray-50 transition-colors text-gray-700 text-sm font-medium"
            >
              取消
            </button>
            <button
              onClick={handleCreate}
              disabled={!selectedTemplate}
              className="flex-1 px-4 py-2.5 bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl hover:from-purple-600 hover:to-pink-600 transition-all text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Sparkles size={16} />
              创建演示文稿
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TemplateSelector;