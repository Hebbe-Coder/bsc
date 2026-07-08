import { useEffect, useRef, useState, useCallback } from 'react';
import usePresentationStore from '../store/presentationStore';
import { themes } from '../theme/themes';
import { Component } from '../types';
import ChartComponent from './ChartComponent';
import TableComponent from './TableComponent';

const CANVAS_WIDTH = 800;
const CANVAS_HEIGHT = 500;
const GRID_SIZE = 20;

const Canvas = () => {
  const { presentation, selectedComponentId, selectComponent, moveComponent, updateComponent } = usePresentationStore();
  const canvasRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [resizeDirection, setResizeDirection] = useState<string>('');
  const [resizeStart, setResizeStart] = useState({ x: 0, y: 0, width: 0, height: 0 });
  const [editingComponentId, setEditingComponentId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const editInputRef = useRef<HTMLInputElement>(null);

  const currentSlide = presentation.slides[presentation.currentSlideIndex];
  const theme = themes[presentation.theme];

  useEffect(() => {
    if (editingComponentId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingComponentId]);

  const snapToGrid = useCallback((value: number) => {
    return Math.round(value / GRID_SIZE) * GRID_SIZE;
  }, []);

  const handleCanvasClick = (e: React.MouseEvent) => {
    if (e.target === canvasRef.current || (e.target as HTMLElement).classList.contains('grid-overlay')) {
      selectComponent(null);
      setEditingComponentId(null);
    }
  };

  const handleComponentClick = (e: React.MouseEvent, component: Component) => {
    e.stopPropagation();
    selectComponent(component.id);
  };

  const handleComponentDoubleClick = (e: React.MouseEvent, component: Component) => {
    e.stopPropagation();
    if (component.type === 'text') {
      setEditingComponentId(component.id);
      setEditValue(component.content);
    }
  };

  const handleMouseDown = (e: React.MouseEvent, component: Component) => {
    if (editingComponentId === component.id) return;
    
    e.stopPropagation();
    const rect = (e.target as HTMLElement).getBoundingClientRect();
    const handleSize = 12;
    
    const isTop = e.clientY <= rect.top + handleSize;
    const isBottom = e.clientY >= rect.bottom - handleSize;
    const isLeft = e.clientX <= rect.left + handleSize;
    const isRight = e.clientX >= rect.right - handleSize;
    
    if (isTop && isLeft) {
      setIsResizing(true);
      setResizeDirection('top-left');
    } else if (isTop && isRight) {
      setIsResizing(true);
      setResizeDirection('top-right');
    } else if (isBottom && isLeft) {
      setIsResizing(true);
      setResizeDirection('bottom-left');
    } else if (isBottom && isRight) {
      setIsResizing(true);
      setResizeDirection('bottom-right');
    } else if (isTop) {
      setIsResizing(true);
      setResizeDirection('top');
    } else if (isBottom) {
      setIsResizing(true);
      setResizeDirection('bottom');
    } else if (isLeft) {
      setIsResizing(true);
      setResizeDirection('left');
    } else if (isRight) {
      setIsResizing(true);
      setResizeDirection('right');
    } else {
      setIsDragging(true);
      setDragOffset({
        x: e.clientX - component.x,
        y: e.clientY - component.y,
      });
    }
    
    if (isResizing) {
      setResizeStart({
        x: e.clientX,
        y: e.clientY,
        width: component.width,
        height: component.height,
      });
    }
    
    selectComponent(component.id);
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging && selectedComponentId) {
        const newX = snapToGrid(Math.max(0, Math.min(CANVAS_WIDTH - 50, e.clientX - dragOffset.x)));
        const newY = snapToGrid(Math.max(0, Math.min(CANVAS_HEIGHT - 50, e.clientY - dragOffset.y)));
        moveComponent(selectedComponentId, newX, newY);
      }
      
      if (isResizing && selectedComponentId) {
        const component = currentSlide.components.find(c => c.id === selectedComponentId);
        if (component) {
          const deltaX = e.clientX - resizeStart.x;
          const deltaY = e.clientY - resizeStart.y;
          let newX = component.x;
          let newY = component.y;
          let newWidth = resizeStart.width;
          let newHeight = resizeStart.height;

          switch (resizeDirection) {
            case 'bottom-right':
              newWidth = Math.max(50, Math.min(CANVAS_WIDTH - component.x, resizeStart.width + deltaX));
              newHeight = Math.max(50, Math.min(CANVAS_HEIGHT - component.y, resizeStart.height + deltaY));
              break;
            case 'bottom-left':
              newWidth = Math.max(50, Math.min(CANVAS_WIDTH - component.x, resizeStart.width - deltaX));
              newHeight = Math.max(50, Math.min(CANVAS_HEIGHT - component.y, resizeStart.height + deltaY));
              newX = Math.max(0, Math.min(CANVAS_WIDTH - newWidth, component.x + deltaX));
              break;
            case 'top-right':
              newWidth = Math.max(50, Math.min(CANVAS_WIDTH - component.x, resizeStart.width + deltaX));
              newHeight = Math.max(50, Math.min(CANVAS_HEIGHT - component.y, resizeStart.height - deltaY));
              newY = Math.max(0, Math.min(CANVAS_HEIGHT - newHeight, component.y + deltaY));
              break;
            case 'top-left':
              newWidth = Math.max(50, Math.min(CANVAS_WIDTH - component.x, resizeStart.width - deltaX));
              newHeight = Math.max(50, Math.min(CANVAS_HEIGHT - component.y, resizeStart.height - deltaY));
              newX = Math.max(0, Math.min(CANVAS_WIDTH - newWidth, component.x + deltaX));
              newY = Math.max(0, Math.min(CANVAS_HEIGHT - newHeight, component.y + deltaY));
              break;
            case 'bottom':
              newHeight = Math.max(50, Math.min(CANVAS_HEIGHT - component.y, resizeStart.height + deltaY));
              break;
            case 'top':
              newHeight = Math.max(50, Math.min(CANVAS_HEIGHT - component.y, resizeStart.height - deltaY));
              newY = Math.max(0, Math.min(CANVAS_HEIGHT - newHeight, component.y + deltaY));
              break;
            case 'right':
              newWidth = Math.max(50, Math.min(CANVAS_WIDTH - component.x, resizeStart.width + deltaX));
              break;
            case 'left':
              newWidth = Math.max(50, Math.min(CANVAS_WIDTH - component.x, resizeStart.width - deltaX));
              newX = Math.max(0, Math.min(CANVAS_WIDTH - newWidth, component.x + deltaX));
              break;
          }

          updateComponent(selectedComponentId, { 
            x: snapToGrid(newX), 
            y: snapToGrid(newY), 
            width: snapToGrid(newWidth), 
            height: snapToGrid(newHeight) 
          });
        }
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      setIsResizing(false);
      setResizeDirection('');
    };

    if (isDragging || isResizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, isResizing, dragOffset, resizeDirection, resizeStart, selectedComponentId, currentSlide, moveComponent, updateComponent, snapToGrid]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!selectedComponentId || editingComponentId) return;
      
      const component = currentSlide.components.find(c => c.id === selectedComponentId);
      if (!component) return;

      const step = e.shiftKey ? 10 : 1;

      switch (e.key) {
        case 'ArrowUp':
          e.preventDefault();
          moveComponent(selectedComponentId, component.x, Math.max(0, component.y - step));
          break;
        case 'ArrowDown':
          e.preventDefault();
          moveComponent(selectedComponentId, component.x, Math.min(CANVAS_HEIGHT - component.height, component.y + step));
          break;
        case 'ArrowLeft':
          e.preventDefault();
          moveComponent(selectedComponentId, Math.max(0, component.x - step), component.y);
          break;
        case 'ArrowRight':
          e.preventDefault();
          moveComponent(selectedComponentId, Math.min(CANVAS_WIDTH - component.width, component.x + step), component.y);
          break;
        case 'Delete':
        case 'Backspace':
          e.preventDefault();
          updateComponent(selectedComponentId, { ...component, x: snapToGrid(component.x), y: snapToGrid(component.y) });
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedComponentId, editingComponentId, currentSlide, moveComponent, updateComponent, snapToGrid]);

  const handleEditBlur = () => {
    if (editingComponentId && editValue.trim()) {
      updateComponent(editingComponentId, { content: editValue });
    }
    setEditingComponentId(null);
  };

  const handleEditKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleEditBlur();
    } else if (e.key === 'Escape') {
      setEditingComponentId(null);
    }
  };

  const getComponentStyle = (component: Component) => {
    const isSelected = selectedComponentId === component.id;
    const isEditing = editingComponentId === component.id;
    
    return {
      position: 'absolute' as const,
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
      padding: component.type === 'text' ? '8px' : 0,
      overflow: 'hidden',
      cursor: isEditing ? 'text' : isSelected ? 'move' : 'pointer',
      outline: isSelected ? `2px solid ${theme.accent}` : 'none',
      borderStyle: isSelected ? 'dashed' : component.style.borderWidth > 0 ? 'solid' : 'none',
      zIndex: isSelected ? 10 : 1,
      display: 'flex',
      alignItems: 'center',
      justifyContent: component.style.textAlign === 'center' ? 'center' : 'flex-start',
      transition: isDragging || isResizing ? 'none' : 'box-shadow 0.2s ease',
    };
  };

  const getResizeCursor = (direction: string) => {
    const cursors: Record<string, string> = {
      'top-left': 'nw-resize',
      'top-right': 'ne-resize',
      'bottom-left': 'sw-resize',
      'bottom-right': 'se-resize',
      'top': 'n-resize',
      'bottom': 's-resize',
      'left': 'w-resize',
      'right': 'e-resize',
    };
    return cursors[direction] || 'default';
  };

  const renderResizeHandles = () => {
    if (!selectedComponentId) return null;
    
    const component = currentSlide.components.find(c => c.id === selectedComponentId);
    if (!component) return null;

    const handles = [
      { position: { left: -4, top: -4 }, cursor: 'nw-resize' },
      { position: { right: -4, top: -4 }, cursor: 'ne-resize' },
      { position: { left: -4, bottom: -4 }, cursor: 'sw-resize' },
      { position: { right: -4, bottom: -4 }, cursor: 'se-resize' },
      { position: { left: -4, top: '50%', transform: 'translateY(-50%)' }, cursor: 'w-resize' },
      { position: { right: -4, top: '50%', transform: 'translateY(-50%)' }, cursor: 'e-resize' },
      { position: { left: '50%', top: -4, transform: 'translateX(-50%)' }, cursor: 'n-resize' },
      { position: { left: '50%', bottom: -4, transform: 'translateX(-50%)' }, cursor: 's-resize' },
    ];

    return (
      <>
        {handles.map((handle, index) => (
          <div
            key={index}
            className="absolute w-3 h-3 bg-white rounded-sm border-2 border-blue-500 shadow-md"
            style={{
              ...handle.position,
              cursor: handle.cursor,
            }}
          />
        ))}
        <div 
          className="absolute w-full h-full pointer-events-none"
          style={{
            boxShadow: `0 0 0 2px ${theme.accent}40`,
          }}
        />
      </>
    );
  };

  const renderComponent = (component: Component) => {
    const isEditing = editingComponentId === component.id;
    
    switch (component.type) {
      case 'text':
        return (
          <div
            key={component.id}
            style={getComponentStyle(component)}
            onClick={(e) => handleComponentClick(e, component)}
            onDoubleClick={(e) => handleComponentDoubleClick(e, component)}
            onMouseDown={(e) => handleMouseDown(e, component)}
          >
            {isEditing ? (
              <textarea
                ref={editInputRef as any}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onBlur={handleEditBlur}
                onKeyDown={handleEditKeyDown}
                className="w-full h-full bg-transparent border-none outline-none text-inherit font-inherit resize-none"
                rows={Math.max(1, Math.ceil(component.content.length / 50))}
              />
            ) : (
              <span className="whitespace-pre-wrap break-words">{component.content}</span>
            )}
          </div>
        );
      case 'chart':
        return (
          <div
            key={component.id}
            style={getComponentStyle(component)}
            onClick={(e) => handleComponentClick(e, component)}
            onMouseDown={(e) => handleMouseDown(e, component)}
          >
            <ChartComponent data={component.data} width={component.width} height={component.height} />
          </div>
        );
      case 'shape':
        return (
          <div
            key={component.id}
            style={getComponentStyle(component)}
            onClick={(e) => handleComponentClick(e, component)}
            onMouseDown={(e) => handleMouseDown(e, component)}
          />
        );
      case 'image':
        return (
          <div
            key={component.id}
            style={getComponentStyle(component)}
            onClick={(e) => handleComponentClick(e, component)}
            onMouseDown={(e) => handleMouseDown(e, component)}
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
            style={getComponentStyle(component)}
            onClick={(e) => handleComponentClick(e, component)}
            onMouseDown={(e) => handleMouseDown(e, component)}
          >
            <TableComponent data={component.data} width={component.width} height={component.height} />
          </div>
        );
      case 'media':
        return (
          <div
            key={component.id}
            style={getComponentStyle(component)}
            onClick={(e) => handleComponentClick(e, component)}
            onMouseDown={(e) => handleMouseDown(e, component)}
          >
            <div className="w-full h-full bg-gray-900 flex items-center justify-center">
              <span className="text-gray-400 text-sm">视频占位</span>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center p-8 bg-gray-100">
      <div 
        ref={canvasRef}
        className="relative shadow-2xl rounded-lg overflow-hidden"
        style={{
          width: CANVAS_WIDTH,
          height: CANVAS_HEIGHT,
          backgroundColor: currentSlide?.backgroundColor || theme.background,
          backgroundImage: currentSlide?.backgroundColor !== theme.background 
            ? undefined 
            : `radial-gradient(circle at 20% 20%, ${theme.accent}10 0%, transparent 50%)`,
        }}
        onClick={handleCanvasClick}
      >
        <div className="absolute inset-0 pointer-events-none grid-overlay" style={{
          backgroundImage: `
            linear-gradient(to right, rgba(0,0,0,0.03) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(0,0,0,0.03) 1px, transparent 1px)
          `,
          backgroundSize: `${GRID_SIZE}px ${GRID_SIZE}px`,
        }} />
        
        {currentSlide?.components.map((component) => (
          <div key={component.id}>
            {renderComponent(component)}
            {selectedComponentId === component.id && renderResizeHandles()}
          </div>
        ))}
      </div>
    </div>
  );
};

export default Canvas;