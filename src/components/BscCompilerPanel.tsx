import { useState, useCallback } from 'react';
import { Play, RefreshCw, Loader2, X, FileText, Sparkles, Check, AlertTriangle } from 'lucide-react';
import usePresentationStore from '../store/presentationStore';
import PipelineVisualization from './PipelineVisualization';

interface BscCompilerPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export const BscCompilerPanel = ({ isOpen, onClose }: BscCompilerPanelProps) => {
  const [inputText, setInputText] = useState('');
  const [executionStatus, setExecutionStatus] = useState<'idle' | 'running' | 'completed' | 'failed'>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  
  const { 
    pipelineStages, 
    isCompiling, 
    compileFromPRD, 
    cancelCompile, 
    resetPipeline,
    error 
  } = usePresentationStore();

  const handleCompile = useCallback(async () => {
    if (!inputText.trim()) return;

    setExecutionStatus('running');
    setErrorMessage('');

    try {
      await compileFromPRD(inputText);
      setExecutionStatus('completed');
      
      setTimeout(() => {
        onClose();
      }, 2000);

    } catch (err) {
      console.error('BSC compilation error:', err);
      setExecutionStatus('failed');
      setErrorMessage(err instanceof Error ? err.message : '编译失败');
    }
  }, [inputText, compileFromPRD, onClose]);

  const handleReset = () => {
    setInputText('');
    setExecutionStatus('idle');
    setErrorMessage('');
    resetPipeline();
  };

  return (
    <div className={`fixed inset-0 bg-black/50 flex items-center justify-center z-50 transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4 flex-shrink-0">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Sparkles size={20} />
              BSC Pipeline 编译
            </h2>
            <button onClick={onClose} className="text-white/80 hover:text-white transition-colors">
              <X size={20} />
            </button>
          </div>
          <p className="text-white/70 text-sm mt-1">将PRD文档转换为完整的业务系统演示文稿</p>
        </div>

        <div className="p-6 overflow-y-auto flex-1">
          {executionStatus === 'idle' && (
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <FileText size={14} className="inline mr-1" />
                PRD文档内容
              </label>
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder="请输入PRD文档内容，例如：

# 内容审核系统PRD

## 1. 业务目标
- 建立完善的内容审核体系
- 确保平台内容合规性
- 提升审核效率至90%以上

## 2. 核心功能
- 图片审核
- 视频审核
- 文本审核
- 实时监控

## 3. 性能要求
- 单条审核响应时间 < 2秒
- 日均处理量 100万条+"
                className="w-full h-48 px-4 py-3 border border-gray-200 rounded-xl resize-none focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 text-sm font-mono"
              />
            </div>
          )}

          {(executionStatus === 'idle' || executionStatus === 'running') && (
            <div className="flex items-center gap-3 mb-6">
              <button
                onClick={handleCompile}
                disabled={!inputText.trim() || isCompiling}
                className={`flex items-center gap-2 px-6 py-3 rounded-xl font-medium transition-all ${
                  !inputText.trim() || isCompiling
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    : 'bg-blue-600 text-white hover:bg-blue-700 shadow-lg shadow-blue-200'
                }`}
              >
                {isCompiling ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    编译中...
                  </>
                ) : (
                  <>
                    <Play size={16} />
                    开始编译
                  </>
                )}
              </button>
              
              {isCompiling && (
                <button
                  onClick={cancelCompile}
                  className="flex items-center gap-2 px-4 py-3 rounded-xl border border-red-200 text-red-600 hover:bg-red-50 transition-colors"
                >
                  <X size={16} />
                  取消编译
                </button>
              )}
            </div>
          )}

          {isCompiling && (
            <PipelineVisualization
              stages={pipelineStages}
              isCompiling={isCompiling}
              onCancel={cancelCompile}
              onReset={handleReset}
            />
          )}

          {executionStatus === 'completed' && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center">
                <Check size={24} className="text-green-600" />
              </div>
              <div>
                <h3 className="font-medium text-green-800">编译完成</h3>
                <p className="text-sm text-green-600">演示文稿已生成并导入</p>
              </div>
            </div>
          )}

          {executionStatus === 'failed' && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <div className="flex items-center gap-2 text-red-700 mb-3">
                <AlertTriangle size={16} />
                <span className="font-medium">编译失败</span>
              </div>
              <pre className="whitespace-pre-wrap text-sm text-red-600 font-mono max-h-40 overflow-y-auto">
                {errorMessage || error}
              </pre>
              <button
                onClick={handleReset}
                className="mt-4 flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <RefreshCw size={16} />
                重新输入
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default BscCompilerPanel;