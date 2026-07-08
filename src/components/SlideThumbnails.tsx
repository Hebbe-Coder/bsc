import { Plus, Trash2, Copy } from 'lucide-react';
import usePresentationStore from '../store/presentationStore';
import { themes } from '../theme/themes';

const THUMBNAIL_WIDTH = 120;
const THUMBNAIL_HEIGHT = 70;

const SlideThumbnails = () => {
  const { presentation, setCurrentSlideIndex, addSlide, deleteSlide, duplicateSlide } = usePresentationStore();
  const theme = themes[presentation.theme];

  return (
    <div className="h-24 bg-gray-50 border-t border-gray-200 flex items-center px-4 gap-3 overflow-x-auto">
      {presentation.slides.map((slide, index) => (
        <div
          key={slide.id}
          className="relative flex-shrink-0 group"
        >
          <div
            className={`cursor-pointer rounded-lg overflow-hidden transition-all ${
              presentation.currentSlideIndex === index
                ? 'ring-2 ring-blue-500 shadow-lg scale-105'
                : 'hover:shadow-md'
            }`}
            style={{
              width: THUMBNAIL_WIDTH,
              height: THUMBNAIL_HEIGHT,
            }}
            onClick={() => setCurrentSlideIndex(index)}
          >
            <div
              className="w-full h-full relative"
              style={{ backgroundColor: slide.backgroundColor }}
            >
              {slide.components.slice(0, 3).map((comp, i) => (
                <div
                  key={comp.id}
                  className="absolute overflow-hidden"
                  style={{
                    left: (comp.x / 800) * THUMBNAIL_WIDTH,
                    top: (comp.y / 500) * THUMBNAIL_HEIGHT,
                    width: (comp.width / 800) * THUMBNAIL_WIDTH,
                    height: (comp.height / 500) * THUMBNAIL_HEIGHT,
                    backgroundColor: comp.style.backgroundColor === 'transparent' 
                      ? 'rgba(0,0,0,0.05)' 
                      : comp.style.backgroundColor,
                    color: comp.style.color,
                    fontSize: Math.max(4, comp.style.fontSize / 8),
                    borderRadius: comp.style.borderRadius / 8,
                    borderWidth: comp.style.borderWidth / 4,
                  }}
                >
                  {comp.type === 'text' && (
                    <span className="text-xs truncate px-0.5">{comp.content.substring(0, 20)}</span>
                  )}
                  {comp.type === 'chart' && (
                    <div className="w-full h-full bg-white/50 flex items-center justify-center">
                      <svg width="20" height="15" viewBox="0 0 20 15">
                        <rect x="2" y="5" width="4" height="8" fill="#3b82f6" rx="1" />
                        <rect x="7" y="3" width="4" height="10" fill="#22c55e" rx="1" />
                        <rect x="12" y="7" width="4" height="6" fill="#f59e0b" rx="1" />
                      </svg>
                    </div>
                  )}
                  {comp.type === 'shape' && (
                    <div className="w-full h-full" style={{ backgroundColor: comp.style.backgroundColor }} />
                  )}
                </div>
              ))}
              
              {slide.components.length === 0 && (
                <div className="absolute inset-0 flex items-center justify-center text-gray-400">
                  <span className="text-xs">空白</span>
                </div>
              )}
            </div>
            
            <div 
              className="absolute bottom-0 left-0 right-0 text-center py-0.5 text-xs font-medium"
              style={{ backgroundColor: presentation.currentSlideIndex === index ? theme.accent : 'rgba(0,0,0,0.6)', color: 'white' }}
            >
              {index + 1}
            </div>
          </div>
          
          <div className="absolute -top-6 right-0 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={(e) => {
                e.stopPropagation();
                duplicateSlide(index);
              }}
              className="p-1 rounded bg-white border border-gray-200 shadow-sm hover:bg-gray-50 text-gray-600"
              title="复制"
            >
              <Copy size={12} />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                deleteSlide(index);
              }}
              className="p-1 rounded bg-white border border-gray-200 shadow-sm hover:bg-red-50 text-red-500"
              title="删除"
              disabled={presentation.slides.length <= 1}
            >
              <Trash2 size={12} />
            </button>
          </div>
        </div>
      ))}
      
      <button
        onClick={() => addSlide()}
        className="flex-shrink-0 w-20 h-20 rounded-lg border-2 border-dashed border-gray-300 hover:border-blue-500 hover:bg-blue-50 transition-colors flex flex-col items-center justify-center gap-1 text-gray-400 hover:text-blue-500"
      >
        <Plus size={20} />
        <span className="text-xs">添加</span>
      </button>
    </div>
  );
};

export default SlideThumbnails;
