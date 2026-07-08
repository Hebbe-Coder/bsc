import React from 'react';
import { Bot, User, Info, Loader2 } from 'lucide-react';

export type MessageType = 'user' | 'assistant' | 'system' | 'thinking';

export interface Message {
  id: string;
  type: MessageType;
  content: string;
  timestamp?: Date;
}

interface MessageBubbleProps {
  message: Message;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const formatTime = (timestamp?: Date) => {
    if (!timestamp) return '';
    return timestamp.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  };

  const getIcon = () => {
    switch (message.type) {
      case 'user':
        return <User className="w-8 h-8 text-white" />;
      case 'assistant':
        return <Bot className="w-8 h-8 text-white" />;
      case 'system':
        return <Info className="w-5 h-5 text-blue-500" />;
      case 'thinking':
        return <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />;
    }
  };

  const getStyles = () => {
    switch (message.type) {
      case 'user':
        return {
          container: 'flex justify-end',
          bubble: 'bg-gradient-to-r from-blue-500 to-indigo-600 text-white rounded-2xl rounded-tr-sm px-5 py-3 max-w-[80%] shadow-lg shadow-blue-200',
          icon: 'hidden',
        };
      case 'assistant':
        return {
          container: 'flex justify-start',
          bubble: 'bg-white border border-gray-100 text-gray-800 rounded-2xl rounded-tl-sm px-5 py-3 max-w-[80%] shadow-sm',
          icon: 'bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl p-1.5 mr-3 flex-shrink-0',
        };
      case 'system':
        return {
          container: 'flex justify-center',
          bubble: 'bg-blue-50 text-blue-600 rounded-full px-4 py-2 max-w-[70%] text-sm',
          icon: '',
        };
      case 'thinking':
        return {
          container: 'flex justify-start',
          bubble: 'bg-gradient-to-r from-blue-50 to-indigo-50 text-gray-600 rounded-2xl rounded-tl-sm px-5 py-3 max-w-[80%]',
          icon: 'mr-3 flex-shrink-0',
        };
    }
  };

  const styles = getStyles();

  return (
    <div className={`flex items-start mb-4 ${styles.container}`}>
      {message.type === 'assistant' && (
        <div className={styles.icon}>
          {getIcon()}
        </div>
      )}
      
      {(message.type === 'system' || message.type === 'thinking') && (
        <div className={styles.icon}>
          {getIcon()}
        </div>
      )}
      
      <div className={`flex flex-col ${message.type === 'user' ? 'items-end' : 'items-start'}`}>
        <div className={styles.bubble}>
          {message.type === 'thinking' ? (
            <div className="flex items-center gap-2">
              <span className="text-sm">正在思考...</span>
              <Loader2 className="w-4 h-4 animate-spin" />
            </div>
          ) : (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
          )}
        </div>
        {message.timestamp && (
          <span className="text-xs text-gray-400 mt-1">{formatTime(message.timestamp)}</span>
        )}
      </div>
    </div>
  );
};

export default MessageBubble;