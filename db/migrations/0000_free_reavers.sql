CREATE TABLE `attempts` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`problem_id` integer NOT NULL,
	`session_id` integer,
	`code` text NOT NULL,
	`time_taken_seconds` integer NOT NULL,
	`hints_viewed` text DEFAULT '[]' NOT NULL,
	`self_rating` integer,
	`self_note` text,
	`execution_result` text,
	`completed` integer DEFAULT false NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`problem_id`) REFERENCES `problems`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`session_id`) REFERENCES `sessions`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX `attempts_problem_idx` ON `attempts` (`problem_id`);--> statement-breakpoint
CREATE INDEX `attempts_session_idx` ON `attempts` (`session_id`);--> statement-breakpoint
CREATE TABLE `problems` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`topic` text NOT NULL,
	`difficulty` text NOT NULL,
	`title` text NOT NULL,
	`description` text NOT NULL,
	`hints` text NOT NULL,
	`reference_solution` text NOT NULL,
	`tags` text DEFAULT '[]' NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL
);
--> statement-breakpoint
CREATE INDEX `problems_topic_idx` ON `problems` (`topic`,`difficulty`);--> statement-breakpoint
CREATE TABLE `sessions` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`mode` text NOT NULL,
	`topic` text,
	`difficulty` text,
	`time_limit_minutes` integer,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`ended_at` integer
);
