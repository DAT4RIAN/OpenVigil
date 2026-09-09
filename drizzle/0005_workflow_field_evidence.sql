CREATE TABLE `alarm_mutation_audit` (
	`id` text PRIMARY KEY NOT NULL,
	`alarm_id` text NOT NULL,
	`action` text NOT NULL,
	`actor_id` text NOT NULL,
	`actor_name` text NOT NULL,
	`actor_role` text NOT NULL,
	`before_state` text NOT NULL,
	`after_state` text NOT NULL,
	`correlation_id` text NOT NULL,
	`idempotency_key` text NOT NULL,
	`request_fingerprint` text NOT NULL,
	`timestamp` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `alarm_mutation_audit_idempotency_key_unique` ON `alarm_mutation_audit` (`idempotency_key`);--> statement-breakpoint
CREATE INDEX `alarm_mutation_audit_alarm_time_idx` ON `alarm_mutation_audit` (`alarm_id`,`timestamp`);--> statement-breakpoint
CREATE TABLE `alarm_runtime_state` (
	`alarm_id` text PRIMARY KEY NOT NULL,
	`status` text NOT NULL,
	`assignee` text,
	`acknowledged_at` text,
	`revision` integer DEFAULT 0 NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
ALTER TABLE `workflow_audit_events` ADD `field_evidence` text;--> statement-breakpoint
ALTER TABLE `workflow_tasks` ADD `field_evidence` text;