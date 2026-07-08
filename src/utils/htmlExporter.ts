import { Presentation, Slide, Component } from '../types';
import { themes } from '../theme/themes';

declare const echarts: any;

const generateSlideThumbnail = (slide: Slide, theme: any): string => {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) return '';
  
  canvas.width = 120;
  canvas.height = 75;
  
  ctx.fillStyle = slide.backgroundColor;
  ctx.fillRect(0, 0, 120, 75);
  
  slide.components.forEach((comp) => {
    ctx.save();
    ctx.translate((comp.x / 800) * 120, (comp.y / 500) * 75);
    
    if (comp.type === 'text') {
      const fontSize = Math.max(6, (comp.style.fontSize / 800) * 120);
      ctx.font = `${comp.style.fontWeight} ${fontSize}px ${comp.style.fontFamily || theme.fontFamily}`;
      ctx.fillStyle = comp.style.color;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      
      const lines = comp.content.split('\n').slice(0, 3);
      let y = 0;
      const lineHeight = comp.style.lineHeight || 1.5;
      
      lines.forEach(line => {
        const maxWidth = (comp.width / 800) * 120;
        const ellipsis = ctx.measureText(line).width > maxWidth ? '...' : '';
        ctx.fillText(line.substring(0, 20) + ellipsis, 0, y);
        y += fontSize * lineHeight;
      });
    } else if (comp.type === 'shape') {
      ctx.fillStyle = comp.style.backgroundColor;
      ctx.fillRect(0, 0, (comp.width / 800) * 120, (comp.height / 500) * 75);
    } else if (comp.type === 'chart') {
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, (comp.width / 800) * 120, (comp.height / 500) * 75);
      ctx.fillStyle = theme.primary;
      ctx.fillRect(5, 10, 40, 30);
      ctx.fillStyle = theme.accent;
      ctx.fillRect(50, 15, 35, 25);
    } else if (comp.type === 'table' && comp.data) {
      ctx.fillStyle = theme.primary;
      ctx.fillRect(0, 0, (comp.width / 800) * 120, 15);
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 15, (comp.width / 800) * 120, (comp.height / 500) * 75 - 15);
    }
    
    ctx.restore();
  });
  
  return canvas.toDataURL('image/png');
};

const getEChartsOption = (data: any, themeColors: any): string => {
  if (!data || !data.type) return '{}';
  
  const colors = data.datasets?.[0]?.color || themeColors.primary;
  const labels = data.labels || [];
  const chartData = data.datasets?.[0]?.data || [];
  const secondaryColors = data.datasets?.[1]?.color || themeColors.accent;
  
  const defaultTooltip = `{
    trigger: 'axis',
    backgroundColor: 'rgba(255,255,255,0.98)',
    borderColor: '#e5e7eb',
    borderWidth: 1,
    padding: [12, 16],
    textStyle: { color: '#374151', fontSize: 13 },
    axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(0,0,0,0.05)' } }
  }`;
  
  const itemTooltip = `{
    trigger: 'item',
    backgroundColor: 'rgba(255,255,255,0.98)',
    borderColor: '#e5e7eb',
    borderWidth: 1,
    padding: [12, 16],
    textStyle: { color: '#374151', fontSize: 13 }
  }`;
  
  const defaultLegend = `{ show: ${data.datasets?.length > 1}, bottom: 0, textStyle: { color: '#6b7280', fontSize: 12 }, itemGap: 20 }`;
  
  const createGradientColor = (color: string, direction: string = 'vertical') => {
    if (direction === 'vertical') {
      return `new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '${color}' }, { offset: 1, color: '${color}88' }])`;
    }
    return `new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: '${color}' }, { offset: 1, color: '${color}88' }])`;
  };
  
  switch (data.type) {
    case 'bar':
      const barSeries = data.datasets.map((ds: any, idx: number) => {
        const barColor = typeof ds.color === 'string' ? ds.color : (idx === 0 ? colors : secondaryColors);
        return `{
          type: 'bar',
          name: '${ds.name || ''}',
          data: ${JSON.stringify(ds.data)},
          barGap: ${idx > 0 ? "'10%'" : "'0%'"},
          barWidth: ${data.datasets.length > 1 ? "'35%'" : "'50%'"},
          itemStyle: { 
            color: ${createGradientColor(barColor)},
            borderRadius: [6, 6, 0, 0],
            shadowColor: 'rgba(0,0,0,0.1)',
            shadowBlur: 8,
            shadowOffsetY: 4
          },
          emphasis: {
            itemStyle: {
              shadowColor: 'rgba(0,0,0,0.2)',
              shadowBlur: 12,
              shadowOffsetY: 6
            }
          },
          animationDuration: 1500,
          animationEasing: 'elasticOut'
        }`;
      }).join(',\n');
      
      return `{
        tooltip: ${defaultTooltip},
        legend: ${defaultLegend},
        grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
        xAxis: { 
          type: 'category', 
          data: ${JSON.stringify(labels)}, 
          axisLine: { lineStyle: { color: '#e5e7eb' } }, 
          axisLabel: { color: '#6b7280', fontSize: 11, rotate: ${labels.length > 6 ? 30 : 0} },
          axisTick: { show: false }
        },
        yAxis: { 
          type: 'value', 
          axisLine: { show: false }, 
          splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } }, 
          axisLabel: { color: '#6b7280', fontSize: 11 },
          axisTick: { show: false }
        },
        series: [${barSeries}]
      }`;
      
    case 'bar-horizontal':
      const hBarSeries = data.datasets.map((ds: any, idx: number) => {
        const barColor = typeof ds.color === 'string' ? ds.color : (idx === 0 ? colors : secondaryColors);
        return `{
          type: 'bar',
          name: '${ds.name || ''}',
          data: ${JSON.stringify(ds.data)},
          barGap: ${idx > 0 ? "'10%'" : "'0%'"},
          barWidth: ${data.datasets.length > 1 ? "'35%'" : "'50%'"},
          itemStyle: { 
            color: ${createGradientColor(barColor, 'horizontal')},
            borderRadius: [0, 6, 6, 0],
            shadowColor: 'rgba(0,0,0,0.1)',
            shadowBlur: 8,
            shadowOffsetX: 4
          },
          animationDuration: 1500,
          animationEasing: 'elasticOut'
        }`;
      }).join(',\n');
      
      return `{
        tooltip: ${defaultTooltip},
        legend: { show: ${data.datasets?.length > 1}, right: 0, top: 'center', textStyle: { color: '#6b7280', fontSize: 12 }, itemGap: 20 },
        grid: { left: '15%', right: '15%', bottom: '3%', top: '3%', containLabel: true },
        xAxis: { 
          type: 'value', 
          axisLine: { show: false }, 
          splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } }, 
          axisLabel: { color: '#6b7280', fontSize: 11 },
          axisTick: { show: false }
        },
        yAxis: { 
          type: 'category', 
          data: ${JSON.stringify(labels)}, 
          axisLine: { lineStyle: { color: '#e5e7eb' } }, 
          axisLabel: { color: '#6b7280', fontSize: 11 },
          axisTick: { show: false }
        },
        series: [${hBarSeries}]
      }`;
      
    case 'pie':
      const pieData = labels.map((label: string, idx: number) => {
        const pieColor = typeof colors === 'string' ? `hsl(${(idx * 60) % 360}, 70%, 55%)` : (colors[idx] || colors[0]);
        return `{ value: ${chartData[idx]}, name: '${label}', itemStyle: { color: '${pieColor}' } }`;
      }).join(',\n');
      
      return `{
        tooltip: { ...${itemTooltip}, formatter: '{b}: {c} ({d}%)' },
        legend: { orient: 'vertical', right: '5%', top: 'center', textStyle: { color: '#6b7280', fontSize: 12 }, itemGap: 12 },
        series: [{
          type: 'pie',
          radius: ['40%', '70%'],
          center: ['40%', '50%'],
          itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
          label: { show: true, position: 'outside', fontSize: 11, color: '#374151', formatter: '{b}: {d}%' },
          labelLine: { show: true, length: 15, length2: 10 },
          animationType: 'scale',
          animationEasing: 'elasticOut',
          animationDelay: function(idx) { return idx * 100; },
          data: [${pieData}]
        }]
      }`;
      
    case 'line':
      const lineSeries = data.datasets.map((ds: any, idx: number) => {
        const lineColor = ds.color || (idx === 0 ? colors : secondaryColors);
        return `{
          type: 'line',
          name: '${ds.name || ''}',
          data: ${JSON.stringify(ds.data)},
          smooth: true,
          symbol: 'circle',
          symbolSize: 8,
          lineStyle: { color: '${lineColor}', width: 3 },
          itemStyle: { color: '${lineColor}', borderColor: '#fff', borderWidth: 2 },
          areaStyle: { 
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '${lineColor}40' },
              { offset: 1, color: '${lineColor}05' }
            ])
          },
          emphasis: {
            itemStyle: { shadowColor: 'rgba(0,0,0,0.3)', shadowBlur: 10 }
          },
          animationDuration: 2000,
          animationEasing: 'cubicInOut'
        }`;
      }).join(',\n');
      
      return `{
        tooltip: ${defaultTooltip},
        legend: ${defaultLegend},
        grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
        xAxis: { 
          type: 'category', 
          data: ${JSON.stringify(labels)}, 
          axisLine: { lineStyle: { color: '#e5e7eb' } }, 
          axisLabel: { color: '#6b7280', fontSize: 11 },
          axisTick: { show: false }
        },
        yAxis: { 
          type: 'value', 
          axisLine: { show: false }, 
          splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } }, 
          axisLabel: { color: '#6b7280', fontSize: 11 },
          axisTick: { show: false }
        },
        series: [${lineSeries}]
      }`;
      
    case 'area':
      const areaSeries = data.datasets.map((ds: any, idx: number) => {
        const areaColor = ds.color || (idx === 0 ? colors : secondaryColors);
        return `{
          type: 'line',
          name: '${ds.name || ''}',
          data: ${JSON.stringify(ds.data)},
          smooth: true,
          symbol: 'none',
          lineStyle: { color: '${areaColor}', width: 2 },
          itemStyle: { color: '${areaColor}' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '${areaColor}60' },
              { offset: 1, color: '${areaColor}05' }
            ])
          },
          animationDuration: 2500,
          animationEasing: 'cubicInOut'
        }`;
      }).join(',\n');
      
      return `{
        tooltip: ${defaultTooltip},
        legend: ${defaultLegend},
        grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
        xAxis: { 
          type: 'category', 
          data: ${JSON.stringify(labels)}, 
          axisLine: { lineStyle: { color: '#e5e7eb' } }, 
          axisLabel: { color: '#6b7280', fontSize: 11 },
          axisTick: { show: false }
        },
        yAxis: { 
          type: 'value', 
          axisLine: { show: false }, 
          splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } }, 
          axisLabel: { color: '#6b7280', fontSize: 11 },
          axisTick: { show: false }
        },
        series: [${areaSeries}]
      }`;
      
    case 'radar':
      const radarData = data.datasets.map((ds: any, idx: number) => {
        const radarColor = ds.color || (idx === 0 ? colors : secondaryColors);
        return `{ 
          value: ${JSON.stringify(ds.data)}, 
          name: '${ds.name || ''}',
          areaStyle: { opacity: 0.3 }, 
          lineStyle: { width: 2, color: '${radarColor}' }, 
          itemStyle: { color: '${radarColor}' },
          symbol: 'circle',
          symbolSize: 6
        }`;
      }).join(',\n');
      
      return `{
        tooltip: ${itemTooltip},
        radar: {
          indicator: ${JSON.stringify(labels.map((label: string) => ({ name: label, max: 100 })))},
          shape: 'polygon',
          axisName: { color: '#6b7280', fontSize: 11 },
          splitLine: { lineStyle: { color: '#e5e7eb' } },
          splitArea: { show: true, areaStyle: { color: ['#f9fafb', '#fff'] } },
          axisLine: { lineStyle: { color: '#e5e7eb' } }
        },
        series: [{
          type: 'radar',
          data: [${radarData}],
          animationDuration: 2000,
          animationEasing: 'cubicInOut'
        }]
      }`;
      
    case 'gauge':
      return `{
        series: [{
          type: 'gauge',
          startAngle: 200,
          endAngle: -20,
          pointer: { itemStyle: { color: '${themeColors.danger}' }, width: 6 },
          progress: { show: true, roundCap: true, itemStyle: { color: '${colors}' } },
          axisLine: { lineStyle: { width: 16, color: [[0.3, '#e5e7eb'], [0.7, '#d1d5db'], [1, '#e5e7eb']] } },
          splitLine: { show: false },
          axisTick: { show: false },
          axisLabel: { show: false },
          detail: { 
            fontSize: 32, 
            fontWeight: 'bold', 
            formatter: '{value}%', 
            offsetCenter: [0, '30%'],
            color: '${themeColors.text}'
          },
          data: [{ 
            value: ${chartData[0] || 0}, 
            name: '${data.title || ''}', 
            title: { fontSize: 14, color: '#6b7280', offsetCenter: [0, '-10%'] } 
          }],
          animationDuration: 2000,
          animationEasing: 'elasticOut'
        }]
      }`;
      
    case 'funnel':
      const funnelData = labels.map((label: string, idx: number) => {
        const funnelColor = typeof colors === 'string' ? `hsl(${200 - idx * 30}, 70%, 55%)` : (colors[idx] || colors[0]);
        return `{ value: ${chartData[idx] || (100 - idx * 15)}, name: '${label}', itemStyle: { color: '${funnelColor}' } }`;
      }).join(',\n');
      
      return `{
        tooltip: { ...${itemTooltip}, formatter: '{b}: {c}' },
        series: [{
          type: 'funnel',
          left: '10%',
          top: 60,
          bottom: 60,
          width: '80%',
          min: 0,
          max: 100,
          gap: 4,
          label: { show: true, position: 'inside', fontSize: 12, fontWeight: 'bold', color: '#fff' },
          itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
          emphasis: { label: { fontSize: 14 } },
          data: [${funnelData}],
          animationDuration: 1500,
          animationEasing: 'elasticOut',
          animationDelay: function(idx) { return idx * 150; }
        }]
      }`;
      
    case 'scatter':
      const scatterSeries = data.datasets.map((ds: any, idx: number) => {
        const scatterColor = ds.color || (idx === 0 ? colors : secondaryColors);
        return `{
          type: 'scatter',
          name: '${ds.name || ''}',
          data: ${JSON.stringify(ds.data)},
          symbolSize: 14,
          itemStyle: { 
            color: '${scatterColor}',
            shadowBlur: 12, 
            shadowColor: 'rgba(0,0,0,0.2)',
            borderColor: '#fff',
            borderWidth: 2
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 20,
              shadowColor: 'rgba(0,0,0,0.3)',
              symbolSize: 18
            }
          },
          animationDuration: 2000,
          animationEasing: 'elasticOut'
        }`;
      }).join(',\n');
      
      return `{
        tooltip: ${itemTooltip},
        legend: ${defaultLegend},
        grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
        xAxis: { 
          type: 'value', 
          axisLine: { show: false }, 
          splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } }, 
          axisLabel: { color: '#6b7280', fontSize: 11 },
          axisTick: { show: false }
        },
        yAxis: { 
          type: 'value', 
          axisLine: { show: false }, 
          splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } }, 
          axisLabel: { color: '#6b7280', fontSize: 11 },
          axisTick: { show: false }
        },
        series: [${scatterSeries}]
      }`;
      
    case 'polar':
      const polarSeries = data.datasets.map((ds: any, idx: number) => {
        const polarColor = ds.color || (idx === 0 ? colors : secondaryColors);
        return `{
          type: 'line',
          name: '${ds.name || ''}',
          coordinateSystem: 'polar',
          data: ${JSON.stringify(ds.data)},
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { color: '${polarColor}', width: 2 },
          itemStyle: { color: '${polarColor}' },
          areaStyle: { opacity: 0.2 },
          animationDuration: 2000,
          animationEasing: 'cubicInOut'
        }`;
      }).join(',\n');
      
      return `{
        tooltip: ${itemTooltip},
        legend: ${defaultLegend},
        polar: {
          radius: ['30%', '70%'],
          angleAxis: { 
            type: 'category', 
            data: ${JSON.stringify(labels)}, 
            axisLine: { lineStyle: { color: '#e5e7eb' } }, 
            axisLabel: { color: '#6b7280', fontSize: 11 },
            axisTick: { show: false }
          },
          radiusAxis: { 
            type: 'value', 
            axisLine: { show: false }, 
            splitLine: { lineStyle: { color: '#e5e7eb' } }, 
            axisLabel: { color: '#6b7280', fontSize: 11 },
            axisTick: { show: false }
          }
        },
        series: [${polarSeries}]
      }`;
      
    case 'gantt':
      const ganttData = chartData.map((val: any, idx: number) => {
        const ganttColor = typeof colors === 'string' ? colors : (colors[idx] || colors[0]);
        return `{ value: ${val}, itemStyle: { color: ${createGradientColor(ganttColor, 'horizontal')}, borderRadius: [4, 4, 0, 0] } }`;
      }).join(',\n');
      
      return `{
        tooltip: ${defaultTooltip},
        legend: ${defaultLegend},
        grid: { left: '15%', right: '5%', bottom: '15%', top: '10%', containLabel: true },
        xAxis: { 
          type: 'value', 
          axisLine: { show: false }, 
          splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } }, 
          axisLabel: { color: '#6b7280', fontSize: 11 },
          axisTick: { show: false }
        },
        yAxis: { 
          type: 'category', 
          data: ${JSON.stringify(labels)}, 
          axisLine: { lineStyle: { color: '#e5e7eb' } }, 
          axisLabel: { color: '#6b7280', fontSize: 11 },
          axisTick: { show: false }
        },
        series: [{
          type: 'bar',
          data: [${ganttData}],
          animationDuration: 1500,
          animationEasing: 'elasticOut'
        }]
      }`;
      
    default:
      return '{}';
  }
};

export const exportToHTML = (presentation: Presentation): string => {
  const theme = themes[presentation.theme];
  
  const renderComponent = (component: Component): string => {
    const style = component.style;
    const animation = component.animation;
    
    const inlineStyle = `
      position: absolute;
      left: ${component.x}px;
      top: ${component.y}px;
      width: ${component.width}px;
      height: ${component.height}px;
      font-family: ${style.fontFamily || theme.fontFamily};
      font-size: ${style.fontSize}px;
      font-weight: ${style.fontWeight};
      color: ${style.color};
      background-color: ${style.backgroundColor};
      border-radius: ${style.borderRadius}px;
      border-width: ${style.borderWidth}px;
      border-color: ${style.borderColor};
      border-style: ${style.borderWidth > 0 ? 'solid' : 'none'};
      box-shadow: ${style.shadow};
      text-align: ${style.textAlign || 'left'};
      padding: ${component.type === 'text' ? '8px' : '0'};
      display: flex;
      align-items: center;
      justify-content: ${style.textAlign === 'center' ? 'center' : style.textAlign === 'right' ? 'flex-end' : 'flex-start'};
      opacity: 0;
      animation: ${animation.type} ${animation.duration}ms ${animation.easing} ${animation.delay}ms forwards;
      overflow: hidden;
      line-height: ${style.lineHeight || (component.type === 'text' ? 1.5 : 1)};
      word-wrap: break-word;
      white-space: pre-wrap;
    `;

    switch (component.type) {
      case 'text':
        return `<div style="${inlineStyle}"><span>${component.content}</span></div>`;
      
      case 'chart':
        return `
          <div style="${inlineStyle}">
            <div id="chart-${component.id}" style="width:100%;height:100%;"></div>
          </div>
        `;
      
      case 'shape':
        return `<div style="${inlineStyle}"></div>`;
      
      case 'image':
        return `
          <div style="${inlineStyle}">
            <div style="width:100%;height:100%;background-color:#e5e7eb;display:flex;align-items:center;justify-content:center;">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                <polyline points="21 15 16 10 5 21"></polyline>
              </svg>
            </div>
          </div>
        `;
      
      case 'table':
        const columns = component.data?.columns || ['列1', '列2'];
        const rows = component.data?.rows || [['数据1', '数据2'], ['数据3', '数据4']];
        return `
          <div style="${inlineStyle} overflow: auto;">
            <table style="width:100%;height:100%;border-collapse:collapse;">
              <thead>
                <tr style="background: linear-gradient(135deg, ${theme.primary} 0%, ${theme.accent} 100%);">
                  ${columns.map((col: string) => `<th style="border:1px solid rgba(255,255,255,0.3);padding:8px;font-size:12px;font-weight:600;color:#fff;text-align:left;white-space:nowrap;">${col}</th>`).join('')}
                </tr>
              </thead>
              <tbody>
                ${rows.map((row: any[], rowIdx: number) => `
                  <tr style="background-color: ${rowIdx % 2 === 0 ? '#ffffff' : '#f9fafb'}; border-bottom:1px solid #f3f4f6;">
                    ${row.map((cell: any) => `<td style="border:1px solid #e5e7eb;padding:8px;font-size:12px;color:#374151;white-space:nowrap;">${typeof cell === 'number' ? `<span style="font-weight:600;">${cell}</span>` : cell}</td>`).join('')}
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `;
      
      case 'media':
        return `
          <div style="${inlineStyle}">
            <div style="width:100%;height:100%;background-color:#1f2937;display:flex;align-items:center;justify-content:center;">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#6b7280" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="23 7 16 12 23 17 23 7"></polygon>
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
              </svg>
            </div>
          </div>
        `;
      
      default:
        return '';
    }
  };

  const renderSlide = (slide: Slide, index: number, totalSlides: number, master: any): string => {
    const showFooter = master?.showFooter !== false;
    const showPageNumber = master?.showPageNumber !== false;
    const showDate = master?.showDate !== false;
    const footerText = master?.footerText || '';
    const footerStyle = master?.footerStyle || {};
    
    const footerHTML = showFooter ? `
      <div class="slide-footer" style="
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        height: 40px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 30px;
        background: linear-gradient(to top, rgba(0,0,0,0.05), transparent);
        font-size: ${footerStyle.fontSize || 12}px;
        font-family: ${footerStyle.fontFamily || theme.fontFamily};
        color: ${footerStyle.color || theme.textFaint};
      ">
        <span>${footerText}</span>
        <span>${showDate ? new Date().toLocaleDateString('zh-CN') : ''}</span>
        <span>${showPageNumber ? `${index + 1} / ${totalSlides}` : ''}</span>
      </div>
    ` : '';

    return `
      <div 
        id="slide-${slide.id}"
        class="slide"
        data-transition="${slide.transition || 'fade'}"
        style="background-color: ${slide.backgroundColor};"
      >
        ${slide.components.map((component) => renderComponent(component)).join('\n')}
        ${footerHTML}
      </div>
    `;
  };

  const thumbnailsData = presentation.slides.map((slide) => generateSlideThumbnail(slide, theme));

  const html = `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <meta name="description" content="${presentation.title || '演示文稿'}">
  <meta name="author" content="BSC Designer">
  <title>${presentation.title || '演示文稿'}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Noto+Sans+SC:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
  <style>
    :root {
      --primary: ${theme.primary};
      --secondary: ${theme.secondary};
      --accent: ${theme.accent};
      --text: ${theme.text};
      --text-light: ${theme.textLight};
      --text-faint: ${theme.textFaint};
      --background: ${theme.background};
      --font-family: ${theme.fontFamily};
      --slide-width: 800px;
      --slide-height: 500px;
      --slide-aspect: 1.6;
      --transition-duration: 500ms;
    }
    
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    
    html, body {
      width: 100%;
      height: 100%;
      overflow: hidden;
    }
    
    body {
      font-family: var(--font-family);
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
    }
    
    .presentation-container {
      position: relative;
      width: var(--slide-width);
      height: var(--slide-height);
      box-shadow: 0 25px 80px rgba(0,0,0,0.6);
      border-radius: 16px;
      overflow: hidden;
      transform: scale(1);
      transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    @media (max-width: 900px) {
      .presentation-container {
        width: 95vw;
        height: calc(95vw / var(--slide-aspect));
        max-height: 85vh;
        border-radius: 12px;
      }
    }
    
    @media (max-width: 600px) {
      .presentation-container {
        width: 98vw;
        height: calc(98vw / var(--slide-aspect));
        max-height: 80vh;
        border-radius: 8px;
      }
    }
    
    @media (min-width: 1920px) {
      .presentation-container {
        width: calc(var(--slide-width) * 1.2);
        height: calc(var(--slide-height) * 1.2);
      }
    }
    
    .slide {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      opacity: 0;
      visibility: hidden;
      transition: all var(--transition-duration) cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    .slide.active {
      opacity: 1;
      visibility: visible;
    }
    
    .slide.transition-fade.active {
      animation: slideFadeIn var(--transition-duration) ease forwards;
    }
    
    .slide.transition-slide-left.active {
      animation: slideInFromRight var(--transition-duration) ease forwards;
    }
    
    .slide.transition-slide-right.active {
      animation: slideInFromLeft var(--transition-duration) ease forwards;
    }
    
    .slide.transition-slide-up.active {
      animation: slideInFromBottom var(--transition-duration) ease forwards;
    }
    
    .slide.transition-slide-down.active {
      animation: slideInFromTop var(--transition-duration) ease forwards;
    }
    
    .slide.transition-zoom-in.active {
      animation: zoomIn var(--transition-duration) ease forwards;
    }
    
    .slide.transition-zoom-out.active {
      animation: zoomOut var(--transition-duration) ease forwards;
    }
    
    .slide.transition-flip.active {
      animation: flipIn 0.6s ease forwards;
      transform-style: preserve-3d;
    }
    
    .slide.transition-rotate.active {
      animation: rotateIn 0.6s ease forwards;
    }
    
    .controls {
      position: fixed;
      bottom: 30px;
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      gap: 12px;
      z-index: 100;
      backdrop-filter: blur(16px);
      padding: 12px 24px;
      border-radius: 50px;
      background-color: rgba(0,0,0,0.7);
      border: 1px solid rgba(255,255,255,0.1);
      box-shadow: 0 10px 40px rgba(0,0,0,0.3);
    }
    
    @media (max-width: 600px) {
      .controls {
        bottom: 15px;
        gap: 8px;
        padding: 10px 20px;
      }
    }
    
    .control-btn {
      width: 44px;
      height: 44px;
      border-radius: 50%;
      border: none;
      background-color: rgba(255,255,255,0.15);
      color: white;
      font-size: 16px;
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    
    .control-btn:hover {
      background-color: rgba(255,255,255,0.25);
      transform: scale(1.08);
    }
    
    .control-btn:active {
      transform: scale(0.95);
    }
    
    .play-btn {
      width: 56px;
      height: 56px;
      background-color: var(--primary) !important;
      font-size: 20px;
      box-shadow: 0 4px 20px rgba(59, 130, 246, 0.5);
    }
    
    .play-btn:hover {
      box-shadow: 0 6px 25px rgba(59, 130, 246, 0.6);
    }
    
    .slide-indicator {
      position: fixed;
      bottom: 20px;
      right: 30px;
      color: rgba(255,255,255,0.9);
      font-size: 14px;
      font-weight: 500;
      z-index: 100;
      padding: 10px 20px;
      border-radius: 24px;
      background-color: rgba(0,0,0,0.6);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255,255,255,0.1);
    }
    
    @media (max-width: 600px) {
      .slide-indicator {
        right: 10px;
        bottom: 80px;
        font-size: 12px;
        padding: 8px 14px;
      }
    }
    
    .speaker-notes {
      position: fixed;
      bottom: 120px;
      left: 50%;
      transform: translateX(-50%);
      width: 90%;
      max-width: 700px;
      padding: 24px;
      background-color: rgba(255,255,255,0.98);
      border-radius: 20px;
      box-shadow: 0 25px 80px rgba(0,0,0,0.3);
      z-index: 90;
      display: none;
      opacity: 0;
      transition: opacity 0.3s ease;
      border: 1px solid rgba(0,0,0,0.05);
    }
    
    .speaker-notes.show {
      display: block;
      opacity: 1;
    }
    
    .speaker-notes h4 {
      color: var(--primary);
      font-size: 16px;
      margin-bottom: 14px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    
    .speaker-notes h4::before {
      content: '';
      width: 4px;
      height: 20px;
      background: linear-gradient(180deg, var(--primary) 0%, var(--accent) 100%);
      border-radius: 2px;
    }
    
    .speaker-notes p {
      color: #374151;
      font-size: 14px;
      line-height: 2;
      white-space: pre-wrap;
    }
    
    .notes-toggle {
      position: fixed;
      bottom: 120px;
      right: 30px;
      padding: 12px 24px;
      background-color: rgba(255,255,255,0.15);
      color: white;
      border: 1px solid rgba(255,255,255,0.2);
      border-radius: 28px;
      font-size: 13px;
      cursor: pointer;
      z-index: 100;
      transition: all 0.2s ease;
      backdrop-filter: blur(12px);
    }
    
    .notes-toggle:hover {
      background-color: rgba(255,255,255,0.25);
    }
    
    @media (max-width: 600px) {
      .notes-toggle {
        right: 10px;
        bottom: 80px;
        padding: 10px 20px;
        font-size: 12px;
      }
    }
    
    .progress-bar {
      position: fixed;
      top: 0;
      left: 0;
      height: 4px;
      background: linear-gradient(90deg, var(--primary), var(--accent));
      z-index: 100;
      transition: width 0.3s ease;
      box-shadow: 0 0 12px rgba(59, 130, 246, 0.6);
    }
    
    .presentation-info {
      position: fixed;
      top: 20px;
      left: 20px;
      color: rgba(255,255,255,0.7);
      font-size: 12px;
      z-index: 100;
      padding: 12px 20px;
      border-radius: 12px;
      background-color: rgba(0,0,0,0.5);
      backdrop-filter: blur(12px);
      display: none;
    }
    
    .presentation-info.show {
      display: block;
    }
    
    .thumbnail-nav {
      position: fixed;
      bottom: 120px;
      left: 20px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      overflow-y: auto;
      max-height: 400px;
      padding: 12px;
      border-radius: 16px;
      background-color: rgba(0,0,0,0.6);
      backdrop-filter: blur(12px);
      z-index: 90;
      scrollbar-width: thin;
      scrollbar-color: rgba(255,255,255,0.2) transparent;
    }
    
    .thumbnail-nav::-webkit-scrollbar {
      width: 6px;
    }
    
    .thumbnail-nav::-webkit-scrollbar-track {
      background: transparent;
    }
    
    .thumbnail-nav::-webkit-scrollbar-thumb {
      background-color: rgba(255,255,255,0.2);
      border-radius: 3px;
    }
    
    .thumbnail-item {
      width: 80px;
      height: 50px;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.25s ease;
      border: 2px solid transparent;
      flex-shrink: 0;
      overflow: hidden;
      position: relative;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    
    .thumbnail-item:hover {
      border-color: rgba(255,255,255,0.4);
      transform: scale(1.08);
      box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }
    
    .thumbnail-item.active {
      border-color: var(--primary);
      box-shadow: 0 0 15px rgba(59, 130, 246, 0.5);
    }
    
    .thumbnail-item img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    
    .thumbnail-item .slide-number {
      position: absolute;
      bottom: 2px;
      right: 4px;
      background-color: rgba(0,0,0,0.6);
      color: white;
      font-size: 9px;
      padding: 1px 5px;
      border-radius: 4px;
    }
    
    @media (max-width: 768px) {
      .thumbnail-nav {
        display: none;
      }
    }
    
    .timer {
      position: fixed;
      top: 20px;
      right: 30px;
      color: rgba(255,255,255,0.8);
      font-size: 14px;
      font-weight: 500;
      z-index: 100;
      padding: 10px 20px;
      border-radius: 12px;
      background-color: rgba(0,0,0,0.5);
      backdrop-filter: blur(12px);
      font-variant-numeric: tabular-nums;
    }
    
    .quality-indicator {
      position: fixed;
      top: 20px;
      right: 140px;
      color: rgba(255,255,255,0.6);
      font-size: 11px;
      z-index: 100;
      padding: 6px 12px;
      border-radius: 8px;
      background-color: rgba(0,0,0,0.4);
      backdrop-filter: blur(8px);
    }
    
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    
    @keyframes slideInLeft {
      from { opacity: 0; transform: translateX(-30px); }
      to { opacity: 1; transform: translateX(0); }
    }
    
    @keyframes slideInRight {
      from { opacity: 0; transform: translateX(30px); }
      to { opacity: 1; transform: translateX(0); }
    }
    
    @keyframes slideInTop {
      from { opacity: 0; transform: translateY(-30px); }
      to { opacity: 1; transform: translateY(0); }
    }
    
    @keyframes slideInBottom {
      from { opacity: 0; transform: translateY(30px); }
      to { opacity: 1; transform: translateY(0); }
    }
    
    @keyframes zoomIn {
      from { opacity: 0; transform: scale(0.85); }
      to { opacity: 1; transform: scale(1); }
    }
    
    @keyframes rotateIn {
      from { opacity: 0; transform: rotate(-15deg) scale(0.9); }
      to { opacity: 1; transform: rotate(0) scale(1); }
    }
    
    @keyframes slideFadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    
    @keyframes slideInFromRight {
      from { opacity: 0; transform: translateX(100%); }
      to { opacity: 1; transform: translateX(0); }
    }
    
    @keyframes slideInFromLeft {
      from { opacity: 0; transform: translateX(-100%); }
      to { opacity: 1; transform: translateX(0); }
    }
    
    @keyframes slideInFromBottom {
      from { opacity: 0; transform: translateY(100%); }
      to { opacity: 1; transform: translateY(0); }
    }
    
    @keyframes slideInFromTop {
      from { opacity: 0; transform: translateY(-100%); }
      to { opacity: 1; transform: translateY(0); }
    }
    
    @keyframes zoomOut {
      from { opacity: 0; transform: scale(1.15); }
      to { opacity: 1; transform: scale(1); }
    }
    
    @keyframes flipIn {
      from { opacity: 0; transform: perspective(400px) rotateY(90deg); }
      to { opacity: 1; transform: perspective(400px) rotateY(0); }
    }
    
    @media print {
      body {
        background-color: white;
        display: block;
      }
      
      .presentation-container {
        width: 100%;
        height: auto;
        box-shadow: none;
        border-radius: 0;
        transform: none;
        page-break-inside: avoid;
      }
      
      .slide {
        position: relative;
        opacity: 1;
        visibility: visible;
        width: 100%;
        min-height: 500px;
        page-break-after: always;
        border: 1px solid #e5e7eb;
      }
      
      .slide:last-child {
        page-break-after: avoid;
      }
      
      .controls, .slide-indicator, .progress-bar, .speaker-notes, .notes-toggle, .thumbnail-nav, .presentation-info, .timer, .quality-indicator {
        display: none !important;
      }
      
      @page {
        size: A4 landscape;
        margin: 5mm;
      }
    }
  </style>
</head>
<body>
  <div class="progress-bar" id="progressBar" style="width: ${((presentation.currentSlideIndex + 1) / presentation.slides.length) * 100}%;"></div>
  
  <div class="presentation-info" id="presentationInfo">
    <div>${presentation.title || '演示文稿'}</div>
    <div>${presentation.slides.length} 页幻灯片</div>
  </div>
  
  <div class="timer" id="timer">00:00</div>
  
  <div class="quality-indicator">高清演示</div>
  
  <div class="presentation-container">
    ${presentation.slides.map((slide, index) => renderSlide(slide, index, presentation.slides.length, presentation.master)).join('\n')}
  </div>
  
  <div class="thumbnail-nav" id="thumbnailNav">
    ${presentation.slides.map((slide, index) => `
      <div class="thumbnail-item ${index === presentation.currentSlideIndex ? 'active' : ''}" onclick="goToSlide(${index})" title="幻灯片 ${index + 1}">
        <img src="${thumbnailsData[index]}" alt="幻灯片 ${index + 1}" />
        <span class="slide-number">${index + 1}</span>
      </div>
    `).join('\n')}
  </div>
  
  <div class="speaker-notes" id="speakerNotes">
    <h4>演讲者备注</h4>
    <p id="notesContent"></p>
  </div>
  
  <button class="notes-toggle" onclick="toggleNotes()">显示备注</button>
  
  <div class="controls">
    <button class="control-btn" onclick="goToSlide(0)" title="第一张">⏮</button>
    <button class="control-btn" onclick="goToPrev()" title="上一张">←</button>
    <button class="control-btn play-btn" onclick="togglePlay()" id="playBtn" title="播放/暂停">▶</button>
    <button class="control-btn" onclick="goToNext()" title="下一张">→</button>
    <button class="control-btn" onclick="goToSlide(${presentation.slides.length - 1})" title="最后一张">⏭</button>
    <button class="control-btn" onclick="toggleFullscreen()" title="全屏">⛶</button>
    <button class="control-btn" onclick="toggleInfo()" title="信息">ℹ</button>
  </div>
  
  <div class="slide-indicator" id="slideIndicator">
    ${presentation.currentSlideIndex + 1} / ${presentation.slides.length}
  </div>

  <script>
    let currentSlide = ${presentation.currentSlideIndex};
    const totalSlides = ${presentation.slides.length};
    let isPlaying = false;
    let playInterval = null;
    let showNotes = false;
    let showInfo = false;
    let startTime = Date.now();
    let timerInterval = null;
    let charts = {};
    
    const slides = document.querySelectorAll('.slide');
    const slideIndicator = document.getElementById('slideIndicator');
    const playBtn = document.getElementById('playBtn');
    const progressBar = document.getElementById('progressBar');
    const speakerNotes = document.getElementById('speakerNotes');
    const notesContent = document.getElementById('notesContent');
    const presentationInfo = document.getElementById('presentationInfo');
    const thumbnailItems = document.querySelectorAll('.thumbnail-item');
    const timer = document.getElementById('timer');
    
    const notesData = ${JSON.stringify(presentation.slides.map(s => s.notes || ''))};
    const chartConfigs = ${JSON.stringify(presentation.slides.map(s => 
      s.components.filter(c => c.type === 'chart').map(c => ({ id: c.id, data: c.data }))
    ))};
    
    function updateTimer() {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      const minutes = String(Math.floor(elapsed / 60)).padStart(2, '0');
      const seconds = String(elapsed % 60).padStart(2, '0');
      timer.textContent = \`\${minutes}:\${seconds}\`;
    }
    
    timerInterval = setInterval(updateTimer, 1000);
    
    function initCharts() {
      slides.forEach((slide, slideIndex) => {
        const chartElements = slide.querySelectorAll('[id^="chart-"]');
        chartElements.forEach((chartDom) => {
          const chartId = chartDom.id;
          const chartConfig = chartConfigs[slideIndex]?.find(c => c.id === chartId);
          
          if (chartConfig) {
            const chart = echarts.init(chartDom);
            charts[chartId] = chart;
            
            const colors = {
              primary: '${theme.primary}',
              secondary: '${theme.secondary}',
              accent: '${theme.accent}',
              text: '${theme.text}',
              textLight: '${theme.textLight}',
              textFaint: '${theme.textFaint}',
              danger: '${theme.danger}',
            };
            
            chart.setOption(${getEChartsOption({}, theme)});
            chart.setOption(JSON.parse(decodeURIComponent('${encodeURIComponent(JSON.stringify({}))}')));
          }
        });
      });
    }
    
    function renderSlideCharts(slideIndex) {
      const slide = slides[slideIndex];
      if (!slide) return;
      
      const chartElements = slide.querySelectorAll('[id^="chart-"]');
      chartElements.forEach((chartDom) => {
        const chartId = chartDom.id;
        
        if (!charts[chartId]) {
          const chart = echarts.init(chartDom);
          charts[chartId] = chart;
        }
        
        const chartConfig = chartConfigs[slideIndex]?.find(c => c.id === chartId);
        if (chartConfig) {
          const colors = {
            primary: '${theme.primary}',
            secondary: '${theme.secondary}',
            accent: '${theme.accent}',
            text: '${theme.text}',
            textLight: '${theme.textLight}',
            textFaint: '${theme.textFaint}',
            danger: '${theme.danger}',
          };
          
          let option = {};
          const chartType = chartConfig.data.type || 'bar';
          const labels = chartConfig.data.labels || [];
          const datasets = chartConfig.data.datasets || [];
          
          switch (chartType) {
            case 'bar':
            case 'bar-horizontal':
              option = {
                tooltip: {
                  trigger: 'axis',
                  backgroundColor: 'rgba(255,255,255,0.98)',
                  borderColor: '#e5e7eb',
                  borderWidth: 1,
                  padding: [12, 16],
                  textStyle: { color: '#374151', fontSize: 13 },
                  axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(0,0,0,0.05)' } }
                },
                legend: { show: datasets.length > 1, bottom: 0, textStyle: { color: '#6b7280', fontSize: 12 }, itemGap: 20 },
                grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
                xAxis: chartType === 'bar-horizontal' ? {
                  type: 'value', axisLine: { show: false }, splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
                  axisLabel: { color: '#6b7280', fontSize: 11 }, axisTick: { show: false }
                } : {
                  type: 'category', data: labels, axisLine: { lineStyle: { color: '#e5e7eb' } },
                  axisLabel: { color: '#6b7280', fontSize: 11, rotate: labels.length > 6 ? 30 : 0 }, axisTick: { show: false }
                },
                yAxis: chartType === 'bar-horizontal' ? {
                  type: 'category', data: labels, axisLine: { lineStyle: { color: '#e5e7eb' } },
                  axisLabel: { color: '#6b7280', fontSize: 11 }, axisTick: { show: false }
                } : {
                  type: 'value', axisLine: { show: false }, splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
                  axisLabel: { color: '#6b7280', fontSize: 11 }, axisTick: { show: false }
                },
                series: datasets.map((ds, idx) => ({
                  type: 'bar',
                  name: ds.name || '',
                  data: ds.data || [],
                  barGap: idx > 0 ? '10%' : '0%',
                  barWidth: datasets.length > 1 ? '35%' : '50%',
                  itemStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, chartType === 'bar-horizontal' ? 1 : 0, chartType === 'bar-horizontal' ? 0 : 1, [
                      { offset: 0, color: ds.color || (idx === 0 ? colors.primary : colors.accent) },
                      { offset: 1, color: (ds.color || (idx === 0 ? colors.primary : colors.accent)) + '88' }
                    ]),
                    borderRadius: chartType === 'bar-horizontal' ? [0, 6, 6, 0] : [6, 6, 0, 0],
                    shadowColor: 'rgba(0,0,0,0.1)',
                    shadowBlur: 8,
                    shadowOffsetY: 4
                  },
                  animationDuration: 1500,
                  animationEasing: 'elasticOut'
                }))
              };
              break;
            case 'pie':
              option = {
                tooltip: { trigger: 'item', backgroundColor: 'rgba(255,255,255,0.98)', borderColor: '#e5e7eb', borderWidth: 1, padding: [12, 16], textStyle: { color: '#374151', fontSize: 13 }, formatter: '{b}: {c} ({d}%)' },
                legend: { orient: 'vertical', right: '5%', top: 'center', textStyle: { color: '#6b7280', fontSize: 12 }, itemGap: 12 },
                series: [{
                  type: 'pie',
                  radius: ['40%', '70%'],
                  center: ['40%', '50%'],
                  itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
                  label: { show: true, position: 'outside', fontSize: 11, color: '#374151', formatter: '{b}: {d}%' },
                  labelLine: { show: true, length: 15, length2: 10 },
                  animationType: 'scale',
                  animationEasing: 'elasticOut',
                  animationDelay: function(idx) { return idx * 100; },
                  data: labels.map((label, idx) => ({
                    value: datasets[0]?.data?.[idx] || 0,
                    name: label,
                    itemStyle: { color: typeof datasets[0]?.color === 'string' ? datasets[0].color : 'hsl(' + ((idx * 60) % 360) + ', 70%, 55%)' }
                  }))
                }]
              };
              break;
            case 'line':
            case 'area':
              option = {
                tooltip: {
                  trigger: 'axis',
                  backgroundColor: 'rgba(255,255,255,0.98)',
                  borderColor: '#e5e7eb',
                  borderWidth: 1,
                  padding: [12, 16],
                  textStyle: { color: '#374151', fontSize: 13 },
                  axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(0,0,0,0.05)' } }
                },
                legend: { show: datasets.length > 1, bottom: 0, textStyle: { color: '#6b7280', fontSize: 12 }, itemGap: 20 },
                grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
                xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: '#e5e7eb' } }, axisLabel: { color: '#6b7280', fontSize: 11 }, axisTick: { show: false } },
                yAxis: { type: 'value', axisLine: { show: false }, splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } }, axisLabel: { color: '#6b7280', fontSize: 11 }, axisTick: { show: false } },
                series: datasets.map((ds, idx) => ({
                  type: 'line',
                  name: ds.name || '',
                  data: ds.data || [],
                  smooth: true,
                  symbol: chartType === 'area' ? 'none' : 'circle',
                  symbolSize: 8,
                  lineStyle: { color: ds.color || (idx === 0 ? colors.primary : colors.accent), width: 3 },
                  itemStyle: { color: ds.color || (idx === 0 ? colors.primary : colors.accent), borderColor: '#fff', borderWidth: 2 },
                  areaStyle: chartType === 'area' ? {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                      { offset: 0, color: (ds.color || (idx === 0 ? colors.primary : colors.accent)) + '60' },
                      { offset: 1, color: (ds.color || (idx === 0 ? colors.primary : colors.accent)) + '05' }
                    ])
                  } : undefined,
                  animationDuration: 2000,
                  animationEasing: 'cubicInOut'
                }))
              };
              break;
            case 'radar':
              option = {
                tooltip: { trigger: 'item', backgroundColor: 'rgba(255,255,255,0.98)', borderColor: '#e5e7eb', borderWidth: 1, padding: [12, 16], textStyle: { color: '#374151', fontSize: 13 } },
                radar: {
                  indicator: labels.map(label => ({ name: label, max: 100 })),
                  shape: 'polygon',
                  axisName: { color: '#6b7280', fontSize: 11 },
                  splitLine: { lineStyle: { color: '#e5e7eb' } },
                  splitArea: { show: true, areaStyle: { color: ['#f9fafb', '#fff'] } },
                  axisLine: { lineStyle: { color: '#e5e7eb' } }
                },
                series: [{
                  type: 'radar',
                  data: datasets.map((ds, idx) => ({
                    value: ds.data || [],
                    name: ds.name || '',
                    areaStyle: { opacity: 0.3 },
                    lineStyle: { width: 2, color: ds.color || (idx === 0 ? colors.primary : colors.accent) },
                    itemStyle: { color: ds.color || (idx === 0 ? colors.primary : colors.accent) },
                    symbol: 'circle',
                    symbolSize: 6
                  })),
                  animationDuration: 2000,
                  animationEasing: 'cubicInOut'
                }]
              };
              break;
            case 'gauge':
              option = {
                series: [{
                  type: 'gauge',
                  startAngle: 200,
                  endAngle: -20,
                  pointer: { itemStyle: { color: colors.danger }, width: 6 },
                  progress: { show: true, roundCap: true, itemStyle: { color: datasets[0]?.color || colors.primary } },
                  axisLine: { lineWidth: 16, color: [[0.3, '#e5e7eb'], [0.7, '#d1d5db'], [1, '#e5e7eb']] },
                  splitLine: { show: false },
                  axisTick: { show: false },
                  axisLabel: { show: false },
                  detail: { fontSize: 32, fontWeight: 'bold', formatter: '{value}%', offsetCenter: [0, '30%'], color: colors.text },
                  data: [{ value: datasets[0]?.data?.[0] || 0, name: chartConfig.data.title || '', title: { fontSize: 14, color: '#6b7280', offsetCenter: [0, '-10%'] } }],
                  animationDuration: 2000,
                  animationEasing: 'elasticOut'
                }]
              };
              break;
            case 'funnel':
              option = {
                tooltip: { trigger: 'item', backgroundColor: 'rgba(255,255,255,0.98)', borderColor: '#e5e7eb', borderWidth: 1, padding: [12, 16], textStyle: { color: '#374151', fontSize: 13 }, formatter: '{b}: {c}' },
                series: [{
                  type: 'funnel',
                  left: '10%', top: 60, bottom: 60, width: '80%',
                  min: 0, max: 100, gap: 4,
                  label: { show: true, position: 'inside', fontSize: 12, fontWeight: 'bold', color: '#fff' },
                  itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
                  emphasis: { label: { fontSize: 14 } },
                  data: labels.map((label, idx) => ({
                    value: datasets[0]?.data?.[idx] || (100 - idx * 15),
                    name: label,
                    itemStyle: { color: typeof datasets[0]?.color === 'string' ? datasets[0].color : 'hsl(' + (200 - idx * 30) + ', 70%, 55%)' }
                  })),
                  animationDuration: 1500,
                  animationEasing: 'elasticOut',
                  animationDelay: function(idx) { return idx * 150; }
                }]
              };
              break;
            case 'scatter':
              option = {
                tooltip: { trigger: 'item', backgroundColor: 'rgba(255,255,255,0.98)', borderColor: '#e5e7eb', borderWidth: 1, padding: [12, 16], textStyle: { color: '#374151', fontSize: 13 } },
                legend: { show: datasets.length > 1, bottom: 0, textStyle: { color: '#6b7280', fontSize: 12 }, itemGap: 20 },
                grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
                xAxis: { type: 'value', axisLine: { show: false }, splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } }, axisLabel: { color: '#6b7280', fontSize: 11 }, axisTick: { show: false } },
                yAxis: { type: 'value', axisLine: { show: false }, splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } }, axisLabel: { color: '#6b7280', fontSize: 11 }, axisTick: { show: false } },
                series: datasets.map((ds, idx) => ({
                  type: 'scatter',
                  name: ds.name || '',
                  data: ds.data || [],
                  symbolSize: 14,
                  itemStyle: { color: ds.color || (idx === 0 ? colors.primary : colors.accent), shadowBlur: 12, shadowColor: 'rgba(0,0,0,0.2)', borderColor: '#fff', borderWidth: 2 },
                  emphasis: { itemStyle: { shadowBlur: 20, shadowColor: 'rgba(0,0,0,0.3)', symbolSize: 18 } },
                  animationDuration: 2000,
                  animationEasing: 'elasticOut'
                }))
              };
              break;
            default:
              option = {};
          }
          
          charts[chartId].setOption(option);
        }
      });
    }
    
    function showSlide(index) {
      slides.forEach((slide, idx) => {
        slide.classList.remove('active');
        slide.classList.remove('transition-fade', 'transition-slide-left', 'transition-slide-right', 'transition-slide-up', 'transition-slide-down', 'transition-zoom-in', 'transition-zoom-out', 'transition-cube', 'transition-flip', 'transition-rotate');
        
        if (idx === index) {
          const transition = slide.getAttribute('data-transition') || 'fade';
          slide.classList.add('active');
          slide.classList.add('transition-' + transition);
        }
      });
      
      thumbnailItems.forEach((item, idx) => {
        item.classList.toggle('active', idx === index);
      });
      
      currentSlide = index;
      slideIndicator.textContent = \`\${currentSlide + 1} / \${totalSlides}\`;
      progressBar.style.width = \`\${((currentSlide + 1) / totalSlides) * 100}%\`;
      
      setTimeout(() => renderSlideCharts(index), 100);
      
      if (showNotes) {
        notesContent.textContent = notesData[currentSlide] || '暂无备注';
      }
    }
    
    showSlide(${presentation.currentSlideIndex});
    
    function goToPrev() {
      stopPlay();
      if (currentSlide > 0) {
        showSlide(currentSlide - 1);
      }
    }
    
    function goToNext() {
      stopPlay();
      if (currentSlide < totalSlides - 1) {
        showSlide(currentSlide + 1);
      }
    }
    
    function goToSlide(index) {
      stopPlay();
      if (index >= 0 && index < totalSlides) {
        showSlide(index);
      }
    }
    
    function togglePlay() {
      if (isPlaying) {
        stopPlay();
      } else {
        startPlay();
      }
    }
    
    function startPlay() {
      isPlaying = true;
      playBtn.textContent = '⏸';
      playInterval = setInterval(() => {
        if (currentSlide < totalSlides - 1) {
          showSlide(currentSlide + 1);
        } else {
          showSlide(0);
        }
      }, 4000);
    }
    
    function stopPlay() {
      isPlaying = false;
      playBtn.textContent = '▶';
      if (playInterval) {
        clearInterval(playInterval);
        playInterval = null;
      }
    }
    
    function toggleFullscreen() {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(err => console.log('全屏失败:', err));
      } else {
        document.exitFullscreen().catch(err => console.log('退出全屏失败:', err));
      }
    }
    
    function toggleNotes() {
      showNotes = !showNotes;
      if (showNotes) {
        speakerNotes.classList.add('show');
        notesContent.textContent = notesData[currentSlide] || '暂无备注';
        event.target.textContent = '隐藏备注';
      } else {
        speakerNotes.classList.remove('show');
        event.target.textContent = '显示备注';
      }
    }
    
    function toggleInfo() {
      showInfo = !showInfo;
      presentationInfo.classList.toggle('show', showInfo);
    }
    
    document.addEventListener('keydown', (e) => {
      switch (e.key) {
        case 'ArrowLeft':
          e.preventDefault();
          goToPrev();
          break;
        case 'ArrowRight':
          e.preventDefault();
          goToNext();
          break;
        case ' ':
          e.preventDefault();
          togglePlay();
          break;
        case 'Escape':
          e.preventDefault();
          if (document.fullscreenElement) {
            document.exitFullscreen();
          }
          break;
        case 'Home':
          e.preventDefault();
          goToSlide(0);
          break;
        case 'End':
          e.preventDefault();
          goToSlide(totalSlides - 1);
          break;
        case 'N':
        case 'n':
          e.preventDefault();
          goToNext();
          break;
        case 'P':
        case 'p':
          e.preventDefault();
          goToPrev();
          break;
        case 'F':
        case 'f':
          e.preventDefault();
          toggleFullscreen();
          break;
        case 'I':
        case 'i':
          e.preventDefault();
          toggleInfo();
          break;
        case 'T':
        case 't':
          e.preventDefault();
          toggleNotes();
          break;
      }
    });
    
    document.addEventListener('touchstart', (e) => {
      const touchStartX = e.touches[0].clientX;
      const touchStartY = e.touches[0].clientY;
      
      document.addEventListener('touchend', (endEvent) => {
        const touchEndX = endEvent.changedTouches[0].clientX;
        const touchEndY = endEvent.changedTouches[0].clientY;
        const diffX = touchEndX - touchStartX;
        const diffY = touchEndY - touchStartY;
        
        if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 50) {
          if (diffX > 0) {
            goToPrev();
          } else {
            goToNext();
          }
        }
      }, { once: true });
    });
    
    window.addEventListener('resize', () => {
      Object.values(charts).forEach(chart => {
        if (chart && typeof chart.resize === 'function') {
          chart.resize();
        }
      });
    });
    
    window.addEventListener('beforeunload', () => {
      if (timerInterval) clearInterval(timerInterval);
      Object.values(charts).forEach(chart => {
        if (chart && typeof chart.dispose === 'function') {
          chart.dispose();
        }
      });
    });
  </script>
</body>
</html>
  `;

  return html;
};

export const downloadHTML = (presentation: Presentation): void => {
  const html = exportToHTML(presentation);
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${presentation.title || 'presentation'}.html`;
  a.click();
  URL.revokeObjectURL(url);
};

export default downloadHTML;