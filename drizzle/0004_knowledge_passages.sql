CREATE TABLE `knowledge_passages` (
	`id` text PRIMARY KEY NOT NULL,
	`document_id` text NOT NULL,
	`page` integer NOT NULL,
	`section` text NOT NULL,
	`body` text NOT NULL,
	`content_hash` text NOT NULL,
	`token_count` integer NOT NULL,
	`turbine_id` text,
	`mission_id` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`document_id`) REFERENCES `knowledge_documents`(`id`) ON UPDATE no action ON DELETE no action,
	CONSTRAINT "knowledge_passages_page_positive_chk" CHECK("knowledge_passages"."page" > 0),
	CONSTRAINT "knowledge_passages_token_count_nonnegative_chk" CHECK("knowledge_passages"."token_count" >= 0)
);
--> statement-breakpoint
CREATE INDEX `knowledge_passages_document_page_idx` ON `knowledge_passages` (`document_id`,`page`);--> statement-breakpoint
CREATE INDEX `knowledge_passages_scope_idx` ON `knowledge_passages` (`turbine_id`,`mission_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `knowledge_passages_document_hash_uidx` ON `knowledge_passages` (`document_id`,`content_hash`);