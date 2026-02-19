import { AppLayout } from '../components/layout/AppLayout'
import { ChatPanel } from '../components/chat/ChatPanel'

export function Chat() {
  return (
    <AppLayout>
      <div className="h-full">
        <ChatPanel />
      </div>
    </AppLayout>
  )
}

export default Chat
