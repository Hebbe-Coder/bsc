import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface ChartComponentProps {
  data: any;
  width: number;
  height: number;
}

const ChartComponent = ({ data, width, height }: ChartComponentProps) => {
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!chartRef.current || !data) return;

    const chart = echarts.init(chartRef.current);
    let option: echarts.EChartsOption;

    const getColor = (index: number, count: number) => {
      const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
      return colors[index % colors.length];
    };

    switch (data.type) {
      case 'pie':
        option = {
          tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#e5e7eb',
            borderWidth: 1,
            textStyle: { color: '#374151' },
            padding: [12, 16],
            extraCssText: 'border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);',
            formatter: '{b}: {c} ({d}%)',
          },
          legend: {
            orient: 'vertical',
            right: '5%',
            top: 'center',
            textStyle: { color: '#6b7280', fontSize: 12 },
            itemGap: 12,
          },
          series: [
            {
              name: data.title || '',
              type: 'pie',
              radius: ['40%', '70%'],
              center: ['40%', '50%'],
              avoidLabelOverlap: false,
              itemStyle: {
                borderRadius: 8,
                borderColor: '#fff',
                borderWidth: 2,
              },
              label: { show: false, position: 'center' },
              emphasis: {
                label: { show: true, fontSize: 20, fontWeight: 'bold' },
                itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.3)' },
              },
              labelLine: { show: false },
              data: (data.datasets?.[0]?.data || []).map((val: number, idx: number) => ({
                value: val,
                name: data.labels?.[idx] || '',
                itemStyle: { color: data.datasets?.[0]?.color || getColor(idx, data.labels?.length || 1) },
              })),
              animationDuration: 1500,
              animationEasing: 'elasticOut',
            },
          ],
        };
        break;

      case 'radar':
        option = {
          tooltip: {
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#e5e7eb',
            borderWidth: 1,
            textStyle: { color: '#374151' },
          },
          legend: {
            data: data.datasets?.map((d: any) => d.name) || [],
            bottom: 0,
            textStyle: { color: '#6b7280', fontSize: 12 },
            itemGap: 20,
          },
          radar: {
            indicator: (data.labels || []).map((label: string) => ({
              name: label,
              max: data.maxValue || 100,
            })),
            shape: 'polygon',
            splitNumber: 5,
            axisName: { color: '#6b7280', fontSize: 11 },
            splitLine: { lineStyle: { color: '#e5e7eb' } },
            splitArea: { show: true, areaStyle: { color: ['#f9fafb', '#fff'] } },
            axisLine: { lineStyle: { color: '#e5e7eb' } },
          },
          series: [{
            type: 'radar',
            data: data.datasets?.map((dataset: any, idx: number) => ({
              value: dataset.data,
              name: dataset.name,
              areaStyle: { opacity: 0.2 },
              lineStyle: { width: 2 },
              itemStyle: { color: dataset.color || getColor(idx, data.datasets?.length || 1) },
            })),
            animationDuration: 1500,
          }],
        };
        break;

      case 'line':
        option = {
          tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#e5e7eb',
            borderWidth: 1,
            textStyle: { color: '#374151' },
            padding: [12, 16],
            extraCssText: 'border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);',
          },
          legend: {
            data: data.datasets?.map((d: any) => d.name) || [],
            bottom: 0,
            textStyle: { color: '#6b7280', fontSize: 12 },
            itemGap: 20,
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '15%',
            top: '10%',
            containLabel: true,
          },
          xAxis: {
            type: 'category',
            data: data.labels || [],
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#6b7280', fontSize: 11 },
            axisTick: { show: false },
          },
          yAxis: {
            type: 'value',
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
            axisLabel: { color: '#6b7280', fontSize: 11 },
          },
          series: data.datasets?.map((dataset: any, idx: number) => ({
            name: dataset.name,
            type: 'line',
            smooth: true,
            data: dataset.data,
            lineStyle: { color: dataset.color || getColor(idx, data.datasets?.length || 1), width: 3 },
            itemStyle: { color: dataset.color || getColor(idx, data.datasets?.length || 1), borderRadius: 4 },
            areaStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: `${dataset.color || getColor(idx, data.datasets?.length || 1)}40` },
                { offset: 1, color: `${dataset.color || getColor(idx, data.datasets?.length || 1)}05` },
              ]),
            },
            animationDuration: 1500,
            animationEasing: 'elasticOut',
          })),
        };
        break;

      case 'gauge':
        option = {
          series: [{
            type: 'gauge',
            startAngle: 200,
            endAngle: -20,
            pointer: { itemStyle: { color: '#ef4444' } },
            progress: {
              show: true,
              overlap: false,
              roundCap: true,
              clip: false,
              itemStyle: { color: data.datasets?.[0]?.color || '#3b82f6' },
            },
            axisLine: {
              lineStyle: {
                width: 12,
                color: [[1, '#e5e7eb']],
              },
            },
            splitLine: { show: false },
            axisTick: { show: false },
            axisLabel: { show: false },
            data: [{
              value: data.datasets?.[0]?.data?.[0] || 0,
              name: data.title || '',
              title: {
                show: true,
                fontSize: 14,
                color: '#6b7280',
                offsetCenter: [0, '-20%'],
              },
              detail: {
                fontSize: 28,
                fontWeight: 'bold',
                offsetCenter: [0, '30%'],
                formatter: '{value}%',
              },
            }],
          }],
        };
        break;

      case 'funnel':
        option = {
          tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#e5e7eb',
            borderWidth: 1,
            textStyle: { color: '#374151' },
          },
          legend: {
            show: false,
          },
          series: [{
            type: 'funnel',
            left: '10%',
            top: 60,
            bottom: 60,
            width: '80%',
            min: 0,
            max: 100,
            minSize: '0%',
            maxSize: '100%',
            sort: 'descending',
            gap: 2,
            label: {
              show: true,
              position: 'inside',
              fontSize: 12,
              fontWeight: 'bold',
              color: '#fff',
            },
            labelLine: { show: false },
            itemStyle: {
              borderRadius: 8,
              borderColor: '#fff',
              borderWidth: 2,
            },
            data: (data.labels || []).map((label: string, idx: number) => ({
              value: data.datasets?.[0]?.data?.[idx] || (100 - idx * 15),
              name: label,
              itemStyle: {
                color: data.datasets?.[0]?.color || `hsl(${200 - idx * 30}, 70%, 55%)`,
              },
            })),
            animationDuration: 1500,
          }],
        };
        break;

      case 'gantt':
        option = {
          tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#e5e7eb',
            borderWidth: 1,
            textStyle: { color: '#374151' },
          },
          grid: {
            left: '15%',
            right: '5%',
            top: '10%',
            bottom: '15%',
          },
          xAxis: {
            type: 'value',
            splitLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#6b7280', fontSize: 11 },
          },
          yAxis: {
            type: 'category',
            data: data.labels || [],
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#374151', fontSize: 12 },
          },
          series: [{
            type: 'bar',
            data: (data.datasets?.[0]?.data || []).map((val: number, idx: number) => ({
              value: val,
              itemStyle: {
                color: data.datasets?.[0]?.color || getColor(idx, data.labels?.length || 1),
                borderRadius: [4, 4, 0, 0],
              },
            })),
            animationDuration: 1000,
          }],
        };
        break;

      case 'scatter':
        option = {
          tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#e5e7eb',
            borderWidth: 1,
            textStyle: { color: '#374151' },
          },
          legend: {
            data: data.datasets?.map((d: any) => d.name) || [],
            bottom: 0,
            textStyle: { color: '#6b7280', fontSize: 12 },
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '15%',
            top: '10%',
            containLabel: true,
          },
          xAxis: {
            type: 'value',
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#6b7280', fontSize: 11 },
            splitLine: { lineStyle: { color: '#f3f4f6' } },
          },
          yAxis: {
            type: 'value',
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#6b7280', fontSize: 11 },
            splitLine: { lineStyle: { color: '#f3f4f6' } },
          },
          series: data.datasets?.map((dataset: any, idx: number) => ({
            name: dataset.name,
            type: 'scatter',
            data: dataset.data,
            symbolSize: 12,
            itemStyle: {
              color: dataset.color || getColor(idx, data.datasets?.length || 1),
              borderWidth: 2,
              borderColor: '#fff',
            },
            animationDuration: 1000,
          })),
        };
        break;

      case 'area':
        option = {
          tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#e5e7eb',
            borderWidth: 1,
            textStyle: { color: '#374151' },
            padding: [12, 16],
            extraCssText: 'border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);',
          },
          legend: {
            data: data.datasets?.map((d: any) => d.name) || [],
            bottom: 0,
            textStyle: { color: '#6b7280', fontSize: 12 },
            itemGap: 20,
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '15%',
            top: '10%',
            containLabel: true,
          },
          xAxis: {
            type: 'category',
            data: data.labels || [],
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#6b7280', fontSize: 11 },
            axisTick: { show: false },
          },
          yAxis: {
            type: 'value',
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
            axisLabel: { color: '#6b7280', fontSize: 11 },
          },
          series: data.datasets?.map((dataset: any, idx: number) => ({
            name: dataset.name,
            type: 'line',
            smooth: true,
            data: dataset.data,
            lineStyle: { color: dataset.color || getColor(idx, data.datasets?.length || 1), width: 3 },
            itemStyle: { color: dataset.color || getColor(idx, data.datasets?.length || 1) },
            areaStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: `${dataset.color || getColor(idx, data.datasets?.length || 1)}80` },
                { offset: 1, color: `${dataset.color || getColor(idx, data.datasets?.length || 1)}10` },
              ]),
            },
            animationDuration: 1500,
            animationEasing: 'elasticOut',
          })),
        };
        break;

      case 'bar-horizontal':
        option = {
          tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#e5e7eb',
            borderWidth: 1,
            textStyle: { color: '#374151' },
            padding: [12, 16],
            extraCssText: 'border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);',
          },
          legend: {
            data: data.datasets?.map((d: any) => d.name) || [],
            top: 0,
            textStyle: { color: '#6b7280', fontSize: 12 },
            itemGap: 20,
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '15%',
            top: '15%',
            containLabel: true,
          },
          xAxis: {
            type: 'value',
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
            axisLabel: { color: '#6b7280', fontSize: 11 },
          },
          yAxis: {
            type: 'category',
            data: data.labels || [],
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#374151', fontSize: 12 },
            axisTick: { show: false },
          },
          series: data.datasets?.map((dataset: any, idx: number) => ({
            name: dataset.name,
            type: 'bar',
            data: dataset.data,
            barWidth: '50%',
            itemStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: dataset.color || getColor(idx, data.datasets?.length || 1) },
                { offset: 1, color: `${dataset.color || getColor(idx, data.datasets?.length || 1)}80` },
              ]),
              borderRadius: [0, 8, 8, 0],
            },
            animationDuration: 1000,
          })),
        };
        break;

      case 'polar':
        option = {
          tooltip: {
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#e5e7eb',
            borderWidth: 1,
            textStyle: { color: '#374151' },
          },
          legend: {
            data: data.datasets?.map((d: any) => d.name) || [],
            bottom: 0,
            textStyle: { color: '#6b7280', fontSize: 12 },
          },
          polar: {
            radius: ['30%', '70%'],
          },
          angleAxis: {
            type: 'category',
            data: data.labels || [],
            boundaryGap: false,
            startAngle: 90,
            axisLine: { show: false },
            axisLabel: { color: '#6b7280', fontSize: 11 },
          },
          radiusAxis: {
            type: 'value',
            axisLine: { show: false },
            axisLabel: { show: false },
            splitLine: { lineStyle: { color: '#e5e7eb' } },
          },
          series: data.datasets?.map((dataset: any, idx: number) => ({
            name: dataset.name,
            type: 'line',
            coordinateSystem: 'polar',
            data: dataset.data,
            lineStyle: { color: dataset.color || getColor(idx, data.datasets?.length || 1), width: 2 },
            areaStyle: { color: `${dataset.color || getColor(idx, data.datasets?.length || 1)}30` },
            animationDuration: 1500,
          })),
        };
        break;

      default:
        option = {
          tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#e5e7eb',
            borderWidth: 1,
            textStyle: { color: '#374151' },
            padding: [12, 16],
            extraCssText: 'border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);',
          },
          legend: {
            data: data.datasets?.map((d: any) => d.name) || [],
            bottom: 0,
            textStyle: { color: '#6b7280', fontSize: 12 },
            itemGap: 20,
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '15%',
            top: '10%',
            containLabel: true,
          },
          xAxis: {
            type: 'category',
            data: data.labels || [],
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#6b7280', fontSize: 11 },
            axisTick: { show: false },
          },
          yAxis: {
            type: 'value',
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
            axisLabel: { color: '#6b7280', fontSize: 11 },
          },
          series: data.datasets?.map((dataset: any, idx: number) => ({
            name: dataset.name,
            type: 'bar',
            data: dataset.data,
            barWidth: '50%',
            itemStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: dataset.color || getColor(idx, data.datasets?.length || 1) },
                { offset: 1, color: `${dataset.color || getColor(idx, data.datasets?.length || 1)}80` },
              ]),
              borderRadius: 4,
            },
            animationDuration: 1000,
            animationDelay: (idx: number) => idx * 100,
          })),
        };
    }

    chart.setOption(option);

    const handleResize = () => {
      chart.resize();
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.dispose();
    };
  }, [data, width, height]);

  return (
    <div 
      ref={chartRef} 
      style={{ width: width, height: height }}
      className="w-full h-full"
    />
  );
};

export default ChartComponent;