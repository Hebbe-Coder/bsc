import { create } from 'zustand';
import { Presentation, Slide, Component, ThemeType, ComponentType, StyleConfig, AnimationConfig } from '../types';
import { themes } from '../theme/themes';
import { bscApi, BusinessSystem } from '../api/bscApi';
import { convertBusinessSystemToPresentation } from '../utils/bscConverter';
import { API_BASE } from '../config';
import { apiFetch } from '../api/fetchWrapper';

interface LayoutTemplate {
  name: string;
  rows: number;
  cols: number;
  components: Omit<Component, 'id'>[];
}

const generateId = () => Math.random().toString(36).substring(2, 11);

const defaultStyle: StyleConfig = {
  fontFamily: 'Inter',
  fontSize: 16,
  fontWeight: '400',
  color: '#1f2937',
  backgroundColor: 'transparent',
  borderRadius: 0,
  borderWidth: 0,
  borderColor: '#e5e7eb',
  shadow: 'none',
};

const defaultAnimation: AnimationConfig = {
  type: 'fadeIn',
  delay: 0,
  duration: 500,
  easing: 'easeOut',
};

const createEmptySlide = (index: number, theme: ThemeType): Slide => ({
  id: generateId(),
  index,
  backgroundColor: themes[theme].background,
  components: [],
  transition: 'fade',
});

const createDefaultPresentation = (theme: ThemeType = 'business'): Presentation => {
  const themeConfig = themes[theme];
  return {
    id: generateId(),
    title: '新演示文稿',
    theme,
    currentSlideIndex: 0,
    master: {
      id: generateId(),
      titleStyle: {
        ...defaultStyle,
        fontSize: 48,
        fontWeight: '700',
        color: themeConfig.primary,
        fontFamily: themeConfig.fontFamily,
        textAlign: 'center' as const,
      },
      bodyStyle: {
        ...defaultStyle,
        fontSize: 20,
        fontWeight: '400',
        color: themeConfig.text,
        fontFamily: themeConfig.fontFamily,
        textAlign: 'left' as const,
        lineHeight: 1.8,
      },
      footerStyle: {
        ...defaultStyle,
        fontSize: 12,
        fontWeight: '400',
        color: themeConfig.textFaint,
        fontFamily: themeConfig.fontFamily,
        textAlign: 'center' as const,
      },
      backgroundColor: themeConfig.background,
      showFooter: true,
      footerText: '',
      showPageNumber: true,
      showDate: true,
    },
    slides: [
      {
        id: generateId(),
        index: 0,
        backgroundColor: themeConfig.background,
        transition: 'fade',
        components: [
          {
            id: generateId(),
            type: 'text',
            x: 50,
            y: 100,
            width: 700,
            height: 80,
            content: '演示文稿标题',
            style: {
              ...defaultStyle,
              fontSize: 48,
              fontWeight: '700',
              color: themeConfig.primary,
            },
            animation: { ...defaultAnimation, delay: 0 },
          },
          {
            id: generateId(),
            type: 'text',
            x: 50,
            y: 200,
            width: 700,
            height: 40,
            content: '副标题文本',
            style: {
              ...defaultStyle,
              fontSize: 24,
              fontWeight: '500',
              color: themeConfig.textLight,
            },
            animation: { ...defaultAnimation, delay: 200 },
          },
        ],
      },
      {
        id: generateId(),
        index: 1,
        backgroundColor: themeConfig.background,
        transition: 'slide-left',
        components: [
          {
            id: generateId(),
            type: 'text',
            x: 50,
            y: 60,
            width: 700,
            height: 50,
            content: '目录',
            style: {
              ...defaultStyle,
              fontSize: 36,
              fontWeight: '600',
              color: themeConfig.primary,
            },
            animation: { ...defaultAnimation, delay: 0 },
          },
          {
            id: generateId(),
            type: 'text',
            x: 50,
            y: 150,
            width: 700,
            height: 36,
            content: '● 第一部分内容',
            style: {
              ...defaultStyle,
              fontSize: 20,
              fontWeight: '500',
              color: themeConfig.text,
            },
            animation: { ...defaultAnimation, delay: 150 },
          },
          {
            id: generateId(),
            type: 'text',
            x: 50,
            y: 200,
            width: 700,
            height: 36,
            content: '● 第二部分内容',
            style: {
              ...defaultStyle,
              fontSize: 20,
              fontWeight: '500',
              color: themeConfig.text,
            },
            animation: { ...defaultAnimation, delay: 300 },
          },
          {
            id: generateId(),
            type: 'text',
            x: 50,
            y: 250,
            width: 700,
            height: 36,
            content: '● 第三部分内容',
            style: {
              ...defaultStyle,
              fontSize: 20,
              fontWeight: '500',
              color: themeConfig.text,
            },
            animation: { ...defaultAnimation, delay: 450 },
          },
        ],
      },
      {
        id: generateId(),
        index: 2,
        backgroundColor: themeConfig.background,
        transition: 'fade',
        components: [
          {
            id: generateId(),
            type: 'text',
            x: 50,
            y: 60,
            width: 700,
            height: 50,
            content: '数据展示',
            style: {
              ...defaultStyle,
              fontSize: 36,
              fontWeight: '600',
              color: themeConfig.primary,
            },
            animation: { ...defaultAnimation, delay: 0 },
          },
          {
            id: generateId(),
            type: 'chart',
            x: 50,
            y: 140,
            width: 700,
            height: 400,
            content: '',
            style: defaultStyle,
            animation: { ...defaultAnimation, delay: 200 },
            data: {
              type: 'bar',
              labels: ['Q1', 'Q2', 'Q3', 'Q4'],
              datasets: [
                { name: '销售额', data: [120, 190, 300, 450], color: themeConfig.primary },
                { name: '利润', data: [45, 78, 120, 180], color: themeConfig.success },
              ],
            },
          },
        ],
      },
      {
        id: generateId(),
        index: 3,
        backgroundColor: themeConfig.background,
        transition: 'zoom-in',
        components: [
          {
            id: generateId(),
            type: 'text',
            x: 50,
            y: 60,
            width: 700,
            height: 50,
            content: '结论',
            style: {
              ...defaultStyle,
              fontSize: 36,
              fontWeight: '600',
              color: themeConfig.primary,
            },
            animation: { ...defaultAnimation, delay: 0 },
          },
          {
            id: generateId(),
            type: 'text',
            x: 50,
            y: 150,
            width: 700,
            height: 100,
            content: '感谢您的观看！',
            style: {
              ...defaultStyle,
              fontSize: 28,
              fontWeight: '500',
              color: themeConfig.text,
              textAlign: 'center' as const,
            },
            animation: { ...defaultAnimation, delay: 300 },
          },
        ],
      },
    ],
  };
};

export type PipelineStageStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface PipelineStage {
  id: string;
  name: string;
  description: string;
  status: PipelineStageStatus;
  progress: number;
  output?: string;
  error?: string;
  startTime?: number;
  endTime?: number;
}

interface PipelineContext {
  prdContent: string;
  prdStructure?: any;
  analysisResult?: any;
  objectives?: any[];
  workflow?: any[];
  risks?: any[];
  businessSystem?: BusinessSystem;
}

interface PresentationStore {
  presentation: Presentation;
  selectedComponentId: string | null;
  isLoading: boolean;
  error: string | null;
  history: Presentation[];
  historyIndex: number;
  pipelineStages: PipelineStage[];
  isCompiling: boolean;
  abortController: AbortController | null;
  pipelineContext: PipelineContext | null;
  setTitle: (title: string) => void;
  setTheme: (theme: ThemeType) => void;
  setCurrentSlideIndex: (index: number) => void;
  addSlide: () => void;
  deleteSlide: (index: number) => void;
  duplicateSlide: (index: number) => void;
  reorderSlides: (fromIndex: number, toIndex: number) => void;
  updateSlideBackground: (index: number, color: string) => void;
  updateSlideTransition: (index: number, transition: string) => void;
  updateSlideNotes: (index: number, notes: string) => void;
  addComponent: (slideIndex: number, type: ComponentType, x: number, y: number) => void;
  updateComponent: (componentId: string, updates: Partial<Component>) => void;
  deleteComponent: (componentId: string) => void;
  selectComponent: (componentId: string | null) => void;
  moveComponent: (componentId: string, x: number, y: number) => void;
  resizeComponent: (componentId: string, width: number, height: number) => void;
  alignComponents: (alignment: 'left' | 'center' | 'right' | 'top' | 'middle' | 'bottom') => void;
  distributeComponents: (direction: 'horizontal' | 'vertical') => void;
  centerComponent: (componentId: string) => void;
  snapToGrid: (componentId: string) => void;
  applyLayoutTemplate: (slideIndex: number, layoutName: string) => void;
  updateMaster: (updates: Partial<Presentation['master']>) => void;
  applyMasterToSlides: () => void;
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
  reset: () => void;
  importPresentation: (presentation: Presentation) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  compileFromPRD: (prdContent: string, theme?: ThemeType) => Promise<{ context: any; presentation: Presentation } | undefined>;
  cancelCompile: () => void;
  resetPipeline: () => void;
  retryStage: (stageId: string) => Promise<void>;
}

const MAX_HISTORY = 50;

const usePresentationStore = create<PresentationStore>((set, get) => {
  const initialPresentation = createDefaultPresentation();
  
  const saveHistory = () => {
    const { presentation, history, historyIndex } = get();
    const newHistory = history.slice(0, historyIndex + 1);
    newHistory.push(JSON.parse(JSON.stringify(presentation)));
    if (newHistory.length > MAX_HISTORY) {
      newHistory.shift();
    }
    set({ history: newHistory, historyIndex: newHistory.length - 1 });
  };

  const createInitialPipelineStages = (): PipelineStage[] => [
    { id: 'analyze', name: 'PRD分析', description: '理解业务需求和目标', status: 'pending', progress: 0 },
    { id: 'extract', name: '目标提取', description: '提取核心目标和关键指标', status: 'pending', progress: 0 },
    { id: 'design', name: '流程设计', description: '设计业务流程和交互逻辑', status: 'pending', progress: 0 },
    { id: 'evaluate', name: '风险评估', description: '识别潜在风险和应对策略', status: 'pending', progress: 0 },
    { id: 'generate', name: '文稿生成', description: '生成演示文稿', status: 'pending', progress: 0 },
  ];

  return {
    presentation: initialPresentation,
    selectedComponentId: null,
    isLoading: false,
    error: null,
    history: [JSON.parse(JSON.stringify(initialPresentation))],
    historyIndex: 0,
    pipelineStages: createInitialPipelineStages(),
    isCompiling: false,
    abortController: null,
    pipelineContext: null,

    setTitle: (title) => {
      set((state) => ({
        presentation: { ...state.presentation, title },
      }));
      setTimeout(saveHistory, 0);
    },

    setTheme: (theme) => {
      set((state) => ({
        presentation: {
          ...state.presentation,
          theme,
          slides: state.presentation.slides.map((slide) => ({
            ...slide,
            backgroundColor: themes[theme].background,
            components: slide.components.map((comp) => ({
              ...comp,
              style: comp.type === 'text' && comp.x === 50 && comp.y === 100
                ? { ...comp.style, color: themes[theme].primary }
                : comp.style,
            })),
          })),
        },
      }));
      setTimeout(saveHistory, 0);
    },

    setCurrentSlideIndex: (index) =>
      set((state) => ({
        presentation: {
          ...state.presentation,
          currentSlideIndex: Math.max(0, Math.min(index, state.presentation.slides.length - 1)),
        },
      })),

    addSlide: () => {
      set((state) => {
        const newSlide = createEmptySlide(state.presentation.slides.length, state.presentation.theme);
        return {
          presentation: {
            ...state.presentation,
            slides: [...state.presentation.slides, newSlide],
          },
        };
      });
      setTimeout(saveHistory, 0);
    },

    deleteSlide: (index) => {
      set((state) => {
        const slides = state.presentation.slides.filter((_, i) => i !== index);
        return {
          presentation: {
            ...state.presentation,
            slides: slides.map((slide, i) => ({ ...slide, index: i })),
            currentSlideIndex: Math.min(state.presentation.currentSlideIndex, slides.length - 1),
          },
        };
      });
      setTimeout(saveHistory, 0);
    },

    duplicateSlide: (index) => {
      set((state) => {
        const slideToDuplicate = state.presentation.slides[index];
        const newSlide: Slide = {
          ...slideToDuplicate,
          id: generateId(),
          index: state.presentation.slides.length,
          components: slideToDuplicate.components.map((comp) => ({
            ...comp,
            id: generateId(),
          })),
        };
        const slides = [...state.presentation.slides.slice(0, index + 1), newSlide, ...state.presentation.slides.slice(index + 1)];
        return {
          presentation: {
            ...state.presentation,
            slides: slides.map((slide, i) => ({ ...slide, index: i })),
          },
        };
      });
      setTimeout(saveHistory, 0);
    },

    reorderSlides: (fromIndex, toIndex) => {
      set((state) => {
        const slides = [...state.presentation.slides];
        const [removed] = slides.splice(fromIndex, 1);
        slides.splice(toIndex, 0, removed);
        return {
          presentation: {
            ...state.presentation,
            slides: slides.map((slide, i) => ({ ...slide, index: i })),
          },
        };
      });
      setTimeout(saveHistory, 0);
    },

    updateSlideBackground: (index, color) => {
      set((state) => ({
        presentation: {
          ...state.presentation,
          slides: state.presentation.slides.map((slide, i) =>
            i === index ? { ...slide, backgroundColor: color } : slide
          ),
        },
      }));
      setTimeout(saveHistory, 0);
    },

    updateSlideTransition: (index, transition) => {
      set((state) => ({
        presentation: {
          ...state.presentation,
          slides: state.presentation.slides.map((slide, i) =>
            i === index ? { ...slide, transition: transition as any } : slide
          ),
        },
      }));
      setTimeout(saveHistory, 0);
    },

    updateSlideNotes: (index, notes) => {
      set((state) => ({
        presentation: {
          ...state.presentation,
          slides: state.presentation.slides.map((slide, i) =>
            i === index ? { ...slide, notes } : slide
          ),
        },
      }));
      setTimeout(saveHistory, 0);
    },

    addComponent: (slideIndex, type, x, y) => {
      set((state) => {
        const theme = themes[state.presentation.theme];
        const newComponent: Component = {
          id: generateId(),
          type,
          x,
          y,
          width: type === 'chart' ? 600 : 300,
          height: type === 'chart' ? 350 : type === 'image' ? 200 : 100,
          content: type === 'text' ? '双击编辑文本' : '',
          style: {
            ...defaultStyle,
            color: theme.text,
            backgroundColor: type === 'shape' ? theme.accent : 'transparent',
          },
          animation: { ...defaultAnimation },
          data: type === 'chart' ? {
            type: 'bar',
            labels: ['项目1', '项目2', '项目3', '项目4'],
            datasets: [{ name: '数据', data: [100, 200, 150, 300], color: theme.primary }],
          } : undefined,
        };
        return {
          presentation: {
            ...state.presentation,
            slides: state.presentation.slides.map((slide, i) =>
              i === slideIndex ? { ...slide, components: [...slide.components, newComponent] } : slide
            ),
          },
          selectedComponentId: newComponent.id,
        };
      });
      setTimeout(saveHistory, 0);
    },

    updateComponent: (componentId, updates) => {
      set((state) => ({
        presentation: {
          ...state.presentation,
          slides: state.presentation.slides.map((slide) => ({
            ...slide,
            components: slide.components.map((comp) =>
              comp.id === componentId ? { ...comp, ...updates } : comp
            ),
          })),
        },
      }));
      setTimeout(saveHistory, 0);
    },

    deleteComponent: (componentId) => {
      set((state) => ({
        presentation: {
          ...state.presentation,
          slides: state.presentation.slides.map((slide) => ({
            ...slide,
            components: slide.components.filter((comp) => comp.id !== componentId),
          })),
        },
        selectedComponentId: null,
      }));
      setTimeout(saveHistory, 0);
    },

    selectComponent: (componentId) =>
      set({ selectedComponentId: componentId }),

    moveComponent: (componentId, x, y) => {
      set((state) => ({
        presentation: {
          ...state.presentation,
          slides: state.presentation.slides.map((slide) => ({
            ...slide,
            components: slide.components.map((comp) =>
              comp.id === componentId ? { ...comp, x, y } : comp
            ),
          })),
        },
      }));
      setTimeout(saveHistory, 0);
    },

    resizeComponent: (componentId, width, height) => {
      set((state) => ({
        presentation: {
          ...state.presentation,
          slides: state.presentation.slides.map((slide) => ({
            ...slide,
            components: slide.components.map((comp) =>
              comp.id === componentId ? { ...comp, width, height } : comp
            ),
          })),
        },
      }));
      setTimeout(saveHistory, 0);
    },

    alignComponents: (alignment) => {
      set((state) => {
        const currentSlide = state.presentation.slides[state.presentation.currentSlideIndex];
        if (!currentSlide || currentSlide.components.length < 2) return state;

        const selectedComponent = currentSlide.components.find(c => c.id === state.selectedComponentId);
        if (!selectedComponent) return state;

        const alignX = () => {
          switch (alignment) {
            case 'left': return selectedComponent.x;
            case 'center': return (800 - selectedComponent.width) / 2;
            case 'right': return 800 - selectedComponent.width;
            default: return 0;
          }
        };

        const alignY = () => {
          switch (alignment) {
            case 'top': return selectedComponent.y;
            case 'middle': return (500 - selectedComponent.height) / 2;
            case 'bottom': return 500 - selectedComponent.height;
            default: return 0;
          }
        };

        const newX = ['left', 'center', 'right'].includes(alignment) ? alignX() : undefined;
        const newY = ['top', 'middle', 'bottom'].includes(alignment) ? alignY() : undefined;

        return {
          presentation: {
            ...state.presentation,
            slides: state.presentation.slides.map((slide, slideIdx) => {
              if (slideIdx !== state.presentation.currentSlideIndex) return slide;
              return {
                ...slide,
                components: slide.components.map((comp) => ({
                  ...comp,
                  x: newX !== undefined ? newX : comp.x,
                  y: newY !== undefined ? newY : comp.y,
                })),
              };
            }),
          },
        };
      });
      setTimeout(saveHistory, 0);
    },

    distributeComponents: (direction) => {
      set((state) => {
        const currentSlide = state.presentation.slides[state.presentation.currentSlideIndex];
        if (!currentSlide || currentSlide.components.length < 3) return state;

        const sortedComponents = [...currentSlide.components].sort(
          direction === 'horizontal' ? (a, b) => a.x - b.x : (a, b) => a.y - b.y
        );

        const first = sortedComponents[0];
        const last = sortedComponents[sortedComponents.length - 1];
        const totalSpan = direction === 'horizontal' 
          ? last.x + last.width - first.x 
          : last.y + last.height - first.y;
        const spacing = totalSpan / (sortedComponents.length + 1);

        const newComponents = sortedComponents.map((comp, idx) => {
          const newPos = first.x + (idx + 1) * spacing - (direction === 'horizontal' ? comp.width / 2 : 0);
          return {
            ...comp,
            [direction === 'horizontal' ? 'x' : 'y']: Math.round(newPos),
          };
        });

        const componentMap = new Map(newComponents.map(c => [c.id, c]));

        return {
          presentation: {
            ...state.presentation,
            slides: state.presentation.slides.map((slide, slideIdx) => {
              if (slideIdx !== state.presentation.currentSlideIndex) return slide;
              return {
                ...slide,
                components: slide.components.map(comp => componentMap.get(comp.id) || comp),
              };
            }),
          },
        };
      });
      setTimeout(saveHistory, 0);
    },

    centerComponent: (componentId) => {
      set((state) => ({
        presentation: {
          ...state.presentation,
          slides: state.presentation.slides.map((slide) => ({
            ...slide,
            components: slide.components.map((comp) =>
              comp.id === componentId
                ? { ...comp, x: (800 - comp.width) / 2, y: (500 - comp.height) / 2 }
                : comp
            ),
          })),
        },
      }));
      setTimeout(saveHistory, 0);
    },

    snapToGrid: (componentId) => {
      const GRID_SIZE = 20;
      const snap = (val: number) => Math.round(val / GRID_SIZE) * GRID_SIZE;
      set((state) => ({
        presentation: {
          ...state.presentation,
          slides: state.presentation.slides.map((slide) => ({
            ...slide,
            components: slide.components.map((comp) =>
              comp.id === componentId
                ? { ...comp, x: snap(comp.x), y: snap(comp.y), width: snap(comp.width), height: snap(comp.height) }
                : comp
            ),
          })),
        },
      }));
      setTimeout(saveHistory, 0);
    },

    applyLayoutTemplate: (slideIndex: number, layoutName: string) => {
      set((state) => {
        const theme = themes[state.presentation.theme];
        const templates: Record<string, Omit<Component, 'id'>[]> = {
          title: [
            {
              type: 'text',
              x: 50,
              y: 100,
              width: 700,
              height: 80,
              content: '演示文稿标题',
              style: { ...defaultStyle, fontSize: 48, fontWeight: '700', color: theme.primary, textAlign: 'center' as const },
              animation: { ...defaultAnimation, delay: 0 },
            },
            {
              type: 'text',
              x: 50,
              y: 220,
              width: 700,
              height: 40,
              content: '副标题文本',
              style: { ...defaultStyle, fontSize: 24, fontWeight: '500', color: theme.textLight, textAlign: 'center' as const },
              animation: { ...defaultAnimation, delay: 200 },
            },
            {
              type: 'text',
              x: 50,
              y: 380,
              width: 700,
              height: 30,
              content: '作者名称 · 日期',
              style: { ...defaultStyle, fontSize: 16, fontWeight: '400', color: theme.textFaint, textAlign: 'center' as const },
              animation: { ...defaultAnimation, delay: 400 },
            },
          ],
          titleContent: [
            {
              type: 'text',
              x: 50,
              y: 50,
              width: 700,
              height: 50,
              content: '章节标题',
              style: { ...defaultStyle, fontSize: 36, fontWeight: '600', color: theme.primary },
              animation: { ...defaultAnimation, delay: 0 },
            },
            {
              type: 'text',
              x: 50,
              y: 130,
              width: 700,
              height: 200,
              content: '● 要点一\n● 要点二\n● 要点三\n● 要点四',
              style: { ...defaultStyle, fontSize: 20, fontWeight: '500', color: theme.text, lineHeight: 1.8 },
              animation: { ...defaultAnimation, delay: 200 },
            },
          ],
          twoColumn: [
            {
              type: 'text',
              x: 50,
              y: 50,
              width: 700,
              height: 50,
              content: '双栏布局',
              style: { ...defaultStyle, fontSize: 36, fontWeight: '600', color: theme.primary },
              animation: { ...defaultAnimation, delay: 0 },
            },
            {
              type: 'text',
              x: 50,
              y: 130,
              width: 325,
              height: 180,
              content: '● 左侧内容\n● 要点一\n● 要点二\n● 要点三',
              style: { ...defaultStyle, fontSize: 18, fontWeight: '500', color: theme.text, lineHeight: 1.8 },
              animation: { ...defaultAnimation, delay: 150 },
            },
            {
              type: 'text',
              x: 425,
              y: 130,
              width: 325,
              height: 180,
              content: '● 右侧内容\n● 要点一\n● 要点二\n● 要点三',
              style: { ...defaultStyle, fontSize: 18, fontWeight: '500', color: theme.text, lineHeight: 1.8 },
              animation: { ...defaultAnimation, delay: 300 },
            },
          ],
          threeColumn: [
            {
              type: 'text',
              x: 50,
              y: 50,
              width: 700,
              height: 50,
              content: '三栏布局',
              style: { ...defaultStyle, fontSize: 36, fontWeight: '600', color: theme.primary },
              animation: { ...defaultAnimation, delay: 0 },
            },
            {
              type: 'text',
              x: 50,
              y: 130,
              width: 216,
              height: 150,
              content: '● 栏目一\n● 内容要点',
              style: { ...defaultStyle, fontSize: 16, fontWeight: '500', color: theme.text, lineHeight: 1.8 },
              animation: { ...defaultAnimation, delay: 150 },
            },
            {
              type: 'text',
              x: 283,
              y: 130,
              width: 234,
              height: 150,
              content: '● 栏目二\n● 内容要点',
              style: { ...defaultStyle, fontSize: 16, fontWeight: '500', color: theme.text, lineHeight: 1.8 },
              animation: { ...defaultAnimation, delay: 250 },
            },
            {
              type: 'text',
              x: 534,
              y: 130,
              width: 216,
              height: 150,
              content: '● 栏目三\n● 内容要点',
              style: { ...defaultStyle, fontSize: 16, fontWeight: '500', color: theme.text, lineHeight: 1.8 },
              animation: { ...defaultAnimation, delay: 350 },
            },
          ],
          titleTwoColumn: [
            {
              type: 'text',
              x: 50,
              y: 50,
              width: 700,
              height: 50,
              content: '标题 + 双栏',
              style: { ...defaultStyle, fontSize: 36, fontWeight: '600', color: theme.primary },
              animation: { ...defaultAnimation, delay: 0 },
            },
            {
              type: 'text',
              x: 50,
              y: 130,
              width: 325,
              height: 120,
              content: '● 左侧要点\n● 详细说明',
              style: { ...defaultStyle, fontSize: 18, fontWeight: '500', color: theme.text, lineHeight: 1.8 },
              animation: { ...defaultAnimation, delay: 150 },
            },
            {
              type: 'chart',
              x: 425,
              y: 130,
              width: 325,
              height: 320,
              content: '',
              style: defaultStyle,
              animation: { ...defaultAnimation, delay: 250 },
              data: {
                type: 'bar',
                labels: ['Q1', 'Q2', 'Q3', 'Q4'],
                datasets: [{ name: '数据', data: [100, 150, 120, 180], color: theme.primary }],
              },
            },
          ],
          titleChart: [
            {
              type: 'text',
              x: 50,
              y: 50,
              width: 700,
              height: 50,
              content: '数据图表',
              style: { ...defaultStyle, fontSize: 36, fontWeight: '600', color: theme.primary },
              animation: { ...defaultAnimation, delay: 0 },
            },
            {
              type: 'chart',
              x: 50,
              y: 120,
              width: 700,
              height: 330,
              content: '',
              style: defaultStyle,
              animation: { ...defaultAnimation, delay: 200 },
              data: {
                type: 'bar',
                labels: ['Q1', 'Q2', 'Q3', 'Q4'],
                datasets: [
                  { name: '销售额', data: [120, 190, 300, 450], color: theme.primary },
                  { name: '利润', data: [45, 78, 120, 180], color: theme.success },
                ],
              },
            },
          ],
          comparison: [
            {
              type: 'text',
              x: 50,
              y: 50,
              width: 700,
              height: 50,
              content: '对比分析',
              style: { ...defaultStyle, fontSize: 36, fontWeight: '600', color: theme.primary },
              animation: { ...defaultAnimation, delay: 0 },
            },
            {
              type: 'table',
              x: 50,
              y: 130,
              width: 700,
              height: 320,
              content: '',
              style: defaultStyle,
              animation: { ...defaultAnimation, delay: 200 },
              data: {
                columns: ['指标', '当前值', '目标值', '达成率'],
                rows: [
                  ['销售额', '¥120万', '¥150万', '80%'],
                  ['用户数', '5,000', '8,000', '62.5%'],
                  ['转化率', '3.5%', '5%', '70%'],
                  ['留存率', '65%', '75%', '86.7%'],
                ],
              },
            },
          ],
        };

        const templateComponents = templates[layoutName] || templates.title;
        const newComponents: Component[] = templateComponents.map((comp) => ({
          ...comp,
          id: generateId(),
        }));

        return {
          presentation: {
            ...state.presentation,
            slides: state.presentation.slides.map((slide, idx) =>
              idx === slideIndex
                ? { ...slide, components: newComponents }
                : slide
            ),
          },
        };
      });
      setTimeout(saveHistory, 0);
    },

    undo: () => {
      const { history, historyIndex } = get();
      if (historyIndex > 0) {
        const newIndex = historyIndex - 1;
        set({ presentation: JSON.parse(JSON.stringify(history[newIndex])), historyIndex: newIndex });
      }
    },

    redo: () => {
      const { history, historyIndex } = get();
      if (historyIndex < history.length - 1) {
        const newIndex = historyIndex + 1;
        set({ presentation: JSON.parse(JSON.stringify(history[newIndex])), historyIndex: newIndex });
      }
    },

    canUndo: () => {
      const { historyIndex } = get();
      return historyIndex > 0;
    },

    canRedo: () => {
      const { history, historyIndex } = get();
      return historyIndex < history.length - 1;
    },

    reset: () => {
      const newPresentation = createDefaultPresentation();
      set({
        presentation: newPresentation,
        selectedComponentId: null,
        isLoading: false,
        error: null,
        history: [JSON.parse(JSON.stringify(newPresentation))],
        historyIndex: 0,
      });
    },

    updateMaster: (updates: Partial<Presentation['master']>) => {
      set((state) => ({
        presentation: {
          ...state.presentation,
          master: state.presentation.master ? { ...state.presentation.master, ...updates } : updates as Presentation['master'],
        },
      }));
      setTimeout(saveHistory, 0);
    },

    applyMasterToSlides: () => {
      set((state) => {
        const master = state.presentation.master;
        if (!master) return state;

        return {
          presentation: {
            ...state.presentation,
            slides: state.presentation.slides.map((slide, index) => {
              const newComponents = slide.components.map((comp) => {
                if (comp.type === 'text') {
                  if (comp.y < 150 && comp.style.fontSize >= 36) {
                    return { ...comp, style: { ...comp.style, ...master.titleStyle } };
                  }
                  return { ...comp, style: { ...comp.style, ...master.bodyStyle } };
                }
                return comp;
              });

              return {
                ...slide,
                backgroundColor: master.backgroundColor,
                components: newComponents,
              };
            }),
          },
        };
      });
      setTimeout(saveHistory, 0);
    },

    importPresentation: (presentation) => {
      set({
        presentation,
        selectedComponentId: null,
        error: null,
        history: [JSON.parse(JSON.stringify(presentation))],
        historyIndex: 0,
      });
    },

    setLoading: (loading) =>
      set({ isLoading: loading }),

    setError: (error) =>
      set({ error }),

    compileFromPRD: async (prdContent: string, theme: ThemeType = 'business') => {
      const abortController = new AbortController();
      set({ 
        isLoading: true, 
        error: null, 
        isCompiling: true,
        abortController,
        pipelineStages: createInitialPipelineStages().map(stage => ({ ...stage, startTime: undefined, endTime: undefined })),
        pipelineContext: { prdContent },
      });

      const updateStage = (stageId: string, updates: Partial<PipelineStage>) => {
        set((state) => ({
          pipelineStages: state.pipelineStages.map(stage => 
            stage.id === stageId ? { ...stage, ...updates } : stage
          ),
        }));
      };

      const runSkillStage = async <T>(stageId: string, stageName: string, skillId: string, context: Record<string, any>, params?: Record<string, string>): Promise<T> => {
        const { abortController } = get();
        if (abortController?.signal.aborted) {
          throw new Error('编译已取消');
        }

        updateStage(stageId, { status: 'running', startTime: Date.now(), progress: 10 });
        
        let accumulatedOutput = '';
        let progress = 10;

        try {
          const onProgress = (content: string, isDone: boolean) => {
            accumulatedOutput += content;
            progress = Math.min(progress + 5, 90);
            updateStage(stageId, { progress, output: accumulatedOutput.slice(-2000) });
          };

          const response = await apiFetch(`${API_BASE}/api/skill/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              skill_id: skillId,
              params: { ...params, ...context },
              streaming: true,
              use_cache: true,
            }),
            signal: abortController.signal,
          });

          if (!response.ok) {
            const errorData = await response.json().catch(() => ({ error: '技能执行失败' }));
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
          }

          const result = await response.json();
          
          if (result.status === 'streaming' && result.execution_id) {
            const decoder = new TextDecoder();
            const streamResponse = await apiFetch(`${API_BASE}/api/skill/stream/${result.execution_id}`, {
              signal: abortController.signal,
            });

            if (!streamResponse.ok) {
              throw new Error(`Stream request failed! status: ${streamResponse.status}`);
            }

            const reader = streamResponse.body?.getReader();
            if (!reader) {
              throw new Error('No readable stream');
            }

            while (true) {
              if (abortController.signal.aborted) {
                throw new Error('编译已取消');
              }

              const { done, value } = await reader.read();
              if (done) break;

              const chunks = decoder.decode(value).split('\n\n');
              for (const chunk of chunks) {
                if (chunk.startsWith('data:')) {
                  try {
                    const data = JSON.parse(chunk.replace(/^data:\s*/, ''));
                    if (data.content) {
                      onProgress(data.content, false);
                    }
                    if (data.status === 'completed') {
                      onProgress('', true);
                      break;
                    }
                  } catch {
                    // ignore parse errors
                  }
                }
              }
            }
          }

          updateStage(stageId, { status: 'completed', progress: 100, endTime: Date.now() });
          return result as T;
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : '阶段执行失败';
          updateStage(stageId, { status: 'failed', progress: 0, error: errorMessage, endTime: Date.now() });
          throw error;
        }
      };

      const updateContext = (updates: Partial<PipelineContext>) => {
        set((state) => ({
          pipelineContext: state.pipelineContext ? { ...state.pipelineContext, ...updates } : updates as PipelineContext,
        }));
      };

      try {
        const analysisResult = await runSkillStage<any>('analyze', 'PRD分析', 'prd-analysis', { prdContent });
        
        if (analysisResult.result) {
          const resultContent = analysisResult.result;
          const lines = resultContent.split('\n');
          const prdStructure: any = {
            business_domain: '',
            objectives: [],
            workflow: [],
            risks: [],
            features: [],
          };

          let currentSection = '';
          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('# ')) {
              prdStructure.business_domain = trimmed.replace('# ', '').trim();
            } else if (trimmed.startsWith('## ') || trimmed.startsWith('### ')) {
              currentSection = trimmed.replace(/^#+\s*/, '').trim();
            } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ') || trimmed.startsWith('1.')) {
              const item = trimmed.replace(/^[-*] |^\d+\./, '').trim();
              switch (currentSection) {
                case '业务目标': case '目标': case 'Objectives': case '产品目标':
                  prdStructure.objectives.push({ objective: item, target: '待定义' });
                  break;
                case '流程设计': case '工作流程': case 'Workflow': case '业务流程':
                  prdStructure.workflow.push({ step: prdStructure.workflow.length + 1, name: item, action: item });
                  break;
                case '风险分析': case '风险': case 'Risks':
                  prdStructure.risks.push({ risk: item, severity: 'medium', mitigation: '待定义' });
                  break;
                case '核心功能': case '功能需求': case 'Features':
                  prdStructure.features.push(item);
                  break;
              }
            }
          }

          if (!prdStructure.business_domain) prdStructure.business_domain = '业务系统分析';
          if (prdStructure.objectives.length === 0) prdStructure.objectives = [{ objective: '提升业务效率', target: '待定义' }];
          
          updateContext({ 
            prdStructure,
            analysisResult: {
              businessName: prdStructure.business_domain || '未命名业务系统',
              description: '',
              keyFeatures: prdStructure.objectives?.map((o: any) => o.objective) || [],
            },
          });
        }

        const currentContext = get().pipelineContext;
        const objectivesResult = await runSkillStage<any>('extract', '目标提取', 'objective-extraction', { 
          prd_structure: currentContext?.prdStructure,
        });

        if (objectivesResult.result) {
          const objectives = currentContext?.prdStructure.objectives?.map((obj: any, idx: number) => ({
            id: `obj-${idx + 1}`,
            objective: obj.objective || obj,
            target: obj.target || '待定义',
            priority: ['high', 'high', 'medium', 'medium', 'low'][idx] || 'low',
            kpi: '达成率',
            status: 'pending',
          })) || [];
          updateContext({ objectives });
        }

        await runSkillStage<any>('design', '流程设计', 'objective-extraction', { 
          prd_structure: get().pipelineContext?.prdStructure,
        });

        const workflow = get().pipelineContext?.prdStructure.workflow?.map((step: any, idx: number) => ({
          step: idx + 1,
          name: step.name || step,
          action: step.action || step.name || step,
          owner: '待定',
          sla: '无',
        })) || [];
        updateContext({ workflow });

        const risksResult = await runSkillStage<any>('evaluate', '风险评估', 'risk-assessment', { 
          risks: get().pipelineContext?.prdStructure.risks || [],
        });

        if (risksResult.result) {
          const risks = get().pipelineContext?.prdStructure.risks?.map((risk: any, idx: number) => ({
            id: `risk-${idx + 1}`,
            risk: risk.risk || risk,
            category: risk.category || '运营风险',
            severity: risk.severity || 'medium',
            mitigation: risk.mitigation || '制定应对计划',
          })) || [];
          updateContext({ risks });
        }

        const finalContext = get().pipelineContext;
        const presentationOutput = await runSkillStage<any>('generate', '文稿生成', 'presentation-generation', { 
          prd_structure: finalContext?.prdStructure,
          objectives_detail: finalContext?.objectives,
        }, { theme });

        const businessSystem: BusinessSystem = {
          name: finalContext?.prdStructure?.business_domain || '业务系统分析',
          description: '',
          business_domain: finalContext?.prdStructure?.business_domain || '业务系统分析',
          objectives: finalContext?.objectives?.map((o: any) => ({
            objective: o.objective,
            target: o.target,
            priority: o.priority,
            kpi: o.kpi,
          })) || [],
          roles: [],
          workflow: finalContext?.workflow?.map((w: any) => ({
            step: w.step,
            name: w.name,
            action: w.action,
            owner: w.owner,
            sla: w.sla,
          })) || [],
          metrics: [],
          risks: finalContext?.risks?.map((r: any) => ({
            risk: r.risk,
            severity: r.severity,
            mitigation: r.mitigation,
            category: r.category,
          })) || [],
          strategy: {},
          optimization: {},
        };

        updateContext({ businessSystem });

        const presentation = convertBusinessSystemToPresentation(businessSystem, theme);
        
        set({
          presentation: {
            ...presentation,
            master: {
              id: generateId(),
              titleStyle: {
                ...defaultStyle,
                fontSize: 48,
                fontWeight: '700',
                color: themes[theme].primary,
                fontFamily: themes[theme].fontFamily,
                textAlign: 'center' as const,
              },
              bodyStyle: {
                ...defaultStyle,
                fontSize: 20,
                fontWeight: '400',
                color: themes[theme].text,
                fontFamily: themes[theme].fontFamily,
                textAlign: 'left' as const,
                lineHeight: 1.8,
              },
              footerStyle: {
                ...defaultStyle,
                fontSize: 12,
                fontWeight: '400',
                color: themes[theme].textFaint,
                fontFamily: themes[theme].fontFamily,
                textAlign: 'center' as const,
              },
              backgroundColor: themes[theme].background,
              showFooter: true,
              footerText: '',
              showPageNumber: true,
              showDate: true,
            },
          },
          selectedComponentId: null,
          history: [JSON.parse(JSON.stringify(presentation))],
          historyIndex: 0,
        });

        updateStage('generate', { output: `📊 已生成 ${presentation.slides.length} 页演示文稿` });

        set({ isLoading: false, isCompiling: false, abortController: null });
        return { context: get().pipelineContext, presentation };
      } catch (error) {
        const errorMessage = error instanceof Error && error.message !== '编译已取消' 
          ? error.message 
          : error instanceof Error && error.message === '编译已取消' 
            ? '编译已取消'
            : '编译失败';
        set({ 
          error: errorMessage, 
          isLoading: false, 
          isCompiling: false, 
          abortController: null 
        });
        throw error;
      }
    },

    cancelCompile: () => {
      const { abortController } = get();
      abortController?.abort();
      set({ 
        isCompiling: false, 
        isLoading: false, 
        abortController: null,
        error: '编译已取消',
        pipelineStages: get().pipelineStages.map(stage => 
          stage.status === 'running' 
            ? { ...stage, status: 'failed' as PipelineStageStatus, error: '已取消', endTime: Date.now() }
            : stage
        ),
      });
    },

    resetPipeline: () => {
      set({ 
        pipelineStages: createInitialPipelineStages(),
        error: null,
        isCompiling: false,
        abortController: null,
      });
    },

    retryStage: async (stageId: string) => {
      const { abortController, pipelineStages, pipelineContext } = get();
      if (abortController?.signal.aborted) {
        return;
      }

      const stage = pipelineStages.find(s => s.id === stageId);
      if (!stage || stage.status !== 'failed') {
        return;
      }

      const updateStage = (stageId: string, updates: Partial<PipelineStage>) => {
        set((state) => ({
          pipelineStages: state.pipelineStages.map(st => 
            st.id === stageId ? { ...st, ...updates } : st
          ),
        }));
      };

      updateStage(stageId, { status: 'running', progress: 10, error: undefined, startTime: Date.now() });

      const skillMap: Record<string, { skillId: string; contextKey: string }> = {
        'analyze': { skillId: 'prd-analysis', contextKey: 'prdContent' },
        'extract': { skillId: 'objective-extraction', contextKey: 'prd_structure' },
        'design': { skillId: 'objective-extraction', contextKey: 'prd_structure' },
        'evaluate': { skillId: 'risk-assessment', contextKey: 'risks' },
        'generate': { skillId: 'presentation-generation', contextKey: 'prd_structure' },
      };

      const skillInfo = skillMap[stageId];
      if (!skillInfo) {
        updateStage(stageId, { status: 'failed', progress: 0, error: '未知阶段', endTime: Date.now() });
        return;
      }

      try {
        const contextData: Record<string, any> = {};
        
        if (skillInfo.contextKey === 'prdContent') {
          contextData.prdContent = pipelineContext?.prdContent;
        } else if (skillInfo.contextKey === 'prd_structure') {
          contextData.prd_structure = pipelineContext?.prdStructure;
        } else if (skillInfo.contextKey === 'risks') {
          contextData.risks = pipelineContext?.prdStructure?.risks || [];
        }

        const response = await apiFetch(`${API_BASE}/api/skill/execute`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            skill_id: skillInfo.skillId,
            params: contextData,
            streaming: true,
            use_cache: true,
          }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ error: '技能执行失败' }));
          throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        if (result.status === 'streaming' && result.execution_id) {
          const decoder = new TextDecoder();
          const streamResponse = await apiFetch(`${API_BASE}/api/skill/stream/${result.execution_id}`);

          if (!streamResponse.ok) {
            throw new Error(`Stream request failed! status: ${streamResponse.status}`);
          }

          const reader = streamResponse.body?.getReader();
          if (!reader) {
            throw new Error('No readable stream');
          }

          let accumulatedOutput = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunks = decoder.decode(value).split('\n\n');
            for (const chunk of chunks) {
              if (chunk.startsWith('data:')) {
                try {
                  const data = JSON.parse(chunk.replace(/^data:\s*/, ''));
                  if (data.content) {
                    accumulatedOutput += data.content;
                  }
                  if (data.status === 'completed') {
                    break;
                  }
                } catch {
                  // ignore parse errors
                }
              }
            }
          }

          if (accumulatedOutput) {
            updateStage(stageId, { output: accumulatedOutput.slice(-2000) });
          }
        }

        updateStage(stageId, { status: 'completed', progress: 100, endTime: Date.now() });
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : '阶段重试失败';
        updateStage(stageId, { status: 'failed', progress: 0, error: errorMessage, endTime: Date.now() });
      }
    },

    compileFromBusinessSystem: (businessSystem: BusinessSystem, theme: ThemeType = 'business') => {
      const presentation = convertBusinessSystemToPresentation(businessSystem, theme);
      set({
        presentation: {
          ...presentation,
          master: {
            id: generateId(),
            titleStyle: {
              ...defaultStyle,
              fontSize: 48,
              fontWeight: '700',
              color: themes[theme].primary,
              fontFamily: themes[theme].fontFamily,
              textAlign: 'center' as const,
            },
            bodyStyle: {
              ...defaultStyle,
              fontSize: 20,
              fontWeight: '400',
              color: themes[theme].text,
              fontFamily: themes[theme].fontFamily,
              textAlign: 'left' as const,
              lineHeight: 1.8,
            },
            footerStyle: {
              ...defaultStyle,
              fontSize: 12,
              fontWeight: '400',
              color: themes[theme].textFaint,
              fontFamily: themes[theme].fontFamily,
              textAlign: 'center' as const,
            },
            backgroundColor: themes[theme].background,
            showFooter: true,
            footerText: '',
            showPageNumber: true,
            showDate: true,
          },
        },
        selectedComponentId: null,
        history: [JSON.parse(JSON.stringify(presentation))],
        historyIndex: 0,
        isLoading: false,
        error: null,
      });
    },
  };
});

export default usePresentationStore;
