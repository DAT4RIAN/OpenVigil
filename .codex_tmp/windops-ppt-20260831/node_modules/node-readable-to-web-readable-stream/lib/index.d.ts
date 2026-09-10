import type { Readable } from 'node:stream';
interface ByteReadableStreamFromNodeReadableOptions {
    highWaterMark?: number;
}
/**
 * Create a Web API default `ReadableStream<Uint8Array>` from a Node.js `stream.Readable`.
 * @param nodeReadable Node Stream to convert
 * @param options Options
 */
export declare function makeDefaultReadableStreamFromNodeReadable(nodeReadable: Readable, options?: ByteReadableStreamFromNodeReadableOptions): ReadableStream<Uint8Array>;
/**
 * Create a Web API byte `ReadableStream<Uint8Array>` from a Node.js `stream.Readable`.
 * @param nodeReadable Node Stream to convert
 * @param options Options
 */
export declare function makeByteReadableStreamFromNodeReadable(nodeReadable: Readable, options?: ByteReadableStreamFromNodeReadableOptions): ReadableStream<Uint8Array>;
export {};
