import { Presentation, ThemeType } from '../types';
import { themes } from '../theme/themes';

const generateId = () => Math.random().toString(36).substring(2, 11);

export interface Template {
  id: string;
  name: string;
  description: string;
  thumbnail: string;
  theme: ThemeType;
  layout: 'classic' | 'modern' | 'minimal' | 'creative';
  colors: {
    primary: string;
    secondary: string;
    accent: string;
  };
}

export const templates: Template[] = [
  {
    id: 'template-business-classic',
    name: '商务经典',
    description: '适合企业汇报、商务演示的经典风格',
    thumbnail: 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=professional%20business%20presentation%20slide%20template%20blue%20corporate%20style&image_size=square',
    theme: 'business',
    layout: 'classic',
    colors: { primary: '#1e3a5f', secondary: '#0ea5e9', accent: '#3b82f6' },
  },
  {
    id: 'template-tech-dark',
    name: '科技暗黑',
    description: '适合科技产品发布、技术分享的深色主题',
    thumbnail: 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=dark%20technology%20presentation%20slide%20template%20purple%20neon%20futuristic&image_size=square',
    theme: 'tech',
    layout: 'modern',
    colors: { primary: '#0f172a', secondary: '#8b5cf6', accent: '#06b6d4' },
  },
  {
    id: 'template-education-orange',
    name: '教育活力',
    description: '适合教育培训、课程介绍的活力风格',
    thumbnail: 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=colorful%20education%20presentation%20slide%20template%20orange%20creative%20youthful&image_size=square',
    theme: 'education',
    layout: 'creative',
    colors: { primary: '#7c3aed', secondary: '#f97316', accent: '#ec4899' },
  },
  {
    id: 'template-creative-pink',
    name: '创意设计',
    description: '适合创意设计、品牌展示的艺术风格',
    thumbnail: 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=creative%20design%20presentation%20slide%20template%20pink%20artistic%20modern&image_size=square',
    theme: 'creative',
    layout: 'creative',
    colors: { primary: '#ec4899', secondary: '#06b6d4', accent: '#8b5cf6' },
  },
  {
    id: 'template-minimal-dark',
    name: '极简暗黑',
    description: '适合高端品牌、极简主义展示',
    thumbnail: 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=minimalist%20dark%20presentation%20slide%20template%20elegant%20sophisticated&image_size=square',
    theme: 'dark',
    layout: 'minimal',
    colors: { primary: '#111827', secondary: '#374151', accent: '#0ea5e9' },
  },
];

export const createPresentationFromTemplate = (template: Template, title: string = '业务分析报告'): Presentation => {
  const themeConfig = themes[template.theme];
  
  return {
    id: generateId(),
    title,
    theme: template.theme,
    currentSlideIndex: 0,
    slides: [
      {
        id: generateId(),
        index: 0,
        backgroundColor: themeConfig.background,
        components: [],
        transition: 'fade',
      },
      {
        id: generateId(),
        index: 1,
        backgroundColor: themeConfig.background,
        components: [],
        transition: 'slide-left',
      },
      {
        id: generateId(),
        index: 2,
        backgroundColor: themeConfig.background,
        components: [],
        transition: 'fade',
      },
      {
        id: generateId(),
        index: 3,
        backgroundColor: themeConfig.background,
        components: [],
        transition: 'zoom-in',
      },
      {
        id: generateId(),
        index: 4,
        backgroundColor: themeConfig.background,
        components: [],
        transition: 'fade',
      },
    ],
  };
};

export const getTemplateById = (id: string): Template | undefined => {
  return templates.find(t => t.id === id);
};

export const getTemplatesByTheme = (theme: ThemeType): Template[] => {
  return templates.filter(t => t.theme === theme);
};

export const getTemplatesByLayout = (layout: Template['layout']): Template[] => {
  return templates.filter(t => t.layout === layout);
};