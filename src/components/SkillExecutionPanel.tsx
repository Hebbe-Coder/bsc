import { useState, useEffect, useCallback, useRef } from 'react';
import { Play, Square, RefreshCw, Copy, Check, Loader2, X, FileText, Target, BarChart3, AlertTriangle, TrendingUp, Sparkles, Clock } from 'lucide-react';
import { bscApi, Skill, ExecuteSkillRequest } from '../api/bscApi';
import usePresentationStore from '../store/presentationStore';
import { DEFAULT_MODEL_PROVIDER, MODEL_PROVIDERS } from '../config';

interface SkillExecutionPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

const iconMap: Record<string, React.ComponentType<{ size?: number | string }>> = {
  'prd-analysis': FileText,
  'objective-extraction': Target,
  'kpi-extraction': BarChart3,
  'chart-generation': BarChart3,
  'risk-assessment': AlertTriangle,
  'strategy-analysis': TrendingUp,
  'presentation-generation': Sparkles,
  'report-generation': FileText,
};

const SkillExecutionPanel = ({ isOpen, onClose }: SkillExecutionPanelProps) => {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [inputText, setInputText] = useState('');
  const [executionStatus, setExecutionStatus] = useState<'idle' | 'running' | 'completed' | 'failed'>('idle');
  const [result, setResult] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);
  const [provider, setProvider] = useState(DEFAULT_MODEL_PROVIDER);
  const [fromCache, setFromCache] = useState(false);
  
  const abortControllerRef = useRef<AbortController | null>(null);
  const executionStatusRef = useRef<'idle' | 'running' | 'completed' | 'failed'>('idle');
  
  const addComponent = usePresentationStore((state) => state.addComponent);
  const setCurrentSlideIndex = usePresentationStore((state) => state.setCurrentSlideIndex);

  useEffect(() => {
    if (isOpen) {
      fetchSkills();
    } else {
      resetState();
    }
  }, [isOpen]);

  const fetchSkills = async () => {
    try {
      const data = await bscApi.getSkills();
      setSkills(data);
    } catch (error) {
      console.error('Failed to fetch skills:', error);
    }
  };

  const resetState = () => {
    setSelectedSkill(null);
    setInputText('');
    const newStatus: 'idle' | 'running' | 'completed' | 'failed' = 'idle';
    setExecutionStatus(newStatus);
    executionStatusRef.current = newStatus;
    setResult('');
    setIsStreaming(false);
    setFromCache(false);
  };

  const handleExecute = useCallback(async () => {
    if (!selectedSkill || !inputText.trim()) return;

    resetState();
    const runningStatus: 'idle' | 'running' | 'completed' | 'failed' = 'running';
    setExecutionStatus(runningStatus);
    executionStatusRef.current = runningStatus;
    setIsStreaming(true);
    setResult('');

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const request: ExecuteSkillRequest = {
        skill_id: selectedSkill.id,
        params: getParamsForSkill(selectedSkill.id, inputText),
        streaming: true,
        llm_provider: provider,
        use_cache: true,
      };

      const response = await bscApi.executeSkill(request);

      if (response.status === 'completed') {
        setResult(response.result || '');
        const completedStatus: 'idle' | 'running' | 'completed' | 'failed' = 'completed';
        setExecutionStatus(completedStatus);
        executionStatusRef.current = completedStatus;
        setIsStreaming(false);
        setFromCache(response.from_cache || false);
        abortControllerRef.current = null;
        return;
      }

      if (response.status !== 'streaming' && response.status !== 'running') {
        throw new Error(`Unexpected status: ${response.status}`);
      }

      const stream = await bscApi.streamSkill(response.execution_id, abortController.signal);
      const reader = stream.getReader();
      const decoder = new TextDecoder();
      let isDone = false;

      while (!isDone) {
        const { done, value } = await reader.read();
        
        if (done) {
          isDone = true;
          break;
        }

        if (!value) continue;

        const chunks = decoder.decode(value).split('\n\n');
        for (const chunk of chunks) {
          if (!chunk.startsWith('data:')) continue;

          try {
            const data = JSON.parse(chunk.replace(/^data:\s*/, ''));
            
            if (data.content && typeof data.content === 'string') {
              setResult(prev => prev + data.content);
            }

            if (data.status === 'completed') {
              const completedStatus: 'idle' | 'running' | 'completed' | 'failed' = 'completed';
              setExecutionStatus(completedStatus);
              executionStatusRef.current = completedStatus;
              setIsStreaming(false);
              isDone = true;
              break;
            } else if (data.status === 'failed') {
              const failedStatus: 'idle' | 'running' | 'completed' | 'failed' = 'failed';
              setExecutionStatus(failedStatus);
              executionStatusRef.current = failedStatus;
              setResult(data.error || '执行失败');
              setIsStreaming(false);
              isDone = true;
              break;
            }
          } catch (e) {
            console.warn('Failed to parse stream chunk:', chunk, e);
          }
        }
      }

      abortControllerRef.current = null;

      if (!isDone && executionStatusRef.current === 'running') {
        const completedStatus: 'idle' | 'running' | 'completed' | 'failed' = 'completed';
        setExecutionStatus(completedStatus);
        executionStatusRef.current = completedStatus;
        setIsStreaming(false);
      }

      if (response.execution_id) {
        try {
          const finalResult = await bscApi.getSkillResult(response.execution_id);
          if (finalResult.from_cache) {
            setFromCache(true);
          }
        } catch (e) {
          console.warn('Failed to get cached result:', e);
        }
      }

    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        console.log('Stream aborted by user');
        const idleStatus: 'idle' | 'running' | 'completed' | 'failed' = 'idle';
        setExecutionStatus(idleStatus);
        executionStatusRef.current = idleStatus;
        setIsStreaming(false);
      } else {
        console.error('Execution error:', error);
        const failedStatus: 'idle' | 'running' | 'completed' | 'failed' = 'failed';
        setExecutionStatus(failedStatus);
        executionStatusRef.current = failedStatus;
        setResult('执行失败: ' + (error instanceof Error ? error.message : String(error)));
        setIsStreaming(false);
      }
      abortControllerRef.current = null;
    }
  }, [selectedSkill, inputText, provider]);

  const getParamsForSkill = (skillId: string, text: string): Record<string, string> => {
    const paramMap: Record<string, string> = {
      'prd-analysis': 'prd_content',
      'objective-extraction': 'business_content',
      'kpi-extraction': 'business_content',
      'chart-generation': 'data_description',
      'risk-assessment': 'business_context',
      'strategy-analysis': 'business_info',
      'presentation-generation': 'business_content',
      'report-generation': 'business_content',
    };
    return { [paramMap[skillId] || 'input']: text };
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(result);
    setCopySuccess(true);
    setTimeout(() => setCopySuccess(false), 2000);
  };

  const handleInsertToSlide = () => {
    if (!result) return;
    
    addComponent(0, 'text', 50, 100);
    setCurrentSlideIndex(0);
    onClose();
  };

  const handleRetry = () => {
    handleExecute();
  };

  return (
    <div className={`fixed inset-0 bg-black/50 flex items-center justify-center z-50 transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl mx-4 overflow-hidden h-[85vh] flex flex-col">
        <div className="bg-gradient-to-r from-purple-500 to-pink-500 px-6 py-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Sparkles size={20} />
              AI 技能执行
            </h2>
            <button onClick={onClose} className="text-white/80 hover:text-white transition-colors">
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="flex flex-1 overflow-hidden">
          <div className="w-72 border-r border-gray-200 overflow-y-auto">
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-500 mb-3">选择技能</h3>
              <div className="space-y-2">
                {skills.map(skill => {
                  const IconComponent = iconMap[skill.id] || Sparkles;
                  return (
                    <button
                      key={skill.id}
                      onClick={() => setSelectedSkill(skill)}
                      className={`w-full text-left p-3 rounded-xl border-2 transition-all ${
                        selectedSkill?.id === skill.id
                          ? 'border-purple-500 bg-purple-50'
                          : 'border-gray-100 hover:border-purple-200 hover:bg-gray-50'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center">
                          <IconComponent size={18} className="text-gray-600" />
                        </div>
                        <div>
                          <div className="font-medium text-gray-800 text-sm">{skill.name}</div>
                          <div className="text-xs text-gray-500 truncate">{skill.description}</div>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="p-4 border-t border-gray-200">
              <h3 className="text-sm font-semibold text-gray-500 mb-3">模型选择</h3>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-xl focus:outline-none focus:border-purple-500 text-sm"
              >
                {MODEL_PROVIDERS.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-gray-200">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-gray-800">
                  {selectedSkill?.name || '请选择技能'}
                </h3>
                {fromCache && (
                  <span className="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full font-medium flex items-center gap-1">
                    <Check size={12} />
                    缓存结果
                  </span>
                )}
              </div>
              
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder={selectedSkill?.description || '请输入技能参数...'}
                className="w-full h-32 px-4 py-3 border border-gray-200 rounded-xl resize-none focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-100 text-sm"
              />

              <div className="flex items-center gap-3 mt-4">
                <button
                  onClick={handleExecute}
                  disabled={!selectedSkill || !inputText.trim() || isStreaming}
                  className={`flex items-center gap-2 px-6 py-2.5 rounded-xl font-medium transition-all ${
                    !selectedSkill || !inputText.trim() || isStreaming
                      ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                      : 'bg-purple-500 text-white hover:bg-purple-600 shadow-lg shadow-purple-200'
                  }`}
                >
                  {isStreaming ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      执行中...
                    </>
                  ) : (
                    <>
                      <Play size={16} />
                      执行
                    </>
                  )}
                </button>
                
                {isStreaming && (
                  <button
                    onClick={() => {
                      abortControllerRef.current?.abort();
                    }}
                    className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-red-200 text-red-600 hover:bg-red-50 transition-colors"
                  >
                    <Square size={16} />
                    停止
                  </button>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {executionStatus === 'idle' && (
                <div className="flex flex-col items-center justify-center h-full text-gray-400">
                  <Sparkles size={48} className="mb-4 opacity-50" />
                  <p className="text-lg font-medium">准备执行技能</p>
                  <p className="text-sm mt-2">选择技能并输入参数后点击执行</p>
                </div>
              )}

              {executionStatus === 'running' && isStreaming && (
                <div className="bg-gray-50 rounded-xl p-4">
                  <div className="flex items-center gap-2 text-sm text-gray-500 mb-3">
                    <Clock size={14} />
                    正在生成...
                  </div>
                  <pre className="whitespace-pre-wrap text-sm text-gray-700 font-mono leading-relaxed">
                    {result || '等待输出...'}
                    <span className="animate-pulse">|</span>
                  </pre>
                </div>
              )}

              {executionStatus === 'completed' && result && (
                <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                  <div className="bg-green-50 px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-green-700">
                      <Check size={16} />
                      <span className="font-medium text-sm">执行完成</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleInsertToSlide}
                        className="px-3 py-1.5 bg-purple-100 text-purple-700 rounded-lg text-xs font-medium hover:bg-purple-200 transition-colors"
                      >
                        插入到幻灯片
                      </button>
                      <button
                        onClick={handleCopy}
                        className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-xs font-medium hover:bg-gray-200 transition-colors flex items-center gap-1"
                      >
                        {copySuccess ? (
                          <>
                            <Check size={12} />
                            已复制
                          </>
                        ) : (
                          <>
                            <Copy size={12} />
                            复制
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                  <div className="p-4">
                    <pre className="whitespace-pre-wrap text-sm text-gray-700 font-mono leading-relaxed max-h-[400px] overflow-y-auto">
                      {result}
                    </pre>
                  </div>
                </div>
              )}

              {executionStatus === 'failed' && result && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                  <div className="flex items-center gap-2 text-red-700 mb-3">
                    <AlertTriangle size={16} />
                    <span className="font-medium">执行失败</span>
                  </div>
                  <pre className="whitespace-pre-wrap text-sm text-red-600 font-mono">
                    {result}
                  </pre>
                  <button
                    onClick={handleRetry}
                    className="mt-4 flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors"
                  >
                    <RefreshCw size={14} />
                    重试
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SkillExecutionPanel;
