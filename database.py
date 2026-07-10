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
	allow_self_assign BOOLEAN NOT NULL CHECK (allow_self_assign IN (0, 1)) DEFAULT 0,
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

	set_timeout_self_assignable = """
UPDATE timeout_configs
SET allow_self_assign = ?
WHERE
	guild_id = ?
	AND timeout_id = ?;
"""

	get_timeout_self_assignable = """
SELECT allow_self_assign
FROM timeout_configs
WHERE
	guild_id = ?
	AND timeout_id = ?;
"""

	# Active Timeouts
	create_timeouts_table = """
CREATE TABLE IF NOT EXISTS timeouts (
	guild_id TEXT NOT NULL,
	user_id TEXT NOT NULL,
	timeout_id TEXT NOT NULL,
	end_date TEXT,
	timeout_by TEXT NOT NULL,
	reason TEXT,
	PRIMARY KEY (guild_id, user_id, timeout_id)
)
"""

	add_timeout = """
INSERT INTO timeouts (
	guild_id,
	user_id,
	timeout_id,
	end_date,
	timeout_by,
	reason
)
VALUES (?, ?, ?, ?, ?, ?);
"""

	get_timeouts = """
SELECT guild_id, user_id, timeout_id, end_date
FROM timeouts;
"""

	get_expired_timeouts = """
SELECT guild_id, user_id, timeout_id
FROM timeouts
WHERE end_date <= datetime('now');
"""

	check_for_timeouts = """
SELECT user_id
FROM timeouts
WHERE guild_id = ? AND timeout_id = ?;
"""

	remove_timeout = """
DELETE FROM timeouts
WHERE guild_id = ? AND user_id = ? AND timeout_id = ?;
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
			cursor = db.cursor()

			cursor.execute(
				TimeoutQueries.remove_config,
				(str(guild_id), timeout_id)
			)

			if cursor.rowcount == 0:
				raise ValueError(f"Failed to delete config `{timeout_id}`: No timeout exists in guild `{guild_id}`.")

			db.commit()

	def add_timeout_role(self, guild_id: int, timeout_id: str, role_id: int):
		role_list = self.get_timeout_roles(guild_id, timeout_id)

		if role_id in role_list:
			raise ValueError(f"Role '{role_id}' already exists in timeout {timeout_id}.")

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

	def set_timeout_self_assignable(self, guild_id: int, timeout_id: str, self_assignable: bool):
		with self.connect_db() as db:
			db.cursor().execute(
				TimeoutQueries.set_timeout_self_assignable,
				(
					int(self_assignable),
					str(guild_id),
					timeout_id,
				)
			)
			db.commit()

	def get_timeout_self_assignable(self, guild_id: int, timeout_id: str):
		with self.connect_db() as db:
			data = db.cursor().execute(
				TimeoutQueries.get_timeout_self_assignable,
				(str(guild_id), timeout_id)
			).fetchone()

			return bool(data[0])

	# Active Timeouts
	def add_timeout(self, guild_id: int, user_id: int, timeout_id: str, end_date: datetime | None, timeout_by: int, reason: str | None):
		with self.connect_db() as db:
			db.cursor().execute(
				TimeoutQueries.add_timeout,
				(
					str(guild_id),
					str(user_id),
					timeout_id,
					end_date.strftime("%Y-%m-%d %H:%M:%S") if end_date is not None else None,
					str(timeout_by),
					reason
				)
			)
			db.commit()

	def get_timeouts(self):
		with self.connect_db() as db:
			return db.cursor().execute(
				TimeoutQueries.get_timeouts
			).fetchall()

	def get_expired_timeouts(self):
		with self.connect_db() as db:
			return db.cursor().execute(
				TimeoutQueries.get_expired_timeouts
			).fetchall()

	def check_for_timeouts(self, guild_id: int, timeout_id: str):
		with self.connect_db() as db:
			return db.cursor().execute(
				TimeoutQueries.check_for_timeouts,
				(str(guild_id), timeout_id)
			).fetchall()

	def remove_timeout(self, guild_id: int, user_id: int, timeout_id: str):
		with self.connect_db() as db:
			db.cursor().execute(
				TimeoutQueries.remove_timeout,
				(str(guild_id), str(user_id), str(timeout_id))
			)
			db.commit()
