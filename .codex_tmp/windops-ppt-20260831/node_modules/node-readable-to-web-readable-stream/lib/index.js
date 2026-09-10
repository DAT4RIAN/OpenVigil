/**
 * Create a Web API default `ReadableStream<Uint8Array>` from a Node.js `stream.Readable`.
 * @param nodeReadable Node Stream to convert
 * @param options Options
 */
export function makeDefaultReadableStreamFromNodeReadable(nodeReadable, options = {}) {
    let closed = false;
    const queueingStrategy = new ByteLengthQueuingStrategy({ highWaterMark: options.highWaterMark ?? 16 * 1024 });
    function close(controller) {
        if (!closed) {
            closed = true;
            controller.close();
        }
    }
    return new ReadableStream({
        start(controller) {
            nodeReadable.on('data', chunk => {
                if (closed) {
                    return;
                }
                controller.enqueue(chunk);
                if (controller.desiredSize != null && controller.desiredSize <= 0) {
                    // Apply backpressure if needed.
                    nodeReadable.pause();
                }
            });
            nodeReadable.once('end', () => {
                close(controller); // Signal EOF
            });
            nodeReadable.once('error', err => {
                controller.error(err);
            });
        },
        pull(controller) {
            if (nodeReadable.isPaused()) {
                nodeReadable.resume();
            }
        },
        cancel(reason) {
            closed = true; // Avoid controller is closed twice
            nodeReadable.destroy(reason);
        },
    }, queueingStrategy);
}
/**
 * Create a Web API byte `ReadableStream<Uint8Array>` from a Node.js `stream.Readable`.
 * @param nodeReadable Node Stream to convert
 * @param options Options
 */
export function makeByteReadableStreamFromNodeReadable(nodeReadable, options = {}) {
    let closed = false;
    let isNodeStreamEnded = false;
    const highWaterMark = options.highWaterMark ?? 16 * 1024;
    const queue = [];
    /**
     * Queue length in bytes
     */
    let queueLength = 0;
    let pullRequest = 0;
    function close(controller) {
        if (!closed) {
            closed = true;
            controller.close();
        }
    }
    // This function will process any leftover bytes
    const processLeftover = (controller) => {
        const byobRequest = controller.byobRequest;
        const chunk = queue.shift();
        if (chunk) {
            queueLength -= chunk.length;
        }
        if (!byobRequest) {
            if (chunk) {
                controller.enqueue(chunk);
                --pullRequest;
                return;
            }
            if (isNodeStreamEnded) {
                close(controller); // Signal EOF
            }
            return;
        }
        const view = byobRequest.view;
        if (!view)
            return;
        if (!chunk) {
            if (isNodeStreamEnded) {
                close(controller); // Signal EOF
                byobRequest.respond(0); // Cancel BYOB request
                --pullRequest;
            }
            return;
        }
        const bytesToCopy = Math.min(view.byteLength, chunk.length);
        new Uint8Array(view.buffer, view.byteOffset, bytesToCopy).set(chunk.subarray(0, bytesToCopy));
        byobRequest.respond(bytesToCopy);
        --pullRequest;
        if (bytesToCopy < chunk.length) {
            const remainder = chunk.subarray(bytesToCopy);
            queue.unshift(remainder);
            queueLength += remainder.length;
        }
        if (chunk.length === 0 && isNodeStreamEnded) {
            close(controller); // Signal EOF
            byobRequest.respond(0); // Cancel BYOB request
            --pullRequest;
        }
    };
    return new ReadableStream({
        type: 'bytes',
        start(controller) {
            nodeReadable.on('data', chunk => {
                queue.push(chunk);
                queueLength += chunk.length;
                if (pullRequest > 0) {
                    processLeftover(controller);
                }
                // Apply backpressure if needed.
                if (!nodeReadable.isPaused()) {
                    if (queueLength > highWaterMark) {
                        nodeReadable.pause();
                    }
                }
            });
            nodeReadable.once('end', () => {
                isNodeStreamEnded = true;
                processLeftover(controller);
            });
            nodeReadable.once('error', err => {
                controller.error(err);
            });
        },
        pull(controller) {
            ++pullRequest;
            processLeftover(controller);
            if (nodeReadable.isPaused() && queueLength < highWaterMark) {
                nodeReadable.resume();
            }
        },
        cancel(reason) {
            closed = true; // Avoid controller is closed twice
            nodeReadable.destroy(reason);
        },
    });
}
