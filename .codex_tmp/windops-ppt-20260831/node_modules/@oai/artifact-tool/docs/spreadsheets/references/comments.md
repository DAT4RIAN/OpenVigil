# Comments

Workbook comments use people, threads, replies, reactions, and thread state.

## Current Author

```ts
workbook.comments.setSelf({
  displayName,
  initials,
  email,
});
```

## Person Inline Type

```ts
type PersonConfig = {
  id?: string;
  displayName: string;
  initials?: string;
  email?: string;
  avatarUrl?: string;
};
```

## Cell And Range Threads

```ts
const cellThread = workbook.comments.addThread(
  { cell: sheet.getRange(cellAddress) },
  bodyText,
);

const rangeThread = workbook.comments.addThread(
  { range: sheet.getRange(rangeAddress) },
  bodyText,
);
```

## Thread Inline Types

```ts
type WorkbookCommentTarget =
  | { cell: Range }
  | { range: Range };

type ThreadAddOptions = {
  author?: Person | PersonConfig | { id: string };
  createdAt?: string;
  position?: { x: number; y: number; unit?: "px" | "emu" };
};
```

## Replies And State

```ts
const reply = cellThread.addReply(replyText);
reply.toggleReaction(reactionText);
cellThread.resolve();
cellThread.reopen();
```
