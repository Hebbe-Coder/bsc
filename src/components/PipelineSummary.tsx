import React from 'react';
import { CheckCircle2, Target, Clock, AlertTriangle, Presentation, Zap, TrendingUp, FileText, Users, Shield } from 'lucide-react';
import { BusinessSystem } from '../api/bscApi';

interface PipelineSummaryProps {
  businessSystem: BusinessSystem;
  slideCount: number;
}

const PipelineSummary: React.FC<PipelineSummaryProps> = ({ businessSystem, slideCount }) => {
  const priorityColors: Record<string, string> = {
    '高': 'bg-red-100 text-red-600 border-red-200',
    '中': 'bg-yellow-100 text-yellow-600 border-yellow-200',
    '低': 'bg-green-100 text-green-600 border-green-200',
  };

  const severityColors: Record<string, string> = {
    '严重': 'bg-red-100 text-red-600',
    '高': 'bg-orange-100 text-orange-600',
    '中': 'bg-yellow-100 text-yellow-600',
    '低': 'bg-green-100 text-green-600',
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-white/20 rounded-xl p-2">
              <Presentation className="w-6 h-6 text-white" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">编译结果汇总</h3>
              <p className="text-white/70 text-sm">{businessSystem.name || '业务系统'} - 完整业务分析报告</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-white">
            <Zap className="w-4 h-4" />
            <span className="text-sm font-medium">生成 {slideCount} 页演示文稿</span>
          </div>
        </div>
      </div>

      <div className="p-6">
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-4">
            <div className="flex items-center gap-2 text-blue-600 mb-2">
              <Target className="w-5 h-5" />
              <span className="text-xs font-medium">核心目标</span>
            </div>
            <div className="text-2xl font-bold text-blue-700">{businessSystem.objectives?.length || 0}</div>
          </div>
          
          <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-4">
            <div className="flex items-center gap-2 text-purple-600 mb-2">
              <Clock className="w-5 h-5" />
              <span className="text-xs font-medium">流程步骤</span>
            </div>
            <div className="text-2xl font-bold text-purple-700">{businessSystem.workflow?.length || 0}</div>
          </div>
          
          <div className="bg-gradient-to-br from-orange-50 to-orange-100 rounded-xl p-4">
            <div className="flex items-center gap-2 text-orange-600 mb-2">
              <AlertTriangle className="w-5 h-5" />
              <span className="text-xs font-medium">潜在风险</span>
            </div>
            <div className="text-2xl font-bold text-orange-700">{businessSystem.risks?.length || 0}</div>
          </div>
          
          <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-xl p-4">
            <div className="flex items-center gap-2 text-green-600 mb-2">
              <TrendingUp className="w-5 h-5" />
              <span className="text-xs font-medium">KPI指标</span>
            </div>
            <div className="text-2xl font-bold text-green-700">
              {businessSystem.objectives?.filter(o => o.kpi).length || 0}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center">
                <Target className="w-4 h-4 text-blue-600" />
              </div>
              <h4 className="font-semibold text-gray-800">核心目标</h4>
            </div>
            
            <div className="space-y-3">
              {businessSystem.objectives?.map((objective, index) => (
                <div 
                  key={index}
                  className="bg-gray-50 rounded-xl p-4 border border-gray-100 hover:border-blue-200 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="font-medium text-gray-800">{objective.objective}</div>
                      <div className="text-sm text-gray-500 mt-1">目标: {objective.target}</div>
                      {objective.kpi && (
                        <div className="text-sm text-blue-600 mt-1 flex items-center gap-1">
                          <Zap size={12} />
                          KPI: {objective.kpi}
                        </div>
                      )}
                    </div>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium border ${priorityColors[objective.priority || '中']}`}>
                      {objective.priority || '中'}
                    </span>
                  </div>
                </div>
              )) || (
                <div className="text-center py-8 text-gray-400">暂无目标数据</div>
              )}
            </div>
          </div>

          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-purple-100 flex items-center justify-center">
                <Clock className="w-4 h-4 text-purple-600" />
              </div>
              <h4 className="font-semibold text-gray-800">业务流程</h4>
            </div>
            
            <div className="relative">
              <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-200" />
              
              <div className="space-y-4">
                {businessSystem.workflow?.map((step, index) => (
                  <div key={index} className="relative pl-10">
                    <div className={`absolute left-2 w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                      index === 0 
                        ? 'border-blue-500 bg-blue-500' 
                        : index === businessSystem.workflow.length - 1
                          ? 'border-green-500 bg-green-500'
                          : 'border-purple-500 bg-white'
                    }`}>
                      {index > 0 && index < businessSystem.workflow.length - 1 && (
                        <div className="w-2 h-2 rounded-full bg-purple-500" />
                      )}
                      {index === 0 && <CheckCircle2 className="w-3 h-3 text-white" />}
                      {index === businessSystem.workflow.length - 1 && <CheckCircle2 className="w-3 h-3 text-white" />}
                    </div>
                    
                    <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-medium text-gray-400">步骤 {step.step}</span>
                        <span className="font-medium text-gray-800">{step.name}</span>
                      </div>
                      <div className="text-sm text-gray-500">{step.action}</div>
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
                        {step.owner && (
                          <span className="flex items-center gap-1">
                            <Users size={12} />
                            {step.owner}
                          </span>
                        )}
                        {step.sla && (
                          <span className="flex items-center gap-1">
                            <Clock size={12} />
                            SLA: {step.sla}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )) || (
                  <div className="text-center py-8 text-gray-400">暂无流程数据</div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-8 h-8 rounded-lg bg-orange-100 flex items-center justify-center">
              <AlertTriangle className="w-4 h-4 text-orange-600" />
            </div>
            <h4 className="font-semibold text-gray-800">风险评估</h4>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {businessSystem.risks?.map((risk, index) => (
              <div 
                key={index}
                className="bg-gradient-to-br from-orange-50 to-red-50 rounded-xl p-4 border border-orange-100 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between mb-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${severityColors[risk.severity] || severityColors['中']}`}>
                    {risk.severity}
                  </span>
                  {risk.category && (
                    <span className="text-xs text-gray-400">{risk.category}</span>
                  )}
                </div>
                <div className="font-medium text-gray-800 mb-2">{risk.risk}</div>
                <div className="flex items-start gap-2">
                  <Shield className="w-4 h-4 text-green-600 mt-0.5 flex-shrink-0" />
                  <p className="text-sm text-gray-600">应对策略: {risk.mitigation}</p>
                </div>
              </div>
            )) || (
              <div className="col-span-full text-center py-8 text-gray-400">暂无风险数据</div>
            )}
          </div>
        </div>

        {businessSystem.description && (
          <div className="mt-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center">
                <FileText className="w-4 h-4 text-indigo-600" />
              </div>
              <h4 className="font-semibold text-gray-800">业务概述</h4>
            </div>
            <div className="bg-indigo-50 rounded-xl p-4 border border-indigo-100">
              <p className="text-gray-700 leading-relaxed">{businessSystem.description}</p>
            </div>
          </div>
        )}

        <div className="mt-6 pt-4 border-t border-gray-100 flex items-center justify-between">
          <div className="flex items-center gap-4 text-sm text-gray-500">
            <span>📋 业务名称: {businessSystem.name || '未命名'}</span>
            {businessSystem.version && <span>🔖 版本: {businessSystem.version}</span>}
          </div>
          <div className="flex items-center gap-2 text-green-600">
            <CheckCircle2 className="w-4 h-4" />
            <span className="text-sm font-medium">编译完成</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PipelineSummary;