import React, { useState } from 'react';
import { PipelineStage } from '../store/presentationStore';
import { CheckCircle2, Circle, Loader2, XCircle, ChevronRight, Info, Clock, TrendingUp, AlertTriangle, RotateCcw } from 'lucide-react';

interface PipelineVisualizationProps {
  stages: PipelineStage[];
  isCompiling: boolean;
  onCancel: () => void;
  onReset: () => void;
  onRetryStage?: (stageId: string) => Promise<void>;
}

const PipelineVisualization: React.FC<PipelineVisualizationProps> = ({ stages, isCompiling, onCancel, onReset, onRetryStage }) => {
  const [hoveredStage, setHoveredStage] = useState<string | null>(null);
  const [expandedStage, setExpandedStage] = useState<string | null>(null);
  const [retryingStage, setRetryingStage] = useState<string | null>(null);

  const getStatusColor = (status: PipelineStage['status']) => {
    switch (status) {
      case 'completed':
        return {
          bg: 'bg-green-50',
          border: 'border-green-500',
          icon: 'text-green-500',
          line: '#22c55e',
          glow: 'drop-shadow-[0_0_8px_rgba(34,197,94,0.5)]',
        };
      case 'running':
        return {
          bg: 'bg-blue-50',
          border: 'border-blue-500',
          icon: 'text-blue-500',
          line: '#3b82f6',
          glow: 'drop-shadow-[0_0_8px_rgba(59,130,246,0.5)]',
        };
      case 'failed':
        return {
          bg: 'bg-red-50',
          border: 'border-red-500',
          icon: 'text-red-500',
          line: '#ef4444',
          glow: 'drop-shadow-[0_0_8px_rgba(239,68,68,0.5)]',
        };
      default:
        return {
          bg: 'bg-gray-50',
          border: 'border-gray-300',
          icon: 'text-gray-400',
          line: '#e5e7eb',
          glow: 'none',
        };
    }
  };

  const getStatusIcon = (status: PipelineStage['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-6 h-6" />;
      case 'running':
        return <Loader2 className="w-6 h-6 animate-spin" />;
      case 'failed':
        return <XCircle className="w-6 h-6" />;
      default:
        return <Circle className="w-6 h-6" />;
    }
  };

  const formatDuration = (startTime?: number, endTime?: number) => {
    if (!startTime) return '--';
    const end = endTime || Date.now();
    const seconds = Math.round((end - startTime) / 1000);
    if (seconds < 60) return `${seconds}秒`;
    const minutes = Math.round(seconds / 60);
    return `${minutes}分钟${seconds % 60 > 0 ? `${seconds % 60}秒` : ''}`;
  };

  const completedCount = stages.filter(s => s.status === 'completed').length;
  const totalCount = stages.length;
  const overallProgress = (completedCount / totalCount) * 100;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-800">编译管道</h3>
            <p className="text-sm text-gray-500">实时监控工作流执行状态</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-2xl font-bold text-blue-600">{Math.round(overallProgress)}%</div>
            <div className="text-xs text-gray-500">{completedCount}/{totalCount} 阶段完成</div>
          </div>
          <div className="flex items-center gap-2">
            {isCompiling ? (
              <button
                onClick={onCancel}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 transition-colors text-sm"
              >
                <XCircle size={14} />
                取消
              </button>
            ) : (
              <button
                onClick={onReset}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors text-sm"
              >
                <Circle size={14} />
                重置
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="relative mb-6">
        <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500 transition-all duration-700 ease-out"
            style={{ width: `${overallProgress}%` }}
          />
        </div>
        <div className="flex justify-between mt-2">
          {stages.map((stage, index) => (
            <div key={stage.id} className="flex flex-col items-center">
              <div 
                className={`w-2 h-2 rounded-full transition-all duration-300 ${
                  index <= completedCount ? 'bg-blue-500 scale-125' : 'bg-gray-300'
                }`}
              />
              <span className="text-xs text-gray-400 mt-1">{stage.name.slice(0, 2)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="relative">
        <svg 
          className="absolute top-8 left-0 w-full pointer-events-none" 
          style={{ height: '40px' }}
        >
          <defs>
            <linearGradient id="pipeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#3b82f6" />
              <stop offset="50%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#8b5cf6" />
            </linearGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
              <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>
          
          {stages.slice(0, -1).map((stage, index) => {
            const nextStage = stages[index + 1];
            const isActive = stage.status === 'completed' || stage.status === 'running';
            const isNextActive = nextStage.status === 'completed' || nextStage.status === 'running';
            
            return (
              <g key={`line-${stage.id}`}>
                <line
                  x1={`${(index + 1) * (100 / stages.length) - 4}%`}
                  y1="20"
                  x2={`${(index + 2) * (100 / stages.length) - 4}%`}
                  y2="20"
                  stroke={isActive && isNextActive ? 'url(#pipeGradient)' : '#e5e7eb'}
                  strokeWidth="3"
                  strokeLinecap="round"
                  filter={isActive && isNextActive ? 'url(#glow)' : undefined}
                  className="transition-all duration-500"
                />
                {isNextActive && nextStage.status === 'running' && (
                  <circle r="4" fill="#3b82f6">
                    <animateMotion
                      dur="2s"
                      repeatCount="indefinite"
                      path={`M ${(index + 1) * (100 / stages.length) - 4}% 20 L ${(index + 2) * (100 / stages.length) - 4}% 20`}
                    />
                  </circle>
                )}
              </g>
            );
          })}
        </svg>

        <div className="grid grid-cols-5 gap-4">
          {stages.map((stage, index) => {
            const colors = getStatusColor(stage.status);
            const isHovered = hoveredStage === stage.id;
            const isExpanded = expandedStage === stage.id;

            return (
              <div key={stage.id}>
                <div
                  className={`relative rounded-xl border-2 p-4 transition-all duration-300 ${colors.bg} ${colors.border} ${
                    isHovered ? 'scale-105 shadow-lg' : ''
                  }`}
                  onMouseEnter={() => setHoveredStage(stage.id)}
                  onMouseLeave={() => setHoveredStage(null)}
                  onClick={() => setExpandedStage(isExpanded ? null : stage.id)}
                >
                  <div className="flex flex-col items-center text-center">
                    <div className={`mb-3 ${colors.icon} ${colors.glow}`}>
                      {getStatusIcon(stage.status)}
                    </div>
                    
                    <div className="font-medium text-gray-800 text-sm mb-1">
                      {stage.name}
                    </div>
                    
                    <div className="text-xs text-gray-500 mb-3">
                      {stage.description}
                    </div>
                    
                    <div className="w-full bg-gray-200 rounded-full h-1.5 mb-2">
                      <div 
                        className={`h-full rounded-full transition-all duration-500 ${
                          stage.status === 'completed' ? 'bg-green-500' :
                          stage.status === 'running' ? 'bg-blue-500' :
                          stage.status === 'failed' ? 'bg-red-500' : 'bg-gray-300'
                        }`}
                        style={{ width: `${stage.progress}%` }}
                      />
                    </div>
                    
                    <div className="flex items-center gap-1 text-xs text-gray-500">
                      <Clock size={10} />
                      {formatDuration(stage.startTime, stage.endTime)}
                    </div>
                  </div>

                  {isHovered && (
                    <div className="absolute -top-1 -right-1 w-3 h-3 bg-blue-500 rounded-full animate-ping" />
                  )}

                  {stage.status === 'running' && (
                    <div className="absolute inset-0 rounded-xl animate-pulse bg-blue-100/30 pointer-events-none" />
                  )}
                </div>

                {isExpanded && (
                  <div className="mt-3 p-3 bg-gray-50 rounded-xl border border-gray-200">
                    {stage.output && (
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                        <p className="text-sm text-gray-600">{stage.output}</p>
                      </div>
                    )}
                    {stage.error && (
                      <div className="flex items-start gap-2 mb-3">
                        <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                        <p className="text-sm text-red-600">{stage.error}</p>
                      </div>
                    )}
                    {stage.status === 'failed' && onRetryStage && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setRetryingStage(stage.id);
                          onRetryStage(stage.id).then(() => {
                            setRetryingStage(null);
                          }).catch(() => {
                            setRetryingStage(null);
                          });
                        }}
                        disabled={retryingStage === stage.id}
                        className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-red-50 text-red-600 hover:bg-red-100 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <RotateCcw size={14} className={retryingStage === stage.id ? 'animate-spin' : ''} />
                        {retryingStage === stage.id ? '重试中...' : '重试此阶段'}
                      </button>
                    )}
                    <div className="mt-2 text-xs text-gray-400">
                      点击其他阶段查看详情
                    </div>
                  </div>
                )}

                {index < stages.length - 1 && (
                  <div className="flex justify-center mt-2">
                    <ChevronRight className="w-4 h-4 text-gray-300" />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-6 pt-4 border-t border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-gray-300" />
            <span className="text-xs text-gray-500">等待</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
            <span className="text-xs text-gray-500">执行中</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-green-500" />
            <span className="text-xs text-gray-500">完成</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-red-500" />
            <span className="text-xs text-gray-500">失败</span>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <Info size={12} />
          <span>点击阶段卡片查看详情</span>
        </div>
      </div>
    </div>
  );
};

export default PipelineVisualization;