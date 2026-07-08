import { useEffect, useState, useCallback } from 'react';
import { X, ChevronLeft, ChevronRight, Play, Pause, RotateCcw } from 'lucide-react';
import usePresentationStore from '../store/presentationStore';
import { themes } from '../theme/themes';
import ChartComponent from './ChartComponent';

const CANVAS_WIDTH = 800;
const CANVAS_HEIGHT = 500;

interface PreviewProps {
  onClose: () => void;
}

const transitionAnimations: Record<string, { enter: string; exit: string }> = {
  'fade': { enter: 'fadeIn', exit: 'fadeOut' },
  'slide-left': { enter: 'slideInRight', exit: 'slideOutLeft' },
  'slide-right': { enter: 'slideInLeft', exit: 'slideOutRight' },
  'slide-up': { enter: 'slideInBottom', exit: 'slideOutTop' },
  'slide-down': { enter: 'slideInTop', exit: 'slideOutBottom' },
  'zoom-in': { enter: 'zoomIn', exit: 'zoomOut' },
  'zoom-out': { enter: 'zoomOutIn', exit: 'zoomOut' },
  'cube': { enter: 'cubeIn', exit: 'cubeOut' },
  'flip': { enter: 'flipIn', exit: 'flipOut' },
  'rotate': { enter: 'rotateIn', exit: 'rotateOut' },
};

const Preview = ({ onClose }: PreviewProps) => {
  const { presentation, setCurrentSlideIndex } = usePresentationStore();
  const [isPlaying, setIsPlaying] = useState(false);
  const [showControls, setShowControls] = useState(true);
  const [transitionDirection, setTransitionDirection] = useState<'forward' | 'backward'>('forward');
  const [isTransitioning, setIsTransitioning] = useState(false);
  
  const currentSlide = presentation.slides[presentation.currentSlideIndex];
  const theme = themes[presentation.theme];

  const goToPrev = useCallback(() => {
    if (isTransitioning || presentation.currentSlideIndex === 0) return;
    setTransitionDirection('backward');
    setIsTransitioning(true);
    setTimeout(() => {
      setCurrentSlideIndex(presentation.currentSlideIndex - 1);
      setIsTransitioning(false);
    }, 300);
  }, [isTransitioning, presentation.currentSlideIndex, setCurrentSlideIndex]);

  const goToNext = useCallback(() => {
    if (isTransitioning || presentation.currentSlideIndex >= presentation.slides.length - 1) return;
    setTransitionDirection('forward');
    setIsTransitioning(true);
    setTimeout(() => {
      setCurrentSlideIndex(presentation.currentSlideIndex + 1);
      setIsTransitioning(false);
    }, 300);
  }, [isTransitioning, presentation.currentSlideIndex, presentation.slides.length, setCurrentSlideIndex]);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (isPlaying) {
      interval = setInterval(() => {
        if (presentation.currentSlideIndex < presentation.slides.length - 1) {
          goToNext();
        } else {
          setIsPlaying(false);
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [isPlaying, presentation.currentSlideIndex, presentation.slides.length, goToNext]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowLeft':
          goToPrev();
          break;
        case 'ArrowRight':
          goToNext();
          break;
        case ' ':
          e.preventDefault();
          setIsPlaying(!isPlaying);
          break;
        case 'Escape':
          onClose();
          break;
        case 'Home':
          setCurrentSlideIndex(0);
          break;
        case 'End':
          setCurrentSlideIndex(presentation.slides.length - 1);
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [goToPrev, goToNext, onClose, setCurrentSlideIndex, presentation.slides.length]);

  useEffect(() => {
    let timeout: ReturnType<typeof setTimeout>;
    const handleMouseMove = () => {
      setShowControls(true);
      clearTimeout(timeout);
      timeout = setTimeout(() => setShowControls(false), 3000);
    };

    document.addEventListener('mousemove', handleMouseMove);
    return () => {
      clearTimeout(timeout);
      document.removeEventListener('mousemove', handleMouseMove);
    };
  }, []);

  const renderComponent = (component: any, index: number) => {
    const animationStyle = {
      animation: `${component.animation.type} ${component.animation.duration}ms ${component.animation.easing} ${component.animation.delay}ms forwards`,
      opacity: 0,
    };

    switch (component.type) {
      case 'text':
        return (
          <div
            key={component.id}
            style={{
              ...animationStyle,
              position: 'absolute',
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
              boxShadow: component.style.shadow,
              textAlign: component.style.textAlign || 'left',
              padding: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: component.style.textAlign === 'center' ? 'center' : 'flex-start',
            }}
          >
            {component.content}
          </div>
        );
      case 'chart':
        return (
          <div
            key={component.id}
            style={{
              ...animationStyle,
              position: 'absolute',
              left: component.x,
              top: component.y,
              width: component.width,
              height: component.height,
            }}
          >
            <ChartComponent data={component.data} width={component.width} height={component.height} />
          </div>
        );
      case 'shape':
        return (
          <div
            key={component.id}
            style={{
              ...animationStyle,
              position: 'absolute',
              left: component.x,
              top: component.y,
              width: component.width,
              height: component.height,
              backgroundColor: component.style.backgroundColor,
              borderRadius: component.style.borderRadius,
            }}
          />
        );
      case 'image':
        return (
          <div
            key={component.id}
            style={{
              ...animationStyle,
              position: 'absolute',
              left: component.x,
              top: component.y,
              width: component.width,
              height: component.height,
            }}
          >
            <div className="w-full h-full bg-gray-200 flex items-center justify-center">
              <span className="text-gray-400 text-sm">图片占位</span>
            </div>
          </div>
        );
      case 'table':
        return (
          <div
            key={component.id}
            style={{
              ...animationStyle,
              position: 'absolute',
              left: component.x,
              top: component.y,
              width: component.width,
              height: component.height,
            }}
          >
            <table className="w-full h-full border-collapse">
              <tbody>
                <tr>
                  <td className="border border-gray-300 p-2 text-sm">单元格 1</td>
                  <td className="border border-gray-300 p-2 text-sm">单元格 2</td>
                </tr>
                <tr>
                  <td className="border border-gray-300 p-2 text-sm">单元格 3</td>
                  <td className="border border-gray-300 p-2 text-sm">单元格 4</td>
                </tr>
              </tbody>
            </table>
          </div>
        );
      default:
        return null;
    }
  };

  const getTransitionClass = () => {
    const transition = currentSlide?.transition || 'fade';
    const anim = transitionAnimations[transition] || transitionAnimations['fade'];
    return transitionDirection === 'forward' ? anim.enter : anim.exit;
  };

  return (
    <div className="fixed inset-0 bg-black z-50 flex items-center justify-center">
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors z-10"
      >
        <X size={24} />
      </button>

      <div 
        className={`relative shadow-2xl rounded-lg overflow-hidden transition-all duration-300 ${getTransitionClass()}`}
        style={{
          width: CANVAS_WIDTH,
          height: CANVAS_HEIGHT,
          backgroundColor: currentSlide?.backgroundColor || theme.background,
        }}
        onMouseMove={() => setShowControls(true)}
      >
        {currentSlide?.components.map((component, index) => renderComponent(component, index))}
      </div>

      <div 
        className={`absolute bottom-8 left-1/2 transform -translate-x-1/2 flex items-center gap-4 transition-opacity duration-300 ${
          showControls ? 'opacity-100' : 'opacity-0'
        }`}
      >
        <button
          onClick={goToPrev}
          disabled={presentation.currentSlideIndex === 0}
          className="p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:scale-110"
        >
          <ChevronLeft size={24} />
        </button>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="p-3 rounded-full bg-blue-500 hover:bg-blue-600 text-white transition-all hover:scale-110 shadow-lg shadow-blue-500/30"
          >
            {isPlaying ? <Pause size={20} /> : <Play size={20} />}
          </button>
          <button
            onClick={() => {
              setCurrentSlideIndex(0);
              setIsPlaying(false);
            }}
            className="p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-all hover:scale-110"
          >
            <RotateCcw size={20} />
          </button>
        </div>

        <button
          onClick={goToNext}
          disabled={presentation.currentSlideIndex === presentation.slides.length - 1}
          className="p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:scale-110"
        >
          <ChevronRight size={24} />
        </button>
      </div>

      <div 
        className={`absolute bottom-8 right-8 text-white text-sm transition-opacity duration-300 ${
          showControls ? 'opacity-100' : 'opacity-0'
        }`}
      >
        {presentation.currentSlideIndex + 1} / {presentation.slides.length}
      </div>

      <div 
        className={`absolute top-8 left-8 text-white/60 text-xs transition-opacity duration-300 ${
          showControls ? 'opacity-100' : 'opacity-0'
        }`}
      >
        <div>← → 切换</div>
        <div>空格 播放/暂停</div>
        <div>Esc 退出</div>
      </div>

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes fadeOut {
          from { opacity: 1; }
          to { opacity: 0; }
        }
        @keyframes slideInLeft {
          from { opacity: 0; transform: translateX(-100%); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes slideInRight {
          from { opacity: 0; transform: translateX(100%); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes slideInTop {
          from { opacity: 0; transform: translateY(-100%); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes slideInBottom {
          from { opacity: 0; transform: translateY(100%); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes slideOutLeft {
          from { opacity: 1; transform: translateX(0); }
          to { opacity: 0; transform: translateX(-100%); }
        }
        @keyframes slideOutRight {
          from { opacity: 1; transform: translateX(0); }
          to { opacity: 0; transform: translateX(100%); }
        }
        @keyframes slideOutTop {
          from { opacity: 1; transform: translateY(0); }
          to { opacity: 0; transform: translateY(-100%); }
        }
        @keyframes slideOutBottom {
          from { opacity: 1; transform: translateY(0); }
          to { opacity: 0; transform: translateY(100%); }
        }
        @keyframes zoomIn {
          from { opacity: 0; transform: scale(0.5); }
          to { opacity: 1; transform: scale(1); }
        }
        @keyframes zoomOut {
          from { opacity: 1; transform: scale(1); }
          to { opacity: 0; transform: scale(0.5); }
        }
        @keyframes zoomOutIn {
          from { opacity: 0; transform: scale(1.5); }
          to { opacity: 1; transform: scale(1); }
        }
        @keyframes rotateIn {
          from { opacity: 0; transform: rotate(-180deg) scale(0.5); }
          to { opacity: 1; transform: rotate(0) scale(1); }
        }
        @keyframes rotateOut {
          from { opacity: 1; transform: rotate(0) scale(1); }
          to { opacity: 0; transform: rotate(180deg) scale(0.5); }
        }
        @keyframes cubeIn {
          from { opacity: 0; transform: rotateY(-90deg); }
          to { opacity: 1; transform: rotateY(0); }
        }
        @keyframes cubeOut {
          from { opacity: 1; transform: rotateY(0); }
          to { opacity: 0; transform: rotateY(90deg); }
        }
        @keyframes flipIn {
          from { opacity: 0; transform: perspective(400px) rotateY(-90deg); }
          to { opacity: 1; transform: perspective(400px) rotateY(0); }
        }
        @keyframes flipOut {
          from { opacity: 1; transform: perspective(400px) rotateY(0); }
          to { opacity: 0; transform: perspective(400px) rotateY(90deg); }
        }
      `}</style>
    </div>
  );
};

export default Preview;
