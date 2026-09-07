CREATE TABLE `activity_events` (
	`id` text PRIMARY KEY NOT NULL,
	`mission_id` text NOT NULL,
	`actor_type` text NOT NULL,
	`actor_id` text,
	`kind` text NOT NULL,
	`title` text NOT NULL,
	`detail` text NOT NULL,
	`timestamp` text NOT NULL,
	`correlation_id` text NOT NULL,
	FOREIGN KEY (`mission_id`) REFERENCES `missions`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `activity_mission_time_idx` ON `activity_events` (`mission_id`,`timestamp`);--> statement-breakpoint
CREATE TABLE `agent_executions` (
	`id` text PRIMARY KEY NOT NULL,
	`mission_id` text,
	`agent_id` text NOT NULL,
	`tool_name` text NOT NULL,
	`status` text NOT NULL,
	`input` text NOT NULL,
	`output` text,
	`started_at` text NOT NULL,
	`completed_at` text,
	`latency_ms` integer,
	`token_usage` integer,
	`error` text,
	`correlation_id` text NOT NULL,
	FOREIGN KEY (`mission_id`) REFERENCES `missions`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`agent_id`) REFERENCES `agents`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `agent_executions_mission_time_idx` ON `agent_executions` (`mission_id`,`started_at`);--> statement-breakpoint
CREATE TABLE `agent_skills` (
	`id` text PRIMARY KEY NOT NULL,
	`agent_id` text NOT NULL,
	`name` text NOT NULL,
	`description` text NOT NULL,
	FOREIGN KEY (`agent_id`) REFERENCES `agents`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `agent_skills_agent_name_uidx` ON `agent_skills` (`agent_id`,`name`);--> statement-breakpoint
CREATE TABLE `agent_tools` (
	`id` text PRIMARY KEY NOT NULL,
	`agent_id` text NOT NULL,
	`name` text NOT NULL,
	`input_schema` text NOT NULL,
	`risk_level` text NOT NULL,
	FOREIGN KEY (`agent_id`) REFERENCES `agents`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `agent_tools_agent_name_uidx` ON `agent_tools` (`agent_id`,`name`);--> statement-breakpoint
CREATE TABLE `agents` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`layer` text NOT NULL,
	`role` text NOT NULL,
	`status` text NOT NULL,
	`model` text NOT NULL,
	`prompt_version` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `alarms` (
	`id` text PRIMARY KEY NOT NULL,
	`turbine_id` text NOT NULL,
	`subsystem_id` text,
	`code` text NOT NULL,
	`severity` text NOT NULL,
	`title` text NOT NULL,
	`status` text NOT NULL,
	`triggered_at` text NOT NULL,
	`resolved_at` text,
	`mission_id` text,
	`correlation_id` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`turbine_id`) REFERENCES `wind_turbines`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`subsystem_id`) REFERENCES `subsystems`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `alarms_turbine_status_idx` ON `alarms` (`turbine_id`,`status`);--> statement-breakpoint
CREATE TABLE `approvals` (
	`id` text PRIMARY KEY NOT NULL,
	`decision_id` text NOT NULL,
	`action` text NOT NULL,
	`approver` text NOT NULL,
	`approver_role` text NOT NULL,
	`reason` text NOT NULL,
	`comment` text NOT NULL,
	`timestamp` text NOT NULL,
	`correlation_id` text NOT NULL,
	FOREIGN KEY (`decision_id`) REFERENCES `decisions`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `decisions` (
	`id` text PRIMARY KEY NOT NULL,
	`mission_id` text NOT NULL,
	`turbine_id` text NOT NULL,
	`status` text NOT NULL,
	`risk` text NOT NULL,
	`recommended_action` text NOT NULL,
	`confidence_percent` real NOT NULL,
	`alternatives` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`mission_id`) REFERENCES `missions`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`turbine_id`) REFERENCES `wind_turbines`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `evidence` (
	`id` text PRIMARY KEY NOT NULL,
	`mission_id` text NOT NULL,
	`turbine_id` text NOT NULL,
	`type` text NOT NULL,
	`title` text NOT NULL,
	`summary` text NOT NULL,
	`source_label` text NOT NULL,
	`source_id` text,
	`observed_at` text NOT NULL,
	`payload` text,
	FOREIGN KEY (`mission_id`) REFERENCES `missions`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`turbine_id`) REFERENCES `wind_turbines`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `failure_cases` (
	`id` text PRIMARY KEY NOT NULL,
	`turbine_id` text,
	`component` text NOT NULL,
	`failure_mode` text NOT NULL,
	`symptoms` text NOT NULL,
	`root_cause` text NOT NULL,
	`action` text NOT NULL,
	`outcome` text NOT NULL,
	`source_document_ids` text NOT NULL,
	`closed_at` text NOT NULL,
	FOREIGN KEY (`turbine_id`) REFERENCES `wind_turbines`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `health_assessments` (
	`id` text PRIMARY KEY NOT NULL,
	`turbine_id` text NOT NULL,
	`subsystem_id` text,
	`health_score` real NOT NULL,
	`anomaly_score` real NOT NULL,
	`failure_probability_30d` real NOT NULL,
	`remaining_useful_life_days` integer,
	`assessed_at` text NOT NULL,
	`model_version` text NOT NULL,
	FOREIGN KEY (`turbine_id`) REFERENCES `wind_turbines`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`subsystem_id`) REFERENCES `subsystems`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `knowledge_documents` (
	`id` text PRIMARY KEY NOT NULL,
	`title` text NOT NULL,
	`type` text NOT NULL,
	`equipment` text NOT NULL,
	`version` text NOT NULL,
	`vectorized` integer NOT NULL,
	`source_uri` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `maintenance_records` (
	`id` text PRIMARY KEY NOT NULL,
	`work_order_id` text NOT NULL,
	`turbine_id` text NOT NULL,
	`performed_by` text NOT NULL,
	`started_at` text NOT NULL,
	`completed_at` text NOT NULL,
	`findings` text NOT NULL,
	`verification` text NOT NULL,
	`evidence_ids` text NOT NULL,
	FOREIGN KEY (`work_order_id`) REFERENCES `work_orders`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`turbine_id`) REFERENCES `wind_turbines`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `mission_tasks` (
	`id` text PRIMARY KEY NOT NULL,
	`mission_id` text NOT NULL,
	`agent_id` text,
	`title` text NOT NULL,
	`status` text NOT NULL,
	`sequence` integer NOT NULL,
	`started_at` text,
	`completed_at` text,
	FOREIGN KEY (`mission_id`) REFERENCES `missions`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`agent_id`) REFERENCES `agents`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `missions` (
	`id` text PRIMARY KEY NOT NULL,
	`turbine_id` text NOT NULL,
	`title` text NOT NULL,
	`severity` text NOT NULL,
	`status` text NOT NULL,
	`progress_percent` integer NOT NULL,
	`lead_agent_id` text NOT NULL,
	`diagnosis` text,
	`confidence_percent` real,
	`correlation_id` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`turbine_id`) REFERENCES `wind_turbines`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`lead_agent_id`) REFERENCES `agents`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `missions_turbine_status_idx` ON `missions` (`turbine_id`,`status`);--> statement-breakpoint
CREATE TABLE `scada_measurements` (
	`id` text PRIMARY KEY NOT NULL,
	`sensor_id` text NOT NULL,
	`turbine_id` text NOT NULL,
	`timestamp` text NOT NULL,
	`value` real NOT NULL,
	`quality` text NOT NULL,
	`is_anomaly` integer DEFAULT false NOT NULL,
	`correlation_id` text,
	FOREIGN KEY (`sensor_id`) REFERENCES `sensors`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`turbine_id`) REFERENCES `wind_turbines`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `scada_turbine_time_idx` ON `scada_measurements` (`turbine_id`,`timestamp`);--> statement-breakpoint
CREATE INDEX `scada_sensor_time_idx` ON `scada_measurements` (`sensor_id`,`timestamp`);--> statement-breakpoint
CREATE TABLE `sensors` (
	`id` text PRIMARY KEY NOT NULL,
	`turbine_id` text NOT NULL,
	`subsystem_id` text,
	`metric` text NOT NULL,
	`unit` text NOT NULL,
	`source` text NOT NULL,
	`sample_interval_seconds` integer NOT NULL,
	`enabled` integer DEFAULT true NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`turbine_id`) REFERENCES `wind_turbines`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`subsystem_id`) REFERENCES `subsystems`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `sensors_turbine_metric_uidx` ON `sensors` (`turbine_id`,`metric`);--> statement-breakpoint
CREATE TABLE `subsystems` (
	`id` text PRIMARY KEY NOT NULL,
	`turbine_id` text NOT NULL,
	`key` text NOT NULL,
	`name` text NOT NULL,
	`health_score` real NOT NULL,
	`state` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`turbine_id`) REFERENCES `wind_turbines`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `subsystems_turbine_key_uidx` ON `subsystems` (`turbine_id`,`key`);--> statement-breakpoint
CREATE TABLE `wind_farms` (
	`id` text PRIMARY KEY NOT NULL,
	`code` text NOT NULL,
	`name` text NOT NULL,
	`location` text NOT NULL,
	`total_capacity_mw` real NOT NULL,
	`status` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `wind_farms_code_unique` ON `wind_farms` (`code`);--> statement-breakpoint
CREATE TABLE `wind_turbines` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`model` text NOT NULL,
	`serial_number` text NOT NULL,
	`rated_power_mw` real NOT NULL,
	`status` text NOT NULL,
	`health_score` real NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `wind_farms`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `wind_turbines_serial_number_unique` ON `wind_turbines` (`serial_number`);--> statement-breakpoint
CREATE INDEX `wind_turbines_farm_idx` ON `wind_turbines` (`farm_id`);--> statement-breakpoint
CREATE TABLE `work_orders` (
	`id` text PRIMARY KEY NOT NULL,
	`turbine_id` text NOT NULL,
	`mission_id` text,
	`decision_id` text,
	`issue` text NOT NULL,
	`priority` text NOT NULL,
	`status` text NOT NULL,
	`assigned_team` text NOT NULL,
	`planned_start` text NOT NULL,
	`deadline` text NOT NULL,
	`tasks` text NOT NULL,
	`safety_plan` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`turbine_id`) REFERENCES `wind_turbines`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`mission_id`) REFERENCES `missions`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`decision_id`) REFERENCES `decisions`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `work_orders_turbine_status_idx` ON `work_orders` (`turbine_id`,`status`);