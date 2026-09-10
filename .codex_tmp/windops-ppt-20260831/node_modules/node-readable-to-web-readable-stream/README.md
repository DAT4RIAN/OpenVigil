[![CI](https://github.com/Borewit/node-readable-to-web-readable-stream/actions/workflows/ci.yml/badge.svg)](https://github.com/Borewit/node-readable-to-web-readable-stream/actions/workflows/ci.yml)
[![NPM version](https://badge.fury.io/js/node-readable-to-web-readable-stream.svg)](https://npmjs.org/package/node-readable-to-web-readable-stream)
[![NPM downloads](http://img.shields.io/npm/dm/node-readable-to-web-readable-stream.svg)](https://npmcharts.com/compare/node-readable-to-web-readable-stream?start=356&interval=7)

# node-readable-to-web-readable-stream

**node-readable-to-web-readable-stream** is a utility that converts a [Node.js stream.Readable](https://nodejs.org/api/stream.html#class-streamreadable) stream into a [Web API ReadableStream](https://developer.mozilla.org/docs/Web/API/ReadableStream).
This is particularly useful for integrating Node.js streams with web-native streaming APIs.

To convert in the opposite direction, see may use [readable-web-to-node-stream](https://github.com/Borewit/readable-web-to-node-stream) instead.

## Installation

Install the package using npm:

```bash
npm install node-readable-to-web-readable-stream
```

Or with yarn:

```bash
yarn add node-readable-to-web-readable-stream
```

## Usage

You can either convert to a [WHATWG / Web API ReadableStream](https://developer.mozilla.org/docs/Web/API/ReadableStream) byte mode, or default mode.

Here's how you can use this utility to convert a [Node.js stream.Readable](https://nodejs.org/api/stream.html#class-streamreadable) stream into a byte [WHATWG / Web API ReadableStream](https://developer.mozilla.org/docs/Web/API/ReadableStream):
If you want to use a [ReadableStreamBYOBReader](https://developer.mozilla.org/docs/Web/API/ReadableStreamBYOBReader) you should use this method.

```javascript
import {makeByteReadableStreamFromNodeReadable} from 'node-readable-to-web-readable-stream';
import {createReadStream} from 'fs';

// Create a Node.js Readable stream
const nodeReadable = fs.createReadStream('example.txt');

// Convert to a web ReadableStream
const webReadable = makeByteReadableStreamFromNodeReadable(nodeReadable);

// Now you can use webReadable as a WHATWG ReadableStream in byte mode
```

If you want to use a [ReadableStreamDefaultReader](https://developer.mozilla.org/docs/Web/API/ReadableStreamDefaultReader) you should use this method.
```javascript
import {makeDefaultReadableStreamFromNodeReadable} from 'node-readable-to-web-readable-stream';
import {createReadStream} from 'fs';

// Create a Node.js Readable stream
const nodeReadable = fs.createReadStream('example.txt');

// Convert to a web ReadableStream
const webReadable = makeDefaultReadableStreamFromNodeReadable(nodeReadable);

// Now you can use webReadable as a WHATWG default ReadableStream
```


## Compatibility

This is an ECMAScript Module (ESM).
Cross-platform compliant:
- Node.js ≥ 18
- Bum ≥ 1.2
- Modern web browsers

You can load the project with `require` in Node.js ≥ 22

## Features
- Supports stream backpressure
- BYOB (Bring Your Own Buffer) compliant

## API

### `toWebReadableStream(nodeReadable, options)`

- **Parameters:**
  - `nodeReadable` ([Node.js stream.Readable](https://nodejs.org/api/stream.html#class-streamreadable)): The Node.js **Readable** stream to convert.
  - `options` Optional: `{highWaterMark?: number}`, high-water mark in bytes, default 16 kB.

- **Returns:**
  - A [WHATWG / Web API ReadableStream](https://developer.mozilla.org/docs/Web/API/ReadableStream).

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE.txt) file for details.
