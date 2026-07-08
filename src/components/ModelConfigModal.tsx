import { useState } from 'react';
import { X, Check, Settings, Sparkles, Globe, Server, Lock, SlidersHorizontal } from 'lucide-react';

interface ModelConfigModalProps {
  onClose: () => void;
}

interface ModelProvider {
  id: string;
  name: string;
  description: string;
  icon: typeof Globe;
  type: 'cloud' | 'local';
  models: string[];
}

const modelProviders: ModelProvider[] = [
  {
    id: 'deepseek',
    name: 'DeepSeek',
    description: '高精度分析模型，适合结构化输出',
    icon: Globe,
    type: 'cloud',
    models: ['deepseek-chat', 'deepseek-r1', 'deepseek-r2'],
  },
  {
    id: 'doubao',
    name: '豆包',
    description: '创意生成模型，适合写作和内容创作',
    icon: Globe,
    type: 'cloud',
    models: ['doubao-pro-32k', 'doubao-pro', 'doubao-lite'],
  },
  {
    id: 'yuanbao',
    name: '腾讯元宝',
    description: '企业级智能助手，支持多模态',
    icon: Globe,
    type: 'cloud',
    models: ['hunyuan-pro', 'hunyuan-standard'],
  },
  {
    id: 'qwen',
    name: '通义千问',
    description: '阿里巴巴大模型，多语言支持',
    icon: Globe,
    type: 'cloud',
    models: ['qwen-turbo', 'qwen-plus', 'qwen-max'],
  },
  {
    id: 'ollama',
    name: 'Ollama',
    description: '本地轻量模型服务，隐私保护',
    icon: Server,
    type: 'local',
    models: ['qwen2.5:7b', 'qwen2.5:14b', 'llama3.2:7b', 'phi3:mini'],
  },
  {
    id: 'vllm',
    name: 'vLLM',
    description: '高性能推理服务器，适合大规模部署',
    icon: Server,
    type: 'local',
    models: ['qwen2.5-7b', 'qwen2.5-14b', 'llama-3.3-70b'],
  },
];

const ModelConfigModal = ({ onClose }: ModelConfigModalProps) => {
  const [selectedProvider, setSelectedProvider] = useState<string>('deepseek');
  const [selectedModel, setSelectedModel] = useState<string>('deepseek-chat');
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(8000);
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [isLocalProvider, setIsLocalProvider] = useState(false);

  const currentProvider = modelProviders.find(p => p.id === selectedProvider);

  const handleProviderChange = (providerId: string) => {
    const provider = modelProviders.find(p => p.id === providerId);
    if (provider) {
      setSelectedProvider(providerId);
      setSelectedModel(provider.models[0]);
      setIsLocalProvider(provider.type === 'local');
    }
  };

  const handleSave = () => {
    const config = {
      provider: selectedProvider,
      model: selectedModel,
      temperature,
      maxTokens,
      apiKey: isLocalProvider ? '' : apiKey,
      baseUrl: isLocalProvider ? baseUrl : '',
    };
    console.log('Saved model config:', config);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 overflow-hidden">
        <div className="bg-gradient-to-r from-indigo-500 to-purple-600 px-6 py-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Settings size={20} />
              模型配置
            </h2>
            <button onClick={onClose} className="text-white/80 hover:text-white">
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="p-6">
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-3">模型提供商</label>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {modelProviders.map(provider => {
                const IconComponent = provider.icon;
                return (
                  <button
                    key={provider.id}
                    onClick={() => handleProviderChange(provider.id)}
                    className={`p-4 rounded-xl border-2 transition-all text-left ${
                      selectedProvider === provider.id
                        ? 'border-indigo-500 bg-indigo-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <IconComponent size={18} className={provider.type === 'cloud' ? 'text-blue-500' : 'text-green-500'} />
                      <span className="font-medium text-gray-800">{provider.name}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        provider.type === 'cloud' 
                          ? 'bg-blue-100 text-blue-600' 
                          : 'bg-green-100 text-green-600'
                      }`}>
                        {provider.type === 'cloud' ? '云端' : '本地'}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500">{provider.description}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-3">模型选择</label>
            <div className="flex flex-wrap gap-2">
              {currentProvider?.models.map(model => (
                <button
                  key={model}
                  onClick={() => setSelectedModel(model)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    selectedModel === model
                      ? 'bg-indigo-500 text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {model}
                </button>
              ))}
            </div>
          </div>

          {isLocalProvider ? (
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-3">
                <Server size={16} className="inline mr-2" />
                本地服务地址
              </label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="http://localhost:11434/v1"
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              />
            </div>
          ) : (
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-3">
                <Lock size={16} className="inline mr-2" />
                API Key
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="输入API密钥..."
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              />
            </div>
          )}

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-3">
              <SlidersHorizontal size={16} className="inline mr-2" />
              参数配置
            </label>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1">温度 (Temperature)</label>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value))}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                />
                <span className="text-sm text-gray-600">{temperature}</span>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">最大令牌数</label>
                <input
                  type="number"
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(parseInt(e.target.value) || 8000)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-500 text-sm"
                />
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between pt-4 border-t border-gray-200">
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <Sparkles size={16} className="text-yellow-500" />
              <span>当前配置: {currentProvider?.name} / {selectedModel}</span>
            </div>
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 border border-gray-300 rounded-xl hover:bg-gray-50 transition-colors text-gray-700 text-sm font-medium"
              >
                取消
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-2 bg-indigo-500 text-white rounded-xl hover:bg-indigo-600 transition-colors text-sm font-medium flex items-center gap-2"
              >
                <Check size={16} />
                保存配置
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ModelConfigModal;