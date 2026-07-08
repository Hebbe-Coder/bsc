import { FileText } from 'lucide-react';
import usePresentationStore from '../store/presentationStore';

const SpeakerNotes = () => {
  const { presentation, updateSlideNotes } = usePresentationStore();
  const currentSlide = presentation.slides[presentation.currentSlideIndex];
  const notes = currentSlide?.notes || '';

  const handleNotesChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    updateSlideNotes(presentation.currentSlideIndex, e.target.value);
  };

  return (
    <div className="h-32 bg-gray-50 border-t border-gray-200 flex flex-col">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-200 bg-white">
        <FileText size={16} className="text-gray-500" />
        <span className="text-sm font-medium text-gray-700">演讲者备注</span>
        <span className="text-xs text-gray-400 ml-auto">幻灯片 {presentation.currentSlideIndex + 1}</span>
      </div>
      <textarea
        value={notes}
        onChange={handleNotesChange}
        placeholder="输入演讲者备注...这些备注仅在演讲模式下可见"
        className="flex-1 w-full px-4 py-3 resize-none focus:outline-none text-sm text-gray-700 placeholder-gray-400"
      />
    </div>
  );
};

export default SpeakerNotes;