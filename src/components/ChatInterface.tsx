import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Paperclip, Loader2, X, Bot, Sparkles, Lightbulb } from 'lucide-react';
import MessageBubble, { Message, MessageType } from './MessageBubble';
import usePresentationStore from '../store/presentationStore';
import PipelineVisualization from './PipelineVisualization';
import PipelineSummary from './PipelineSummary';
import { recognizeIntent, getIntentResponse, IntentType } from '../skill/intentRecognizer';
import { BusinessSystem } from '../api/bscApi';
import { ThemeType } from '../types';

interface ChatInterfaceProps {
  isOpen: boolean;
  onClose: () => void;
}

const initialMessages: Message[] = [
  {
    id: '1',
    type: 'system',
    content: '欢迎使用BSC智能助手！我可以帮您将PRD文档转换为专业的演示文稿。',
  },
  {
    id: '2',
    type: 'assistant',
    content: '您可以直接输入PRD文档内容，或者告诉我您的业务需求，我会帮您生成完整的演示文稿。\n\n例如：\n- 输入PRD文档\n- 描述您的业务系统\n- 提出具体需求',
    timestamp: new Date(),
  },
];

const ChatInterface: React.FC<ChatInterfaceProps> = ({ isOpen, onClose }) => {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [inputText, setInputText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [summaryData, setSummaryData] = useState<{ businessSystem: BusinessSystem; slideCount: number } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  const { 
    pipelineStages, 
    isCompiling, 
    compileFromPRD, 
    cancelCompile, 
    resetPipeline,
    isLoading,
    setTheme,
    presentation,
    retryStage,
  } = usePresentationStore();

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const addMessage = (content: string, type: MessageType): Message => {
    const newMessage: Message = {
      id: Date.now().toString(),
      type,
      content,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, newMessage]);
    return newMessage;
  };

  const handleSend = async () => {
    if (!inputText.trim() || isTyping || isCompiling) return;

    const userMessage = inputText.trim();
    setInputText('');
    
    addMessage(userMessage, 'user');
    addMessage('', 'thinking');
    setIsTyping(true);

    try {
      const intentResult = recognizeIntent(userMessage);
      
      setMessages(prev => prev.map(msg => 
        msg.type === 'thinking'
          ? { ...msg, content: `正在分析您的需求...\n\n识别意图: ${intentResult.intent} (置信度: ${Math.round(intentResult.confidence * 100)}%)` }
          : msg
      ));

      await new Promise(resolve => setTimeout(resolve, 1500));

      setMessages(prev => prev.filter(msg => msg.type !== 'thinking'));

      if (intentResult.intent === 'help') {
        addMessage(getIntentResponse('help'), 'assistant');
      } else if (intentResult.intent === 'unknown' && !intentResult.prdContent) {
        addMessage(getIntentResponse('unknown', userMessage), 'assistant');
      } else if (intentResult.intent === 'modify_theme') {
        addMessage(getIntentResponse('modify_theme'), 'assistant');
        
        const themeMap: Record<string, ThemeType> = {
          '暖色': 'creative',
          '冷色': 'business',
          '深色': 'dark',
          '浅色': 'education',
          '商务': 'business',
          '科技': 'tech',
        };
        
        let targetTheme: ThemeType = 'business';
        for (const [keyword, theme] of Object.entries(themeMap)) {
          if (userMessage.includes(keyword)) {
            targetTheme = theme;
            break;
          }
        }
        
        setTheme(targetTheme);
        addMessage(`🎨 已将演示文稿主题切换为「${targetTheme === 'creative' ? '暖色' : targetTheme === 'dark' ? '深色' : targetTheme === 'education' ? '浅色' : targetTheme === 'tech' ? '科技' : '商务'}」风格`, 'assistant');
      } else if (intentResult.intent === 'modify_slide') {
        addMessage(getIntentResponse('modify_slide'), 'assistant');
        
        const slideMatch = userMessage.match(/第(\d+)页/) || userMessage.match(/(\d+)页/);
        if (slideMatch) {
          const slideIndex = parseInt(slideMatch[1]) - 1;
          if (slideIndex >= 0 && slideIndex < presentation.slides.length) {
            addMessage(`📄 定位到第 ${slideIndex + 1} 页，标题为「${presentation.slides[slideIndex].components.find((c: any) => c.type === 'text' && c.style.fontSize > 28)?.content || '无标题'}」`, 'assistant');
            addMessage('请详细描述您想如何修改这一页的内容，例如：\n- 修改标题为"新标题"\n- 添加一段描述文本\n- 调整布局', 'assistant');
          } else {
            addMessage(`⚠️ 当前演示文稿只有 ${presentation.slides.length} 页，请输入有效的页码。`, 'assistant');
          }
        } else {
          addMessage('📋 当前演示文稿共有 ' + presentation.slides.length + ' 页，请告诉我您想修改哪一页。', 'assistant');
        }
      } else if (intentResult.intent === 'regenerate_section') {
        addMessage(getIntentResponse('regenerate_section'), 'assistant');
        
        if (!summaryData?.businessSystem) {
          addMessage('⚠️ 请先生成演示文稿，然后再重新生成特定章节。', 'assistant');
        } else {
          addMessage('🔄 重新生成演示文稿...', 'system');
          const result = await compileFromPRD(summaryData.businessSystem.business_domain || '业务系统');
          
          if (result && result.context?.businessSystem) {
            setSummaryData({
              businessSystem: result.context.businessSystem,
              slideCount: result.presentation?.slides.length || 0,
            });
            addMessage('✅ 指定章节已重新生成完成！', 'assistant');
          }
        }
      } else {
        addMessage(getIntentResponse(intentResult.intent), 'assistant');
        
        addMessage(`💡 识别到意图: ${intentResult.keywords.join('、')}`, 'system');
        
        addMessage('开始执行BSC编译工作流...', 'system');

        const contentToCompile = intentResult.prdContent || userMessage;
        const result = await compileFromPRD(contentToCompile);

        if (result && result.context?.businessSystem) {
          setSummaryData({
            businessSystem: result.context.businessSystem,
            slideCount: result.presentation?.slides.length || 0,
          });
        }

        addMessage('🎉 演示文稿已成功生成！您可以继续修改主题、调整内容或重新生成某个章节。', 'assistant');
      }

    } catch (error) {
      setMessages(prev => prev.filter(msg => msg.type !== 'thinking'));
      
      if (error instanceof Error && error.message === '编译已取消') {
        addMessage('编译已取消。', 'system');
      } else {
        addMessage(`抱歉，编译过程中出现问题：${error instanceof Error ? error.message : '未知错误'}`, 'assistant');
      }
    } finally {
      setIsTyping(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = () => {
    setMessages(initialMessages);
    setSummaryData(null);
    resetPipeline();
  };

  return (
    <div className={`fixed inset-0 bg-black/50 flex items-center justify-center z-50 transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        <div className="bg-gradient-to-r from-purple-600 to-indigo-600 px-6 py-4 flex-shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-white/20 rounded-xl p-2">
              <Bot className="w-6 h-6 text-white" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">BSC 智能助手</h2>
              <p className="text-white/70 text-sm">将PRD转换为专业演示文稿</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleClear}
              className="text-white/70 hover:text-white transition-colors px-3 py-1.5 rounded-lg hover:bg-white/10"
              title="清空对话"
            >
              清空
            </button>
            <button onClick={onClose} className="text-white/80 hover:text-white transition-colors">
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6 bg-gray-50">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          
          {isCompiling && (
            <div className="mt-4">
              <PipelineVisualization
                stages={pipelineStages}
                isCompiling={isCompiling}
                onCancel={cancelCompile}
                onReset={resetPipeline}
                onRetryStage={retryStage}
              />
            </div>
          )}
          
          {summaryData && !isCompiling && (
            <div className="mt-4">
              <PipelineSummary
                businessSystem={summaryData.businessSystem}
                slideCount={summaryData.slideCount}
              />
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        <div className="border-t border-gray-100 p-4 bg-white flex-shrink-0">
          <div className="flex items-center gap-3">
            <button className="p-2.5 rounded-xl border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors" title="上传文件">
              <Paperclip size={18} />
            </button>
            
            <div className="flex-1 relative">
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="输入PRD文档内容或描述您的业务需求..."
                disabled={isTyping || isCompiling}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl resize-none focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 text-sm disabled:bg-gray-50 disabled:text-gray-400"
                rows={2}
              />
            </div>
            
            <button
              onClick={handleSend}
              disabled={!inputText.trim() || isTyping || isCompiling}
              className={`flex items-center gap-2 px-5 py-3 rounded-xl font-medium transition-all ${
                !inputText.trim() || isTyping || isCompiling
                  ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  : 'bg-gradient-to-r from-blue-500 to-indigo-600 text-white hover:from-blue-600 hover:to-indigo-700 shadow-lg shadow-blue-200'
              }`}
            >
              {isTyping || isCompiling ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  <span>{isLoading ? '生成中...' : '发送中'}</span>
                </>
              ) : (
                <>
                  <Send size={16} />
                  <span>发送</span>
                </>
              )}
            </button>
          </div>
          
          <div className="flex items-center gap-4 mt-3 px-1">
            <span className="text-xs text-gray-400">支持 Markdown 格式</span>
            <span className="text-xs text-gray-400">按 Enter 发送，Shift+Enter 换行</span>
            <div className="flex items-center gap-1 ml-auto">
              <Sparkles className="w-3 h-3 text-purple-500" />
              <span className="text-xs text-gray-400">AI 驱动</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;