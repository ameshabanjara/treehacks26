import { IMessageSDK } from '@photon-ai/imessage-kit'
import { appendFileSync } from 'fs'

const sdk = new IMessageSDK()
const messages: any[] = []

console.log('Watching for new iMessages... (Ctrl+C to stop)\n')

await sdk.startWatching({
  onMessage: (msg) => {
    const entry = {
      sender: msg.sender,
      text: msg.text,
      timestamp: new Date().toISOString(),
    }
    messages.push(entry)
    appendFileSync('messages.json', JSON.stringify(entry) + '\n')
    console.log(`[${new Date().toLocaleTimeString()}] ${msg.sender}: ${msg.text}`)
    console.log(`  → Full msg keys:`, Object.keys(msg))
    console.log(`  → chatId:`, (msg as any).chatId ?? (msg as any).chat_id ?? (msg as any).group ?? 'not found')
    console.log(`  → raw:`, JSON.stringify(msg, null, 2))
  },
  onError: (error) => {
    console.error('Error:', error)
  },
  pollInterval: 1000,
  excludeOwnMessages: false,
})
