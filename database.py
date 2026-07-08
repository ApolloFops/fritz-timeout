import sqlite3
from datetime import datetime

from .config import DATABASE_PATH


class TimeoutQueries:
	# Configuration
	create_config_table = """
CREATE TABLE IF NOT EXISTS timeout_configs (
	guild_id TEXT NOT NULL,
	timeout_id TEXT NOT NULL,
	role_ids TEXT,
	channel_ids TEXT,
	PRIMARY KEY (guild_id, timeout_id)
)
"""

	insert_config = """
INSERT INTO timeout_configs (
	guild_id,
	timeout_id
)
VALUES (?, ?)
"""

	remove_config = """
DELETE FROM timeout_configs
WHERE
	guild_id = ? AND timeout_id = ?;
"""

	set_timeout_roles = """
UPDATE timeout_configs
SET role_ids = ?
WHERE
	guild_id = ?
	AND timeout_id = ?;
"""

	get_timeout_roles = """
SELECT role_ids
FROM timeout_configs
WHERE
	guild_id = ?
	AND timeout_id = ?;
"""

	# Active Timeouts
	create_timeouts_table = """
CREATE TABLE IF NOT EXISTS timeouts (
	user_id TEXT NOT NULL,
	timeout_id TEXT NOT NULL,
	end_date TEXT NOT NULL,
	timeout_by TEXT NOT NULL,
	reason TEXT,
	PRIMARY KEY (user_id, timeout_id)
)
"""

	add_timeout = """
INSERT INTO timeouts (
	user_id,
	timeout_id,
	end_date,
	timeout_by,
	reason
)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(user_id, timeout_id)
DO UPDATE SET
	end_date = excluded.end_date,
	timeout_by = excluded.timeout_by,
	reason = excluded.reason;
"""

	get_timeout = """
SELECT timeout_id, end_date, timeout_by, reason
FROM timeouts
WHERE user_id = ?;
"""

	get_expired_timeouts = """
SELECT user_id, timeout_id
FROM timeouts
WHERE end_date <= datetime('now');
"""

	remove_timeout = """
DELETE FROM timeouts
WHERE user_id = ? AND timeout_id = ?;
"""


class TimeoutDatabase:
	def __init__(self):
		with self.connect_db() as db:
			db.cursor().execute(TimeoutQueries.create_config_table)
			db.cursor().execute(TimeoutQueries.create_timeouts_table)
			db.commit()

	def connect_db(self):
		return sqlite3.connect(DATABASE_PATH)

	# Configuration
	def insert_timeout_config(self, guild_id: int, timeout_id: str):
		with self.connect_db() as db:
			db.cursor().execute(
				TimeoutQueries.insert_config,
				(str(guild_id), timeout_id)
			)
			db.commit()

	def remove_timeout_config(self, guild_id: int, timeout_id: str):
		with self.connect_db() as db:
			db.cursor().execute(
				TimeoutQueries.remove_config,
				(str(guild_id), timeout_id)
			)
			db.commit()

	def add_timeout_role(self, guild_id: int, timeout_id: str, role_id: int):
		role_list = self.get_timeout_roles(guild_id, timeout_id)
		role_list.add(role_id)

		self.set_timeout_roles(guild_id, timeout_id, role_list)

	def remove_timeout_role(self, guild_id: int, timeout_id: str, role_id: int):
		role_list = self.get_timeout_roles(guild_id, timeout_id)
		role_list.remove(role_id)

		self.set_timeout_roles(guild_id, timeout_id, role_list)

	def set_timeout_roles(self, guild_id: int, timeout_id: str, role_ids: set):
		with self.connect_db() as db:
			db.cursor().execute(
				TimeoutQueries.set_timeout_roles,
				(
					",".join(map(str, role_ids)),
					str(guild_id),
					timeout_id,
				)
			)
			db.commit()

	def get_timeout_roles(self, guild_id: int, timeout_id: str):
		with self.connect_db() as db:
			data = db.cursor().execute(
				TimeoutQueries.get_timeout_roles,
				(str(guild_id), timeout_id)
			).fetchone()

			if (data is None) or (data[0] is None) or (data[0] == ''):
				return set()
			else:
				return set(map(int, data[0].split(",")))

	# Active Timeouts
	def add_timeout(self, user_id, role_id, end_date: datetime, timeout_by, reason):
		with self.connect_db() as db:
			db.cursor().execute(
				TimeoutQueries.add_timeout,
				(
					str(user_id),
					str(role_id),
					end_date.strftime("%Y-%m-%d %H:%M:%S"),
					str(timeout_by),
					reason
				)
			)
			db.commit()

	def get_timeout(self, user_id):
		with self.connect_db() as db:
			result = db.cursor().execute(
				TimeoutQueries.get_timeout,
				(str(user_id),)
			).fetchone()

		if result is None:
			return None

		role_id, end_date, timeout_by, reason = result

		return (
			role_id,
			datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S"),
			timeout_by,
			reason
		)

	def get_expired_timeouts(self):
		with self.connect_db() as db:
			return db.cursor().execute(
				TimeoutQueries.get_expired_timeouts
			).fetchall()

	def remove_timeout(self, user_id, role_id):
		with self.connect_db() as db:
			db.cursor().execute(
				TimeoutQueries.remove_timeout,
				(str(user_id), str(role_id))
			)
			db.commit()
