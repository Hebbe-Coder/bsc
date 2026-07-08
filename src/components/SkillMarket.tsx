import { useState } from 'react';
import { X, Search, Play, Clock, Zap, CheckCircle, FileText, Target, BarChart3, PieChart, Presentation, AlertTriangle, TrendingUp, Sparkles } from 'lucide-react';
import { skillManager, SkillConfig } from '../skill';

interface SkillMarketProps {
  onClose: () => void;
}

const iconMap: Record<string, React.ComponentType<{ size?: number | string }>> = {
  FileText,
  Target,
  BarChart3,
  PieChart,
  Presentation,
  AlertTriangle,
  TrendingUp,
  Sparkles,
};

const categoryLabels: Record<SkillConfig['category'], { label: string; color: string; bg: string }> = {
  analysis: { label: '分析', color: '#3b82f6', bg: 'bg-blue-100' },
  generation: { label: '生成', color: '#ec4899', bg: 'bg-pink-100' },
  visualization: { label: '可视化', color: '#8b5cf6', bg: 'bg-purple-100' },
  export: { label: '导出', color: '#10b981', bg: 'bg-green-100' },
  data: { label: '数据', color: '#f59e0b', bg: 'bg-amber-100' },
};

const SkillMarket = ({ onClose }: SkillMarketProps) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<SkillConfig['category'] | 'all'>('all');
  const [selectedSkill, setSelectedSkill] = useState<SkillConfig | null>(null);

  const skills = skillManager.getAllSkills();
  
  const filteredSkills = skills.filter(skill => {
    const matchesSearch = skill.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         skill.description.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = selectedCategory === 'all' || skill.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const handleExecuteSkill = (skill: SkillConfig) => {
    setSelectedSkill(skill);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl mx-4 overflow-hidden h-[80vh]">
        <div className="bg-gradient-to-r from-purple-500 to-pink-500 px-6 py-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Sparkles size={20} />
              技能市场
            </h2>
            <button onClick={onClose} className="text-white/80 hover:text-white">
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="flex border-b border-gray-200">
          <div className="flex-1 p-4">
            <div className="relative">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="搜索技能..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-100"
              />
            </div>
          </div>
          <div className="flex items-center gap-2 p-4 border-l border-gray-200">
            <button
              onClick={() => setSelectedCategory('all')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                selectedCategory === 'all' 
                  ? 'bg-purple-500 text-white' 
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              全部
            </button>
            {(Object.keys(categoryLabels) as SkillConfig['category'][]).map(category => (
              <button
                key={category}
                onClick={() => setSelectedCategory(category)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  selectedCategory === category 
                    ? 'bg-purple-500 text-white' 
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {categoryLabels[category].label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredSkills.map(skill => {
              const IconComponent = iconMap[skill.icon] || Sparkles;
              const categoryInfo = categoryLabels[skill.category];
              
              return (
                <div
                  key={skill.id}
                  onClick={() => handleExecuteSkill(skill)}
                  className={`relative cursor-pointer rounded-xl p-4 border-2 transition-all hover:shadow-lg ${
                    selectedSkill?.id === skill.id 
                      ? 'border-purple-500 shadow-lg' 
                      : 'border-gray-100 hover:border-purple-300'
                  }`}
                >
                  <div className="flex items-start gap-4">
                    <div className={`w-12 h-12 rounded-xl ${categoryInfo.bg} flex items-center justify-center`}>
                      <IconComponent size={24} style={{ color: categoryInfo.color }} />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <h3 className="font-semibold text-gray-800">{skill.name}</h3>
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${categoryInfo.bg}`} style={{ color: categoryInfo.color }}>
                          {categoryInfo.label}
                        </span>
                      </div>
                      <p className="text-sm text-gray-500 mb-3">{skill.description}</p>
                      <div className="flex items-center gap-4 text-xs text-gray-400">
                        <span className="flex items-center gap-1">
                          <Zap size={14} />
                          {skill.produces.length}个产出
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock size={14} />
                          自动执行
                        </span>
                      </div>
                    </div>
                    <button className="p-2 rounded-lg bg-purple-50 text-purple-500 hover:bg-purple-100 transition-colors">
                      <Play size={18} />
                    </button>
                  </div>
                  {skill.requires.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-100">
                      <p className="text-xs text-gray-400 mb-2">依赖技能:</p>
                      <div className="flex flex-wrap gap-2">
                        {skill.requires.map(req => (
                          <span key={req} className="px-2 py-1 bg-gray-100 rounded-lg text-xs text-gray-600">
                            {req}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {filteredSkills.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-gray-400">
              <Search size={48} className="mb-4" />
              <p>没有找到匹配的技能</p>
              <p className="text-sm mt-1">尝试更换搜索关键词或筛选条件</p>
            </div>
          )}
        </div>

        <div className="border-t border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6 text-sm text-gray-500">
              <span className="flex items-center gap-2">
                <CheckCircle size={16} className="text-green-500" />
                已加载 {skills.length} 个技能
              </span>
              <span className="flex items-center gap-2">
                <Zap size={16} className="text-yellow-500" />
                支持自动执行
              </span>
            </div>
            <button
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 rounded-xl hover:bg-gray-50 transition-colors text-gray-700 text-sm font-medium"
            >
              关闭
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SkillMarket;