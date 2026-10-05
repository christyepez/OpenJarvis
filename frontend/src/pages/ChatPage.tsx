import { ChatArea } from '../components/Chat/ChatArea';
import { SystemPanel } from '../components/Chat/SystemPanel';
import { JarvisCoreHud } from '../components/Dashboard/JarvisCoreHud';
import { useAppStore } from '../lib/store';

export function ChatPage() {
  const systemPanelOpen = useAppStore((s) => s.systemPanelOpen);

  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="px-3 pt-3 md:px-4 md:pt-4 shrink-0">
          <JarvisCoreHud compact />
        </div>
        <div className="flex-1 min-h-0">
          <ChatArea />
        </div>
      </div>
      {systemPanelOpen && <SystemPanel />}
    </div>
  );
}
