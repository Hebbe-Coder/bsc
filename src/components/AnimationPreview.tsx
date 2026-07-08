import { useEffect, useState } from 'react';
import { X, Play, Pause, SkipBack, SkipForward, RotateCcw } from 'lucide-react';
import usePresentationStore from '../store/presentationStore';
import { themes } from '../theme/themes';
import { AnimationType } from '../types';

interface AnimationPreviewProps {
  onClose: () => void;
}

const animationDefinitions: Record<AnimationType, { keyframes: string; name: string }> = {
  fadeIn: { name: 'fadeIn', keyframes: 'from { opacity: 0; } to { opacity: 1; }' },
  fadeInUp: { name: 'fadeInUp', keyframes: 'from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); }' },
  fadeInDown: { name: 'fadeInDown', keyframes: 'from { opacity: 0; transform: translateY(-30px); } to { opacity: 1; transform: translateY(0); }' },
  fadeInLeft: { name: 'fadeInLeft', keyframes: 'from { opacity: 0; transform: translateX(-30px); } to { opacity: 1; transform: translateX(0); }' },
  fadeInRight: { name: 'fadeInRight', keyframes: 'from { opacity: 0; transform: translateX(30px); } to { opacity: 1; transform: translateX(0); }' },
  slideInLeft: { name: 'slideInLeft', keyframes: 'from { opacity: 0; transform: translateX(-100%); } to { opacity: 1; transform: translateX(0); }' },
  slideInRight: { name: 'slideInRight', keyframes: 'from { opacity: 0; transform: translateX(100%); } to { opacity: 1; transform: translateX(0); }' },
  slideInTop: { name: 'slideInTop', keyframes: 'from { opacity: 0; transform: translateY(-100%); } to { opacity: 1; transform: translateY(0); }' },
  slideInBottom: { name: 'slideInBottom', keyframes: 'from { opacity: 0; transform: translateY(100%); } to { opacity: 1; transform: translateY(0); }' },
  slideInUp: { name: 'slideInUp', keyframes: 'from { opacity: 0; transform: translateY(100%); } to { opacity: 1; transform: translateY(0); }' },
  slideInDown: { name: 'slideInDown', keyframes: 'from { opacity: 0; transform: translateY(-100%); } to { opacity: 1; transform: translateY(0); }' },
  zoomIn: { name: 'zoomIn', keyframes: 'from { opacity: 0; transform: scale(0.5); } to { opacity: 1; transform: scale(1); }' },
  zoomInUp: { name: 'zoomInUp', keyframes: 'from { opacity: 0; transform: scale(0.5) translateY(50px); } to { opacity: 1; transform: scale(1) translateY(0); }' },
  zoomInDown: { name: 'zoomInDown', keyframes: 'from { opacity: 0; transform: scale(0.5) translateY(-50px); } to { opacity: 1; transform: scale(1) translateY(0); }' },
  rotateIn: { name: 'rotateIn', keyframes: 'from { opacity: 0; transform: rotate(-180deg) scale(0.5); } to { opacity: 1; transform: rotate(0) scale(1); }' },
  rotateInLeft: { name: 'rotateInLeft', keyframes: 'from { opacity: 0; transform: rotate(-90deg); } to { opacity: 1; transform: rotate(0); }' },
  rotateInRight: { name: 'rotateInRight', keyframes: 'from { opacity: 0; transform: rotate(90deg); } to { opacity: 1; transform: rotate(0); }' },
  bounceIn: { name: 'bounceIn', keyframes: '0% { opacity: 0; transform: scale(0.3); } 50% { opacity: 1; transform: scale(1.05); } 70% { transform: scale(0.9); } 100% { transform: scale(1); }' },
  bounceInDown: { name: 'bounceInDown', keyframes: '0% { opacity: 0; transform: translateY(-2000px); } 60% { opacity: 1; transform: translateY(30px); } 75% { transform: translateY(-10px); } 90% { transform: translateY(5px); } 100% { transform: translateY(0); }' },
  bounceInUp: { name: 'bounceInUp', keyframes: '0% { opacity: 0; transform: translateY(2000px); } 60% { opacity: 1; transform: translateY(-30px); } 75% { transform: translateY(10px); } 90% { transform: translateY(-5px); } 100% { transform: translateY(0); }' },
  flipInX: { name: 'flipInX', keyframes: 'from { opacity: 0; transform: perspective(400px) rotateX(90deg); } to { opacity: 1; transform: perspective(400px) rotateX(0); }' },
  flipInY: { name: 'flipInY', keyframes: 'from { opacity: 0; transform: perspective(400px) rotateY(90deg); } to { opacity: 1; transform: perspective(400px) rotateY(0); }' },
};

const AnimationPreview = ({ onClose }: AnimationPreviewProps) => {
  const { presentation } = usePresentationStore();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isAnimating, setIsAnimating] = useState(true);
  
  const theme = themes[presentation.theme];
  const currentSlide = presentation.slides[currentIndex];

  useEffect(() => {
    setIsAnimating(true);
    const timer = setTimeout(() => setIsAnimating(false), 1500);
    return () => clearTimeout(timer);
  }, [currentIndex]);

  useEffect(() => {
    if (!isPlaying) return;
    
    const timer = setTimeout(() => {
      if (currentIndex < presentation.slides.length - 1) {
        setCurrentIndex(prev => prev + 1);
      } else {
        setIsPlaying(false);
      }
    }, 3000);
    
    return () => clearTimeout(timer);
  }, [isPlaying, currentIndex, presentation.slides.length]);

  const handlePrev = () => {
    setCurrentIndex(prev => Math.max(0, prev - 1));
    setIsPlaying(false);
  };

  const handleNext = () => {
    setCurrentIndex(prev => Math.min(presentation.slides.length - 1, prev + 1));
    setIsPlaying(false);
  };

  const handlePlayPause = () => {
    setIsPlaying(prev => !prev);
  };

  const handleReset = () => {
    setCurrentIndex(0);
    setIsPlaying(false);
  };

  const getAnimationStyle = (animationType: AnimationType, duration: number, delay: number) => {
    const anim = animationDefinitions[animationType] || animationDefinitions['fadeIn'];
    return {
      opacity: 0,
      animation: `${anim.name} ${duration}ms ease ${delay}ms forwards`,
    };
  };

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div className="relative w-[90vw] max-w-4xl">
        <button
          onClick={onClose}
          className="absolute -top-12 right-0 text-white hover:text-gray-300 transition-colors z-10"
        >
          <X size={24} />
        </button>

        <div 
          className={`relative rounded-lg overflow-hidden shadow-2xl ${isAnimating ? 'animate-fade-in' : ''}`}
          style={{
            width: 800,
            height: 500,
            backgroundColor: currentSlide?.backgroundColor || theme.background,
            backgroundImage: currentSlide?.backgroundColor !== theme.background 
              ? `linear-gradient(135deg, ${theme.primary}10 0%, ${theme.accent}10 100%)` 
              : undefined,
          }}
        >
          {currentSlide?.components.map((component, idx) => (
            <div
              key={component.id}
              className="absolute"
              style={{
                ...getAnimationStyle(component.animation.type, component.animation.duration, component.animation.delay),
                left: component.x,
                top: component.y,
                width: component.width,
                height: component.height,
                fontFamily: component.style.fontFamily,
                fontSize: component.style.fontSize,
                fontWeight: component.style.fontWeight,
                color: component.style.color,
                backgroundColor: component.style.backgroundColor,
                borderRadius: component.style.borderRadius,
                borderWidth: component.style.borderWidth,
                borderColor: component.style.borderColor,
                borderStyle: component.style.borderWidth > 0 ? 'solid' : 'none',
                boxShadow: component.style.shadow,
                textAlign: component.style.textAlign || 'left',
                padding: component.type === 'text' ? '8px' : 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: component.style.textAlign === 'center' ? 'center' : 'flex-start',
              }}
            >
              {component.type === 'text' && (
                <span className="whitespace-pre-wrap break-words">{component.content}</span>
              )}
              {component.type === 'chart' && (
                <div className="w-full h-full flex items-center justify-center">
                  <span className="text-gray-500 text-sm">图表预览</span>
                </div>
              )}
              {component.type === 'shape' && null}
              {component.type === 'image' && (
                <div className="w-full h-full bg-gray-200 flex items-center justify-center">
                  <span className="text-gray-400 text-sm">图片</span>
                </div>
              )}
              {component.type === 'table' && (
                <table className="w-full h-full border-collapse text-xs">
                  <thead>
                    <tr className="bg-blue-500 text-white">
                      {(component.data?.columns || ['列1', '列2']).map((col, i) => (
                        <th key={i} className="border border-gray-300 p-1">{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(component.data?.rows || [['数据1', '数据2'], ['数据3', '数据4']]).map((row, i) => (
                      <tr key={i}>
                        {row.map((cell, j) => (
                          <td key={j} className="border border-gray-300 p-1">{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {component.type === 'media' && (
                <div className="w-full h-full bg-gray-900 flex items-center justify-center">
                  <span className="text-gray-400 text-sm">视频</span>
                </div>
              )}
            </div>
          ))}

          <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 flex items-center gap-4 bg-black/50 backdrop-blur-sm rounded-full px-6 py-3">
            <button
              onClick={handleReset}
              className="text-white hover:text-gray-300 transition-colors"
              title="重置"
            >
              <RotateCcw size={18} />
            </button>
            <button
              onClick={handlePrev}
              disabled={currentIndex === 0}
              className="text-white hover:text-gray-300 transition-colors disabled:opacity-50"
              title="上一页"
            >
              <SkipBack size={18} />
            </button>
            <button
              onClick={handlePlayPause}
              className="w-10 h-10 bg-white rounded-full flex items-center justify-center text-black hover:bg-gray-200 transition-colors"
              title={isPlaying ? '暂停' : '播放'}
            >
              {isPlaying ? <Pause size={18} /> : <Play size={18} />}
            </button>
            <button
              onClick={handleNext}
              disabled={currentIndex === presentation.slides.length - 1}
              className="text-white hover:text-gray-300 transition-colors disabled:opacity-50"
              title="下一页"
            >
              <SkipForward size={18} />
            </button>
            
            <div className="flex items-center gap-2 ml-4">
              {presentation.slides.map((_, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    setCurrentIndex(idx);
                    setIsPlaying(false);
                  }}
                  className={`w-2 h-2 rounded-full transition-all ${
                    idx === currentIndex 
                      ? 'bg-white w-6' 
                      : 'bg-white/50 hover:bg-white/70'
                  }`}
                />
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4 text-center text-white/70 text-sm">
          幻灯片 {currentIndex + 1} / {presentation.slides.length}
        </div>
      </div>

      <style>{`
        ${Object.entries(animationDefinitions).map(([_, anim]) => `
          @keyframes ${anim.name} {
            ${anim.keyframes}
          }
        `).join('')}
      `}</style>
    </div>
  );
};

export default AnimationPreview;
