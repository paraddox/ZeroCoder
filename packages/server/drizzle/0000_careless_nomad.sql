CREATE TABLE `containers` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`project_name` text(50) NOT NULL,
	`container_number` integer NOT NULL,
	`container_type` text(20) DEFAULT 'coding' NOT NULL,
	`docker_container_id` text(100),
	`status` text(20) DEFAULT 'created' NOT NULL,
	`current_feature` text(50),
	`created_at` text NOT NULL,
	`user_started_at` text,
	`graceful_stop_requested` integer DEFAULT false NOT NULL,
	`restarting` integer DEFAULT false NOT NULL,
	`last_agent_was_overseer` integer DEFAULT false NOT NULL,
	`is_milestone_overseer` integer DEFAULT false NOT NULL,
	`last_activity_at` text,
	`last_closed_feature` text(50),
	FOREIGN KEY (`project_name`) REFERENCES `projects`(`name`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_container_identity` ON `containers` (`project_name`,`container_number`,`container_type`);--> statement-breakpoint
CREATE TABLE `feature_cache` (
	`project_name` text(50) NOT NULL,
	`feature_id` text(50) NOT NULL,
	`priority` integer DEFAULT 999 NOT NULL,
	`category` text(100) DEFAULT '' NOT NULL,
	`name` text(255) NOT NULL,
	`description` text DEFAULT '' NOT NULL,
	`steps_json` text DEFAULT '[]' NOT NULL,
	`status` text(20) NOT NULL,
	`updated_at` text NOT NULL,
	PRIMARY KEY(`project_name`, `feature_id`),
	FOREIGN KEY (`project_name`) REFERENCES `projects`(`name`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `feature_stats_cache` (
	`project_name` text(50) PRIMARY KEY NOT NULL,
	`pending_count` integer DEFAULT 0 NOT NULL,
	`in_progress_count` integer DEFAULT 0 NOT NULL,
	`done_count` integer DEFAULT 0 NOT NULL,
	`total_count` integer DEFAULT 0 NOT NULL,
	`percentage` real DEFAULT 0 NOT NULL,
	`last_polled_at` text NOT NULL,
	`poll_error` text(500),
	`last_overseer_milestone` integer DEFAULT 0 NOT NULL,
	FOREIGN KEY (`project_name`) REFERENCES `projects`(`name`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `project_verification_state` (
	`project_name` text(50) PRIMARY KEY NOT NULL,
	`verification_running` integer DEFAULT false NOT NULL,
	`started_at` text
);
--> statement-breakpoint
CREATE TABLE `projects` (
	`name` text(50) PRIMARY KEY NOT NULL,
	`git_url` text NOT NULL,
	`target_container_count` integer DEFAULT 1 NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `remote_agents` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`project_name` text(50) NOT NULL,
	`machine_id` integer NOT NULL,
	`agent_number` integer DEFAULT 1 NOT NULL,
	`status` text(20) DEFAULT 'created' NOT NULL,
	`current_feature` text(50),
	`pid` integer,
	`user_started_at` text,
	`graceful_stop_requested` integer DEFAULT false NOT NULL,
	`restarting` integer DEFAULT false NOT NULL,
	`last_activity_at` text,
	`created_at` text NOT NULL,
	FOREIGN KEY (`project_name`) REFERENCES `projects`(`name`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`machine_id`) REFERENCES `remote_machines`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_remote_agent_identity` ON `remote_agents` (`project_name`,`machine_id`,`agent_number`);--> statement-breakpoint
CREATE TABLE `remote_machines` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`name` text(100) NOT NULL,
	`host` text(255) NOT NULL,
	`port` integer DEFAULT 22 NOT NULL,
	`username` text(100) DEFAULT 'root' NOT NULL,
	`ssh_key_path` text(500),
	`git_ssh_key_path` text(500),
	`status` text(20) DEFAULT 'unknown' NOT NULL,
	`last_checked_at` text,
	`created_at` text NOT NULL,
	`daemon_port` integer DEFAULT 9999,
	`daemon_pid` integer,
	`daemon_last_seen` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `remote_machines_name_unique` ON `remote_machines` (`name`);