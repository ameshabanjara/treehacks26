import { IMessageSDK } from '@photon-ai/imessage-kit'

const sdk = new IMessageSDK()

// Replace with the phone number or email you want to message
await sdk.send('+14083689761', 'Hello from iMessage Kit!')

await sdk.close()
