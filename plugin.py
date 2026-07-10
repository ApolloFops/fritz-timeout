from datetime import datetime, timedelta
import re
import sqlite3

import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from resources.shared import CONTEXTS, INTEGRATION_TYPES

from .config import LOG_COMPONENT
from .database import TimeoutDatabase

database = TimeoutDatabase()


class Timeout(commands.Cog):
	command_group = SlashCommandGroup("timeout", "Timeout functions", contexts=CONTEXTS, integration_types=INTEGRATION_TYPES)

	def __init__(self, bot: discord.Bot):
		self.bot = bot

		self.scheduler = AsyncIOScheduler()

	@commands.Cog.listener()
	async def on_ready(self):
		# Clear out all the expired timeouts
		for raw_timeout in database.get_expired_timeouts():
			guild_id, user_id, timeout_id = raw_timeout

			guild = await self.bot.get_or_fetch(discord.Guild, guild_id)
			member = await guild.get_or_fetch(discord.Member, user_id)

			await self.untimeout_user(guild_id, timeout_id, member)

		# Schedule all the active timeouts
		active_timeouts = database.get_timeouts()

		for guild_id, user_id, timeout_id, end_date in active_timeouts:
			if end_date is not None:
				exec_time = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")

				guild = await self.bot.get_or_fetch(discord.Guild, guild_id)
				member = await guild.get_or_fetch(discord.Member, user_id)

				self.schedule_untimeout(guild_id, timeout_id, member, exec_time)

		self.scheduler.start()

	def schedule_untimeout(self, guild_id: int, timeout_id: str, member: discord.Member, end_date: datetime):
		job_id = f"{guild_id}-{member.id}-{timeout_id}"

		if not self.scheduler.get_job(job_id):
			self.scheduler.add_job(
				self.untimeout_user,
				"date",
				run_date=end_date,
				args=[guild_id, timeout_id, member],
				id=job_id,
			)

	hm_regex = re.compile(r"((?P<years>\d+)y)?((?P<months>\d+)M)?((?P<weeks>\d+)w)?((?P<days>\d+)d)?((?P<hours>\d+)h)?((?P<minutes>\d+)m)?((?P<seconds>\d+)s)?")

	def hm_to_date(self, hm_str: str):
		"""Converts an hour-minute string to a time in the future.

		This is mostly borrowed from Dozer."""

		matches = re.match(self.hm_regex, hm_str).groupdict()
		years = int(matches.get('years') or 0)
		months = int(matches.get('months') or 0)
		weeks = int(matches.get('weeks') or 0)
		days = int(matches.get('days') or 0)
		hours = int(matches.get('hours') or 0)
		minutes = int(matches.get('minutes') or 0)
		seconds = int(matches.get('seconds') or 0)
		val = int((years * 3.154e+7) + (months * 2.628e+6) + (weeks * 604800) + (days * 86400) + (hours * 3600) + (minutes * 60) + seconds)
		# Make sure it is a positive number, and it doesn't exceed the max 32-bit int
		seconds = max(0, min(2147483647, val))

		return datetime.now() + timedelta(seconds=seconds)

	@command_group.command(name="create_timeout", description="Creates a timeout category that you can assign roles and channels to.")
	@commands.has_permissions(administrator=True)
	async def create_timeout(self, ctx, timeout_id: str):
		database.insert_timeout_config(ctx.guild.id, timeout_id)

		await ctx.respond(f"Created timeout `{timeout_id}`")

	@command_group.command(name="delete_timeout", description="Deletes a timeout category. THIS CAN NOT BE UNDONE!")
	@commands.has_permissions(administrator=True)
	async def delete_timeout(self, ctx, timeout_id: str):
		database.remove_timeout_config(ctx.guild.id, timeout_id)

		await ctx.respond(f"Removed timeout `{timeout_id}`")

	@command_group.command(name="add_role", description="Adds a role to the given timeout category, which will be assigned when the timeout is active.")
	@commands.has_permissions(administrator=True)
	async def add_role(self, ctx, timeout_id: str, role: discord.Role):
		try:
			database.add_timeout_role(ctx.guild.id, timeout_id, role.id)

			# Update existing timeouts
			for user_id in database.check_for_timeouts(ctx.guild.id, timeout_id):
				member = await ctx.guild.get_or_fetch(discord.Member, user_id[0])

				await member.add_roles(role)

			await ctx.respond(f"Added role {role.mention} to timeout `{timeout_id}`", allowed_mentions=discord.AllowedMentions(roles=False))
		except ValueError:
			await ctx.respond(f"Failed to add role: role {role.mention} already in timeout `{timeout_id}`", allowed_mentions=discord.AllowedMentions(roles=False))

	@command_group.command(name="remove_role", description="Removes a role from the given timeout category.")
	@commands.has_permissions(administrator=True)
	async def remove_role(self, ctx, timeout_id: str, role: discord.Role):
		try:
			database.remove_timeout_role(ctx.guild.id, timeout_id, role.id)

			# Update existing timeouts
			for user_id in database.check_for_timeouts(ctx.guild.id, timeout_id):
				member = await ctx.guild.get_or_fetch(discord.Member, user_id[0])

				await member.remove_roles(role)

			await ctx.respond(f"Removed role {role.mention} from timeout `{timeout_id}`", allowed_mentions=discord.AllowedMentions(roles=False))
		except KeyError:
			await ctx.respond(f"Failed to remove role: role {role.mention} not in timeout `{timeout_id}`", allowed_mentions=discord.AllowedMentions(roles=False))

	@command_group.command(name="timeout_user", description="Time out a user.")
	@commands.has_permissions(administrator=True)
	async def timeout_user_command(self, ctx, timeout_id: str, user: discord.Member, end_in: discord.Option(str, required=False), reason: discord.Option(str, required=False)):
		try:
			await self.timeout_user(ctx.guild.id, timeout_id, user, self.hm_to_date(end_in) if end_in is not None else None, ctx.author.id, reason or "")

			await ctx.respond(f"Added timeout `{timeout_id}` to user {user.mention}", allowed_mentions=discord.AllowedMentions(users=False))
		except sqlite3.IntegrityError:
			await ctx.respond(f"User {user.mention} already has timeout `{timeout_id}`. Untimeout them first before attempting to timeout them.", allowed_mentions=discord.AllowedMentions(users=False))

	@command_group.command(name="untimeout_user", description="Remove a time out from a user.")
	@commands.has_permissions(administrator=True)
	async def untimeout_user_command(self, ctx, timeout_id: str, user: discord.Member, reason: discord.Option(str, required=False)):
		await self.untimeout_user(ctx.guild.id, timeout_id, user)

		await ctx.respond(f"Removed timeout `{timeout_id}` from user {user.mention}", allowed_mentions=discord.AllowedMentions(users=False))

	async def timeout_user(self, guild_id: int, timeout_id: str, user: discord.Member, end_date: datetime | None, timeout_by: int, reason: str):
		database.add_timeout(guild_id, user.id, timeout_id, end_date, timeout_by, reason)

		roles = database.get_timeout_roles(guild_id, timeout_id)

		await user.add_roles(*map(discord.Object, roles))

		if end_date is not None:
			self.schedule_untimeout(guild_id, timeout_id, user, end_date)

	async def untimeout_user(self, guild_id: int, timeout_id: str, user: discord.Member):
		roles = database.get_timeout_roles(guild_id, timeout_id)

		await user.remove_roles(*map(discord.Object, roles))

		job_id = f"{guild_id}-{user.id}-{timeout_id}"

		if self.scheduler.get_job(job_id):
			self.scheduler.remove_job(job_id)

		database.remove_timeout(guild_id, user.id, timeout_id)


def setup(bot):
	bot.add_cog(Timeout(bot))


def teardown(bot):
	bot.remove_cog("Timeout")
