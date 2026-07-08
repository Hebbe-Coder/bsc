import React from 'react';
import { CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react';
import { PipelineStage } from '../store/presentationStore';

interface PipelineProgressProps {
  stages: PipelineStage[];
  isCompiling: boolean;
  onCancel: () => void;
  onReset: () => void;
}

const PipelineProgress: React.FC<PipelineProgressProps> = ({ stages, isCompiling, onCancel, onReset }) => {
  const getStatusIcon = (status: PipelineStage['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-5 h-5 text-green-500" />;
      case 'running':
        return <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />;
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-500" />;
      default:
        return <Circle className="w-5 h-5 text-gray-300" />;
    }
  };

  const getStatusColor = (status: PipelineStage['status']) => {
    switch (status) {
      case 'completed':
        return 'border-green-500 bg-green-50';
      case 'running':
        return 'border-blue-500 bg-blue-50';
      case 'failed':
        return 'border-red-500 bg-red-50';
      default:
        return 'border-gray-200 bg-gray-50';
    }
  };

  const getProgressColor = (status: PipelineStage['status']) => {
    switch (status) {
      case 'completed':
        return 'bg-green-500';
      case 'running':
        return 'bg-blue-500';
      case 'failed':
        return 'bg-red-500';
      default:
        return 'bg-gray-200';
    }
  };

  const formatDuration = (startTime?: number, endTime?: number) => {
    if (!startTime || !endTime) return '';
    const seconds = Math.round((endTime - startTime) / 1000);
    if (seconds < 60) return `${seconds}秒`;
    const minutes = Math.round(seconds / 60);
    return `${minutes}分钟`;
  };

  const completedCount = stages.filter(s => s.status === 'completed').length;
  const totalCount = stages.length;
  const overallProgress = (completedCount / totalCount) * 100;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-gray-800">编译进度</h3>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">
            {completedCount}/{totalCount} 阶段
          </span>
          <span className="text-sm font-medium text-blue-600">
            {Math.round(overallProgress)}%
          </span>
        </div>
      </div>

      <div className="relative mb-6">
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-blue-500 to-green-500 transition-all duration-500 ease-out"
            style={{ width: `${overallProgress}%` }}
          />
        </div>
      </div>

      <div className="space-y-3">
        {stages.map((stage, index) => (
          <div 
            key={stage.id}
            className={`rounded-xl border-2 p-4 transition-all duration-300 ${getStatusColor(stage.status)}`}
          >
            <div className="flex items-center gap-4">
              <div className="flex-shrink-0">
                {getStatusIcon(stage.status)}
              </div>
              
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-400">#{index + 1}</span>
                    <span className="font-medium text-gray-800">{stage.name}</span>
                  </div>
                  {stage.startTime && stage.endTime && (
                    <span className="text-xs text-gray-500">
                      {formatDuration(stage.startTime, stage.endTime)}
                    </span>
                  )}
                </div>
                
                <p className="text-sm text-gray-500 mt-1">{stage.description}</p>
                
                <div className="mt-3">
                  <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                    <div 
                      className={`h-full transition-all duration-500 ${getProgressColor(stage.status)}`}
                      style={{ width: `${stage.progress}%` }}
                    />
                  </div>
                </div>
                
                {stage.output && (
                  <div className="mt-3 p-3 bg-white/50 rounded-lg">
                    <p className="text-sm text-gray-600">{stage.output}</p>
                  </div>
                )}
                
                {stage.error && (
                  <div className="mt-3 p-3 bg-red-50 rounded-lg">
                    <p className="text-sm text-red-600">{stage.error}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-gray-100">
        {isCompiling && (
          <button
            onClick={onCancel}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-red-200 text-red-600 hover:bg-red-50 transition-colors"
          >
            <XCircle size={16} />
            取消编译
          </button>
        )}
        
        {!isCompiling && (
          <button
            onClick={onReset}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
          >
            <Circle size={16} />
            重置
          </button>
        )}
      </div>
    </div>
  );
};

export default PipelineProgress;