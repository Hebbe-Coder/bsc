export type ComponentType = 'text' | 'image' | 'chart' | 'shape' | 'table' | 'media';
export type ThemeType = 'business' | 'tech' | 'education' | 'creative' | 'dark';
export type TransitionType = 'fade' | 'slide-left' | 'slide-right' | 'slide-up' | 'slide-down' | 'zoom-in' | 'zoom-out' | 'cube' | 'flip' | 'rotate';
export type AnimationType = 'fadeIn' | 'fadeInUp' | 'fadeInDown' | 'fadeInLeft' | 'fadeInRight' | 
  'slideInLeft' | 'slideInRight' | 'slideInTop' | 'slideInBottom' | 
  'zoomIn' | 'zoomInUp' | 'zoomInDown' | 
  'rotateIn' | 'rotateInLeft' | 'rotateInRight' | 
  'bounceIn' | 'bounceInDown' | 'bounceInUp' | 
  'flipInX' | 'flipInY' | 
  'slideInUp' | 'slideInDown';
export type EasingType = 'ease' | 'easeIn' | 'easeOut' | 'easeInOut';
export type ChartType = 'bar' | 'pie' | 'line' | 'radar' | 'gauge' | 'funnel' | 'gantt' | 'scatter' | 'area' | 'bar-horizontal' | 'polar';

export interface AnimationConfig {
  type: AnimationType;
  delay: number;
  duration: number;
  easing: EasingType;
}

export interface StyleConfig {
  fontFamily: string;
  fontSize: number;
  fontWeight: string;
  color: string;
  backgroundColor: string;
  borderRadius: number;
  borderWidth: number;
  borderColor: string;
  shadow: string;
  textAlign?: 'left' | 'center' | 'right' | 'justify';
  lineHeight?: number;
}

export interface Component {
  id: string;
  type: ComponentType;
  x: number;
  y: number;
  width: number;
  height: number;
  content: string;
  style: StyleConfig;
  animation: AnimationConfig;
  data?: any;
}

export interface Slide {
  id: string;
  index: number;
  backgroundColor: string;
  components: Component[];
  transition: TransitionType;
  notes?: string;
}

export interface SlideMaster {
  id: string;
  titleStyle: StyleConfig;
  bodyStyle: StyleConfig;
  footerStyle: StyleConfig;
  backgroundColor: string;
  backgroundImage?: string;
  showFooter: boolean;
  footerText: string;
  showPageNumber: boolean;
  showDate: boolean;
}

export interface Presentation {
  id: string;
  title: string;
  theme: ThemeType;
  slides: Slide[];
  currentSlideIndex: number;
  master?: SlideMaster;
}

export interface ThemeConfig {
  name: string;
  primary: string;
  secondary: string;
  background: string;
  text: string;
  textLight: string;
  textFaint: string;
  accent: string;
  success: string;
  warning: string;
  danger: string;
  border: string;
  card: string;
  fontFamily: string;
}

export interface AnimationPreset {
  name: string;
  type: AnimationType;
  duration: number;
  delay: number;
}
