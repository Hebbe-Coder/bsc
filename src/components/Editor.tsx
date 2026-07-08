import Toolbar from './Toolbar';
import Sidebar from './Sidebar';
import Canvas from './Canvas';
import PropertyPanel from './PropertyPanel';
import SlideThumbnails from './SlideThumbnails';
import SpeakerNotes from './SpeakerNotes';

const Editor = () => {
  return (
    <div className="h-screen flex flex-col bg-gray-100">
      <Toolbar />
      
      <div className="flex-1 flex overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col">
          <Canvas />
          <SpeakerNotes />
        </div>
        <PropertyPanel />
      </div>
      
      <SlideThumbnails />
    </div>
  );
};

export default Editor;
