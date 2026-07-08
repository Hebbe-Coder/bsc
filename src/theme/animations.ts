import { AnimationPreset, AnimationType, EasingType } from '../types';

export const animationPresets: AnimationPreset[] = [
  { name: '淡入', type: 'fadeIn', duration: 500, delay: 0 },
  { name: '从左滑入', type: 'slideInLeft', duration: 600, delay: 100 },
  { name: '从右滑入', type: 'slideInRight', duration: 600, delay: 100 },
  { name: '从上方滑入', type: 'slideInTop', duration: 600, delay: 100 },
  { name: '从下方滑入', type: 'slideInBottom', duration: 600, delay: 100 },
  { name: '缩放进入', type: 'zoomIn', duration: 500, delay: 150 },
  { name: '旋转进入', type: 'rotateIn', duration: 700, delay: 200 },
];

export const getAnimationPreset = (type: AnimationType): AnimationPreset => {
  return animationPresets.find(p => p.type === type) || animationPresets[0];
};

export const getAnimationStyle = (type: AnimationType, delay: number, duration: number, easing: EasingType) => {
  const easingMap: Record<EasingType, string> = {
    ease: 'ease',
    easeIn: 'ease-in',
    easeOut: 'ease-out',
    easeInOut: 'ease-in-out',
  };
  
  const baseStyle = {
    animationDuration: `${duration}ms`,
    animationDelay: `${delay}ms`,
    animationTimingFunction: easingMap[easing],
    animationFillMode: 'forwards' as const,
  };

  switch (type) {
    case 'fadeIn':
      return {
        ...baseStyle,
        animationName: 'fadeIn',
        opacity: 0,
      };
    case 'slideInLeft':
      return {
        ...baseStyle,
        animationName: 'slideInLeft',
        opacity: 0,
        transform: 'translateX(-100px)',
      };
    case 'slideInRight':
      return {
        ...baseStyle,
        animationName: 'slideInRight',
        opacity: 0,
        transform: 'translateX(100px)',
      };
    case 'slideInTop':
      return {
        ...baseStyle,
        animationName: 'slideInTop',
        opacity: 0,
        transform: 'translateY(-100px)',
      };
    case 'slideInBottom':
      return {
        ...baseStyle,
        animationName: 'slideInBottom',
        opacity: 0,
        transform: 'translateY(100px)',
      };
    case 'zoomIn':
      return {
        ...baseStyle,
        animationName: 'zoomIn',
        opacity: 0,
        transform: 'scale(0.5)',
      };
    case 'rotateIn':
      return {
        ...baseStyle,
        animationName: 'rotateIn',
        opacity: 0,
        transform: 'rotate(-180deg)',
      };
    default:
      return baseStyle;
  }
};

export const getTransitionStyle = (type: 'fade' | 'slide' | 'cube' | 'zoom') => {
  switch (type) {
    case 'fade':
      return {
        enter: { opacity: 0 },
        enterActive: { opacity: 1, transition: { duration: 500 } },
        exit: { opacity: 1 },
        exitActive: { opacity: 0, transition: { duration: 500 } },
      };
    case 'slide':
      return {
        enter: { opacity: 0, x: 100 },
        enterActive: { opacity: 1, x: 0, transition: { duration: 500 } },
        exit: { opacity: 1, x: 0 },
        exitActive: { opacity: 0, x: -100, transition: { duration: 500 } },
      };
    case 'cube':
      return {
        enter: { opacity: 0, rotateY: -90 },
        enterActive: { opacity: 1, rotateY: 0, transition: { duration: 600 } },
        exit: { opacity: 1, rotateY: 0 },
        exitActive: { opacity: 0, rotateY: 90, transition: { duration: 600 } },
      };
    case 'zoom':
      return {
        enter: { opacity: 0, scale: 0.8 },
        enterActive: { opacity: 1, scale: 1, transition: { duration: 400 } },
        exit: { opacity: 1, scale: 1 },
        exitActive: { opacity: 0, scale: 1.2, transition: { duration: 400 } },
      };
    default:
      return {
        enter: { opacity: 0 },
        enterActive: { opacity: 1, transition: { duration: 500 } },
        exit: { opacity: 1 },
        exitActive: { opacity: 0, transition: { duration: 500 } },
      };
  }
};
