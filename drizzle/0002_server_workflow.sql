CREATE TABLE `workflow_audit_events` (
	`id` text PRIMARY KEY NOT NULL,
	`mission_id` text NOT NULL,
	`revision` integer NOT NULL,
	`event_sequence` integer NOT NULL,
	`action` text NOT NULL,
	`kind` text NOT NULL,
	`actor_id` text NOT NULL,
	`actor_name` text NOT NULL,
	`actor_role` text,
	`correlation_id` text NOT NULL,
	`idempotency_key` text NOT NULL,
	`from_state` text NOT NULL,
	`to_state` text NOT NULL,
	`detail` text NOT NULL,
	`timestamp` text NOT NULL,
	FOREIGN KEY (`mission_id`) REFERENCES `workflow_instances`(`mission_id`) ON UPDATE no action ON DELETE no action,
	CONSTRAINT "workflow_audit_revision_positive_chk" CHECK("workflow_audit_events"."revision" > 0),
	CONSTRAINT "workflow_audit_event_sequence_positive_chk" CHECK("workflow_audit_events"."event_sequence" > 0),
	CONSTRAINT "workflow_audit_kind_chk" CHECK("workflow_audit_events"."kind" in ('approval', 'execution', 'verification', 'knowledge', 'reset'))
);
--> statement-breakpoint
CREATE UNIQUE INDEX `workflow_audit_mission_revision_sequence_uidx` ON `workflow_audit_events` (`mission_id`,`revision`,`event_sequence`);--> statement-breakpoint
CREATE INDEX `workflow_audit_mission_time_idx` ON `workflow_audit_events` (`mission_id`,`timestamp`);--> statement-breakpoint
CREATE INDEX `workflow_audit_correlation_idx` ON `workflow_audit_events` (`correlation_id`);--> statement-breakpoint
CREATE TABLE `workflow_idempotency` (
	`idempotency_key` text PRIMARY KEY NOT NULL,
	`mission_id` text NOT NULL,
	`request_fingerprint` text NOT NULL,
	`response_snapshot` text NOT NULL,
	`correlation_id` text NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`mission_id`) REFERENCES `workflow_instances`(`mission_id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `workflow_idempotency_mission_time_idx` ON `workflow_idempotency` (`mission_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `workflow_instances` (
	`mission_id` text PRIMARY KEY NOT NULL,
	`turbine_id` text NOT NULL,
	`mission_status` text NOT NULL,
	`mission_progress_percent` integer NOT NULL,
	`decision_id` text NOT NULL,
	`decision_status` text NOT NULL,
	`decision_risk` text NOT NULL,
	`approval_required` integer DEFAULT true NOT NULL,
	`approval_record` text,
	`work_order_id` text NOT NULL,
	`work_order_status` text NOT NULL,
	`turbine_health_score` integer NOT NULL,
	`main_bearing_health_score` integer NOT NULL,
	`knowledge_case_id` text,
	`revision` integer DEFAULT 0 NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	CONSTRAINT "workflow_instances_mission_status_chk" CHECK("workflow_instances"."mission_status" in ('under-review', 'approved', 'decision-pending', 'diagnosed', 'executing', 'completed')),
	CONSTRAINT "workflow_instances_decision_status_chk" CHECK("workflow_instances"."decision_status" in ('under-review', 'approved', 'rejected', 'revision-requested')),
	CONSTRAINT "workflow_instances_decision_risk_chk" CHECK("workflow_instances"."decision_risk" = 'high'),
	CONSTRAINT "workflow_instances_work_order_status_chk" CHECK("workflow_instances"."work_order_status" in ('draft', 'scheduled', 'in-progress', 'completed')),
	CONSTRAINT "workflow_instances_mission_progress_chk" CHECK("workflow_instances"."mission_progress_percent" between 0 and 100),
	CONSTRAINT "workflow_instances_turbine_health_chk" CHECK("workflow_instances"."turbine_health_score" between 0 and 100),
	CONSTRAINT "workflow_instances_main_bearing_health_chk" CHECK("workflow_instances"."main_bearing_health_score" between 0 and 100),
	CONSTRAINT "workflow_instances_revision_nonnegative_chk" CHECK("workflow_instances"."revision" >= 0)
);
--> statement-breakpoint
CREATE UNIQUE INDEX `workflow_instances_turbine_id_unique` ON `workflow_instances` (`turbine_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `workflow_instances_decision_id_unique` ON `workflow_instances` (`decision_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `workflow_instances_work_order_id_unique` ON `workflow_instances` (`work_order_id`);--> statement-breakpoint
CREATE INDEX `workflow_instances_turbine_idx` ON `workflow_instances` (`turbine_id`);--> statement-breakpoint
CREATE TRIGGER `workflow_audit_revision_guard`
BEFORE INSERT ON `workflow_audit_events`
FOR EACH ROW
WHEN COALESCE((SELECT `revision` FROM `workflow_instances` WHERE `mission_id` = NEW.`mission_id`), -1) != NEW.`revision`
BEGIN
	SELECT RAISE(ABORT, 'workflow revision conflict');
END;--> statement-breakpoint
CREATE TABLE `workflow_tasks` (
	`id` text PRIMARY KEY NOT NULL,
	`mission_id` text NOT NULL,
	`sequence` integer NOT NULL,
	`title` text NOT NULL,
	`completed` integer DEFAULT false NOT NULL,
	`completed_at` text,
	`completed_by` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`mission_id`) REFERENCES `workflow_instances`(`mission_id`) ON UPDATE no action ON DELETE no action,
	CONSTRAINT "workflow_tasks_sequence_positive_chk" CHECK("workflow_tasks"."sequence" > 0)
);
--> statement-breakpoint
CREATE UNIQUE INDEX `workflow_tasks_mission_sequence_uidx` ON `workflow_tasks` (`mission_id`,`sequence`);--> statement-breakpoint
CREATE INDEX `workflow_tasks_mission_completed_idx` ON `workflow_tasks` (`mission_id`,`completed`);
