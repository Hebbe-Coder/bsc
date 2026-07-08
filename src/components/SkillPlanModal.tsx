import { useState, useEffect } from 'react';
import { X, Play, CheckCircle, Loader2, AlertCircle, ChevronRight, Sparkles, FileText, Target, BarChart3, PieChart, Presentation } from 'lucide-react';
import { skillManager, SkillPlan, SkillTask, SkillStatus } from '../skill';
import usePresentationStore from '../store/presentationStore';

interface SkillPlanModalProps {
  onClose: () => void;
  prdContent: string;
}

const iconMap: Record<string, any> = {
  'FileText': FileText,
  'Target': Target,
  'BarChart3': BarChart3,
  'PieChart': PieChart,
  'Presentation': Presentation,
};

const statusConfig: Record<SkillStatus, { color: string; label: string; bg: string }> = {
  idle: { color: '#9ca3af', label: '待执行', bg: 'bg-gray-100' },
  running: { color: '#3b82f6', label: '执行中', bg: 'bg-blue-100' },
  completed: { color: '#22c55e', label: '已完成', bg: 'bg-green-100' },
  failed: { color: '#ef4444', label: '失败', bg: 'bg-red-100' },
  waiting: { color: '#f59e0b', label: '等待中', bg: 'bg-amber-100' },
};

const SkillPlanModal = ({ onClose, prdContent }: SkillPlanModalProps) => {
  const [plan, setPlan] = useState<SkillPlan | null>(null);
  const [status, setStatus] = useState<'draft' | 'confirmed' | 'executing' | 'completed'>('draft');
  const [logs, setLogs] = useState<string[]>([]);
  const { importPresentation, setLoading, setError } = usePresentationStore();

  useEffect(() => {
    const skills = skillManager.getAllSkills();
    const tasks: Omit<SkillTask, 'status' | 'result'>[] = [
      {
        id: 'task-prd',
        skillId: 'prd-analysis',
        name: skills.find(s => s.id === 'prd-analysis')?.name || 'PRD分析',
        description: skills.find(s => s.id === 'prd-analysis')?.description || '',
        params: { prdContent },
        dependsOn: [],
      },
      {
        id: 'task-objective',
        skillId: 'objective-extraction',
        name: skills.find(s => s.id === 'objective-extraction')?.name || '目标提取',
        description: skills.find(s => s.id === 'objective-extraction')?.description || '',
        params: {},
        dependsOn: ['task-prd'],
      },
      {
        id: 'task-kpi',
        skillId: 'kpi-extraction',
        name: skills.find(s => s.id === 'kpi-extraction')?.name || 'KPI提取',
        description: skills.find(s => s.id === 'kpi-extraction')?.description || '',
        params: {},
        dependsOn: ['task-objective'],
      },
      {
        id: 'task-chart',
        skillId: 'chart-generation',
        name: skills.find(s => s.id === 'chart-generation')?.name || '图表生成',
        description: skills.find(s => s.id === 'chart-generation')?.description || '',
        params: {},
        dependsOn: ['task-kpi'],
      },
      {
        id: 'task-risk',
        skillId: 'risk-assessment',
        name: skills.find(s => s.id === 'risk-assessment')?.name || '风险评估',
        description: skills.find(s => s.id === 'risk-assessment')?.description || '',
        params: {},
        dependsOn: ['task-prd'],
      },
      {
        id: 'task-strategy',
        skillId: 'strategy-analysis',
        name: skills.find(s => s.id === 'strategy-analysis')?.name || '战略分析',
        description: skills.find(s => s.id === 'strategy-analysis')?.description || '',
        params: {},
        dependsOn: ['task-objective'],
      },
      {
        id: 'task-report',
        skillId: 'report-generation',
        name: skills.find(s => s.id === 'report-generation')?.name || '报告生成',
        description: skills.find(s => s.id === 'report-generation')?.description || '',
        params: {},
        dependsOn: ['task-risk', 'task-strategy'],
      },
      {
        id: 'task-presentation',
        skillId: 'presentation-generation',
        name: skills.find(s => s.id === 'presentation-generation')?.name || '演示文稿生成',
        description: skills.find(s => s.id === 'presentation-generation')?.description || '',
        params: {},
        dependsOn: ['task-chart', 'task-risk', 'task-strategy'],
      },
    ];

    setPlan(skillManager.createPlan(tasks));
  }, [prdContent]);

  const handleConfirm = () => {
    if (!plan) return;
    setStatus('confirmed');
    setLogs(['计划已确认，准备执行...']);
  };

  const handleExecute = async () => {
    if (!plan) return;

    setStatus('executing');
    setLoading(true);
    setError(null);

    try {
      const updatedPlan = await skillManager.executePlan(plan);
      setPlan(updatedPlan);
      setStatus('completed');

      const presentationTask = updatedPlan.tasks.find(t => t.skillId === 'presentation-generation');
      if (presentationTask?.result?.success && presentationTask.result.data.presentation) {
        importPresentation(presentationTask.result.data.presentation);
        setLogs([...logs, '演示文稿生成成功！']);
      }
    } catch (error) {
      setError('执行失败');
      setLogs([...logs, `执行失败: ${error instanceof Error ? error.message : 'Unknown error'}`]);
    } finally {
      setLoading(false);
    }
  };

  const completedCount = plan?.tasks.filter(t => t.status === 'completed').length || 0;
  const totalCount = plan?.tasks.length || 0;
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 overflow-hidden">
        <div className="bg-gradient-to-r from-purple-500 to-pink-500 px-6 py-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Sparkles size={20} />
              AI智能生成计划
            </h2>
            <button onClick={onClose} className="text-white/80 hover:text-white">
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="p-6">
          {status === 'draft' && (
            <div className="mb-6">
              <p className="text-gray-600 text-sm mb-4">AI将按照以下步骤执行，确认后开始生成演示文稿：</p>
            </div>
          )}

          {status === 'executing' && (
            <div className="mb-6">
              <div className="flex justify-between text-sm text-gray-600 mb-2">
                <span>执行进度</span>
                <span>{completedCount}/{totalCount} ({Math.round(progress)}%)</span>
              </div>
              <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-gradient-to-r from-purple-500 to-pink-500 transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          <div className="space-y-3 mb-6 max-h-80 overflow-y-auto">
            {plan?.tasks.map((task, idx) => {
              const config = statusConfig[task.status];
              const IconComponent = iconMap[task.skillId.split('-')[0].charAt(0).toUpperCase() + task.skillId.split('-')[0].slice(1)] || FileText;
              
              return (
                <div 
                  key={task.id}
                  className={`flex items-center gap-4 p-4 rounded-xl border-2 transition-all ${
                    task.status === 'running' ? 'border-blue-500 bg-blue-50' :
                    task.status === 'completed' ? 'border-green-500 bg-green-50' :
                    task.status === 'failed' ? 'border-red-500 bg-red-50' :
                    'border-gray-100 bg-gray-50'
                  }`}
                >
                  <div className="flex-shrink-0">
                    {task.status === 'completed' ? (
                      <CheckCircle size={24} className="text-green-500" />
                    ) : task.status === 'running' ? (
                      <Loader2 size={24} className="text-blue-500 animate-spin" />
                    ) : task.status === 'failed' ? (
                      <AlertCircle size={24} className="text-red-500" />
                    ) : (
                      <span className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-sm font-bold text-gray-600">
                        {idx + 1}
                      </span>
                    )}
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <IconComponent size={18} className="text-gray-500" />
                      <span className="font-medium text-gray-800">{task.name}</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${config.bg}`} style={{ color: config.color }}>
                        {config.label}
                      </span>
                    </div>
                    <p className="text-sm text-gray-500 mt-1">{task.description}</p>
                    {task.dependsOn.length > 0 && (
                      <p className="text-xs text-gray-400 mt-1">
                        依赖: {plan?.tasks.filter(t => task.dependsOn.includes(t.id)).map(t => t.name).join(', ')}
                      </p>
                    )}
                  </div>

                  <ChevronRight size={20} className="text-gray-400" />
                </div>
              );
            })}
          </div>

          {logs.length > 0 && (
            <div className="mb-6 p-4 bg-gray-900 rounded-xl text-sm font-mono text-gray-300 max-h-32 overflow-y-auto">
              {logs.map((log, idx) => (
                <div key={idx} className="flex gap-2">
                  <span className="text-purple-400">{'>'}</span>
                  <span>{log}</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-3">
            {status === 'draft' && (
              <>
                <button
                  onClick={onClose}
                  className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl hover:bg-gray-50 transition-colors text-gray-700 text-sm font-medium"
                >
                  取消
                </button>
                <button
                  onClick={handleConfirm}
                  className="flex-1 px-4 py-2.5 bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl hover:from-purple-600 hover:to-pink-600 transition-all text-white text-sm font-medium flex items-center justify-center gap-2"
                >
                  <CheckCircle size={16} />
                  确认计划
                </button>
              </>
            )}

            {status === 'confirmed' && (
              <>
                <button
                  onClick={() => setStatus('draft')}
                  className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl hover:bg-gray-50 transition-colors text-gray-700 text-sm font-medium"
                >
                  返回修改
                </button>
                <button
                  onClick={handleExecute}
                  className="flex-1 px-4 py-2.5 bg-gradient-to-r from-green-500 to-emerald-500 rounded-xl hover:from-green-600 hover:to-emerald-600 transition-all text-white text-sm font-medium flex items-center justify-center gap-2"
                >
                  <Play size={16} />
                  开始执行
                </button>
              </>
            )}

            {status === 'executing' && (
              <button
                disabled
                className="flex-1 px-4 py-2.5 bg-gray-400 rounded-xl text-white text-sm font-medium flex items-center justify-center gap-2"
              >
                <Loader2 size={16} className="animate-spin" />
                执行中...
              </button>
            )}

            {status === 'completed' && (
              <>
                <button
                  onClick={onClose}
                  className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl hover:bg-gray-50 transition-colors text-gray-700 text-sm font-medium"
                >
                  返回
                </button>
                <button
                  onClick={onClose}
                  className="flex-1 px-4 py-2.5 bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl hover:from-purple-600 hover:to-pink-600 transition-all text-white text-sm font-medium"
                >
                  查看结果
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SkillPlanModal;