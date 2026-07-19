import { useState } from 'react';
import { UnifiedWorkspace } from './components/UnifiedWorkspace';

export default function App() {
  return (
    <div className='flex h-screen flex-col bg-[#0d1117] text-[#c9d1d9]'>
      <UnifiedWorkspace />
    </div>
  );
}
