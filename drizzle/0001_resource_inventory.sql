CREATE TABLE `crews` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`specialties` text NOT NULL,
	`member_count` integer NOT NULL,
	`availability` text NOT NULL,
	`certifications` text NOT NULL,
	`current_location` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	CONSTRAINT "crews_member_count_positive_chk" CHECK("crews"."member_count" > 0),
	CONSTRAINT "crews_availability_chk" CHECK("crews"."availability" in ('available', 'reserved', 'assigned', 'unavailable'))
);
--> statement-breakpoint
CREATE INDEX `crews_availability_idx` ON `crews` (`availability`);--> statement-breakpoint
CREATE TABLE `inventory_reservations` (
	`id` text PRIMARY KEY NOT NULL,
	`work_order_part_id` text NOT NULL,
	`quantity` integer NOT NULL,
	`status` text NOT NULL,
	`reserved_at` text NOT NULL,
	`released_at` text,
	`consumed_at` text,
	`correlation_id` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`work_order_part_id`) REFERENCES `work_order_parts`(`id`) ON UPDATE no action ON DELETE no action,
	CONSTRAINT "inventory_reservations_quantity_positive_chk" CHECK("inventory_reservations"."quantity" > 0),
	CONSTRAINT "inventory_reservations_status_chk" CHECK("inventory_reservations"."status" in ('reserved', 'released', 'consumed', 'cancelled'))
);
--> statement-breakpoint
CREATE INDEX `inventory_reservations_requirement_status_idx` ON `inventory_reservations` (`work_order_part_id`,`status`);--> statement-breakpoint
CREATE INDEX `inventory_reservations_correlation_idx` ON `inventory_reservations` (`correlation_id`);--> statement-breakpoint
CREATE TABLE `maintenance_tools` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`category` text NOT NULL,
	`availability` text NOT NULL,
	`calibration_due_at` text NOT NULL,
	`location` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	CONSTRAINT "maintenance_tools_availability_chk" CHECK("maintenance_tools"."availability" in ('available', 'reserved', 'assigned', 'unavailable', 'calibration'))
);
--> statement-breakpoint
CREATE INDEX `maintenance_tools_availability_idx` ON `maintenance_tools` (`availability`);--> statement-breakpoint
CREATE INDEX `maintenance_tools_calibration_due_idx` ON `maintenance_tools` (`calibration_due_at`);--> statement-breakpoint
CREATE TABLE `resource_assignments` (
	`id` text PRIMARY KEY NOT NULL,
	`work_order_id` text NOT NULL,
	`crew_id` text,
	`vessel_id` text,
	`maintenance_tool_id` text,
	`role` text NOT NULL,
	`status` text NOT NULL,
	`planned_from` text NOT NULL,
	`planned_to` text NOT NULL,
	`assigned_at` text NOT NULL,
	`released_at` text,
	`correlation_id` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`work_order_id`) REFERENCES `work_orders`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`crew_id`) REFERENCES `crews`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`vessel_id`) REFERENCES `vessels`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`maintenance_tool_id`) REFERENCES `maintenance_tools`(`id`) ON UPDATE no action ON DELETE no action,
	CONSTRAINT "resource_assignments_exactly_one_resource_chk" CHECK((case when "resource_assignments"."crew_id" is not null then 1 else 0 end + case when "resource_assignments"."vessel_id" is not null then 1 else 0 end + case when "resource_assignments"."maintenance_tool_id" is not null then 1 else 0 end) = 1),
	CONSTRAINT "resource_assignments_status_chk" CHECK("resource_assignments"."status" in ('reserved', 'assigned', 'released', 'cancelled')),
	CONSTRAINT "resource_assignments_window_chk" CHECK("resource_assignments"."planned_to" > "resource_assignments"."planned_from")
);
--> statement-breakpoint
CREATE INDEX `resource_assignments_work_order_status_idx` ON `resource_assignments` (`work_order_id`,`status`);--> statement-breakpoint
CREATE INDEX `resource_assignments_crew_idx` ON `resource_assignments` (`crew_id`);--> statement-breakpoint
CREATE INDEX `resource_assignments_vessel_idx` ON `resource_assignments` (`vessel_id`);--> statement-breakpoint
CREATE INDEX `resource_assignments_tool_idx` ON `resource_assignments` (`maintenance_tool_id`);--> statement-breakpoint
CREATE TABLE `spare_parts` (
	`id` text PRIMARY KEY NOT NULL,
	`part_number` text NOT NULL,
	`name` text NOT NULL,
	`category` text NOT NULL,
	`warehouse` text NOT NULL,
	`on_hand` integer NOT NULL,
	`reorder_point` integer NOT NULL,
	`unit` text NOT NULL,
	`status` text NOT NULL,
	`compatible_turbine_models` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	CONSTRAINT "spare_parts_on_hand_nonnegative_chk" CHECK("spare_parts"."on_hand" >= 0),
	CONSTRAINT "spare_parts_reorder_point_nonnegative_chk" CHECK("spare_parts"."reorder_point" >= 0),
	CONSTRAINT "spare_parts_status_chk" CHECK("spare_parts"."status" in ('in-stock', 'low-stock', 'out-of-stock', 'quarantined'))
);
--> statement-breakpoint
CREATE UNIQUE INDEX `spare_parts_part_number_unique` ON `spare_parts` (`part_number`);--> statement-breakpoint
CREATE INDEX `spare_parts_category_status_idx` ON `spare_parts` (`category`,`status`);--> statement-breakpoint
CREATE TABLE `vessels` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`vessel_type` text NOT NULL,
	`availability` text NOT NULL,
	`capacity` integer NOT NULL,
	`max_wave_height_m` real NOT NULL,
	`berth` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	CONSTRAINT "vessels_capacity_positive_chk" CHECK("vessels"."capacity" > 0),
	CONSTRAINT "vessels_max_wave_height_positive_chk" CHECK("vessels"."max_wave_height_m" > 0),
	CONSTRAINT "vessels_availability_chk" CHECK("vessels"."availability" in ('available', 'reserved', 'assigned', 'unavailable'))
);
--> statement-breakpoint
CREATE INDEX `vessels_availability_idx` ON `vessels` (`availability`);--> statement-breakpoint
CREATE TABLE `work_order_parts` (
	`id` text PRIMARY KEY NOT NULL,
	`work_order_id` text NOT NULL,
	`spare_part_id` text NOT NULL,
	`quantity_required` integer NOT NULL,
	`quantity_issued` integer DEFAULT 0 NOT NULL,
	`status` text NOT NULL,
	`notes` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`work_order_id`) REFERENCES `work_orders`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`spare_part_id`) REFERENCES `spare_parts`(`id`) ON UPDATE no action ON DELETE no action,
	CONSTRAINT "work_order_parts_required_positive_chk" CHECK("work_order_parts"."quantity_required" > 0),
	CONSTRAINT "work_order_parts_issued_nonnegative_chk" CHECK("work_order_parts"."quantity_issued" >= 0),
	CONSTRAINT "work_order_parts_issued_not_over_required_chk" CHECK("work_order_parts"."quantity_issued" <= "work_order_parts"."quantity_required"),
	CONSTRAINT "work_order_parts_status_chk" CHECK("work_order_parts"."status" in ('requested', 'reserved', 'issued', 'consumed', 'cancelled'))
);
--> statement-breakpoint
CREATE UNIQUE INDEX `work_order_parts_work_order_part_uidx` ON `work_order_parts` (`work_order_id`,`spare_part_id`);--> statement-breakpoint
CREATE INDEX `work_order_parts_part_status_idx` ON `work_order_parts` (`spare_part_id`,`status`);