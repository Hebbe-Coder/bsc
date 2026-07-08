import { Presentation, Slide, Component } from '../types';
import { themes } from '../theme/themes';
import pptxgen from 'pptxgenjs';

declare const html2canvas: any;

interface JSPDFOptions {
  orientation?: 'portrait' | 'landscape';
  unit?: string;
  format?: number[] | string;
}

interface JSPDFInstance {
  addImage(dataUrl: string, format: string, x: number, y: number, width: number, height: number): void;
  addPage(): void;
  save(filename: string): void;
}

type JSPDFConstructor = new(options?: JSPDFOptions) => JSPDFInstance;

interface JSPDFModule {
  jsPDF: JSPDFConstructor;
}

declare global {
  interface Window {
    jspdf?: JSPDFModule;
  }
}

export const exportToMarkdown = (presentation: Presentation): string => {
  let md = `# ${presentation.title || '演示文稿'}\n\n`;
  md += `> 共 ${presentation.slides.length} 页幻灯片\n\n`;
  
  presentation.slides.forEach((slide, index) => {
    md += `---\n\n`;
    md += `## 幻灯片 ${index + 1}\n\n`;
    
    if (slide.notes) {
      md += `> **演讲者备注**: ${slide.notes}\n\n`;
    }
    
    slide.components.forEach(comp => {
      if (comp.type === 'text') {
        const fontSize = comp.style.fontSize;
        let headingLevel = 3;
        if (fontSize >= 40) headingLevel = 1;
        else if (fontSize >= 28) headingLevel = 2;
        
        const heading = '#'.repeat(headingLevel);
        md += `${heading} ${comp.content}\n\n`;
      } else if (comp.type === 'table' && comp.data) {
        const columns = comp.data.columns || [];
        const rows = comp.data.rows || [];
        if (columns.length > 0) {
          md += `| ${columns.join(' | ')} |\n`;
          md += `| ${columns.map(() => '---').join(' | ')} |\n`;
          rows.forEach(row => {
            md += `| ${row.join(' | ')} |\n`;
          });
          md += '\n';
        }
      } else if (comp.type === 'chart' && comp.data) {
        md += `**图表**: ${comp.data.type || '图表'}\n\n`;
        if (comp.data.labels && comp.data.datasets) {
          md += `\`\`\`json\n${JSON.stringify(comp.data, null, 2)}\n\`\`\`\n\n`;
        }
      }
    });
  });
  
  return md;
};

export const downloadMarkdown = (presentation: Presentation): void => {
  const mdContent = exportToMarkdown(presentation);
  const blob = new Blob([mdContent], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${presentation.title || 'presentation'}.md`;
  a.click();
  URL.revokeObjectURL(url);
};

export const exportToJSON = (presentation: Presentation): string => {
  return JSON.stringify(presentation, null, 2);
};

export const downloadJSON = (presentation: Presentation): void => {
  const json = exportToJSON(presentation);
  const blob = new Blob([json], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${presentation.title || 'presentation'}.json`;
  a.click();
  URL.revokeObjectURL(url);
};

export const generateSlideImage = (slide: Slide, theme: any): Promise<HTMLCanvasElement> => {
  return new Promise((resolve) => {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      resolve(canvas);
      return;
    }
    
    canvas.width = 800;
    canvas.height = 500;
    
    ctx.fillStyle = slide.backgroundColor;
    ctx.fillRect(0, 0, 800, 500);
    
    slide.components.forEach((comp) => {
      ctx.save();
      
      if (comp.type === 'text') {
        ctx.font = `${comp.style.fontWeight} ${comp.style.fontSize}px ${comp.style.fontFamily || theme.fontFamily}`;
        ctx.fillStyle = comp.style.color;
        ctx.textAlign = (comp.style.textAlign === 'justify' ? 'left' : comp.style.textAlign) || 'left';
        ctx.textBaseline = 'top';
        
        const lines = comp.content.split('\n');
        let y = 0;
        const lineHeight = comp.style.lineHeight || 1.5;
        
        lines.forEach(line => {
          ctx.fillText(line, 0, y);
          y += comp.style.fontSize * lineHeight;
        });
      } else if (comp.type === 'shape') {
        ctx.fillStyle = comp.style.backgroundColor;
        ctx.strokeStyle = comp.style.borderColor;
        ctx.lineWidth = comp.style.borderWidth;
        
        if (comp.style.borderRadius > 0) {
          const radius = comp.style.borderRadius;
          ctx.beginPath();
          ctx.roundRect(comp.x, comp.y, comp.width, comp.height, radius);
          ctx.fill();
          if (comp.style.borderWidth > 0) {
            ctx.stroke();
          }
        } else {
          ctx.fillRect(comp.x, comp.y, comp.width, comp.height);
          if (comp.style.borderWidth > 0) {
            ctx.strokeRect(comp.x, comp.y, comp.width, comp.height);
          }
        }
      } else if (comp.type === 'table' && comp.data) {
        const columns = comp.data.columns || [];
        const rows = comp.data.rows || [];
        const cellWidth = comp.width / columns.length;
        const headerHeight = 40;
        const rowHeight = (comp.height - headerHeight) / rows.length;
        
        const gradient = ctx.createLinearGradient(comp.x, comp.y, comp.x, comp.y + headerHeight);
        gradient.addColorStop(0, theme.primary);
        gradient.addColorStop(1, theme.accent);
        
        ctx.fillStyle = gradient;
        ctx.fillRect(comp.x, comp.y, comp.width, headerHeight);
        
        ctx.fillStyle = '#fff';
        ctx.font = '600 12px Inter, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        
        columns.forEach((col, idx) => {
          ctx.fillText(col, comp.x + idx * cellWidth + 8, comp.y + headerHeight / 2);
        });
        
        rows.forEach((row, rowIdx) => {
          const y = comp.y + headerHeight + rowIdx * rowHeight;
          ctx.fillStyle = rowIdx % 2 === 0 ? '#ffffff' : '#f9fafb';
          ctx.fillRect(comp.x, y, comp.width, rowHeight);
          
          ctx.fillStyle = '#374151';
          ctx.font = '12px Inter, sans-serif';
          
          row.forEach((cell, colIdx) => {
            ctx.fillText(String(cell), comp.x + colIdx * cellWidth + 8, y + rowHeight / 2);
          });
        });
        
        ctx.strokeStyle = '#e5e7eb';
        ctx.lineWidth = 1;
        ctx.strokeRect(comp.x, comp.y, comp.width, comp.height);
      }
      
      ctx.restore();
    });
    
    resolve(canvas);
  });
};

export const downloadSlideAsPNG = async (slide: Slide, presentation: Presentation, slideIndex: number): Promise<void> => {
  const theme = themes[presentation.theme];
  const canvas = await generateSlideImage(slide, theme);
  
  canvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${presentation.title || 'slide'}_slide_${slideIndex + 1}.png`;
    a.click();
    URL.revokeObjectURL(url);
  }, 'image/png');
};

export const downloadAllSlidesAsPNG = async (presentation: Presentation): Promise<void> => {
  const theme = themes[presentation.theme];
  
  for (let i = 0; i < presentation.slides.length; i++) {
    const slide = presentation.slides[i];
    const canvas = await generateSlideImage(slide, theme);
    
    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${presentation.title || 'slide'}_slide_${i + 1}.png`;
      a.click();
      URL.revokeObjectURL(url);
    }, 'image/png');
    
    await new Promise(resolve => setTimeout(resolve, 500));
  }
};

export const downloadCurrentSlideAsPNG = async (presentation: Presentation): Promise<void> => {
  const currentSlide = presentation.slides[presentation.currentSlideIndex];
  if (currentSlide) {
    await downloadSlideAsPNG(currentSlide, presentation, presentation.currentSlideIndex);
  }
};

export const importFromJSON = (jsonString: string): Presentation | null => {
  try {
    const data = JSON.parse(jsonString);
    
    if (!data.id || !data.slides || !Array.isArray(data.slides)) {
      return null;
    }
    
    return data as Presentation;
  } catch {
    return null;
  }
};

export const triggerImport = (onSuccess: (presentation: Presentation) => void, onError: () => void): void => {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  input.style.display = 'none';
  
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;
    
    try {
      const text = await file.text();
      const presentation = importFromJSON(text);
      if (presentation) {
        onSuccess(presentation);
      } else {
        onError();
      }
    } catch {
      onError();
    }
  };
  
  document.body.appendChild(input);
  input.click();
  document.body.removeChild(input);
};

interface ExportOptions {
  resolution?: 'low' | 'medium' | 'high';
  includeAnimations?: boolean;
  includeFooter?: boolean;
  pageRange?: { start: number; end: number } | 'all';
  format?: 'pdf' | 'png' | 'html';
  includeCoverPage?: boolean;
  watermark?: string;
  watermarkOpacity?: number;
}

const drawWatermark = (ctx: CanvasRenderingContext2D, text: string, opacity: number = 0.15): void => {
  ctx.save();
  ctx.globalAlpha = opacity;
  ctx.font = 'bold 60px Inter, sans-serif';
  ctx.fillStyle = '#9ca3af';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  
  const canvas = ctx.canvas;
  const width = canvas.width;
  const height = canvas.height;
  
  ctx.translate(width / 2, height / 2);
  ctx.rotate(-Math.PI / 6);
  
  const textWidth = ctx.measureText(text).width;
  const gap = 150;
  const cols = Math.ceil((width + textWidth) / (textWidth + gap));
  const rows = Math.ceil((height + 100) / 100);
  
  for (let row = -rows; row <= rows; row++) {
    for (let col = -cols; col <= cols; col++) {
      ctx.fillText(text, col * (textWidth + gap), row * 100);
    }
  }
  
  ctx.restore();
};

const drawCoverPage = (ctx: CanvasRenderingContext2D, presentation: Presentation, theme: any): void => {
  ctx.fillStyle = theme.background;
  ctx.fillRect(0, 0, 800, 500);
  
  const gradient = ctx.createLinearGradient(0, 0, 800, 500);
  gradient.addColorStop(0, theme.primary);
  gradient.addColorStop(1, theme.accent);
  
  ctx.fillStyle = gradient;
  ctx.beginPath();
  ctx.moveTo(600, 0);
  ctx.lineTo(800, 0);
  ctx.lineTo(800, 200);
  ctx.closePath();
  ctx.fill();
  
  ctx.beginPath();
  ctx.moveTo(0, 400);
  ctx.lineTo(200, 500);
  ctx.lineTo(0, 500);
  ctx.closePath();
  ctx.fill();
  
  ctx.fillStyle = '#ffffff';
  ctx.font = 'bold 48px Inter, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  
  const title = presentation.title || '演示文稿';
  const maxWidth = 600;
  const words = title.split(' ');
  let lines: string[] = [];
  let currentLine = '';
  
  words.forEach(word => {
    const testLine = currentLine + (currentLine ? ' ' : '') + word;
    if (ctx.measureText(testLine).width <= maxWidth) {
      currentLine = testLine;
    } else {
      lines.push(currentLine);
      currentLine = word;
    }
  });
  if (currentLine) lines.push(currentLine);
  
  const totalHeight = lines.length * 60;
  const startY = 250 - totalHeight / 2;
  
  lines.forEach((line, idx) => {
    ctx.fillText(line, 400, startY + idx * 60);
  });
  
  ctx.fillStyle = 'rgba(255,255,255,0.8)';
  ctx.font = '16px Inter, sans-serif';
  ctx.fillText(`${presentation.slides.length} 页幻灯片`, 400, startY + totalHeight + 40);
  
  ctx.fillStyle = 'rgba(255,255,255,0.6)';
  ctx.font = '14px Inter, sans-serif';
  ctx.fillText(new Date().toLocaleDateString('zh-CN'), 400, startY + totalHeight + 70);
  
  ctx.fillStyle = 'rgba(255,255,255,0.4)';
  ctx.font = '12px Inter, sans-serif';
  ctx.fillText('Generated by BSC Designer', 400, 470);
};

export const downloadPDF = async (presentation: Presentation, options?: ExportOptions): Promise<void> => {
  const resolution = options?.resolution || 'high';
  const scale = resolution === 'high' ? 2 : resolution === 'medium' ? 1.5 : 1;
  const pageRange = options?.pageRange || 'all';
  const includeCoverPage = options?.includeCoverPage || false;
  const watermark = options?.watermark;
  const watermarkOpacity = options?.watermarkOpacity || 0.15;
  
  const startIdx = typeof pageRange === 'object' ? pageRange.start : 0;
  const endIdx = typeof pageRange === 'object' ? pageRange.end : presentation.slides.length - 1;
  
  const { jsPDF } = window.jspdf;
  const pdf = new jsPDF({
    orientation: 'landscape',
    unit: 'px',
    format: [800, 500],
  });
  
  const theme = themes[presentation.theme];
  
  if (includeCoverPage) {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (ctx) {
      canvas.width = 800 * scale;
      canvas.height = 500 * scale;
      ctx.scale(scale, scale);
      
      drawCoverPage(ctx, presentation, theme);
      
      const imgData = canvas.toDataURL('image/png');
      pdf.addImage(imgData, 'PNG', 0, 0, 800, 500);
      pdf.addPage();
    }
  }
  
  for (let i = startIdx; i <= endIdx; i++) {
    const slide = presentation.slides[i];
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) continue;
    
    canvas.width = 800 * scale;
    canvas.height = 500 * scale;
    ctx.scale(scale, scale);
    
    ctx.fillStyle = slide.backgroundColor;
    ctx.fillRect(0, 0, 800, 500);
    
    slide.components.forEach((comp) => {
      ctx.save();
      ctx.translate(comp.x, comp.y);
      
      if (comp.type === 'text') {
        ctx.font = `${comp.style.fontWeight} ${comp.style.fontSize}px ${comp.style.fontFamily || theme.fontFamily}`;
        ctx.fillStyle = comp.style.color;
        ctx.textAlign = (comp.style.textAlign === 'justify' ? 'left' : comp.style.textAlign) || 'left';
        ctx.textBaseline = 'top';
        
        const lines = comp.content.split('\n');
        let y = 0;
        const lineHeight = comp.style.lineHeight || 1.5;
        
        lines.forEach(line => {
          ctx.fillText(line, 0, y);
          y += comp.style.fontSize * lineHeight;
        });
      } else if (comp.type === 'shape') {
        ctx.fillStyle = comp.style.backgroundColor;
        ctx.strokeStyle = comp.style.borderColor;
        ctx.lineWidth = comp.style.borderWidth;
        
        if (comp.style.borderRadius > 0) {
          const radius = comp.style.borderRadius;
          ctx.beginPath();
          ctx.roundRect(0, 0, comp.width, comp.height, radius);
          ctx.fill();
          if (comp.style.borderWidth > 0) {
            ctx.stroke();
          }
        } else {
          ctx.fillRect(0, 0, comp.width, comp.height);
          if (comp.style.borderWidth > 0) {
            ctx.strokeRect(0, 0, comp.width, comp.height);
          }
        }
      } else if (comp.type === 'table' && comp.data) {
        const columns = comp.data.columns || [];
        const rows = comp.data.rows || [];
        const cellWidth = comp.width / columns.length;
        const headerHeight = 40;
        const rowHeight = (comp.height - headerHeight) / rows.length;
        
        const gradient = ctx.createLinearGradient(0, 0, 0, headerHeight);
        gradient.addColorStop(0, theme.primary);
        gradient.addColorStop(1, theme.accent);
        
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, comp.width, headerHeight);
        
        ctx.fillStyle = '#fff';
        ctx.font = '600 12px Inter, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        
        columns.forEach((col, idx) => {
          ctx.fillText(col, idx * cellWidth + 8, headerHeight / 2);
        });
        
        rows.forEach((row, rowIdx) => {
          const y = headerHeight + rowIdx * rowHeight;
          ctx.fillStyle = rowIdx % 2 === 0 ? '#ffffff' : '#f9fafb';
          ctx.fillRect(0, y, comp.width, rowHeight);
          
          ctx.fillStyle = '#374151';
          ctx.font = '12px Inter, sans-serif';
          
          row.forEach((cell, colIdx) => {
            ctx.fillText(String(cell), colIdx * cellWidth + 8, y + rowHeight / 2);
          });
        });
        
        ctx.strokeStyle = '#e5e7eb';
        ctx.lineWidth = 1;
        ctx.strokeRect(0, 0, comp.width, comp.height);
      } else if (comp.type === 'chart') {
        renderChartToCanvas(ctx, comp, theme);
      }
      
      ctx.restore();
    });
    
    if (options?.includeFooter !== false && presentation.master?.showFooter !== false) {
      const footerY = 470;
      ctx.fillStyle = theme.textFaint;
      ctx.font = '12px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(`${includeCoverPage ? i + 2 : i + 1} / ${presentation.slides.length + (includeCoverPage ? 1 : 0)}`, 400, footerY);
    }
    
    if (watermark) {
      drawWatermark(ctx, watermark, watermarkOpacity);
    }
    
    const imgData = canvas.toDataURL('image/png');
    pdf.addImage(imgData, 'PNG', 0, 0, 800, 500);
    
    if (i < endIdx) {
      pdf.addPage();
    }
  }
  
  pdf.save(`${presentation.title || 'presentation'}.pdf`);
};

const renderChartToCanvas = (ctx: CanvasRenderingContext2D, comp: Component, theme: any): void => {
  const data = comp.data;
  if (!data || !data.type) return;
  
  const labels = data.labels || [];
  const datasets = data.datasets || [];
  
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, comp.width, comp.height);
  
  if (data.type === 'bar' || data.type === 'bar-horizontal') {
    const isHorizontal = data.type === 'bar-horizontal';
    const maxVal = Math.max(...datasets.flatMap(ds => ds.data || []));
    const padding = 40;
    const chartWidth = comp.width - padding * 2;
    const chartHeight = comp.height - padding * 2;
    
    const barCount = labels.length;
    const groupCount = datasets.length;
    const groupGap = chartWidth * 0.1;
    const groupWidth = (chartWidth - groupGap * (barCount - 1)) / barCount;
    const barWidth = groupWidth / (groupCount + 1);
    
    ctx.strokeStyle = '#f3f4f6';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
      const y = padding + (chartHeight / 5) * i;
      ctx.beginPath();
      ctx.moveTo(padding, y);
      ctx.lineTo(comp.width - padding, y);
      ctx.stroke();
      
      ctx.fillStyle = '#6b7280';
      ctx.font = '10px Inter, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(String(Math.round(maxVal * (1 - i / 5))), padding - 5, y + 3);
    }
    
    datasets.forEach((ds: any, dsIdx: number) => {
      const color = ds.color || (dsIdx === 0 ? theme.primary : theme.accent);
      
      labels.forEach((label: string, idx: number) => {
        const value = ds.data?.[idx] || 0;
        const barHeight = (value / maxVal) * chartHeight;
        
        if (isHorizontal) {
          const x = padding + (groupWidth + groupGap) * idx + barWidth * (dsIdx + 0.5);
          const y = padding + chartHeight - barHeight;
          
          const gradient = ctx.createLinearGradient(x, y, x, padding + chartHeight);
          gradient.addColorStop(0, color);
          gradient.addColorStop(1, `${color}88`);
          
          ctx.fillStyle = gradient;
          ctx.beginPath();
          ctx.roundRect(x - barWidth / 2, y, barWidth, barHeight, [0, 6, 6, 0]);
          ctx.fill();
        } else {
          const x = padding + (groupWidth + groupGap) * idx + barWidth * (dsIdx + 0.5);
          const y = padding + chartHeight - barHeight;
          
          const gradient = ctx.createLinearGradient(x, y, x, padding + chartHeight);
          gradient.addColorStop(0, color);
          gradient.addColorStop(1, `${color}88`);
          
          ctx.fillStyle = gradient;
          ctx.beginPath();
          ctx.roundRect(x - barWidth / 2, y, barWidth, barHeight, [6, 6, 0, 0]);
          ctx.fill();
        }
      });
    });
    
    ctx.fillStyle = '#374151';
    ctx.font = '11px Inter, sans-serif';
    ctx.textAlign = 'center';
    labels.forEach((label: string, idx: number) => {
      if (isHorizontal) {
        const y = padding + chartHeight + 20;
        ctx.fillText(label, padding + (groupWidth + groupGap) * idx + groupWidth / 2, y);
      } else {
        const y = padding + chartHeight + 20;
        ctx.fillText(label, padding + (groupWidth + groupGap) * idx + groupWidth / 2, y);
      }
    });
  } else if (data.type === 'pie') {
    const centerX = comp.width / 2;
    const centerY = comp.height / 2;
    const radius = Math.min(comp.width, comp.height) / 2 - 40;
    const innerRadius = radius * 0.5;
    
    let startAngle = -Math.PI / 2;
    
    datasets.forEach((ds: any) => {
      const dataValues = ds.data || [];
      const total = dataValues.reduce((a: number, b: number) => a + b, 0);
      
      dataValues.forEach((value: number, idx: number) => {
        const sliceAngle = (value / total) * 2 * Math.PI;
        const endAngle = startAngle + sliceAngle;
        
        const hue = (idx * 60) % 360;
        const color = typeof ds.color === 'string' ? ds.color : `hsl(${hue}, 70%, 55%)`;
        
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, startAngle, endAngle);
        ctx.closePath();
        ctx.fill();
        
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, innerRadius, startAngle, endAngle);
        ctx.closePath();
        ctx.fill();
        
        startAngle = endAngle;
      });
    });
    
    if (labels.length > 0) {
      const legendY = centerY + radius + 20;
      const legendSpacing = 80;
      const startX = centerX - (labels.length * legendSpacing) / 2 + legendSpacing / 2;
      
      ctx.font = '11px Inter, sans-serif';
      ctx.textAlign = 'left';
      
      labels.forEach((label: string, idx: number) => {
        const x = startX + idx * legendSpacing;
        const hue = (idx * 60) % 360;
        const color = typeof datasets[0]?.color === 'string' ? datasets[0].color : `hsl(${hue}, 70%, 55%)`;
        
        ctx.fillStyle = color;
        ctx.fillRect(x, legendY - 8, 12, 12);
        
        ctx.fillStyle = '#374151';
        ctx.fillText(label, x + 18, legendY + 3);
      });
    }
  } else if (data.type === 'line' || data.type === 'area') {
    const isArea = data.type === 'area';
    const maxVal = Math.max(...datasets.flatMap(ds => ds.data || []));
    const padding = 40;
    const chartWidth = comp.width - padding * 2;
    const chartHeight = comp.height - padding * 2;
    const pointSpacing = chartWidth / (labels.length - 1 || 1);
    
    ctx.strokeStyle = '#f3f4f6';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
      const y = padding + (chartHeight / 5) * i;
      ctx.beginPath();
      ctx.moveTo(padding, y);
      ctx.lineTo(comp.width - padding, y);
      ctx.stroke();
      
      ctx.fillStyle = '#6b7280';
      ctx.font = '10px Inter, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(String(Math.round(maxVal * (1 - i / 5))), padding - 5, y + 3);
    }
    
    datasets.forEach((ds: any, dsIdx: number) => {
      const color = ds.color || (dsIdx === 0 ? theme.primary : theme.accent);
      const dataValues = ds.data || [];
      
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 3;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      
      dataValues.forEach((value: number, idx: number) => {
        const x = padding + idx * pointSpacing;
        const y = padding + chartHeight - (value / maxVal) * chartHeight;
        
        if (idx === 0) {
          ctx.moveTo(x, y);
        } else {
          const prevX = padding + (idx - 1) * pointSpacing;
          const prevY = padding + chartHeight - (dataValues[idx - 1] / maxVal) * chartHeight;
          const cpX = (prevX + x) / 2;
          ctx.quadraticCurveTo(prevX, prevY, cpX, (prevY + y) / 2);
        }
      });
      
      const lastX = padding + (dataValues.length - 1) * pointSpacing;
      const lastY = padding + chartHeight - (dataValues[dataValues.length - 1] / maxVal) * chartHeight;
      ctx.lineTo(lastX, lastY);
      ctx.stroke();
      
      if (isArea) {
        ctx.lineTo(lastX, padding + chartHeight);
        ctx.lineTo(padding, padding + chartHeight);
        ctx.closePath();
        
        const gradient = ctx.createLinearGradient(0, padding, 0, padding + chartHeight);
        gradient.addColorStop(0, `${color}60`);
        gradient.addColorStop(1, `${color}05`);
        ctx.fillStyle = gradient;
        ctx.fill();
      }
      
      dataValues.forEach((value: number, idx: number) => {
        const x = padding + idx * pointSpacing;
        const y = padding + chartHeight - (value / maxVal) * chartHeight;
        
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(x, y, 6, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
      });
    });
    
    ctx.fillStyle = '#374151';
    ctx.font = '11px Inter, sans-serif';
    ctx.textAlign = 'center';
    labels.forEach((label: string, idx: number) => {
      const x = padding + idx * pointSpacing;
      const y = padding + chartHeight + 20;
      ctx.fillText(label, x, y);
    });
  } else if (data.type === 'radar') {
    const centerX = comp.width / 2;
    const centerY = comp.height / 2;
    const radius = Math.min(comp.width, comp.height) / 2 - 40;
    const indicatorCount = labels.length;
    const angleStep = (Math.PI * 2) / indicatorCount;
    
    for (let level = 1; level <= 5; level++) {
      const levelRadius = (radius / 5) * level;
      ctx.beginPath();
      ctx.strokeStyle = '#e5e7eb';
      ctx.lineWidth = 1;
      
      for (let i = 0; i < indicatorCount; i++) {
        const angle = -Math.PI / 2 + i * angleStep;
        const x = centerX + Math.cos(angle) * levelRadius;
        const y = centerY + Math.sin(angle) * levelRadius;
        
        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.closePath();
      ctx.stroke();
    }
    
    for (let i = 0; i < indicatorCount; i++) {
      const angle = -Math.PI / 2 + i * angleStep;
      ctx.beginPath();
      ctx.strokeStyle = '#e5e7eb';
      ctx.lineWidth = 1;
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(centerX + Math.cos(angle) * radius, centerY + Math.sin(angle) * radius);
      ctx.stroke();
      
      ctx.fillStyle = '#6b7280';
      ctx.font = '10px Inter, sans-serif';
      ctx.textAlign = 'center';
      const labelRadius = radius + 20;
      const labelX = centerX + Math.cos(angle) * labelRadius;
      const labelY = centerY + Math.sin(angle) * labelRadius;
      ctx.fillText(labels[i], labelX, labelY);
    }
    
    datasets.forEach((ds: any, dsIdx: number) => {
      const color = ds.color || (dsIdx === 0 ? theme.primary : theme.accent);
      const dataValues = ds.data || [];
      
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.fillStyle = `${color}30`;
      
      dataValues.forEach((value: number, idx: number) => {
        const angle = -Math.PI / 2 + idx * angleStep;
        const valueRadius = (value / 100) * radius;
        const x = centerX + Math.cos(angle) * valueRadius;
        const y = centerY + Math.sin(angle) * valueRadius;
        
        if (idx === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    });
  } else if (data.type === 'gauge') {
    const centerX = comp.width / 2;
    const centerY = comp.height / 2;
    const radius = Math.min(comp.width, comp.height) / 2 - 30;
    
    const startAngle = Math.PI * 0.75;
    const endAngle = Math.PI * 2.25;
    
    ctx.beginPath();
    ctx.strokeStyle = '#e5e7eb';
    ctx.lineWidth = 20;
    ctx.lineCap = 'round';
    ctx.arc(centerX, centerY, radius, startAngle, endAngle);
    ctx.stroke();
    
    const value = datasets[0]?.data?.[0] || 0;
    const valueAngle = startAngle + ((value / 100) * (endAngle - startAngle));
    
    const gradient = ctx.createLinearGradient(0, 0, comp.width, comp.height);
    gradient.addColorStop(0, theme.primary);
    gradient.addColorStop(1, theme.accent);
    
    ctx.beginPath();
    ctx.strokeStyle = gradient;
    ctx.lineWidth = 20;
    ctx.lineCap = 'round';
    ctx.arc(centerX, centerY, radius, startAngle, valueAngle);
    ctx.stroke();
    
    ctx.fillStyle = theme.text;
    ctx.font = 'bold 48px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(`${value}%`, centerX, centerY + 15);
    
    ctx.fillStyle = '#6b7280';
    ctx.font = '14px Inter, sans-serif';
    ctx.fillText(data.title || '', centerX, centerY + 45);
  }
};

export const downloadPDFWithProgress = async (
  presentation: Presentation, 
  onProgress: (progress: number, current: number, total: number) => void,
  options?: ExportOptions
): Promise<void> => {
  const resolution = options?.resolution || 'high';
  const scale = resolution === 'high' ? 2 : resolution === 'medium' ? 1.5 : 1;
  const pageRange = options?.pageRange || 'all';
  const includeCoverPage = options?.includeCoverPage || false;
  const watermark = options?.watermark;
  const watermarkOpacity = options?.watermarkOpacity || 0.15;
  
  const startIdx = typeof pageRange === 'object' ? pageRange.start : 0;
  const endIdx = typeof pageRange === 'object' ? pageRange.end : presentation.slides.length - 1;
  const totalPages = endIdx - startIdx + 1;
  
  const { jsPDF } = window.jspdf;
  const pdf = new jsPDF({
    orientation: 'landscape',
    unit: 'px',
    format: [800, 500],
  });
  
  const theme = themes[presentation.theme];
  
  let currentProgress = 0;
  
  if (includeCoverPage) {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (ctx) {
      canvas.width = 800 * scale;
      canvas.height = 500 * scale;
      ctx.scale(scale, scale);
      
      drawCoverPage(ctx, presentation, theme);
      
      if (watermark) {
        drawWatermark(ctx, watermark, watermarkOpacity);
      }
      
      const imgData = canvas.toDataURL('image/png');
      pdf.addImage(imgData, 'PNG', 0, 0, 800, 500);
      pdf.addPage();
    }
    
    currentProgress = 5;
    onProgress(currentProgress, 0, totalPages);
  }
  
  for (let i = startIdx; i <= endIdx; i++) {
    const slide = presentation.slides[i];
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) continue;
    
    canvas.width = 800 * scale;
    canvas.height = 500 * scale;
    ctx.scale(scale, scale);
    
    ctx.fillStyle = slide.backgroundColor;
    ctx.fillRect(0, 0, 800, 500);
    
    slide.components.forEach((comp) => {
      ctx.save();
      ctx.translate(comp.x, comp.y);
      
      if (comp.type === 'text') {
        ctx.font = `${comp.style.fontWeight} ${comp.style.fontSize}px ${comp.style.fontFamily || theme.fontFamily}`;
        ctx.fillStyle = comp.style.color;
        ctx.textAlign = (comp.style.textAlign === 'justify' ? 'left' : comp.style.textAlign) || 'left';
        ctx.textBaseline = 'top';
        
        const lines = comp.content.split('\n');
        let y = 0;
        const lineHeight = comp.style.lineHeight || 1.5;
        
        lines.forEach(line => {
          ctx.fillText(line, 0, y);
          y += comp.style.fontSize * lineHeight;
        });
      } else if (comp.type === 'shape') {
        ctx.fillStyle = comp.style.backgroundColor;
        ctx.strokeStyle = comp.style.borderColor;
        ctx.lineWidth = comp.style.borderWidth;
        
        if (comp.style.borderRadius > 0) {
          const radius = comp.style.borderRadius;
          ctx.beginPath();
          ctx.roundRect(0, 0, comp.width, comp.height, radius);
          ctx.fill();
          if (comp.style.borderWidth > 0) {
            ctx.stroke();
          }
        } else {
          ctx.fillRect(0, 0, comp.width, comp.height);
          if (comp.style.borderWidth > 0) {
            ctx.strokeRect(0, 0, comp.width, comp.height);
          }
        }
      } else if (comp.type === 'table' && comp.data) {
        const columns = comp.data.columns || [];
        const rows = comp.data.rows || [];
        const cellWidth = comp.width / columns.length;
        const headerHeight = 40;
        const rowHeight = (comp.height - headerHeight) / rows.length;
        
        const gradient = ctx.createLinearGradient(0, 0, 0, headerHeight);
        gradient.addColorStop(0, theme.primary);
        gradient.addColorStop(1, theme.accent);
        
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, comp.width, headerHeight);
        
        ctx.fillStyle = '#fff';
        ctx.font = '600 12px Inter, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        
        columns.forEach((col, idx) => {
          ctx.fillText(col, idx * cellWidth + 8, headerHeight / 2);
        });
        
        rows.forEach((row, rowIdx) => {
          const y = headerHeight + rowIdx * rowHeight;
          ctx.fillStyle = rowIdx % 2 === 0 ? '#ffffff' : '#f9fafb';
          ctx.fillRect(0, y, comp.width, rowHeight);
          
          ctx.fillStyle = '#374151';
          ctx.font = '12px Inter, sans-serif';
          
          row.forEach((cell, colIdx) => {
            ctx.fillText(String(cell), colIdx * cellWidth + 8, y + rowHeight / 2);
          });
        });
        
        ctx.strokeStyle = '#e5e7eb';
        ctx.lineWidth = 1;
        ctx.strokeRect(0, 0, comp.width, comp.height);
      } else if (comp.type === 'chart') {
        renderChartToCanvas(ctx, comp, theme);
      }
      
      ctx.restore();
    });
    
    if (options?.includeFooter !== false && presentation.master?.showFooter !== false) {
      const footerY = 470;
      ctx.fillStyle = theme.textFaint;
      ctx.font = '12px Inter, sans-serif';
      ctx.textAlign = 'center';
      const totalWithCover = presentation.slides.length + (includeCoverPage ? 1 : 0);
      ctx.fillText(`${includeCoverPage ? i + 2 : i + 1} / ${totalWithCover}`, 400, footerY);
    }
    
    if (watermark) {
      drawWatermark(ctx, watermark, watermarkOpacity);
    }
    
    const imgData = canvas.toDataURL('image/png');
    pdf.addImage(imgData, 'PNG', 0, 0, 800, 500);
    
    if (i < endIdx) {
      pdf.addPage();
    }
    
    currentProgress = (includeCoverPage ? 5 : 0) + ((i - startIdx + 1) / totalPages) * (includeCoverPage ? 95 : 100);
    onProgress(currentProgress, i - startIdx + 1, totalPages);
  }
  
  pdf.save(`${presentation.title || 'presentation'}.pdf`);
};

export const downloadPPTX = async (presentation: Presentation, options?: ExportOptions): Promise<void> => {
  const theme = themes[presentation.theme];
  const presentationTitle = presentation.title || '演示文稿';
  
  const ppt = new pptxgen();
  
  for (let i = 0; i < presentation.slides.length; i++) {
    const slide = presentation.slides[i];
    const pptSlide = ppt.addSlide();
    
    pptSlide.background = { color: slide.backgroundColor };
    
    slide.components.forEach((comp) => {
      if (comp.type === 'text') {
        const fontSize = Math.max(10, comp.style.fontSize);
        const x = (comp.x / 800) * 10;
        const y = (comp.y / 500) * 6.25;
        const w = (comp.width / 800) * 10;
        const h = (comp.height / 500) * 6.25;
        
        pptSlide.addText(comp.content, {
          x: x,
          y: y,
          w: w,
          h: h,
          fontSize: fontSize,
          color: comp.style.color,
          align: comp.style.textAlign === 'center' ? 'center' : comp.style.textAlign === 'right' ? 'right' : 'left',
          valign: 'top',
        });
      } else if (comp.type === 'shape') {
        const x = (comp.x / 800) * 10;
        const y = (comp.y / 500) * 6.25;
        const w = (comp.width / 800) * 10;
        const h = (comp.height / 500) * 6.25;
        
        pptSlide.addShape(pptxgen.ShapeType.rect, {
          x: x,
          y: y,
          w: w,
          h: h,
          fill: { color: comp.style.backgroundColor },
        });
      }
    });
    
    if (options?.includeFooter !== false && presentation.master?.showFooter !== false) {
      const footerText = presentation.master.footerText || '';
      const showPageNumber = presentation.master.showPageNumber !== false;
      
      let footerContent = '';
      if (footerText) footerContent += footerText + ' | ';
      if (showPageNumber) footerContent += `${i + 1} / ${presentation.slides.length}`;
      
      pptSlide.addText(footerContent, {
        x: 0,
        y: 5.7,
        w: 10,
        h: 0.5,
        fontSize: 10,
        color: theme.textFaint,
        align: 'center',
        valign: 'middle',
      });
    }
  }
  
  ppt.writeFile({ fileName: `${presentationTitle}.pptx` });
};

export const downloadPPTXWithProgress = async (
  presentation: Presentation,
  onProgress: (progress: number, current: number, total: number) => void,
  options?: ExportOptions
): Promise<void> => {
  const theme = themes[presentation.theme];
  const presentationTitle = presentation.title || '演示文稿';
  
  const ppt = new pptxgen();
  
  const totalSlides = presentation.slides.length;
  
  for (let i = 0; i < totalSlides; i++) {
    const slide = presentation.slides[i];
    const pptSlide = ppt.addSlide();
    
    pptSlide.background = { color: slide.backgroundColor };
    
    slide.components.forEach((comp) => {
      if (comp.type === 'text') {
        const fontSize = Math.max(10, comp.style.fontSize);
        const x = (comp.x / 800) * 10;
        const y = (comp.y / 500) * 6.25;
        const w = (comp.width / 800) * 10;
        const h = (comp.height / 500) * 6.25;
        
        pptSlide.addText(comp.content, {
          x: x,
          y: y,
          w: w,
          h: h,
          fontSize: fontSize,
          color: comp.style.color,
          align: comp.style.textAlign === 'center' ? 'center' : comp.style.textAlign === 'right' ? 'right' : 'left',
          valign: 'top',
        });
      } else if (comp.type === 'shape') {
        const x = (comp.x / 800) * 10;
        const y = (comp.y / 500) * 6.25;
        const w = (comp.width / 800) * 10;
        const h = (comp.height / 500) * 6.25;
        
        pptSlide.addShape(pptxgen.ShapeType.rect, {
          x: x,
          y: y,
          w: w,
          h: h,
          fill: { color: comp.style.backgroundColor },
        });
      }
    });
    
    if (options?.includeFooter !== false && presentation.master?.showFooter !== false) {
      const footerText = presentation.master.footerText || '';
      const showPageNumber = presentation.master.showPageNumber !== false;
      
      let footerContent = '';
      if (footerText) footerContent += footerText + ' | ';
      if (showPageNumber) footerContent += `${i + 1} / ${totalSlides}`;
      
      pptSlide.addText(footerContent, {
        x: 0,
        y: 5.7,
        w: 10,
        h: 0.5,
        fontSize: 10,
        color: theme.textFaint,
        align: 'center',
        valign: 'middle',
      });
    }
    
    onProgress(((i + 1) / totalSlides) * 100, i + 1, totalSlides);
  }
  
  ppt.writeFile({ fileName: `${presentationTitle}.pptx` });
};
