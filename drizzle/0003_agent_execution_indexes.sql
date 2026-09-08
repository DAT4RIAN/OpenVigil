CREATE INDEX IF NOT EXISTS `agent_executions_agent_time_idx` ON `agent_executions` (`agent_id`,`started_at`);--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `agent_executions_status_time_idx` ON `agent_executions` (`status`,`started_at`);--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `agent_executions_tool_time_idx` ON `agent_executions` (`tool_name`,`started_at`);--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS `agent_executions_correlation_uidx` ON `agent_executions` (`correlation_id`);
